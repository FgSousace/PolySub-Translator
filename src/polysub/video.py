from __future__ import annotations

import os
import re
import subprocess
import textwrap
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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


@dataclass(frozen=True)
class VideoImportResult:
    document: SRTDocument
    subtitle_path: Path
    method: str
    detected_language: str | None = None


class VideoSubtitleImporter:
    def __init__(
        self,
        *,
        model_size: str = "medium",
        ffmpeg_executable: str | None = None,
        model_factory: ModelFactory | None = None,
    ) -> None:
        self.model_size = model_size
        self.ffmpeg_executable = ffmpeg_executable
        self.model_factory = model_factory

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

        status(
            f"Brak tekstowych napisów — rozpoznawanie mowy przez Whisper {self.model_size}..."
        )
        return self._transcribe_audio(video, progress=progress)

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
        progress: MediaProgressCallback,
    ) -> VideoImportResult:
        model_factory = self.model_factory
        if model_factory is None:
            try:
                from faster_whisper import WhisperModel
            except ImportError as exc:
                raise VideoImportError(
                    'Brakuje obsługi wideo. Zainstaluj: pip install -e ".[video]"'
                ) from exc
            model_factory = WhisperModel

        device = os.getenv("POLYSUB_WHISPER_DEVICE", "cpu").strip() or "cpu"
        compute_type = os.getenv(
            "POLYSUB_WHISPER_COMPUTE_TYPE", "int8" if device == "cpu" else "float16"
        )
        try:
            model = model_factory(
                self.model_size,
                device=device,
                compute_type=compute_type,
                download_root=str(_whisper_cache_path()),
            )
            segments, info = model.transcribe(
                str(video_path),
                task="transcribe",
                beam_size=5,
                vad_filter=True,
                word_timestamps=True,
            )
            duration = float(getattr(info, "duration", 0.0) or 0.0)
            cues: list[SRTCue] = []
            for segment in segments:
                cues.extend(_cues_from_segment(segment, first_identifier=len(cues) + 1))
                processed = float(getattr(segment, "end", 0.0) or 0.0)
                progress(processed, max(duration, processed, 1.0))
        except VideoImportError:
            raise
        except Exception as exc:
            raise VideoImportError(f"Nie udało się rozpoznać mowy z filmu: {exc}") from exc

        if not cues:
            raise VideoImportError(
                "Film nie zawiera tekstowych napisów ani możliwej do rozpoznania mowy."
            )

        output = transcribed_subtitle_path(video_path)
        document = SRTDocument(cues=cues, source_path=output)
        document.save(output)
        return VideoImportResult(
            document=document,
            subtitle_path=output,
            method="transcribed",
            detected_language=getattr(info, "language", None),
        )


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
    ) -> Path:
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


def _same_path(first: Path, second: Path) -> bool:
    return os.path.normcase(os.path.abspath(first)) == os.path.normcase(os.path.abspath(second))


def _process_error(stderr: bytes | str | None) -> str:
    if isinstance(stderr, bytes):
        value = stderr.decode("utf-8", errors="replace")
    else:
        value = stderr or ""
    return " ".join(value.strip().split())[-1200:]


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
