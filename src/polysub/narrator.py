from __future__ import annotations

import json
import os
import subprocess
import threading
import wave
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from .narrator_runtime import (
    install_narrator_runtime,
    narrator_worker_environment,
    narrator_worker_script,
)
from .performance import DEFAULT_CPU_USAGE, cpu_allocation
from .subtitles import SRTCue, SRTDocument

StatusCallback = Callable[[str], None]
NarrationProgressCallback = Callable[[int, int], None]


class NarrationError(RuntimeError):
    pass


@dataclass(frozen=True)
class NarrationResult:
    output_path: Path
    cue_count: int
    sample_rate: int
    original_volume: float


class ChatterboxNarrator:
    """Create one Polish voice track and mix it with quieter original audio."""

    def __init__(
        self,
        *,
        ffmpeg_executable: str | None = None,
        runtime_installer: Callable[[StatusCallback | None], Path] | None = None,
    ) -> None:
        self.ffmpeg_executable = ffmpeg_executable
        self.runtime_installer = runtime_installer or install_narrator_runtime

    def render(
        self,
        video_path: str | Path,
        subtitle_path: str | Path,
        model_path: str | Path,
        *,
        output_path: str | Path | None = None,
        original_volume: float = 0.28,
        cpu_usage_limit: int = DEFAULT_CPU_USAGE,
        status: StatusCallback | None = None,
        progress: NarrationProgressCallback | None = None,
    ) -> NarrationResult:
        status = status or (lambda _message: None)
        progress = progress or (lambda _done, _total: None)
        video = Path(video_path)
        subtitles = Path(subtitle_path)
        model = Path(model_path)
        output = Path(output_path) if output_path else narrator_video_output_path(video)
        self._validate(video, subtitles, model, output, original_volume)
        output.parent.mkdir(parents=True, exist_ok=True)
        document = SRTDocument.load(subtitles)
        ffmpeg = self._resolve_ffmpeg()
        if ffmpeg is None:
            raise NarrationError("Brakuje FFmpeg potrzebnego do zmiksowania polskiego lektora.")

        status("Sprawdzanie prywatnego środowiska Chatterbox…")
        try:
            python_path = self.runtime_installer(status)
        except Exception as exc:
            raise NarrationError(f"Nie udało się przygotować Chatterbox: {exc}") from exc

        with TemporaryDirectory(prefix="polysub-narrator-") as temporary_name:
            temporary = Path(temporary_name)
            threads = cpu_allocation(cpu_usage_limit).threads
            status(
                "Wczytywanie Chatterbox Multilingual V3 i jednego głosu lektora "
                f"({threads} wątków CPU)…"
            )
            worker = _NarratorWorker(python_path, model, threads=threads)
            try:
                sample_rate = worker.start()
                clips: list[tuple[SRTCue, Path]] = []
                total = len(document.cues)
                progress(0, total)
                for position, cue in enumerate(document.cues, start=1):
                    text = " ".join(cue.visible_text.replace("\\N", " ").split())
                    if not text:
                        progress(position, total)
                        continue
                    status(f"Lektor: kwestia {position} z {total}…")
                    clip = temporary / f"cue-{position:06d}.wav"
                    worker.synthesize(text, clip)
                    clip = self._fit_clip(ffmpeg, clip, cue, temporary)
                    clips.append((cue, clip))
                    progress(position, total)
            finally:
                worker.close()
            if not clips:
                raise NarrationError("Napisy nie zawierają tekstu, który można przeczytać.")

            status("Układanie głosu zgodnie z czasami napisów…")
            narration_track = temporary / "polish-narrator.wav"
            sample_rate = build_narration_track(clips, narration_track)
            status("Miksowanie lektora ze ściszoną oryginalną ścieżką…")
            self._mix_video(
                ffmpeg,
                video,
                narration_track,
                subtitles,
                output,
                original_volume=original_volume,
            )
        return NarrationResult(
            output_path=output,
            cue_count=len(clips),
            sample_rate=sample_rate,
            original_volume=original_volume,
        )

    @staticmethod
    def _validate(
        video: Path,
        subtitles: Path,
        model: Path,
        output: Path,
        original_volume: float,
    ) -> None:
        if not video.is_file():
            raise NarrationError(f"Nie znaleziono filmu: {video}")
        if not subtitles.is_file() or subtitles.suffix.lower() != ".srt":
            raise NarrationError("Polski lektor wymaga gotowych napisów SRT.")
        if not model.is_dir():
            raise NarrationError("Model Chatterbox nie jest pobrany lub jest niekompletny.")
        if output.suffix.lower() != ".mkv":
            raise NarrationError("Film z lektorem jest zapisywany w bezpiecznym kontenerze .mkv.")
        if _same_path(video, output):
            raise NarrationError("Film wynikowy nie może nadpisywać oryginału.")
        if not 0 <= original_volume <= 1:
            raise NarrationError("Głośność oryginału musi mieścić się w zakresie 0–1.")

    def _fit_clip(
        self,
        ffmpeg: str,
        clip: Path,
        cue: SRTCue,
        temporary: Path,
    ) -> Path:
        start, end = parse_srt_timing(cue.timing)
        available = max(end - start, 0.5)
        with wave.open(str(clip), "rb") as source:
            duration = source.getnframes() / max(source.getframerate(), 1)
        ratio = duration / available
        if ratio <= 1.05:
            return clip
        # A narrator may slightly overrun a subtitle, but modest acceleration avoids
        # cumulative drift in rapid dialogue without making the voice unnatural.
        tempo = min(ratio, 1.35)
        fitted = temporary / f"{clip.stem}.fitted.wav"
        command = [
            ffmpeg,
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(clip),
            "-filter:a",
            f"atempo={tempo:.4f}",
            "-ac",
            "1",
            "-c:a",
            "pcm_s16le",
            str(fitted),
        ]
        try:
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except OSError:
            return clip
        return fitted if completed.returncode == 0 and fitted.is_file() else clip

    def _mix_video(
        self,
        ffmpeg: str,
        video: Path,
        narration: Path,
        subtitles: Path,
        output: Path,
        *,
        original_volume: float,
    ) -> None:
        temporary = output.with_name(f".{output.stem}.narrating{output.suffix}")
        temporary.unlink(missing_ok=True)
        command = [
            ffmpeg,
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(video),
            "-i",
            str(narration),
            "-i",
            str(subtitles),
        ]
        if self._has_audio_stream(ffmpeg, video):
            command += [
                "-filter_complex",
                (
                    f"[0:a:0]volume={original_volume:.3f}[original];"
                    "[1:a:0]volume=1.0[narrator];"
                    "[original][narrator]amix=inputs=2:duration=first:"
                    "dropout_transition=0[aout]"
                ),
                "-map",
                "0:v?",
                "-map",
                "[aout]",
            ]
        else:
            command += ["-map", "0:v?", "-map", "1:a:0"]
        command += [
            "-map",
            "2:0",
            "-map_metadata",
            "0",
            "-map_chapters",
            "0",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-c:s",
            "srt",
            "-metadata:s:a:0",
            "language=pol",
            "-metadata:s:a:0",
            "title=Polski lektor — Chatterbox V3",
            "-metadata:s:s:0",
            "language=pol",
            "-metadata:s:s:0",
            "title=Polskie napisy",
            str(temporary),
        ]
        try:
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except OSError as exc:
            temporary.unlink(missing_ok=True)
            raise NarrationError(f"Nie udało się uruchomić FFmpeg: {exc}") from exc
        if completed.returncode != 0 or not temporary.is_file() or temporary.stat().st_size == 0:
            temporary.unlink(missing_ok=True)
            details = _process_error(completed.stderr)
            raise NarrationError(
                "Nie udało się zmiksować filmu z lektorem."
                + (f"\n\nFFmpeg: {details}" if details else "")
            )
        temporary.replace(output)

    @staticmethod
    def _has_audio_stream(ffmpeg: str, video: Path) -> bool:
        try:
            completed = subprocess.run(
                [ffmpeg, "-nostdin", "-hide_banner", "-i", str(video)],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except OSError:
            return True
        return "Audio:" in (completed.stderr or "")

    def _resolve_ffmpeg(self) -> str | None:
        if self.ffmpeg_executable:
            return self.ffmpeg_executable
        try:
            import imageio_ffmpeg

            return imageio_ffmpeg.get_ffmpeg_exe()
        except (ImportError, RuntimeError):
            return None


class _NarratorWorker:
    def __init__(self, python_path: Path, model_path: Path, *, threads: int = 1) -> None:
        self.python_path = python_path
        self.model_path = model_path
        self.threads = max(int(threads), 1)
        self.process: subprocess.Popen[str] | None = None
        self._diagnostic_lines: list[str] = []
        self._stderr_thread: threading.Thread | None = None

    def start(self) -> int:
        script = narrator_worker_script()
        if not script.is_file():
            raise NarrationError(f"Brakuje workera lektora: {script}")
        try:
            self.process = subprocess.Popen(
                [
                    str(self.python_path),
                    str(script),
                    "--model-dir",
                    str(self.model_path),
                    "--language",
                    "pl",
                    "--threads",
                    str(self.threads),
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                env=narrator_worker_environment(self.threads),
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except OSError as exc:
            raise NarrationError(f"Nie udało się uruchomić Chatterbox: {exc}") from exc
        # Continuously drain diagnostics so a verbose dependency cannot fill the
        # stderr pipe and block the Chatterbox process during a long film.
        self._stderr_thread = threading.Thread(target=self._drain_stderr, daemon=True)
        self._stderr_thread.start()
        payload = self._read_payload()
        if not payload.get("ready"):
            raise NarrationError(str(payload.get("error") or "Chatterbox nie zgłosił gotowości."))
        return int(payload.get("sample_rate") or 24000)

    def synthesize(self, text: str, output: Path) -> None:
        process = self._require_process()
        assert process.stdin is not None
        process.stdin.write(
            json.dumps(
                {
                    "command": "synthesize",
                    "text": text,
                    "output": str(output),
                    "language": "pl",
                    "exaggeration": 0.45,
                    "cfg_weight": 0.5,
                },
                ensure_ascii=False,
            )
            + "\n"
        )
        process.stdin.flush()
        payload = self._read_payload()
        if not payload.get("ok") or not output.is_file():
            raise NarrationError(str(payload.get("error") or "Nie powstał plik głosu."))

    def close(self) -> None:
        process = self.process
        self.process = None
        if process is None:
            return
        try:
            if process.poll() is None and process.stdin is not None:
                process.stdin.write('{"command":"close"}\n')
                process.stdin.flush()
                process.wait(timeout=10)
        except (OSError, subprocess.SubprocessError):
            process.terminate()
        finally:
            if process.poll() is None:
                process.kill()

    def _read_payload(self) -> dict[str, object]:
        process = self._require_process()
        assert process.stdout is not None
        for line in process.stdout:
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                cleaned = line.strip()
                if cleaned:
                    self._record_diagnostic(cleaned)
                continue
            if isinstance(payload, dict) and {"ready", "ok", "closed"}.intersection(payload):
                return payload
            cleaned = line.strip()
            if cleaned:
                self._record_diagnostic(cleaned)
        if self._stderr_thread is not None:
            self._stderr_thread.join(timeout=0.2)
        detail = "\n".join(self._diagnostic_lines)[-1800:]
        raise NarrationError(f"Worker Chatterbox zakończył pracę. {detail}".strip())

    def _drain_stderr(self) -> None:
        process = self.process
        if process is None or process.stderr is None:
            return
        for line in process.stderr:
            cleaned = line.strip()
            if cleaned:
                self._record_diagnostic(cleaned)

    def _record_diagnostic(self, line: str) -> None:
        self._diagnostic_lines = [*self._diagnostic_lines, line][-24:]

    def _require_process(self) -> subprocess.Popen[str]:
        if self.process is None:
            raise NarrationError("Worker Chatterbox nie jest uruchomiony.")
        return self.process


def build_narration_track(
    clips: Sequence[tuple[SRTCue, Path]],
    output_path: str | Path,
) -> int:
    if not clips:
        raise NarrationError("Brak fragmentów głosu do ułożenia.")
    output = Path(output_path)
    sample_rate: int | None = None
    current_frame = 0
    with wave.open(str(output), "wb") as timeline:
        for cue, clip_path in clips:
            with wave.open(str(clip_path), "rb") as clip:
                if clip.getnchannels() != 1 or clip.getsampwidth() != 2:
                    raise NarrationError("Chatterbox zwrócił nieobsługiwany format WAV.")
                clip_rate = clip.getframerate()
                if sample_rate is None:
                    sample_rate = clip_rate
                    timeline.setnchannels(1)
                    timeline.setsampwidth(2)
                    timeline.setframerate(sample_rate)
                elif clip_rate != sample_rate:
                    raise NarrationError("Fragmenty lektora mają różne częstotliwości próbkowania.")
                start, _end = parse_srt_timing(cue.timing)
                target_frame = round(start * sample_rate)
                if target_frame > current_frame:
                    _write_silence(timeline, target_frame - current_frame)
                    current_frame = target_frame
                frames = clip.readframes(clip.getnframes())
                timeline.writeframesraw(frames)
                current_frame += len(frames) // 2
        timeline.writeframes(b"")
    return sample_rate or 24000


def parse_srt_timing(value: str) -> tuple[float, float]:
    start_text, separator, end_text = value.partition("-->")
    if not separator:
        raise NarrationError(f"Nie można odczytać timestampa: {value}")
    return _timestamp_seconds(start_text.strip()), _timestamp_seconds(end_text.split()[0])


def narrator_video_output_path(video_path: str | Path) -> Path:
    video = Path(video_path)
    return video.with_name(f"{video.stem}.pl.narrator.mkv")


def _timestamp_seconds(value: str) -> float:
    try:
        hours, minutes, remainder = value.replace(".", ",").split(":")
        seconds, milliseconds = remainder.split(",")
        return int(hours) * 3600 + int(minutes) * 60 + int(seconds) + int(milliseconds) / 1000
    except (TypeError, ValueError) as exc:
        raise NarrationError(f"Nie można odczytać timestampa: {value}") from exc


def _write_silence(output: wave.Wave_write, frames: int) -> None:
    remaining = max(frames, 0)
    block_frames = 24000
    silence = b"\0" * (block_frames * 2)
    while remaining:
        count = min(remaining, block_frames)
        output.writeframesraw(silence[: count * 2])
        remaining -= count


def _same_path(first: Path, second: Path) -> bool:
    return os.path.normcase(os.path.abspath(first)) == os.path.normcase(os.path.abspath(second))


def _process_error(stderr: bytes | str | None) -> str:
    if isinstance(stderr, bytes):
        value = stderr.decode("utf-8", errors="replace")
    else:
        value = stderr or ""
    return " ".join(value.strip().split())[-1200:]
