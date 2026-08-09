from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from .subtitles import SRTDocument, strip_markup

TIMING_PARTS_RE = re.compile(
    r"^\s*(?P<start>\d{1,3}:\d{2}:\d{2}[,.]\d{3})\s*-->\s*"
    r"(?P<end>\d{1,3}:\d{2}:\d{2}[,.]\d{3})(?P<suffix>\s+.*)?$"
)


class SubtitleTimingError(ValueError):
    pass


class SubtitleTimingMode(str, Enum):
    ORIGINAL = "original"
    DYNAMIC = "dynamic"
    RECOMMENDED = "recommended"
    COMFORTABLE = "comfortable"
    CUSTOM = "custom"


@dataclass(frozen=True)
class SubtitleTimingSettings:
    mode: SubtitleTimingMode
    minimum_duration_ms: int
    max_chars_per_second: float
    safety_gap_ms: int
    max_extension_ms: int
    max_duration_ms: int = 8_000

    @classmethod
    def original(cls) -> SubtitleTimingSettings:
        return cls(SubtitleTimingMode.ORIGINAL, 0, 0, 0, 0)

    @classmethod
    def dynamic(cls) -> SubtitleTimingSettings:
        return cls(SubtitleTimingMode.DYNAMIC, 1_000, 20.0, 80, 700)

    @classmethod
    def recommended(cls) -> SubtitleTimingSettings:
        return cls(SubtitleTimingMode.RECOMMENDED, 1_500, 17.0, 100, 1_500)

    @classmethod
    def comfortable(cls) -> SubtitleTimingSettings:
        return cls(SubtitleTimingMode.COMFORTABLE, 2_000, 14.0, 120, 2_500)

    @classmethod
    def custom(
        cls,
        *,
        minimum_duration_seconds: float,
        max_chars_per_second: float,
    ) -> SubtitleTimingSettings:
        if not 0.5 <= minimum_duration_seconds <= 5.0:
            raise SubtitleTimingError("Minimalny czas musi mieścić się między 0,5 a 5 sekund.")
        if not 8.0 <= max_chars_per_second <= 30.0:
            raise SubtitleTimingError("Prędkość czytania musi wynosić od 8 do 30 znaków/s.")
        return cls(
            SubtitleTimingMode.CUSTOM,
            round(minimum_duration_seconds * 1_000),
            float(max_chars_per_second),
            100,
            3_000,
        )

    @classmethod
    def for_mode(
        cls,
        mode: SubtitleTimingMode | str,
        *,
        minimum_duration_seconds: float = 1.5,
        max_chars_per_second: float = 17.0,
    ) -> SubtitleTimingSettings:
        resolved = SubtitleTimingMode(mode)
        if resolved is SubtitleTimingMode.ORIGINAL:
            return cls.original()
        if resolved is SubtitleTimingMode.DYNAMIC:
            return cls.dynamic()
        if resolved is SubtitleTimingMode.RECOMMENDED:
            return cls.recommended()
        if resolved is SubtitleTimingMode.COMFORTABLE:
            return cls.comfortable()
        return cls.custom(
            minimum_duration_seconds=minimum_duration_seconds,
            max_chars_per_second=max_chars_per_second,
        )


@dataclass(frozen=True)
class SubtitleTimingStats:
    adjusted_cues: int = 0
    limited_cues: int = 0
    total_cues: int = 0

    @property
    def summary(self) -> str:
        if self.total_cues == 0 or (self.adjusted_cues == 0 and self.limited_cues == 0):
            return "Nie zmieniono timestampów."
        message = f"Dopasowano czas {self.adjusted_cues} z {self.total_cues} napisów."
        if self.limited_cues:
            message += (
                f" {self.limited_cues} krótkich napisów nie dało się wydłużyć bez wejścia "
                "na następną wypowiedź."
            )
        return message


@dataclass(frozen=True)
class SubtitleTimingResult:
    document: SRTDocument
    stats: SubtitleTimingStats


@dataclass(frozen=True)
class _ParsedTiming:
    start_ms: int
    end_ms: int
    suffix: str


def optimize_subtitle_timing(
    document: SRTDocument,
    settings: SubtitleTimingSettings,
    *,
    timing_source: SRTDocument | None = None,
) -> SubtitleTimingResult:
    optimized = document.clone()
    if timing_source is not None:
        optimized.assert_structure_matches(timing_source, allow_timing_changes=True)
        for cue, source_cue in zip(optimized.cues, timing_source.cues, strict=True):
            cue.timing = source_cue.timing
    if settings.mode is SubtitleTimingMode.ORIGINAL:
        return SubtitleTimingResult(optimized, SubtitleTimingStats(total_cues=len(optimized.cues)))

    parsed = [_parse_timing(cue.timing) for cue in optimized.cues]
    _validate_timing_order(parsed)
    adjusted = 0
    limited = 0

    for position, (cue, timing) in enumerate(zip(optimized.cues, parsed, strict=True)):
        original_duration = timing.end_ms - timing.start_ms
        readable_duration = _required_duration_ms(cue.visible_text, settings)
        desired_duration = max(original_duration, readable_duration)
        maximum_end = timing.end_ms + settings.max_extension_ms
        if position + 1 < len(parsed):
            next_start = parsed[position + 1].start_ms
            preferred_boundary = next_start - settings.safety_gap_ms
            maximum_end = min(
                maximum_end,
                preferred_boundary if preferred_boundary > timing.start_ms else next_start,
            )
        if maximum_end <= timing.start_ms:
            raise SubtitleTimingError(
                "Dwa napisy zaczynają się jednocześnie i nie można rozdzielić ich bez nachodzenia."
            )
        new_end = min(timing.start_ms + desired_duration, maximum_end)

        if new_end - timing.start_ms < readable_duration:
            limited += 1
        if new_end != timing.end_ms:
            adjusted += 1
            cue.timing = _compose_timing(timing.start_ms, new_end, timing.suffix)

    _validate_no_overlaps(optimized)
    return SubtitleTimingResult(
        optimized,
        SubtitleTimingStats(
            adjusted_cues=adjusted,
            limited_cues=limited,
            total_cues=len(optimized.cues),
        ),
    )


def _required_duration_ms(text: str, settings: SubtitleTimingSettings) -> int:
    readable = " ".join(strip_markup(text).replace("\\N", " ").split())
    characters = len(readable)
    reading_time = round(characters / settings.max_chars_per_second * 1_000)
    return min(
        max(settings.minimum_duration_ms, reading_time),
        settings.max_duration_ms,
    )


def _parse_timing(value: str) -> _ParsedTiming:
    match = TIMING_PARTS_RE.match(value)
    if match is None:
        raise SubtitleTimingError(f"Nie można odczytać timestampa: {value}")
    start_ms = _timestamp_to_ms(match.group("start"))
    end_ms = _timestamp_to_ms(match.group("end"))
    if end_ms <= start_ms:
        raise SubtitleTimingError(f"Koniec napisu nie jest późniejszy od początku: {value}")
    return _ParsedTiming(start_ms, end_ms, match.group("suffix") or "")


def _timestamp_to_ms(value: str) -> int:
    hours, minutes, remainder = value.replace(".", ",").split(":")
    seconds, milliseconds = remainder.split(",")
    return (
        int(hours) * 3_600_000
        + int(minutes) * 60_000
        + int(seconds) * 1_000
        + int(milliseconds)
    )


def _format_timestamp(milliseconds: int) -> str:
    milliseconds = max(milliseconds, 0)
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, millis = divmod(remainder, 1_000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def _compose_timing(start_ms: int, end_ms: int, suffix: str) -> str:
    return f"{_format_timestamp(start_ms)} --> {_format_timestamp(end_ms)}{suffix}"


def _validate_timing_order(timings: list[_ParsedTiming]) -> None:
    for previous, current in zip(timings, timings[1:], strict=False):
        if current.start_ms < previous.start_ms:
            raise SubtitleTimingError("Timestampy nie są ułożone chronologicznie.")


def _validate_no_overlaps(document: SRTDocument) -> None:
    timings = [_parse_timing(cue.timing) for cue in document.cues]
    for previous, current in zip(timings, timings[1:], strict=False):
        if previous.end_ms > current.start_ms:
            raise SubtitleTimingError(
                "Nie udało się bezpiecznie rozdzielić sąsiadujących napisów."
            )


__all__ = [
    "SubtitleTimingError",
    "SubtitleTimingMode",
    "SubtitleTimingResult",
    "SubtitleTimingSettings",
    "SubtitleTimingStats",
    "optimize_subtitle_timing",
]
