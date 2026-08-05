"""Expose bundled CUDA and cuDNN DLLs before torch or CTranslate2 is imported."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _add_bundled_dll_directories() -> None:
    bundle_root = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    candidates = (
        bundle_root / "torch" / "lib",
        Path(sys.executable).parent / "_internal" / "torch" / "lib",
        Path(sys.executable).parent / "torch" / "lib",
    )
    handles = getattr(sys, "_polysub_dll_directory_handles", [])
    for candidate in candidates:
        if not candidate.is_dir():
            continue
        value = str(candidate)
        current_path = os.environ.get("PATH", "")
        if value not in current_path.split(os.pathsep):
            os.environ["PATH"] = value + os.pathsep + current_path
        add_dll_directory = getattr(os, "add_dll_directory", None)
        if callable(add_dll_directory):
            try:
                handles.append(add_dll_directory(value))
            except OSError:
                pass
    sys._polysub_dll_directory_handles = handles


_add_bundled_dll_directories()
