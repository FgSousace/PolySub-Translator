"""Shared diagnostics for the local translation runtime."""

from __future__ import annotations

import os
import sys

MANAGED_AI_RUNTIME_ENV = "POLYSUB_MANAGED_AI_RUNTIME"


def local_ai_dependency_error(component: str, exc: BaseException) -> str:
    """Return actionable guidance without hiding the original import failure."""

    detail = f"{type(exc).__name__}: {exc}"
    managed_runtime = os.getenv(MANAGED_AI_RUNTIME_ENV, "").strip().casefold()
    if managed_runtime == "amd-rocm":
        guidance = (
            "Prywatne środowisko AMD ROCm jest niekompletne. Uruchom ponownie "
            "PolySub — program sprawdzi i automatycznie naprawi biblioteki modeli."
        )
    elif getattr(sys, "frozen", False):
        guidance = (
            "Pakiety powinny być częścią instalacji PolySub. Zainstaluj ponownie "
            "najnowsze wydanie; zwykły pip systemowy nie naprawia aplikacji EXE."
        )
    else:
        guidance = (
            'W instalacji uruchamianej ze źródeł wykonaj w katalogu repozytorium: '
            'python -m pip install -e ".[local]"'
        )
    return f"Nie udało się wczytać {component} ({detail}).\n\n{guidance}"
