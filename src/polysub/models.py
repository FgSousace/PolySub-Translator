from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

from .subtitle_timing import SubtitleTimingSettings, SubtitleTimingStats

if TYPE_CHECKING:
    from .subtitles import SRTDocument


class TranslationMode(str, Enum):
    AUTOMATIC = "automatic"
    REVIEW = "review"


class ReviewReason(str, Enum):
    GENDER_OR_INFLECTION = "Możliwa niejednoznaczna płeć lub odmiana"
    MULTIPLE_SPEAKERS = "Kilku rozmówców w jednej kwestii"
    UNCHANGED = "Tłumaczenie jest identyczne z oryginałem"
    EMPTY = "Silnik zwrócił pustą treść"
    FORMATTING = "Nie udało się zachować całego formatowania"


@dataclass(frozen=True)
class DetectionResult:
    code: str
    confidence: float
    name: str


@dataclass
class ReviewItem:
    cue_position: int
    identifier: str
    timing: str
    source_text: str
    translated_text: str
    reasons: list[ReviewReason] = field(default_factory=list)


@dataclass
class TranslationResult:
    document: SRTDocument
    output_path: Path | None
    checkpoint_path: Path | None
    total_words: int
    processed_words: int
    review_items: list[ReviewItem]
    timing_stats: SubtitleTimingStats = field(default_factory=SubtitleTimingStats)
    timing_settings: SubtitleTimingSettings = field(
        default_factory=SubtitleTimingSettings.recommended
    )
    resumed_cues: int = 0
