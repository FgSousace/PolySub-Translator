from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .detector import LanguageDetectionError, detect_language
from .engines import DeepLEngine, TranslationEngineError, create_local_engine
from .model_downloads import ModelDownloadError, download_model, model_status
from .models import TranslationMode
from .narrator import ChatterboxNarrator, NarrationError, narrator_video_output_path
from .narrator_models import CHATTERBOX_MULTILINGUAL_V3
from .performance import CPU_USAGE_OPTIONS, DEFAULT_CPU_USAGE
from .service import TranslationOptions, TranslationService
from .subtitle_timing import (
    SubtitleTimingError,
    SubtitleTimingMode,
    SubtitleTimingSettings,
    optimize_subtitle_timing,
)
from .subtitles import SRTDocument, SubtitleFormatError, default_output_path
from .translation_models import DEFAULT_MODEL_ID, MODEL_CATALOG, get_model_spec
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
from .whisper_models import WHISPER_MODEL_CATALOG


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
        help="Pobrany lokalny model AI albo DeepL API",
    )
    parser.add_argument(
        "--local-model",
        choices=tuple(model.id for model in MODEL_CATALOG),
        default=DEFAULT_MODEL_ID,
        help="Identyfikator lokalnego modelu AI; listę pokazuje --list-models",
    )
    parser.add_argument(
        "--list-models",
        action="store_true",
        help="Pokaż katalog 20 opcjonalnych modeli AI i zakończ",
    )
    parser.add_argument(
        "--manage-models",
        action="store_true",
        help="Otwórz graficzny menedżer pobierania modeli AI",
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
        choices=tuple(model.runtime_alias for model in WHISPER_MODEL_CATALOG),
        default="medium",
        help="Pobrany model Whisper używany, gdy film nie ma tekstowych napisów",
    )
    parser.add_argument(
        "--cpu-limit",
        type=int,
        choices=CPU_USAGE_OPTIONS,
        default=DEFAULT_CPU_USAGE,
        help="Maksymalna część logicznych wątków CPU: 25, 50, 75 albo 100%%",
    )
    parser.add_argument(
        "--subtitle-timing",
        choices=tuple(mode.value for mode in SubtitleTimingMode),
        default=SubtitleTimingMode.RECOMMENDED.value,
        help="Czas napisów: original, dynamic, recommended, comfortable albo custom",
    )
    parser.add_argument(
        "--minimum-subtitle-seconds",
        type=float,
        default=1.5,
        help="Własny minimalny czas napisu dla --subtitle-timing custom (0.5–5.0)",
    )
    parser.add_argument(
        "--subtitle-cps",
        type=float,
        default=17.0,
        help="Własna maksymalna prędkość czytania dla trybu custom (8–30 znaków/s)",
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
    video_output_mode.add_argument(
        "--polish-narrator",
        action="store_true",
        help="Utwórz jeden polski głos Chatterbox i zmiksuj go z cichszym oryginałem",
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
    if args.list_models:
        _print_model_catalog()
        return 0
    if args.manage_models:
        from .model_manager_window import run_model_manager

        run_model_manager()
        return 0
    if args.gui or args.input is None:
        from .gui import main as gui_main

        gui_main()
        return 0

    try:
        media_path: Path | None = None
        if args.input.suffix.lower() in VIDEO_EXTENSIONS:
            media_path = args.input
            whisper_model = next(
                model for model in WHISPER_MODEL_CATALOG if model.runtime_alias == args.speech_model
            )
            whisper_status = model_status(whisper_model)
            imported = VideoSubtitleImporter(
                model_size=whisper_status.snapshot_path,
                model_name=whisper_model.display_name,
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
        subtitle_timing = SubtitleTimingSettings.for_mode(
            args.subtitle_timing,
            minimum_duration_seconds=args.minimum_subtitle_seconds,
            max_chars_per_second=args.subtitle_cps,
        )

        context_notes = ""
        if args.context_file:
            context_notes = args.context_file.read_text(encoding="utf-8")
        engine = _create_engine(
            args.engine,
            local_model_id=args.local_model,
            source_language=source,
            target_language=target,
            cpu_usage_limit=args.cpu_limit,
        )
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
            subtitle_timing=subtitle_timing,
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
            timing_result = optimize_subtitle_timing(
                result.document,
                result.timing_settings,
                timing_source=document,
            )
            result.document = timing_result.document
            result.timing_stats = timing_result.stats
            result.document.save(output)
            if result.checkpoint_path:
                result.checkpoint_path.unlink(missing_ok=True)
        print(f"Gotowe: {output}")
        print(result.timing_stats.summary)
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
        elif args.polish_narrator:
            if media_path is None:
                raise NarrationError("Opcja --polish-narrator wymaga filmu wejściowego.")
            if target != "pl":
                raise NarrationError("Polski lektor wymaga języka docelowego --target pl.")
            chatterbox_status = model_status(CHATTERBOX_MULTILINGUAL_V3)
            if chatterbox_status.snapshot_path is None:
                raise NarrationError(
                    "Chatterbox Multilingual V3 nie jest pobrany. Uruchom --manage-models "
                    "i pobierz go w zakładce Lektor."
                )
            video_output = args.video_output or narrator_video_output_path(media_path)
            narrated = ChatterboxNarrator().render(
                media_path,
                output,
                chatterbox_status.snapshot_path,
                output_path=video_output,
                cpu_usage_limit=args.cpu_limit,
                status=print,
                progress=lambda done, total: print(
                    f"\rLektor: {done} z {total} kwestii", end="", flush=True
                ),
            )
            print()
            print(f"Film z polskim lektorem: {narrated.output_path}")
        return 0
    except (
        OSError,
        SubtitleFormatError,
        LanguageDetectionError,
        TranslationEngineError,
        ModelDownloadError,
        SubtitleTimingError,
        VideoBurnError,
        VideoImportError,
        VideoMuxError,
        NarrationError,
    ) as exc:
        print(f"Błąd: {exc}", file=sys.stderr)
        return 1


def _create_engine(
    name: str,
    *,
    local_model_id: str = DEFAULT_MODEL_ID,
    source_language: str,
    target_language: str,
    cpu_usage_limit: int = DEFAULT_CPU_USAGE,
):
    if name == "deepl":
        if not os.getenv("DEEPL_API_KEY"):
            raise TranslationEngineError(
                "Ustaw DEEPL_API_KEY w zmiennych środowiskowych. Klucza nie podawaj w komendzie."
            )
        return DeepLEngine()
    model = get_model_spec(local_model_id)
    if not model.supports_pair(source_language, target_language):
        raise TranslationEngineError(
            f"Model {model.display_name} nie obsługuje pary "
            f"{source_language} → {target_language}."
        )
    current = model_status(model)
    source = current.snapshot_path
    if source is None:
        print(
            f"Pobieranie {model.display_name} (około {model.size_label}; "
            f"licencja {model.license_name})..."
        )
        if model.note:
            print(f"Uwaga: {model.note}")
        source = download_model(model, status=print)
    else:
        print(f"Wczytywanie pobranego modelu {model.display_name}...")
    return create_local_engine(
        model,
        model_source=source,
        cpu_usage_limit=cpu_usage_limit,
        status=print,
    )


def _print_model_catalog() -> None:
    print(f"{len(MODEL_CATALOG)} opcjonalnych modeli tłumaczeniowych:")
    for model in MODEL_CATALOG:
        state = model_status(model).status_label
        print(
            f"{model.rank:02d}. {model.id:<29} {model.display_name:<33} "
            f"{model.size_label:>8}  {model.accuracy_score}/5  "
            f"{model.license_name:<20} {state}"
        )
    print("\nModele rozpoznawania mowy Whisper:")
    for model in WHISPER_MODEL_CATALOG:
        print(
            f"{model.rank:02d}. {model.runtime_alias:<12} {model.display_name:<25} "
            f"{model.size_label:>8}  {model.accuracy_score}/5  {model_status(model).status_label}"
        )
    print("\nPolski lektor:")
    model = CHATTERBOX_MULTILINGUAL_V3
    print(
        f"{model.display_name}  {model.size_label}  "
        f"{model.accuracy_score}/5  {model_status(model).status_label}"
    )


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
