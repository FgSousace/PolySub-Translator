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

        from polysub.video import VideoSubtitleMuxer

        ffmpeg_executable = Path(imageio_ffmpeg.get_ffmpeg_exe())
        if not ffmpeg_executable.is_file():
            raise RuntimeError(f"Nie znaleziono FFmpeg: {ffmpeg_executable}")

        with TemporaryDirectory(prefix="polysub-self-test-") as temporary_directory:
            temporary = Path(temporary_directory)
            source_video = temporary / "source.mp4"
            subtitles = temporary / "source.pl.srt"
            output_video = temporary / "source.pl.subtitled.mp4"
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

        # Validate the bundled video stack without downloading a speech model.
        _ = (av, ctranslate2, faster_whisper, onnxruntime)
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
