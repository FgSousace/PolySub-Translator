from __future__ import annotations

import sys
from pathlib import Path


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

        ffmpeg_executable = Path(imageio_ffmpeg.get_ffmpeg_exe())
        if not ffmpeg_executable.is_file():
            raise RuntimeError(f"Nie znaleziono FFmpeg: {ffmpeg_executable}")

        # Validate the bundled video stack without downloading a speech model.
        _ = (av, ctranslate2, faster_whisper, onnxruntime)
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
