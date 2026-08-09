from pathlib import Path

import pytest

from polysub.cancellation import CancellationToken, TranslationCancelled
from polysub.engines.base import TranslationEngine, TranslationEngineError
from polysub.models import ReviewReason, TranslationMode
from polysub.service import TranslationOptions, TranslationService
from polysub.subtitles import SRTDocument

SAMPLE = """1
00:00:01,000 --> 00:00:02,000
<i>Hello world.</i>

2
00:00:03,000 --> 00:00:04,000
I'm ready.
"""


class FakeEngine(TranslationEngine):
    name = "fake"
    max_batch_size = 1
    supports_context = True

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def translate_batch(
        self,
        texts,
        *,
        source_language,
        target_language,
        contexts=None,
        accurate=False,
    ):
        self.calls.append(list(texts))
        replacements = {
            "Hello world.": "Witaj świecie.",
            "I'm ready.": "Jestem gotowa.",
        }
        translated = []
        for text in texts:
            value = text
            for source, target in replacements.items():
                value = value.replace(source, target)
            translated.append(value)
        return translated


class FailingEngine(FakeEngine):
    def translate_batch(self, *args, **kwargs):
        if len(self.calls) == 1:
            raise TranslationEngineError("planned failure")
        return super().translate_batch(*args, **kwargs)


def test_translation_preserves_markup_and_reports_word_progress() -> None:
    document = SRTDocument.parse(SAMPLE)
    updates = []
    statuses = []
    result = TranslationService(FakeEngine()).translate(
        document,
        TranslationOptions("en", "pl"),
        progress=lambda done, total: updates.append((done, total)),
        status=statuses.append,
    )

    assert result.document.cues[0].text == "<i>Witaj świecie.</i>"
    assert result.document.cues[1].text == "Jestem gotowa."
    assert updates[-1] == (document.total_words, document.total_words)
    assert statuses[0] == "Sprawdzanie zapisu wznowienia..."
    assert any(message.startswith("Tłumaczenie 2 kwestii") for message in statuses)
    assert "Kontrola struktury, timestampów i formatowania..." in statuses
    assert statuses[-1] == "Przygotowywanie gotowego wyniku w pamięci..."
    result.document.assert_structure_matches(document, allow_timing_changes=True)
    assert result.timing_stats.adjusted_cues == 2


def test_review_mode_marks_gender_ambiguity() -> None:
    document = SRTDocument.parse(SAMPLE)
    result = TranslationService(FakeEngine()).translate(
        document,
        TranslationOptions("en", "pl", mode=TranslationMode.REVIEW),
    )

    assert any(ReviewReason.GENDER_OR_INFLECTION in item.reasons for item in result.review_items)


def test_checkpoint_resumes_finished_cues(tmp_path: Path) -> None:
    source = tmp_path / "movie.srt"
    source.write_text(SAMPLE, encoding="utf-8")
    document = SRTDocument.load(source)
    options = TranslationOptions("en", "pl")

    with pytest.raises(TranslationEngineError, match="planned failure"):
        TranslationService(FailingEngine()).translate(document, options)

    checkpoint = source.with_suffix(".srt.polysub.json")
    assert checkpoint.exists()

    resumed = TranslationService(FakeEngine()).translate(document, options)
    assert resumed.resumed_cues == 1
    assert not checkpoint.exists()


def test_cancellation_stops_between_batches_and_preserves_checkpoint(tmp_path: Path) -> None:
    source = tmp_path / "movie.srt"
    source.write_text(SAMPLE, encoding="utf-8")
    document = SRTDocument.load(source)
    token = CancellationToken()

    def cancel_after_first_batch(done: int, total: int) -> None:
        if 0 < done < total:
            token.cancel()

    with pytest.raises(TranslationCancelled, match="anulowane"):
        TranslationService(FakeEngine()).translate(
            document,
            TranslationOptions("en", "pl"),
            progress=cancel_after_first_batch,
            cancellation=token,
        )

    checkpoint = source.with_suffix(".srt.polysub.json")
    assert checkpoint.exists()

    resumed = TranslationService(FakeEngine()).translate(
        document,
        TranslationOptions("en", "pl"),
    )
    assert resumed.resumed_cues == 1
    assert not checkpoint.exists()
