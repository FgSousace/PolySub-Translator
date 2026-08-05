from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .detector import LanguageDetectionError, detect_language
from .engines import DeepLEngine, M2M100Engine, TranslationEngineError
from .models import TranslationMode
from .performance import CPU_USAGE_OPTIONS, DEFAULT_CPU_USAGE
from .service import TranslationOptions, TranslationService
from .subtitles import SRTDocument, SubtitleFormatError, default_output_path
from .video import (
    VIDEO_EXTENSIONS,
    VideoBurnError,
    VideoImportError,
    VideoMuxError,
    VideoSubtitleBurner,
    VideoSubtitleImporter,
    VideoSubtitleMuxer,
    burned_video_output_path,
    fast_mux_output_path,
    format_media_duration,
    translated_video_subtitle_path,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="polysub",
        description="Automatycznie wykrywa język i tłumaczy napisy SRT albo film.",
    )
    parser.add_argument("input", nargs="?", type=Path, help="Plik wejściowy .srt lub wideo")
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
    parser.add_argument(
        "--speech-model",
        choices=("small", "medium"),
        default="medium",
        help="Model Whisper używany tylko wtedy, gdy film nie ma tekstowych napisów",
    )
    parser.add_argument(
        "--cpu-limit",
        type=int,
        choices=CPU_USAGE_OPTIONS,
        default=DEFAULT_CPU_USAGE,
        help="Maksymalna część logicznych wątków CPU: 25, 50, 75 albo 100%%",
    )
    video_output_mode = parser.add_mutually_exclusive_group()
    video_output_mode.add_argument(
        "--attach-to-video",
        action="store_true",
        help="Po tłumaczeniu szybko dołącz SRT do filmu bez ponownego kodowania",
    )
    video_output_mode.add_argument(
        "--burn-into-video",
        action="store_true",
        help="Wypal napisy na obrazie filmu, próbując najpierw akceleracji sprzętowej",
    )
    parser.add_argument(
        "--video-output",
        type=Path,
        help="Opcjonalna ścieżka filmu .mp4 lub .mkv z gotowymi napisami",
    )
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
        media_path: Path | None = None
        if args.input.suffix.lower() in VIDEO_EXTENSIONS:
            media_path = args.input
            imported = VideoSubtitleImporter(
                model_size=args.speech_model,
                cpu_usage_limit=args.cpu_limit,
            ).import_video(
                args.input,
                status=lambda message: print(message),
                progress=_console_media_progress,
            )
            print()
            document = imported.document
            print(f"Napisy robocze: {imported.subtitle_path}")
        else:
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
        engine = _create_engine(args.engine, cpu_usage_limit=args.cpu_limit)
        mode = TranslationMode(args.mode)
        output = args.output or (
            translated_video_subtitle_path(media_path, target)
            if media_path is not None
            else default_output_path(args.input, target)
        )
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
        if args.attach_to_video:
            if media_path is None:
                raise VideoMuxError("Opcja --attach-to-video wymaga filmu jako pliku wejściowego.")
            video_output = args.video_output or fast_mux_output_path(media_path, target)
            print("Dołączanie napisów bez ponownego kodowania obrazu i dźwięku...")
            attached = VideoSubtitleMuxer().mux(
                media_path,
                output,
                target_language=target,
                output_path=video_output,
            )
            print(f"Film z napisami: {attached}")
        elif args.burn_into_video:
            if media_path is None:
                raise VideoBurnError("Opcja --burn-into-video wymaga filmu wejściowego.")
            video_output = args.video_output or burned_video_output_path(media_path, target)
            print("Wypalanie napisów na obrazie filmu...")
            burned = VideoSubtitleBurner(cpu_usage_limit=args.cpu_limit).burn(
                media_path,
                output,
                target_language=target,
                output_path=video_output,
                status=print,
                progress=_console_media_progress,
            )
            print()
            print(f"Film z trwałymi napisami: {burned.output_path} ({burned.encoder})")
        return 0
    except (
        OSError,
        SubtitleFormatError,
        LanguageDetectionError,
        TranslationEngineError,
        VideoBurnError,
        VideoImportError,
        VideoMuxError,
    ) as exc:
        print(f"Błąd: {exc}", file=sys.stderr)
        return 1


def _create_engine(name: str, *, cpu_usage_limit: int = DEFAULT_CPU_USAGE):
    if name == "deepl":
        if not os.getenv("DEEPL_API_KEY"):
            raise TranslationEngineError(
                "Ustaw DEEPL_API_KEY w zmiennych środowiskowych. Klucza nie podawaj w komendzie."
            )
        return DeepLEngine()
    print("Wczytywanie lokalnego modelu (pierwsze uruchomienie pobiera około 2 GB)...")
    return M2M100Engine(cpu_usage_limit=cpu_usage_limit)


def _ask_target() -> str:
    if not sys.stdin.isatty():
        raise TranslationEngineError("Podaj język docelowy przez --target, np. --target pl.")
    value = input("Na jaki język przetłumaczyć? Podaj kod, np. pl: ").strip()
    if not value:
        raise TranslationEngineError("Nie podano języka docelowego.")
    return value


def _console_progress(processed: int, total: int) -> None:
    print(f"\rPrzetłumaczono {processed:,} z {total:,} słów".replace(",", " "), end="", flush=True)


def _console_media_progress(processed: float, total: float) -> None:
    print(
        "\rRozpoznano "
        f"{format_media_duration(processed)} z {format_media_duration(total)} nagrania",
        end="",
        flush=True,
    )


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
