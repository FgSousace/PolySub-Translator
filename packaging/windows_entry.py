from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory


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
        if not cuda_version or not str(cuda_version).startswith("12.6"):
            raise RuntimeError(
                f"Pakiet nie zawiera oczekiwanego środowiska CUDA 12.6: {cuda_version!r}."
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
        from polysub.gui import PolySubApp
        from polysub.subtitle_timing import SubtitleTimingMode

        app = PolySubApp()
        try:
            app.withdraw()
            app.update_idletasks()
            required_widgets = (
                app.stage_progress_bar,
                app.progress_bar,
                app.activity_log,
                app.start_button,
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
                app.burn_button,
            )
            if any(not widget.winfo_manager() for widget in required_widgets):
                raise RuntimeError("Nie wszystkie elementy interfejsu zostały rozmieszczone.")
            if app.start_button.winfo_manager() != "grid":
                raise RuntimeError("Przycisk rozpoczęcia nie jest przypięty do dolnego paska.")
            if len(app.timing_profile_buttons) != 5:
                raise RuntimeError("Panel czasu napisów nie zawiera pięciu profili.")
            if app.timing_var.get() != "recommended":
                raise RuntimeError("Profil Zalecane nie jest domyślnie zaznaczony.")
            recommended = app.timing_profile_buttons[SubtitleTimingMode.RECOMMENDED]
            if recommended.cget("background") != "#eaf3ff":
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
            app._lock_translation_settings(False)
            app._select_timing_mode(SubtitleTimingMode.RECOMMENDED)
        finally:
            app.destroy()
        return

    try:
        from polysub.gui import main as gui_main

        gui_main()
    except Exception as exc:
        try:
            from tkinter import messagebox

            messagebox.showerror(
                "PolySub Translator — błąd uruchamiania",
                f"Nie udało się uruchomić aplikacji:\n\n{exc}",
            )
        finally:
            raise


if __name__ == "__main__":
    main()
