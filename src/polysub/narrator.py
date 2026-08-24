from __future__ import annotations

import json
import os
import subprocess
import threading
import wave
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from .narrator_runtime import (
    active_narrator_runtime,
    install_narrator_runtime,
    narrator_worker_environment,
    narrator_worker_script,
)
from .performance import DEFAULT_CPU_USAGE, cpu_allocation
from .subtitles import SRTCue, SRTDocument

StatusCallback = Callable[[str], None]
NarrationProgressCallback = Callable[[int, int], None]
GIB = 1024**3


@dataclass(frozen=True)
class NarratorPaceProfile:
    id: str
    label: str
    description: str
    speech_rate: float
    max_fit_speed: float
    safety_gap_seconds: float = 0.12


NARRATOR_PACE_PROFILES = (
    NarratorPaceProfile(
        "slow",
        "Bardzo spokojny — około 0,82×",
        "Najwolniejsze, wyraźne mówienie; może lekko wyjść poza krótki napis.",
        0.82,
        1.00,
    ),
    NarratorPaceProfile(
        "comfortable",
        "Spokojny — około 0,90× (zalecany)",
        "Wyraźny głos, wykorzystanie przerw między napisami i maksymalnie 1,08×.",
        0.90,
        1.08,
    ),
    NarratorPaceProfile(
        "natural",
        "Naturalny — 1,00×",
        "Naturalne tempo z delikatnym dopasowaniem do krótkich kwestii do 1,15×.",
        1.00,
        1.15,
    ),
    NarratorPaceProfile(
        "sync",
        "Ścisłe dopasowanie — maks. 1,25×",
        "Priorytetem jest zmieszczenie głosu w napisach; najszybszy wariant.",
        1.00,
        1.25,
    ),
)
DEFAULT_NARRATOR_PACE_ID = "comfortable"
NARRATOR_PACE_BY_ID = {profile.id: profile for profile in NARRATOR_PACE_PROFILES}
NARRATOR_PACE_ID_BY_LABEL = {profile.label: profile.id for profile in NARRATOR_PACE_PROFILES}


def get_narrator_pace_profile(
    value: str | NarratorPaceProfile | None,
) -> NarratorPaceProfile:
    if isinstance(value, NarratorPaceProfile):
        return value
    key = str(value or DEFAULT_NARRATOR_PACE_ID).strip()
    profile_id = NARRATOR_PACE_ID_BY_LABEL.get(key, key)
    try:
        return NARRATOR_PACE_BY_ID[profile_id]
    except KeyError as exc:
        raise NarrationError(f"Nieznany profil tempa lektora: {value}") from exc


def recommended_narrator_worker_count(
    *,
    cue_count: int,
    active_device: str,
    vram_total: int,
    vram_free: int,
    vram_reserved: int,
) -> int:
    """Choose a conservative number of persistent models for one GPU."""

    if not str(active_device).startswith("cuda") or cue_count < 8 or vram_total < 12 * GIB:
        return 1
    first_model = max(int(vram_reserved), 3 * GIB)
    margin = 1 * GIB
    if vram_free < int(first_model * 1.25) + margin:
        return 1
    if (
        vram_total >= 24 * GIB
        and cue_count >= 18
        and vram_free >= int(first_model * 2.5) + margin
    ):
        return 3
    return 2


class NarrationError(RuntimeError):
    pass


@dataclass(frozen=True)
class NarrationResult:
    output_path: Path
    cue_count: int
    sample_rate: int
    original_volume: float
    pace_profile: str = DEFAULT_NARRATOR_PACE_ID
    worker_count: int = 1


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
        pace_profile: str | NarratorPaceProfile = DEFAULT_NARRATOR_PACE_ID,
        status: StatusCallback | None = None,
        progress: NarrationProgressCallback | None = None,
    ) -> NarrationResult:
        status = status or (lambda _message: None)
        progress = progress or (lambda _done, _total: None)
        video = Path(video_path)
        subtitles = Path(subtitle_path)
        model = Path(model_path)
        output = Path(output_path) if output_path else narrator_video_output_path(video)
        pace = get_narrator_pace_profile(pace_profile)
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
        runtime = active_narrator_runtime()
        strict_gpu = runtime.backend == "rocm"

        with TemporaryDirectory(prefix="polysub-narrator-") as temporary_name:
            temporary = Path(temporary_name)
            threads = cpu_allocation(cpu_usage_limit).threads
            if strict_gpu:
                status(
                    "Wczytywanie Chatterbox Multilingual V3 na GPU — "
                    f"{runtime.label}…"
                )
            else:
                status(
                    "Wczytywanie Chatterbox Multilingual V3 na CPU "
                    f"({threads} wątków)…"
                )
            worker_threads = min(threads, 4) if strict_gpu else threads
            workers = [_NarratorWorker(python_path, model, threads=worker_threads)]
            worker_count = 1
            try:
                sample_rate = workers[0].start()
                if workers[0].active_device == "cpu" and strict_gpu:
                    detail = (
                        workers[0].last_fallback
                        or "worker nie utrzymał modelu na urządzeniu ROCm"
                    )
                    status(f"⚠ Chatterbox spadł z GPU na CPU podczas ładowania: {detail}")
                    raise NarrationError(
                        "Chatterbox nie utrzymał się na Radeonie i przełączył się na CPU. "
                        "Render został przerwany, żeby nie wykonywać wielogodzinnej "
                        "syntezy na CPU. "
                        f"Powód GPU: {detail}"
                    )
                if workers[0].active_device.startswith("cuda"):
                    memory = workers[0].vram_total
                    memory_label = f" • {memory / GIB:.1f} GB VRAM" if memory else ""
                    status(f"Chatterbox: GPU aktywne — {runtime.label}{memory_label}.")
                else:
                    status(
                        f"Chatterbox: aktywne urządzenie — {workers[0].active_device}."
                    )

                worker_count = recommended_narrator_worker_count(
                    cue_count=len(document.cues),
                    active_device=workers[0].active_device,
                    vram_total=workers[0].vram_total,
                    vram_free=workers[0].vram_free,
                    vram_reserved=workers[0].vram_reserved,
                )
                for worker_index in range(1, worker_count):
                    extra = _NarratorWorker(python_path, model, threads=worker_threads)
                    try:
                        extra.start()
                        if not extra.active_device.startswith("cuda"):
                            raise NarrationError(
                                extra.last_fallback or "dodatkowy worker nie uruchomił się na GPU"
                            )
                    except Exception as exc:
                        extra.close()
                        worker_count = len(workers)
                        status(
                            "VRAM nie pozwolił uruchomić kolejnego równoległego głosu — "
                            f"pozostaje {worker_count} worker. Szczegóły: {str(exc)[-500:]}"
                        )
                        break
                    workers.append(extra)
                    status(
                        f"Chatterbox: uruchomiono worker GPU {worker_index + 1} z "
                        f"{worker_count} — kwestie będą liczone równolegle."
                    )

                total = len(document.cues)
                progress(0, total)
                tasks: list[tuple[int, SRTCue, str, float | None]] = []
                for position, cue in enumerate(document.cues, start=1):
                    text = " ".join(cue.visible_text.replace("\\N", " ").split())
                    if not text:
                        continue
                    next_start = None
                    if position < total:
                        next_start, _ = parse_srt_timing(document.cues[position].timing)
                    tasks.append((position, cue, text, next_start))

                completed = total - len(tasks)
                if completed:
                    progress(completed, total)
                completed_lock = threading.Lock()

                def render_batch(
                    active_worker: _NarratorWorker,
                    batch: list[tuple[int, SRTCue, str, float | None]],
                ) -> list[tuple[int, SRTCue, Path]]:
                    nonlocal completed
                    rendered: list[tuple[int, SRTCue, Path]] = []
                    for position, cue, text, next_start in batch:
                        device_label = (
                            "GPU" if active_worker.active_device.startswith("cuda") else "CPU"
                        )
                        status(f"Lektor: kwestia {position} z {total} • {device_label}…")
                        clip = temporary / f"cue-{position:06d}.wav"
                        fallback = active_worker.synthesize(text, clip)
                        if active_worker.active_device == "cpu" and strict_gpu:
                            detail = (
                                fallback
                                or active_worker.last_fallback
                                or "błąd operacji ROCm"
                            )
                            raise NarrationError(
                                f"Chatterbox spadł z Radeona na CPU przy kwestii "
                                f"{position} z {total}. Render został przerwany zamiast "
                                f"kontynuować bardzo wolno na CPU. Powód GPU: {detail}"
                            )
                        fitted = self._fit_clip(
                            ffmpeg,
                            clip,
                            cue,
                            temporary,
                            pace=pace,
                            next_cue_start=next_start,
                        )
                        rendered.append((position, cue, fitted))
                        with completed_lock:
                            completed += 1
                            progress(completed, total)
                    return rendered

                partitions = [tasks[index:: len(workers)] for index in range(len(workers))]
                rendered_clips: list[tuple[int, SRTCue, Path]] = []
                if len(workers) == 1:
                    rendered_clips.extend(render_batch(workers[0], partitions[0]))
                else:
                    with ThreadPoolExecutor(
                        max_workers=len(workers),
                        thread_name_prefix="polysub-narrator",
                    ) as executor:
                        futures = [
                            executor.submit(render_batch, active_worker, batch)
                            for active_worker, batch in zip(workers, partitions, strict=True)
                            if batch
                        ]
                        for future in futures:
                            rendered_clips.extend(future.result())
                rendered_clips.sort(key=lambda item: item[0])
                clips = [(cue, clip) for _position, cue, clip in rendered_clips]
            finally:
                for active_worker in reversed(workers):
                    active_worker.close()
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
            pace_profile=pace.id,
            worker_count=worker_count,
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
        *,
        pace: NarratorPaceProfile | str = DEFAULT_NARRATOR_PACE_ID,
        next_cue_start: float | None = None,
    ) -> Path:
        pace = get_narrator_pace_profile(pace)
        start, end = parse_srt_timing(cue.timing)
        available = max(end - start, 0.5)
        if next_cue_start is not None and next_cue_start > start:
            available = max(
                available,
                next_cue_start - start - pace.safety_gap_seconds,
            )
        with wave.open(str(clip), "rb") as source:
            duration = source.getnframes() / max(source.getframerate(), 1)
        required_tempo = duration / available
        tempo = min(max(pace.speech_rate, required_tempo), pace.max_fit_speed)
        if abs(tempo - 1.0) <= 0.01:
            return clip
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
        self.requested_device = "cpu"
        self.active_device = "cpu"
        self.backend = "cpu"
        self.last_fallback: str | None = None
        self.vram_total = 0
        self.vram_free = 0
        self.vram_allocated = 0
        self.vram_reserved = 0

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
        self.active_device = str(payload.get("device") or "cpu")
        self.requested_device = str(payload.get("requested_device") or self.active_device)
        self.backend = str(payload.get("backend") or "cpu")
        fallback = payload.get("fallback")
        self.last_fallback = str(fallback) if fallback else None
        self.vram_total = int(payload.get("vram_total") or 0)
        self.vram_free = int(payload.get("vram_free") or 0)
        self.vram_allocated = int(payload.get("vram_allocated") or 0)
        self.vram_reserved = int(payload.get("vram_reserved") or 0)
        return int(payload.get("sample_rate") or 24000)

    def synthesize(self, text: str, output: Path) -> str | None:
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
        self.active_device = str(payload.get("device") or self.active_device)
        fallback = payload.get("fallback")
        self.last_fallback = str(fallback) if fallback else None
        return self.last_fallback

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
