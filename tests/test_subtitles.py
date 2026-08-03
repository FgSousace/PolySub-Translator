from pathlib import Path

import pytest

from polysub.subtitles import (
    SRTDocument,
    SubtitleFormatError,
    count_words,
    default_output_path,
)

SAMPLE = """1
00:00:01,000 --> 00:00:03,000
<i>Hello world!</i>

2
00:00:04,500 --> 00:00:06,250
- I'm ready.
- Let's go.
"""


def test_parse_and_compose_preserve_structure() -> None:
    document = SRTDocument.parse(SAMPLE)

    assert len(document.cues) == 2
    assert document.cues[0].identifier == "1"
    assert document.cues[1].timing == "00:00:04,500 --> 00:00:06,250"
    assert document.cues[0].visible_text == "Hello world!"

    round_trip = SRTDocument.parse(document.compose())
    round_trip.assert_structure_matches(document)


def test_structure_validation_rejects_timestamp_change() -> None:
    original = SRTDocument.parse(SAMPLE)
    changed = original.clone()
    changed.cues[0].timing = "00:00:01,100 --> 00:00:03,000"

    with pytest.raises(SubtitleFormatError, match="timestamp"):
        changed.assert_structure_matches(original)


def test_word_counter_handles_polish_and_cjk() -> None:
    assert count_words("Zażółć gęślą jaźń") == 3
    assert count_words("你好世界") == 4


def test_default_output_path() -> None:
    assert default_output_path(Path("movie.en.srt"), "PL") == Path("movie.en.pl.srt")


def test_invalid_file_is_rejected() -> None:
    with pytest.raises(SubtitleFormatError):
        SRTDocument.parse("This is not an SRT file")
