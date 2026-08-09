import pytest

from polysub.subtitle_timing import (
    SubtitleTimingError,
    SubtitleTimingSettings,
    optimize_subtitle_timing,
)
from polysub.subtitles import SRTDocument


def _document(second_start: str = "00:00:03,000") -> SRTDocument:
    return SRTDocument.parse(
        f"""1
00:00:00,000 --> 00:00:00,700
Krótko

2
{second_start} --> 00:00:04,000
Następna kwestia
"""
    )


def test_profiles_offer_distinct_reading_durations() -> None:
    document = _document()

    dynamic = optimize_subtitle_timing(document, SubtitleTimingSettings.dynamic())
    recommended = optimize_subtitle_timing(document, SubtitleTimingSettings.recommended())
    comfortable = optimize_subtitle_timing(document, SubtitleTimingSettings.comfortable())

    assert dynamic.document.cues[0].timing.endswith("00:00:01,000")
    assert recommended.document.cues[0].timing.endswith("00:00:01,500")
    assert comfortable.document.cues[0].timing.endswith("00:00:02,000")


def test_recommended_mode_never_crosses_next_speaker_start() -> None:
    document = _document(second_start="00:00:00,800")

    result = optimize_subtitle_timing(document, SubtitleTimingSettings.recommended())

    assert result.document.cues[0].timing == "00:00:00,000 --> 00:00:00,700"
    assert result.document.cues[1].timing.startswith("00:00:00,800 -->")
    assert result.stats.limited_cues == 1


def test_existing_overlap_is_trimmed_in_readability_mode() -> None:
    document = SRTDocument.parse(
        """1
00:00:00,000 --> 00:00:01,200
Pierwszy

2
00:00:01,000 --> 00:00:02,000
Drugi
"""
    )

    result = optimize_subtitle_timing(document, SubtitleTimingSettings.recommended())

    assert result.document.cues[0].timing == "00:00:00,000 --> 00:00:00,900"
    assert result.document.cues[1].timing.startswith("00:00:01,000 -->")


def test_start_times_and_optional_srt_suffix_are_preserved() -> None:
    document = SRTDocument.parse(
        """1
00:00:01,000 --> 00:00:01,500 X1:0 X2:100
Czytelny tekst
"""
    )

    result = optimize_subtitle_timing(document, SubtitleTimingSettings.recommended())

    assert result.document.cues[0].timing.startswith("00:00:01,000 -->")
    assert result.document.cues[0].timing.endswith(" X1:0 X2:100")


def test_original_mode_is_exactly_non_mutating() -> None:
    document = _document()

    result = optimize_subtitle_timing(document, SubtitleTimingSettings.original())

    result.document.assert_structure_matches(document)
    assert result.stats.adjusted_cues == 0
    assert result.stats.summary == "Nie zmieniono timestampów."


def test_review_edit_is_retimed_from_source_instead_of_compounding_extensions() -> None:
    source = SRTDocument.parse(
        """1
00:00:00,000 --> 00:00:00,500
Krótko
"""
    )
    first_pass = optimize_subtitle_timing(source, SubtitleTimingSettings.recommended())
    first_pass.document.cues[0].text = "Bardzo długa poprawiona wypowiedź wymagająca więcej czasu."

    reviewed = optimize_subtitle_timing(
        first_pass.document,
        SubtitleTimingSettings.recommended(),
        timing_source=source,
    )

    assert first_pass.document.cues[0].timing.endswith("00:00:01,500")
    assert reviewed.document.cues[0].timing.endswith("00:00:02,000")


def test_custom_settings_are_validated() -> None:
    settings = SubtitleTimingSettings.custom(
        minimum_duration_seconds=2.3,
        max_chars_per_second=13,
    )

    assert settings.minimum_duration_ms == 2_300
    assert settings.max_chars_per_second == 13
    with pytest.raises(SubtitleTimingError, match="0,5"):
        SubtitleTimingSettings.custom(
            minimum_duration_seconds=0.1,
            max_chars_per_second=13,
        )


def test_simultaneous_cues_fail_instead_of_creating_an_overlap() -> None:
    document = SRTDocument.parse(
        """1
00:00:01,000 --> 00:00:01,500
Pierwszy

2
00:00:01,000 --> 00:00:02,000
Drugi
"""
    )

    with pytest.raises(SubtitleTimingError, match="jednocześnie"):
        optimize_subtitle_timing(document, SubtitleTimingSettings.recommended())
