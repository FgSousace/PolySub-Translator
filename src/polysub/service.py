from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from .cancellation import CancellationToken
from .checkpoint import CheckpointStore, checkpoint_for
from .engines.base import TranslationEngine, TranslationEngineError
from .markup import ProtectedText
from .models import ReviewItem, TranslationMode, TranslationResult
from .review import analyze_translation
from .subtitle_timing import SubtitleTimingSettings, optimize_subtitle_timing
from .subtitles import SRTDocument

ProgressCallback = Callable[[int, int], None]
StatusCallback = Callable[[str], None]


@dataclass(frozen=True)
class TranslationOptions:
    source_language: str
    target_language: str
    mode: TranslationMode = TranslationMode.AUTOMATIC
    context_notes: str = ""
    context_window: int = 3
    use_checkpoint: bool = True
    subtitle_timing: SubtitleTimingSettings = field(
        default_factory=SubtitleTimingSettings.recommended
    )


class TranslationService:
    def __init__(self, engine: TranslationEngine) -> None:
        self.engine = engine

    def translate(
        self,
        document: SRTDocument,
        options: TranslationOptions,
        *,
        progress: ProgressCallback | None = None,
        status: StatusCallback | None = None,
        output_path: Path | None = None,
        cancellation: CancellationToken | None = None,
    ) -> TranslationResult:
        original = document.clone()
        translated = document.clone()
        total_words = original.total_words
        progress = progress or (lambda _processed, _total: None)
        status = status or (lambda _message: None)
        cancellation = cancellation or CancellationToken()
        cancellation.raise_if_cancelled()
        status("Sprawdzanie zapisu wznowienia...")
        store = self._checkpoint(original, options)
        cached = store.load() if store else {}
        restored_translations: dict[int, str] = {}
        formatting: dict[int, bool] = {}
        processed_words = 0

        for position, text in cached.items():
            cancellation.raise_if_cancelled()
            if 0 <= position < len(translated.cues):
                translated.cues[position].text = text
                restored_translations[position] = text
                formatting[position] = True
                processed_words += original.cues[position].word_count
        if cached:
            status(f"Przywrócono {len(cached)} wcześniej przetłumaczonych kwestii.")
        else:
            status("Brak wcześniejszego postępu — rozpoczynanie od początku.")

        pending = [position for position in range(len(original.cues)) if position not in cached]
        accurate = options.mode is TranslationMode.REVIEW
        batch_size = 1 if accurate and self.engine.supports_context else self.engine.max_batch_size
        total_batches = (len(pending) + batch_size - 1) // batch_size
        status(
            f"Tłumaczenie {len(pending)} kwestii w {total_batches} partiach "
            f"przez {self.engine.display_name}..."
        )
        progress(processed_words, total_words)

        for start in range(0, len(pending), batch_size):
            cancellation.raise_if_cancelled()
            positions = pending[start : start + batch_size]
            protected = [ProtectedText.from_text(original.cues[pos].text) for pos in positions]
            contexts = [self._context_for(original, pos, options) for pos in positions]
            results = self.engine.translate_batch(
                [item.text for item in protected],
                source_language=options.source_language,
                target_language=options.target_language,
                contexts=contexts,
                accurate=accurate,
            )
            if len(results) != len(positions):
                raise TranslationEngineError("Silnik zwrócił nieprawidłową liczbę kwestii.")

            for position, template, result in zip(positions, protected, results, strict=True):
                restored, format_ok = template.restore(result)
                translated.cues[position].text = restored
                restored_translations[position] = restored
                formatting[position] = format_ok
                processed_words += original.cues[position].word_count
            if store:
                store.save(restored_translations)
            progress(processed_words, total_words)
            cancellation.raise_if_cancelled()

        cancellation.raise_if_cancelled()
        status("Kontrola struktury, timestampów i formatowania...")
        translated.assert_structure_matches(original)
        status("Dopasowywanie czasu wyświetlania napisów bez zmiany ich początku...")
        timing_result = optimize_subtitle_timing(translated, options.subtitle_timing)
        cancellation.raise_if_cancelled()
        translated = timing_result.document
        status(timing_result.stats.summary)
        status("Analizowanie jakości gotowego tłumaczenia...")
        review_items = self._review(original, translated, options, formatting)
        cancellation.raise_if_cancelled()
        if output_path:
            status("Zapisywanie przetłumaczonego pliku...")
        elif options.mode is TranslationMode.REVIEW:
            status("Przygotowywanie tłumaczenia do ręcznej weryfikacji...")
        else:
            status("Przygotowywanie gotowego wyniku w pamięci...")
        saved_path = translated.save(output_path) if output_path else None
        if store and options.mode is TranslationMode.AUTOMATIC:
            status("Czyszczenie zakończonego punktu wznowienia...")
            store.clear()
        return TranslationResult(
            document=translated,
            output_path=saved_path,
            checkpoint_path=store.path if store and store.path.exists() else None,
            total_words=total_words,
            processed_words=processed_words,
            review_items=review_items,
            timing_stats=timing_result.stats,
            timing_settings=options.subtitle_timing,
            resumed_cues=len(cached),
        )

    def _checkpoint(
        self, document: SRTDocument, options: TranslationOptions
    ) -> CheckpointStore | None:
        if not options.use_checkpoint or document.source_path is None:
            return None
        return checkpoint_for(
            document.source_path,
            source_fingerprint=document.fingerprint,
            target_language=options.target_language,
            engine_name=self.engine.name,
            mode=options.mode.value,
        )

    @staticmethod
    def _context_for(document: SRTDocument, position: int, options: TranslationOptions) -> str:
        start = max(0, position - options.context_window)
        end = min(len(document.cues), position + options.context_window + 1)
        neighbors = [
            cue.visible_text
            for index, cue in enumerate(document.cues[start:end], start=start)
            if index != position
        ]
        pieces = []
        if options.context_notes.strip():
            pieces.append("Informacje o postaciach i stylu:\n" + options.context_notes.strip())
        if neighbors:
            pieces.append("Sąsiednie kwestie:\n" + "\n".join(neighbors))
        return "\n\n".join(pieces)[:8_000]

    @staticmethod
    def _review(
        original: SRTDocument,
        translated: SRTDocument,
        options: TranslationOptions,
        formatting: dict[int, bool],
    ) -> list[ReviewItem]:
        items: list[ReviewItem] = []
        for position, (source, target) in enumerate(
            zip(original.cues, translated.cues, strict=True)
        ):
            item = analyze_translation(
                source,
                target,
                cue_position=position,
                source_language=options.source_language,
                target_language=options.target_language,
                formatting_ok=formatting.get(position, True),
            )
            if item:
                items.append(item)
        return items
