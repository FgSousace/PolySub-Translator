from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .detector import LanguageDetectionError, detect_language
from .engines import DeepLEngine, M2M100Engine, TranslationEngineError
from .models import TranslationMode
from .service import TranslationOptions, TranslationService
from .subtitles import SRTDocument, SubtitleFormatError, default_output_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="polysub",
        description="Automatycznie wykrywa język i tłumaczy napisy SRT.",
    )
    parser.add_argument("input", nargs="?", type=Path, help="Plik wejściowy .srt")
    parser.add_argument("--target", "-t", help="Kod języka docelowego, np. pl")
    parser.add_argument("--source", "-s", default="auto", help="Kod źródłowy lub auto")
    parser.add_argument(
        "--engine",
        choices=("local", "deepl"),
        default="local",
        help="Lokalny M2M100 albo DeepL API",
    )
    parser.add_argument(
        "--mode",
        choices=("automatic", "review"),
        default="automatic",
        help="Tłumaczenie automatyczne albo z weryfikacją",
    )
    parser.add_argument("--output", "-o", type=Path, help="Ścieżka pliku wynikowego")
    parser.add_argument(
        "--context-file",
        type=Path,
        help="Plik TXT z informacjami o postaciach, płci i preferowanej terminologii",
    )
    parser.add_argument("--no-resume", action="store_true", help="Nie używaj zapisu awaryjnego")
    parser.add_argument("--gui", action="store_true", help="Uruchom interfejs graficzny")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.gui or args.input is None:
        from .gui import main as gui_main

        gui_main()
        return 0

    try:
        document = SRTDocument.load(args.input)
        detected = detect_language(document.combined_text)
        source = detected.code if args.source == "auto" else args.source.lower()
        print(
            f"Wykryty język: {detected.name} ({detected.code}), pewność {detected.confidence:.0%}"
        )
        target = (args.target or _ask_target()).lower()
        if source == target:
            parser.error("Język źródłowy i docelowy nie mogą być takie same.")

        context_notes = ""
        if args.context_file:
            context_notes = args.context_file.read_text(encoding="utf-8")
        engine = _create_engine(args.engine)
        mode = TranslationMode(args.mode)
        output = args.output or default_output_path(args.input, target)
        service = TranslationService(engine)
        options = TranslationOptions(
            source_language=source,
            target_language=target,
            mode=mode,
            context_notes=context_notes,
            use_checkpoint=not args.no_resume,
        )

        print(f"Silnik: {engine.display_name}")
        result = service.translate(
            document,
            options,
            progress=_console_progress,
            output_path=None if mode is TranslationMode.REVIEW else output,
        )
        print()

        if mode is TranslationMode.REVIEW:
            _review_interactively(result)
            result.document.assert_structure_matches(document)
            result.document.save(output)
            if result.checkpoint_path:
                result.checkpoint_path.unlink(missing_ok=True)
        print(f"Gotowe: {output}")
        if result.review_items:
            print(f"Oznaczono do kontroli: {len(result.review_items)} kwestii")
        return 0
    except (OSError, SubtitleFormatError, LanguageDetectionError, TranslationEngineError) as exc:
        print(f"Błąd: {exc}", file=sys.stderr)
        return 1


def _create_engine(name: str):
    if name == "deepl":
        if not os.getenv("DEEPL_API_KEY"):
            raise TranslationEngineError(
                "Ustaw DEEPL_API_KEY w zmiennych środowiskowych. Klucza nie podawaj w komendzie."
            )
        return DeepLEngine()
    print("Wczytywanie lokalnego modelu (pierwsze uruchomienie pobiera około 2 GB)...")
    return M2M100Engine()


def _ask_target() -> str:
    if not sys.stdin.isatty():
        raise TranslationEngineError("Podaj język docelowy przez --target, np. --target pl.")
    value = input("Na jaki język przetłumaczyć? Podaj kod, np. pl: ").strip()
    if not value:
        raise TranslationEngineError("Nie podano języka docelowego.")
    return value


def _console_progress(processed: int, total: int) -> None:
    print(f"\rPrzetłumaczono {processed:,} z {total:,} słów".replace(",", " "), end="", flush=True)


def _review_interactively(result) -> None:
    if not result.review_items:
        print("Nie wykryto kwestii wymagających szczególnej kontroli.")
        return
    print(f"Do weryfikacji: {len(result.review_items)} kwestii. Enter zachowuje tłumaczenie.")
    for item in result.review_items:
        cue = result.document.cues[item.cue_position]
        print("\n" + "─" * 72)
        print(f"Kwestia {item.identifier} | {item.timing}")
        print("Powód: " + "; ".join(reason.value for reason in item.reasons))
        print(f"Oryginał:     {item.source_text}")
        print(f"Tłumaczenie: {cue.text}")
        replacement = input("Nowe tłumaczenie [Enter = zaakceptuj]: ").strip()
        if replacement:
            cue.text = replacement


if __name__ == "__main__":
    raise SystemExit(main())
