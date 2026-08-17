"""PolySub Translator™ by FgSousace.

Required Notice: PolySub Translator™ — Copyright © 2026 FgSousace.
Licensed for noncommercial use only under PolyForm Noncommercial 1.0.0.
"""

from .models import TranslationMode

__all__ = ["TranslationMode"]
__version__ = "0.6.0"


def _install_optional_runtime_hooks() -> None:
    # DirectML is attached lazily to the existing device/video modules.  Keep
    # package import fail-safe so optional GPU support can never prevent PolySub
    # from starting on unsupported systems.
    try:
        from .whisper_directml import install_whisper_directml_hooks

        install_whisper_directml_hooks()
    except Exception:
        pass


_install_optional_runtime_hooks()
