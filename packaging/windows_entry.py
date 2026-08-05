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
                app.burn_button,
            )
            if any(not widget.winfo_manager() for widget in required_widgets):
                raise RuntimeError("Nie wszystkie elementy interfejsu zostały rozmieszczone.")
            if app.start_button.winfo_manager() != "grid":
                raise RuntimeError("Przycisk rozpoczęcia nie jest przypięty do dolnego paska.")
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
