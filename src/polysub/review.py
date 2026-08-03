from __future__ import annotations

import re

from .models import ReviewItem, ReviewReason
from .subtitles import SRTCue

ENGLISH_GENDER_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bI(?:'m| am| was| have been| felt| got)\b",
        r"\byou(?:'re| are| were| have been| felt| got)\b",
        r"\b(?:he|she)\b",
        r"\b(?:boyfriend|girlfriend|husband|wife|actor|actress)\b",
    )
]


def analyze_translation(
    source_cue: SRTCue,
    translated_cue: SRTCue,
    *,
    cue_position: int,
    source_language: str,
    target_language: str,
    formatting_ok: bool,
) -> ReviewItem | None:
    reasons: list[ReviewReason] = []
    source = source_cue.visible_text.strip()
    translated = translated_cue.visible_text.strip()

    if not translated:
        reasons.append(ReviewReason.EMPTY)
    elif source.casefold() == translated.casefold() and source:
        reasons.append(ReviewReason.UNCHANGED)
    if not formatting_ok:
        reasons.append(ReviewReason.FORMATTING)
    if "\n-" in source_cue.text or "\\N-" in source_cue.text:
        reasons.append(ReviewReason.MULTIPLE_SPEAKERS)
    if source_language.startswith("en") and target_language.startswith("pl"):
        if any(pattern.search(source) for pattern in ENGLISH_GENDER_PATTERNS):
            reasons.append(ReviewReason.GENDER_OR_INFLECTION)

    if not reasons:
        return None
    return ReviewItem(
        cue_position=cue_position,
        identifier=source_cue.identifier,
        timing=source_cue.timing,
        source_text=source_cue.text,
        translated_text=translated_cue.text,
        reasons=list(dict.fromkeys(reasons)),
    )
