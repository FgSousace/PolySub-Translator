from __future__ import annotations

import os
import subprocess
import sys
import traceback
from pathlib import Path
from tempfile import TemporaryDirectory


def _record_self_test_trace(message: str) -> None:
    trace_path = os.getenv("POLYSUB_SELF_TEST_TRACE")
    if not trace_path:
        return
    try:
        with Path(trace_path).open("a", encoding="utf-8") as trace_file:
            trace_file.write(message + "\n")
    except OSError:
        pass


def main() -> None:
    if "--version" in sys.argv:
        from polysub import __version__

        print(__version__)
        return

    if "--model-manager" in sys.argv:
        from polysub.model_manager_window import run_model_manager

        run_model_manager()
        return

    if "--self-test-model-catalog" in sys.argv:
        import huggingface_hub

        from polysub.translation_models import DEFAULT_MODEL_ID, MODEL_CATALOG, get_model_spec

        if len(MODEL_CATALOG) != 20:
            raise RuntimeError(f"Katalog powinien zawierać 20 modeli, ma {len(MODEL_CATALOG)}.")
        if [model.rank for model in MODEL_CATALOG] != list(range(1, 21)):
            raise RuntimeError("Ranking modeli nie zawiera kolejnych pozycji 1–20.")
        if len({model.id for model in MODEL_CATALOG}) != len(MODEL_CATALOG):
            raise RuntimeError("Katalog zawiera powielone identyfikatory modeli.")
        if get_model_spec(DEFAULT_MODEL_ID).repo_id != "facebook/m2m100_418M":
            raise RuntimeError("Domyślny model nie zachowuje zgodności z M2M100 418M.")
        _ = huggingface_hub
        return

    if "--self-test-branding" in sys.argv:
        from polysub.branding import AUTHOR, PRODUCT_NAME, REQUIRED_NOTICE

        if PRODUCT_NAME != "PolySub Translator™" or AUTHOR != "fgSousace":
            raise RuntimeError("Metadane marki PolySub Translator™ są nieprawidłowe.")
        if not REQUIRED_NOTICE.startswith("Required Notice:"):
            raise RuntimeError("Brakuje wymaganego oznaczenia licencyjnego.")
        roots = [
            Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1])),
            Path(__file__).resolve().parents[1],
        ]
        for filename in ("LICENSE", "NOTICE.txt"):
            candidate = next(
                (root / filename for root in roots if (root / filename).is_file()),
                None,
            )
            if candidate is None:
                raise RuntimeError(f"W pakiecie brakuje pliku {filename}.")
            if "fgSousace" not in candidate.read_text(encoding="utf-8"):
                raise RuntimeError(f"Plik {filename} nie zawiera oznaczenia autora.")
        return

    if "--self-test-amd-runtime" in sys.argv:
        from polysub.amd_runtime import (
            EMBEDDED_PYTHON_URL,
            ROCM_INDEX_URL,
            ROCM_VERSION,
            amd_worker_script,
            select_amd_runtime_plan,
        )

        plan = select_amd_runtime_plan(("AMD Radeon RX 9070 XT",))
        if plan is None or plan.target != "gfx1201":
            raise RuntimeError("Automat AMD nie dobrał gfx1201 dla Radeona RX 9070 XT.")
        if ROCM_VERSION != "7.14.0" or "repo.amd.com" not in ROCM_INDEX_URL:
            raise RuntimeError("Automat AMD nie wskazuje oficjalnego ROCm 7.14.0.")
        if "python.org" not in EMBEDDED_PYTHON_URL:
            raise RuntimeError("Automat AMD nie zawiera własnego oficjalnego środowiska Python.")
        if "[device-gfx1201]" not in plan.torch_requirement:
            raise RuntimeError("PyTorch AMD nie został ograniczony do architektury RX 9070 XT.")
        worker = amd_worker_script()
        if not worker.is_file():
            raise RuntimeError(f"W pakiecie brakuje workera AMD: {worker}")
        compile(worker.read_text(encoding="utf-8"), str(worker), "exec")
        return

    if "--self-test-subtitle-timing" in sys.argv:
        from polysub.subtitle_timing import (
            SubtitleTimingSettings,
            optimize_subtitle_timing,
        )
        from polysub.subtitles import SRTDocument

        source = SRTDocument.parse(
            "1\n"
            "00:00:00,000 --> 00:00:01,200\n"
            "To jest celowo dłuższa pierwsza wypowiedź.\n\n"
            "2\n"
            "00:00:01,000 --> 00:00:01,500\n"
            "Nowa postać.\n\n"
            "3\n"
            "00:00:03,000 --> 00:00:03,500\n"
            "Spokojny koniec.\n"
        )
        result = optimize_subtitle_timing(
            source,
            SubtitleTimingSettings.recommended(),
        )
        first, second, third = result.document.cues
        if first.timing != "00:00:00,000 --> 00:00:00,900":
            raise RuntimeError("Poprzedni napis nachodzi na początek nowej wypowiedzi.")
        if not second.timing.startswith("00:00:01,000 -->"):
            raise RuntimeError("Program zmienił początek drugiej wypowiedzi.")
        if not third.timing.startswith("00:00:03,000 -->"):
            raise RuntimeError("Program zmienił początek trzeciej wypowiedzi.")
        if result.stats.adjusted_cues < 2:
            raise RuntimeError("Profil zalecany nie dopasował czasu krótkich napisów.")

        profile_source = SRTDocument.parse(
            "1\n"
            "00:00:00,000 --> 00:00:00,700\n"
            "Krótko.\n\n"
            "2\n"
            "00:00:04,000 --> 00:00:05,000\n"
            "Następna kwestia.\n"
        )
        expected_endings = (
            (SubtitleTimingSettings.dynamic(), "00:00:01,000"),
            (SubtitleTimingSettings.recommended(), "00:00:01,500"),
            (SubtitleTimingSettings.comfortable(), "00:00:02,000"),
        )
        for settings, expected_ending in expected_endings:
            profile_result = optimize_subtitle_timing(profile_source, settings)
            if not profile_result.document.cues[0].timing.endswith(expected_ending):
                raise RuntimeError(
                    f"Profil {settings.mode.value} ma nieprawidłowy czas wyświetlania."
                )
        return

    if "--self-test-video" in sys.argv:
        import av
        import ctranslate2
        import faster_whisper
        import imageio_ffmpeg
        import onnxruntime

        from polysub.video import VideoSubtitleBurner, VideoSubtitleMuxer

        ffmpeg_executable = Path(imageio_ffmpeg.get_ffmpeg_exe())
        if not ffmpeg_executable.is_file():
            raise RuntimeError(f"Nie znaleziono FFmpeg: {ffmpeg_executable}")

        with TemporaryDirectory(prefix="polysub-self-test-") as temporary_directory:
            temporary = Path(temporary_directory)
            source_video = temporary / "source.mp4"
            subtitles = temporary / "source.pl.srt"
            output_video = temporary / "source.pl.subtitled.mp4"
            burned_video = temporary / "source.pl.burned.mp4"
            subtitles.write_text(
                "1\n00:00:00,000 --> 00:00:00,800\nTest napisów.\n",
                encoding="utf-8",
            )
            subprocess.run(
                [
                    str(ffmpeg_executable),
                    "-nostdin",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-y",
                    "-f",
                    "lavfi",
                    "-i",
                    "color=c=black:s=160x90:d=1",
                    "-c:v",
                    "mpeg4",
                    "-an",
                    str(source_video),
                ],
                check=True,
                capture_output=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            result = VideoSubtitleMuxer(
                ffmpeg_executable=str(ffmpeg_executable)
            ).mux(
                source_video,
                subtitles,
                target_language="pl",
                output_path=output_video,
                subtitle_title="Polski",
            )
            if not result.is_file() or result.stat().st_size == 0:
                raise RuntimeError("Test szybkiego dołączania napisów nie utworzył filmu.")
            burned = VideoSubtitleBurner(
                ffmpeg_executable=str(ffmpeg_executable),
            ).burn(
                source_video,
                subtitles,
                target_language="pl",
                output_path=burned_video,
                preferred_vendor="CPU",
            )
            if not burned.output_path.is_file() or burned.output_path.stat().st_size == 0:
                raise RuntimeError("Test wypalania napisów nie utworzył filmu.")

        # Validate the bundled video stack without downloading a speech model.
        _ = (av, ctranslate2, faster_whisper, onnxruntime)
        return

    if "--self-test-performance" in sys.argv:
        import torch

        from polysub.performance import configure_torch_threads, cpu_allocation

        allocation = cpu_allocation(100)
        configure_torch_threads(torch, allocation)
        if torch.get_num_threads() != allocation.threads:
            raise RuntimeError(
                "PyTorch nie zastosował pełnej liczby wybranych wątków procesora."
            )
        return

    if "--self-test-nvidia-runtime" in sys.argv:
        import ctranslate2
        import torch

        cuda_version = getattr(torch.version, "cuda", None)
        if not cuda_version or not str(cuda_version).startswith("12.8"):
            raise RuntimeError(
                f"Pakiet nie zawiera oczekiwanego środowiska CUDA 12.8: {cuda_version!r}."
            )
        torch_lib = Path(torch.__file__).resolve().parent / "lib"
        required_libraries = ("cublas64_12.dll", "cudnn64_9.dll")
        missing = [name for name in required_libraries if not (torch_lib / name).is_file()]
        if missing:
            raise RuntimeError(
                "W pakiecie NVIDIA brakuje bibliotek: " + ", ".join(missing)
            )
        _ = ctranslate2
        return

    if "--self-test-hardware" in sys.argv:
        from polysub.compute_devices import (
            AUTO_DEVICE_ID,
            detect_compute_devices,
            resolve_compute_device,
        )

        devices = detect_compute_devices()
        if not any(device.kind == "cpu" for device in devices):
            raise RuntimeError("Wykrywanie sprzętu nie znalazło procesora.")
        if len({device.id for device in devices}) != len(devices):
            raise RuntimeError("Wykrywanie sprzętu zwróciło powielone identyfikatory.")
        for task in ("translation", "transcription"):
            resolution = resolve_compute_device(devices, AUTO_DEVICE_ID, task)
            if not resolution.runtime_device:
                raise RuntimeError(f"Tryb Auto nie wybrał urządzenia dla zadania {task}.")
        return

    if "--self-test-gui" in sys.argv:
        _record_self_test_trace("GUI: importowanie modułów")
        from polysub.appearance import (
            CLASSIC_INTERFACE,
            MODERN_INTERFACE,
            AppearanceSettings,
            AppearanceSettingsStore,
        )
        from polysub.gui import MODEL_LABEL_TO_ID, MODEL_NOT_READY_LABEL, PolySubApp
        from polysub.model_downloads import model_status
        from polysub.models import TranslationMode
        from polysub.subtitle_timing import SubtitleTimingMode
        from polysub.translation_models import get_model_spec

        _record_self_test_trace("GUI: tworzenie aplikacji")
        with TemporaryDirectory(prefix="polysub-appearance-test-") as temporary_directory:
            store = AppearanceSettingsStore(Path(temporary_directory) / "appearance.json")
            app = PolySubApp(
                appearance_settings=AppearanceSettings(
                    interface=MODERN_INTERFACE,
                    theme="midnight",
                ),
                appearance_store=store,
                schedule_background_tasks=False,
            )
            _record_self_test_trace("GUI: aplikacja utworzona")
            try:
                app.withdraw()
                app.update_idletasks()
                _record_self_test_trace("GUI: pierwsze rozmieszczenie zakończone")
                required_widgets = (
                    app.stage_progress_bar,
                    app.progress_bar,
                    app.activity_log,
                    app.start_button,
                    app.cancel_translation_button,
                    app.check_update_button,
                    app.device_combo,
                    app.refresh_devices_button,
                    app.cpu_usage_combo,
                    *app.timing_profile_buttons.values(),
                    app.minimum_duration_spinbox,
                    app.max_cps_spinbox,
                    app.timing_status_label,
                    app.model_combo,
                    app.model_manager_button,
                    app.automatic_mode_checkbox,
                    app.review_mode_checkbox,
                    app.amd_runtime_status_label,
                    app.burn_button,
                    app.about_button,
                    app.appearance_interface_combo,
                    app.appearance_theme_combo,
                )
                if any(not widget.winfo_manager() for widget in required_widgets):
                    raise RuntimeError("Nie wszystkie elementy interfejsu zostały rozmieszczone.")
                if hasattr(app, "amd_runtime_button"):
                    raise RuntimeError("GUI nadal zawiera ręczny przycisk konfiguracji AMD.")
                if "automaty" not in app.amd_runtime_status_var.get().casefold():
                    raise RuntimeError("GUI nie opisuje automatycznego przygotowania AMD.")
                _record_self_test_trace("GUI: wymagane kontrolki są rozmieszczone")
                if app.start_button.winfo_manager() != "grid":
                    raise RuntimeError("Przycisk rozpoczęcia nie jest przypięty do dolnego paska.")
                if "Wyszukaj napisy" not in app.start_button.cget("text"):
                    raise RuntimeError(
                        "Pierwszy krok GUI nie prowadzi do wyboru napisów lub filmu."
                    )
                if app.mode_var.get():
                    raise RuntimeError("Tryb tłumaczenia został zaznaczony bez zgody użytkownika.")
                app.automatic_mode_checked.set(True)
                app._select_translation_mode(TranslationMode.AUTOMATIC)
                if (
                    app.mode_var.get() != TranslationMode.AUTOMATIC.value
                    or not app.automatic_mode_checked.get()
                    or app.review_mode_checked.get()
                ):
                    raise RuntimeError("Wymagane checkboxy trybu nie są wzajemnie wykluczające.")
                for label in app.model_combo.cget("values"):
                    if label == MODEL_NOT_READY_LABEL:
                        continue
                    model_id = MODEL_LABEL_TO_ID.get(label)
                    if model_id is None or not model_status(get_model_spec(model_id)).installed:
                        raise RuntimeError("Główna lista pokazała model, który nie jest gotowy.")
                _record_self_test_trace("GUI: tryb i lista modeli są poprawne")
                if len(app._modern_nav_buttons) != 5:
                    raise RuntimeError("Nowy interfejs nie zawiera pięciu skrótów nawigacji.")
                if set(app._content_sections) != {
                    "start",
                    "translation",
                    "models",
                    "film",
                    "settings",
                }:
                    raise RuntimeError("Nowa nawigacja nie prowadzi do wszystkich sekcji.")
                if len(app.timing_profile_buttons) != 5:
                    raise RuntimeError("Panel czasu napisów nie zawiera pięciu profili.")
                if app.timing_var.get() != "recommended":
                    raise RuntimeError("Profil Zalecane nie jest domyślnie zaznaczony.")
                recommended = app.timing_profile_buttons[SubtitleTimingMode.RECOMMENDED]
                if recommended.cget("background") != app.theme.selected:
                    raise RuntimeError("Domyślny profil Zalecane nie jest wizualnie wyróżniony.")
                app._select_timing_mode(SubtitleTimingMode.CUSTOM)
                app.update_idletasks()
                if app.timing_custom_frame.winfo_manager() != "grid":
                    raise RuntimeError("Pola profilu Własne nie pojawiły się po wybraniu kafelka.")
                app._lock_translation_settings(True)
                if any(
                    button.cget("state") != "disabled"
                    for button in app.timing_profile_buttons.values()
                ):
                    raise RuntimeError("Kafelki czasu nie zostały zablokowane podczas pracy.")
                if any(
                    not checkbox.instate(("disabled",))
                    for checkbox in (
                        app.automatic_mode_checkbox,
                        app.review_mode_checkbox,
                    )
                ):
                    raise RuntimeError("Tryb tłumaczenia nie został zablokowany podczas pracy.")
                app._lock_translation_settings(False)
                app._select_timing_mode(SubtitleTimingMode.RECOMMENDED)
                _record_self_test_trace("GUI: profile czasu i blokady są poprawne")

                app.target_var.set("English (en)")
                app.context_text.insert("1.0", "Zachowaj luźny ton.")
                app._apply_appearance(MODERN_INTERFACE, "oled")
                _record_self_test_trace("GUI: motyw OLED zastosowany")
                if app.theme.id != "oled" or app.cget("background") != "#000000":
                    raise RuntimeError("Motyw OLED nie został zastosowany do aplikacji.")

                app._apply_appearance(CLASSIC_INTERFACE, "oled")
                _record_self_test_trace("GUI: klasyczny interfejs zbudowany")
                app.update_idletasks()
                _record_self_test_trace("GUI: klasyczny interfejs rozmieszczony")
                if app._modern_nav_buttons:
                    raise RuntimeError("Klasyczny interfejs nadal pokazuje nowy panel boczny.")
                if app.target_var.get() != "English (en)":
                    raise RuntimeError("Przełączenie interfejsu zgubiło ustawienia formularza.")
                if app.context_text.get("1.0", "end-1c") != "Zachowaj luźny ton.":
                    raise RuntimeError("Przełączenie interfejsu zgubiło kontekst tłumaczenia.")
                if store.load() != AppearanceSettings(
                    interface=CLASSIC_INTERFACE,
                    theme="oled",
                ):
                    raise RuntimeError("Wybrany wygląd nie został zapamiętany.")
                _record_self_test_trace("GUI: wszystkie asercje zakończone")
            finally:
                _record_self_test_trace("GUI: zamykanie aplikacji")
                app.destroy()
                _record_self_test_trace("GUI: aplikacja zamknięta")
        return

    try:
        from polysub.gui import main as gui_main

        gui_main()
    except Exception as exc:
        try:
            from tkinter import messagebox

            messagebox.showerror(
                "PolySub Translator™ — błąd uruchamiania",
                f"Nie udało się uruchomić aplikacji:\n\n{exc}",
            )
        finally:
            raise


if __name__ == "__main__":
    try:
        main()
    except Exception:
        is_self_test = "--version" in sys.argv or any(
            argument.startswith("--self-test-") for argument in sys.argv[1:]
        )
        if not is_self_test:
            raise
        details = traceback.format_exc()
        trace_path = os.getenv("POLYSUB_SELF_TEST_TRACE")
        if trace_path:
            try:
                with Path(trace_path).open("a", encoding="utf-8") as trace_file:
                    trace_file.write("BŁĄD:\n" + details)
            except OSError:
                pass
        try:
            print(details, file=sys.stderr)
        except OSError:
            pass
        raise SystemExit(1) from None
