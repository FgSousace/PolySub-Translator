from __future__ import annotations

import os
import re
import subprocess
import textwrap
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .performance import (
    DEFAULT_CPU_USAGE,
    configure_thread_environment,
    cpu_allocation,
)
from .subtitles import SRTCue, SRTDocument, SubtitleFormatError

VIDEO_EXTENSIONS = {".avi", ".m4v", ".mkv", ".mov", ".mp4", ".webm"}
FAST_MUX_MP4_EXTENSIONS = {".m4v", ".mov", ".mp4"}
MAX_CUE_CHARACTERS = 78
MAX_CUE_DURATION = 7.0

StatusCallback = Callable[[str], None]
MediaProgressCallback = Callable[[float, float], None]
ModelFactory = Callable[..., Any]


class VideoImportError(RuntimeError):
    pass


class VideoMuxError(RuntimeError):
    pass


class VideoBurnError(RuntimeError):
    pass


@dataclass(frozen=True)
class VideoImportResult:
    document: SRTDocument
    subtitle_path: Path
    method: str
    detected_language: str | None = None


@dataclass(frozen=True)
class VideoBurnResult:
    output_path: Path
    encoder: str
    hardware_accelerated: bool


class VideoSubtitleImporter:
    def __init__(
        self,
        *,
        model_size: str | Path | None = "medium",
        model_name: str | None = None,
        ffmpeg_executable: str | None = None,
        model_factory: ModelFactory | None = None,
        device: str | None = None,
        device_index: int = 0,
        allow_cpu_fallback: bool = True,
        cpu_usage_limit: int = DEFAULT_CPU_USAGE,
    ) -> None:
        self.model_size = model_size
        self.model_name = model_name or (
            f"Whisper {model_size}"
            if isinstance(model_size, str)
            else str(model_size or "niepobrany")
        )
        self.ffmpeg_executable = ffmpeg_executable
        self.model_factory = model_factory
        self.device = device
        self.device_index = device_index
        self.allow_cpu_fallback = allow_cpu_fallback
        self.cpu_allocation = cpu_allocation(cpu_usage_limit)
        configure_thread_environment(self.cpu_allocation)

    def import_video(
        self,
        video_path: str | Path,
        *,
        status: StatusCallback | None = None,
        progress: MediaProgressCallback | None = None,
    ) -> VideoImportResult:
        video = Path(video_path)
        if not video.is_file():
            raise VideoImportError(f"Nie znaleziono pliku wideo: {video}")
        if video.suffix.lower() not in VIDEO_EXTENSIONS:
            raise VideoImportError(f"Nieobsługiwany format wideo: {video.suffix or 'brak'}")

        status = status or (lambda _message: None)
        progress = progress or (lambda _processed, _total: None)
        status("Sprawdzanie wbudowanej ścieżki napisów...")
        embedded = self._extract_embedded_subtitles(video)
        if embedded is not None:
            document, subtitle_path = embedded
            return VideoImportResult(document, subtitle_path, "embedded")

        status(f"Brak tekstowych napisów — rozpoznawanie mowy przez {self.model_name}...")
        return self._transcribe_audio(video, status=status, progress=progress)

    def _extract_embedded_subtitles(
        self, video_path: Path
    ) -> tuple[SRTDocument, Path] | None:
        ffmpeg = self._resolve_ffmpeg()
        if ffmpeg is None:
            return None

        output = extracted_subtitle_path(video_path)
        temporary = output.with_name(f".{output.stem}.tmp.srt")
        temporary.unlink(missing_ok=True)
        command = [
            ffmpeg,
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(video_path),
            "-map",
            "0:s:0",
            "-c:s",
            "srt",
            str(temporary),
        ]
        try:
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except OSError:
            temporary.unlink(missing_ok=True)
            return None

        if completed.returncode != 0 or not temporary.exists() or temporary.stat().st_size == 0:
            temporary.unlink(missing_ok=True)
            return None
        try:
            document = SRTDocument.load(temporary)
        except (OSError, SubtitleFormatError):
            temporary.unlink(missing_ok=True)
            return None

        temporary.replace(output)
        document.source_path = output
        return document, output

    def _resolve_ffmpeg(self) -> str | None:
        if self.ffmpeg_executable:
            return self.ffmpeg_executable
        try:
            import imageio_ffmpeg

            return imageio_ffmpeg.get_ffmpeg_exe()
        except (ImportError, RuntimeError):
            return None

    def _transcribe_audio(
        self,
        video_path: Path,
        *,
        status: StatusCallback,
        progress: MediaProgressCallback,
    ) -> VideoImportResult:
        if self.model_size is None:
            raise VideoImportError(
                "Film nie ma tekstowych napisów, a żaden model Whisper nie jest pobrany. "
                "Otwórz menedżer modeli, wybierz zakładkę Whisper i pobierz model."
            )
        model_factory = self.model_factory
        if model_factory is None:
            status("Ładowanie modułu rozpoznawania mowy Whisper...")
            try:
                from faster_whisper import WhisperModel
            except ImportError as exc:
                raise VideoImportError(
                    'Brakuje obsługi wideo. Zainstaluj: pip install -e ".[video]"'
                ) from exc
            model_factory = WhisperModel

        configured_device = self.device or os.getenv("POLYSUB_WHISPER_DEVICE", "cpu")
        device, device_index = _split_device(configured_device, self.device_index)
        try:
            cues, info = self._run_whisper(
                model_factory,
                video_path,
                device=device,
                device_index=device_index,
                status=status,
                progress=progress,
            )
        except VideoImportError:
            raise
        except Exception as exc:
            if device != "cpu" and self.allow_cpu_fallback:
                status(
                    f"Nie udało się użyć GPU ({exc}). "
                    "Automatyczne przełączanie rozpoznawania mowy na CPU..."
                )
                try:
                    cues, info = self._run_whisper(
                        model_factory,
                        video_path,
                        device="cpu",
                        device_index=0,
                        status=status,
                        progress=progress,
                    )
                except Exception as cpu_exc:
                    raise VideoImportError(
                        f"Nie udało się rozpoznać mowy także na CPU: {cpu_exc}"
                    ) from cpu_exc
            else:
                raise VideoImportError(f"Nie udało się rozpoznać mowy z filmu: {exc}") from exc

        if not cues:
            raise VideoImportError(
                "Film nie zawiera tekstowych napisów ani możliwej do rozpoznania mowy."
            )

        status("Zapisywanie rozpoznanych napisów SRT...")
        output = transcribed_subtitle_path(video_path)
        document = SRTDocument(cues=cues, source_path=output)
        document.save(output)
        return VideoImportResult(
            document=document,
            subtitle_path=output,
            method="transcribed",
            detected_language=getattr(info, "language", None),
        )

    def _run_whisper(
        self,
        model_factory: ModelFactory,
        video_path: Path,
        *,
        device: str,
        device_index: int,
        status: StatusCallback,
        progress: MediaProgressCallback,
    ):
        compute_type = os.getenv(
            "POLYSUB_WHISPER_COMPUTE_TYPE", "int8" if device == "cpu" else "float16"
        )
        status(f"Ładowanie pobranego modelu {self.model_name} na urządzenie {device.upper()}...")
        model_kwargs: dict[str, Any] = {
            "device": device,
            "compute_type": compute_type,
            "download_root": str(_whisper_cache_path()),
            "cpu_threads": self.cpu_allocation.threads,
            "num_workers": 1,
        }
        if device != "cpu":
            model_kwargs["device_index"] = device_index
        model = model_factory(self.model_size, **model_kwargs)
        status(
            "Whisper może użyć "
            f"{self.cpu_allocation.threads} z "
            f"{self.cpu_allocation.logical_processors} logicznych wątków CPU "
            f"({self.cpu_allocation.percentage}%)."
        )
        status("Analizowanie ścieżki dźwiękowej filmu...")
        segments, info = model.transcribe(
            str(video_path),
            task="transcribe",
            beam_size=7,
            patience=1.2,
            vad_filter=True,
            vad_parameters={
                "min_silence_duration_ms": 350,
                "speech_pad_ms": 250,
            },
            word_timestamps=True,
            condition_on_previous_text=True,
            temperature=0.0,
            compression_ratio_threshold=2.4,
            log_prob_threshold=-1.0,
            no_speech_threshold=0.6,
        )
        status("Rozpoznawanie mowy i tworzenie kwestii napisów...")
        duration = float(getattr(info, "duration", 0.0) or 0.0)
        cues: list[SRTCue] = []
        for segment in segments:
            cues.extend(_cues_from_segment(segment, first_identifier=len(cues) + 1))
            processed = float(getattr(segment, "end", 0.0) or 0.0)
            progress(processed, max(duration, processed, 1.0))
        return cues, info


class VideoSubtitleMuxer:
    """Attach an SRT track without re-encoding the video or audio streams."""

    def __init__(self, *, ffmpeg_executable: str | None = None) -> None:
        self.ffmpeg_executable = ffmpeg_executable

    def mux(
        self,
        video_path: str | Path,
        subtitle_path: str | Path,
        *,
        target_language: str,
        output_path: str | Path | None = None,
        subtitle_title: str | None = None,
        status: StatusCallback | None = None,
    ) -> Path:
        status = status or (lambda _message: None)
        status("Sprawdzanie filmu i przetłumaczonych napisów...")
        video = Path(video_path)
        subtitles = Path(subtitle_path)
        output = Path(output_path) if output_path else fast_mux_output_path(video, target_language)

        if not video.is_file():
            raise VideoMuxError(f"Nie znaleziono filmu: {video}")
        if not subtitles.is_file():
            raise VideoMuxError(f"Nie znaleziono napisów: {subtitles}")
        if subtitles.suffix.lower() != ".srt":
            raise VideoMuxError("Szybkie dołączanie obsługuje napisy w formacie SRT.")
        if output.suffix.lower() not in {".mp4", ".mkv"}:
            raise VideoMuxError("Film wynikowy musi mieć rozszerzenie .mp4 albo .mkv.")
        if _same_path(video, output):
            raise VideoMuxError("Film wynikowy nie może nadpisywać oryginalnego filmu.")

        status("Przygotowywanie programu FFmpeg...")
        ffmpeg = self._resolve_ffmpeg()
        if ffmpeg is None:
            raise VideoMuxError(
                'Brakuje FFmpeg. Zainstaluj obsługę wideo: pip install -e ".[video]"'
            )

        subtitle_codec = "mov_text" if output.suffix.lower() == ".mp4" else "srt"
        temporary = output.with_name(f".{output.stem}.tmp{output.suffix}")
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
            str(subtitles),
            "-map",
            "0:v?",
            "-map",
            "0:a?",
            "-map",
            "1:0",
            "-map_metadata",
            "0",
            "-map_chapters",
            "0",
            "-c:v",
            "copy",
            "-c:a",
            "copy",
            "-c:s",
            subtitle_codec,
            "-metadata:s:s:0",
            f"language={target_language.lower()}",
            "-metadata:s:s:0",
            f"title={subtitle_title or target_language.upper()}",
        ]
        command.append(str(temporary))

        status("Kopiowanie obrazu, dźwięku i dołączanie ścieżki napisów...")
        try:
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except OSError as exc:
            temporary.unlink(missing_ok=True)
            raise VideoMuxError(f"Nie udało się uruchomić FFmpeg: {exc}") from exc

        if completed.returncode != 0 or not temporary.exists() or temporary.stat().st_size == 0:
            temporary.unlink(missing_ok=True)
            details = _process_error(completed.stderr)
            message = "Nie udało się dołączyć napisów do filmu."
            if details:
                message += f"\n\nFFmpeg: {details}"
            raise VideoMuxError(message)

        status("Finalizowanie pliku filmu...")
        temporary.replace(output)
        return output

    def _resolve_ffmpeg(self) -> str | None:
        if self.ffmpeg_executable:
            return self.ffmpeg_executable
        try:
            import imageio_ffmpeg

            return imageio_ffmpeg.get_ffmpeg_exe()
        except (ImportError, RuntimeError):
            return None


class VideoSubtitleBurner:
    """Render SRT text into every video frame and create a separate output file."""

    HARDWARE_ENCODERS = {
        "NVIDIA": "h264_nvenc",
        "Intel": "h264_qsv",
        "AMD": "h264_amf",
    }
    ENCODER_NAMES = {
        "h264_nvenc": "NVIDIA NVENC",
        "h264_qsv": "Intel Quick Sync",
        "h264_amf": "AMD AMF",
        "libx264": "CPU (x264)",
        "mpeg4": "CPU (MPEG-4)",
    }

    def __init__(
        self,
        *,
        ffmpeg_executable: str | None = None,
        cpu_usage_limit: int = DEFAULT_CPU_USAGE,
    ) -> None:
        self.ffmpeg_executable = ffmpeg_executable
        self.cpu_allocation = cpu_allocation(cpu_usage_limit)

    def burn(
        self,
        video_path: str | Path,
        subtitle_path: str | Path,
        *,
        target_language: str,
        output_path: str | Path | None = None,
        preferred_vendor: str | None = None,
        status: StatusCallback | None = None,
        progress: MediaProgressCallback | None = None,
    ) -> VideoBurnResult:
        status = status or (lambda _message: None)
        progress = progress or (lambda _processed, _total: None)
        status("Sprawdzanie filmu i przetłumaczonych napisów...")
        video = Path(video_path)
        subtitles = Path(subtitle_path)
        output = (
            Path(output_path)
            if output_path
            else burned_video_output_path(video, target_language)
        )
        self._validate_paths(video, subtitles, output)

        status("Przygotowywanie programu FFmpeg i wykrywanie akceleracji...")
        ffmpeg = self._resolve_ffmpeg()
        if ffmpeg is None:
            raise VideoBurnError(
                'Brakuje FFmpeg. Zainstaluj obsługę wideo: pip install -e ".[video]"'
            )

        available = self._available_encoders(ffmpeg)
        candidates = self._encoder_candidates(available, preferred_vendor)
        if not candidates:
            raise VideoBurnError("FFmpeg nie udostępnia zgodnego kodera obrazu.")

        duration = self._probe_duration(ffmpeg, video)
        temporary = output.with_name(f".{output.stem}.burning{output.suffix}")
        temporary.unlink(missing_ok=True)
        errors: list[str] = []
        for encoder in candidates:
            encoder_name = self.ENCODER_NAMES[encoder]
            hardware = encoder in self.HARDWARE_ENCODERS.values()
            status(
                f"Wypalanie napisów przez {encoder_name}..."
                if hardware
                else f"Wypalanie napisów przez {encoder_name} — tryb awaryjny..."
            )
            temporary.unlink(missing_ok=True)
            command = self._burn_command(
                ffmpeg,
                video,
                subtitles,
                temporary,
                encoder,
            )
            try:
                returncode, details = self._run_with_progress(
                    command,
                    duration=duration,
                    progress=progress,
                )
            except OSError as exc:
                temporary.unlink(missing_ok=True)
                raise VideoBurnError(f"Nie udało się uruchomić FFmpeg: {exc}") from exc

            if returncode == 0 and temporary.is_file() and temporary.stat().st_size > 0:
                status("Finalizowanie filmu z napisami na obrazie...")
                temporary.replace(output)
                progress(max(duration, 1.0), max(duration, 1.0))
                return VideoBurnResult(output, encoder_name, hardware)

            temporary.unlink(missing_ok=True)
            errors.append(f"{encoder_name}: {details or 'koder nie uruchomił się'}")
            if hardware:
                status(
                    f"{encoder_name} nie zadziałał — próba kolejnego kodera "
                    "lub bezpiecznego trybu CPU..."
                )

        details = "\n".join(errors[-3:])
        message = "Nie udało się wypalić napisów na obrazie filmu."
        if details:
            message += f"\n\nFFmpeg:\n{details}"
        raise VideoBurnError(message)

    @staticmethod
    def _validate_paths(video: Path, subtitles: Path, output: Path) -> None:
        if not video.is_file():
            raise VideoBurnError(f"Nie znaleziono filmu: {video}")
        if not subtitles.is_file():
            raise VideoBurnError(f"Nie znaleziono napisów: {subtitles}")
        if subtitles.suffix.lower() != ".srt":
            raise VideoBurnError("Wypalanie napisów obsługuje pliki SRT.")
        if output.suffix.lower() not in {".mp4", ".mkv"}:
            raise VideoBurnError("Film wynikowy musi mieć rozszerzenie .mp4 albo .mkv.")
        if _same_path(video, output):
            raise VideoBurnError("Film wynikowy nie może nadpisywać oryginalnego filmu.")

    def _resolve_ffmpeg(self) -> str | None:
        if self.ffmpeg_executable:
            return self.ffmpeg_executable
        try:
            import imageio_ffmpeg

            return imageio_ffmpeg.get_ffmpeg_exe()
        except (ImportError, RuntimeError):
            return None

    def _available_encoders(self, ffmpeg: str) -> set[str] | None:
        try:
            completed = subprocess.run(
                [ffmpeg, "-nostdin", "-hide_banner", "-encoders"],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except OSError:
            return None
        if completed.returncode != 0:
            return None
        encoders = set()
        for line in completed.stdout.splitlines():
            pieces = line.split()
            if len(pieces) >= 2 and pieces[0].startswith("V"):
                encoders.add(pieces[1])
        return encoders

    def _encoder_candidates(
        self,
        available: set[str] | None,
        preferred_vendor: str | None,
    ) -> list[str]:
        def is_available(name: str) -> bool:
            return available is None or name in available

        software = [
            name
            for name in ("libx264", "mpeg4")
            if is_available(name)
        ][:1]
        if preferred_vendor == "CPU":
            return software

        if preferred_vendor in self.HARDWARE_ENCODERS:
            hardware_order = [self.HARDWARE_ENCODERS[preferred_vendor]]
        else:
            hardware_order = [
                self.HARDWARE_ENCODERS[vendor]
                for vendor in ("NVIDIA", "Intel", "AMD")
            ]
        hardware = [name for name in hardware_order if is_available(name)]
        return hardware + software

    def _burn_command(
        self,
        ffmpeg: str,
        video: Path,
        subtitles: Path,
        temporary: Path,
        encoder: str,
    ) -> list[str]:
        command = [
            ffmpeg,
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(video),
            "-map",
            "0:v:0",
            "-map",
            "0:a?",
            "-map_metadata",
            "0",
            "-map_chapters",
            "0",
            "-vf",
            _subtitle_filter(subtitles),
            "-filter_threads",
            str(self.cpu_allocation.threads),
        ]
        command += _video_encoder_arguments(encoder)
        command += [
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-threads",
            str(self.cpu_allocation.threads),
            "-sn",
        ]
        if temporary.suffix.lower() == ".mp4":
            command += ["-movflags", "+faststart"]
        command += ["-progress", "pipe:1", "-nostats", str(temporary)]
        return command

    @staticmethod
    def _run_with_progress(
        command: list[str],
        *,
        duration: float,
        progress: MediaProgressCallback,
    ) -> tuple[int, str]:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        details_lines: list[str] = []
        if process.stdout is not None:
            for raw_line in process.stdout:
                key, separator, raw_value = raw_line.strip().partition("=")
                if not separator or key not in {"out_time_us", "out_time_ms"}:
                    details_lines.append(raw_line)
                    details_lines = details_lines[-50:]
                    continue
                try:
                    processed = max(float(raw_value) / 1_000_000, 0.0)
                except ValueError:
                    continue
                progress(processed, max(duration, processed, 1.0))
        returncode = process.wait()
        details = _process_error("".join(details_lines))
        return returncode, details

    @staticmethod
    def _probe_duration(ffmpeg: str, video: Path) -> float:
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
            return 0.0
        match = re.search(
            r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)",
            completed.stderr or "",
        )
        if match is None:
            return 0.0
        hours, minutes, seconds = match.groups()
        return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def extracted_subtitle_path(video_path: str | Path) -> Path:
    video = Path(video_path)
    return video.with_name(f"{video.stem}.extracted.srt")


def transcribed_subtitle_path(video_path: str | Path) -> Path:
    video = Path(video_path)
    return video.with_name(f"{video.stem}.transcribed.srt")


def translated_video_subtitle_path(video_path: str | Path, target_language: str) -> Path:
    video = Path(video_path)
    return video.with_name(f"{video.stem}.{target_language.lower()}.srt")


def fast_mux_output_path(video_path: str | Path, target_language: str) -> Path:
    video = Path(video_path)
    suffix = ".mp4" if video.suffix.lower() in FAST_MUX_MP4_EXTENSIONS else ".mkv"
    return video.with_name(f"{video.stem}.{target_language.lower()}.subtitled{suffix}")


def burned_video_output_path(video_path: str | Path, target_language: str) -> Path:
    video = Path(video_path)
    return video.with_name(f"{video.stem}.{target_language.lower()}.burned.mp4")


def format_media_duration(seconds: float) -> str:
    total = max(0, int(round(seconds)))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours:d} godz. {minutes:02d} min {secs:02d} s"
    if minutes:
        return f"{minutes:d} min {secs:02d} s"
    return f"{secs:d} s"


def _whisper_cache_path() -> Path:
    configured = os.getenv("POLYSUB_MODEL_CACHE")
    if configured:
        return Path(configured) / "faster-whisper"
    local_app_data = os.getenv("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "PolySub" / "models" / "faster-whisper"
    return Path.home() / ".cache" / "polysub" / "faster-whisper"


def _split_device(value: str, default_index: int) -> tuple[str, int]:
    normalized = value.strip().lower() or "cpu"
    if ":" not in normalized:
        return normalized, max(default_index, 0)
    backend, raw_index = normalized.split(":", 1)
    try:
        index = max(int(raw_index), 0)
    except ValueError:
        index = max(default_index, 0)
    return backend or "cpu", index


def _same_path(first: Path, second: Path) -> bool:
    return os.path.normcase(os.path.abspath(first)) == os.path.normcase(os.path.abspath(second))


def _process_error(stderr: bytes | str | None) -> str:
    if isinstance(stderr, bytes):
        value = stderr.decode("utf-8", errors="replace")
    else:
        value = stderr or ""
    return " ".join(value.strip().split())[-1200:]


def _subtitle_filter(subtitles: Path) -> str:
    escaped = str(subtitles.resolve()).replace("\\", "/")
    for character in ("\\", ":", "'", "[", "]", ",", ";"):
        escaped = escaped.replace(character, f"\\{character}")
    style = "FontName=Arial,FontSize=22,Outline=2,Shadow=0,MarginV=24,Alignment=2"
    return (
        f"subtitles=filename='{escaped}':charenc=UTF-8:"
        f"force_style='{style}'"
    )


def _video_encoder_arguments(encoder: str) -> list[str]:
    if encoder == "h264_nvenc":
        return [
            "-c:v",
            encoder,
            "-preset",
            "p4",
            "-tune",
            "hq",
            "-rc",
            "vbr",
            "-cq",
            "20",
            "-b:v",
            "0",
        ]
    if encoder == "h264_qsv":
        return ["-c:v", encoder, "-preset", "medium", "-global_quality", "20"]
    if encoder == "h264_amf":
        return [
            "-c:v",
            encoder,
            "-quality",
            "balanced",
            "-rc",
            "cqp",
            "-qp_i",
            "20",
            "-qp_p",
            "22",
            "-qp_b",
            "24",
        ]
    if encoder == "libx264":
        return ["-c:v", encoder, "-preset", "veryfast", "-crf", "20"]
    return ["-c:v", "mpeg4", "-q:v", "3"]


def _cues_from_segment(segment: Any, *, first_identifier: int) -> list[SRTCue]:
    pieces = _split_segment(segment)
    cues: list[SRTCue] = []
    for start, end, text in pieces:
        cleaned = re.sub(r"\s+", " ", text).strip()
        if not cleaned:
            continue
        cues.append(
            SRTCue(
                identifier=str(first_identifier + len(cues)),
                timing=f"{_srt_timestamp(start)} --> {_srt_timestamp(max(end, start + 0.1))}",
                text=_wrap_subtitle(cleaned),
            )
        )
    return cues


def _split_segment(segment: Any) -> list[tuple[float, float, str]]:
    words = list(getattr(segment, "words", None) or [])
    if not words:
        return [
            (
                float(getattr(segment, "start", 0.0) or 0.0),
                float(getattr(segment, "end", 0.0) or 0.0),
                str(getattr(segment, "text", "")),
            )
        ]

    groups: list[list[Any]] = []
    current: list[Any] = []
    for word in words:
        candidate = [*current, word]
        candidate_text = _joined_words(candidate)
        candidate_start = float(getattr(candidate[0], "start", 0.0) or 0.0)
        candidate_end = float(getattr(candidate[-1], "end", candidate_start) or candidate_start)
        too_long = len(candidate_text) > MAX_CUE_CHARACTERS
        too_slow = candidate_end - candidate_start > MAX_CUE_DURATION
        if current and (too_long or too_slow):
            groups.append(current)
            current = [word]
        else:
            current = candidate

        current_text = _joined_words(current)
        current_start = float(getattr(current[0], "start", 0.0) or 0.0)
        current_end = float(getattr(current[-1], "end", current_start) or current_start)
        sentence_end = current_text.endswith((".", "!", "?", "…"))
        if sentence_end and (len(current_text) >= 32 or current_end - current_start >= 2.5):
            groups.append(current)
            current = []
    if current:
        groups.append(current)

    return [
        (
            float(getattr(group[0], "start", 0.0) or 0.0),
            float(getattr(group[-1], "end", 0.0) or 0.0),
            _joined_words(group),
        )
        for group in groups
    ]


def _joined_words(words: list[Any]) -> str:
    return "".join(str(getattr(word, "word", "")) for word in words).strip()


def _wrap_subtitle(text: str) -> str:
    lines = textwrap.wrap(
        text,
        width=42,
        break_long_words=False,
        break_on_hyphens=False,
    )
    return "\n".join(lines) if lines else text


def _srt_timestamp(seconds: float) -> str:
    milliseconds = max(0, int(round(seconds * 1000)))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"
