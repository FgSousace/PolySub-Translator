"""Isolated Chatterbox runtime used by the optional Polish narrator."""

from __future__ import annotations

import importlib.util
import json
import os
import platform
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

from .amd_runtime import (
    _embedded_pip_ready,
    _embedded_python_core_ready,
    _install_embedded_python,
    _run_install_command,
)

CHATTERBOX_VERSION = "0.1.7"
NARRATOR_RUNTIME_SCHEMA = 1
StatusCallback = Callable[[str], None]


class NarratorRuntimeError(RuntimeError):
    pass


def narrator_runtime_directory() -> Path:
    base = os.getenv("LOCALAPPDATA")
    parent = Path(base) / "PolySub Translator" if base else Path.home() / ".polysub-translator"
    return parent / f"narrator-runtime-{CHATTERBOX_VERSION}-cpu"


def narrator_runtime_python() -> Path:
    executable = "python.exe" if os.name == "nt" else "python"
    return narrator_runtime_directory() / executable


def narrator_runtime_manifest() -> Path:
    return narrator_runtime_directory() / "polysub-narrator-runtime.json"


def narrator_worker_script() -> Path:
    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root:
        return Path(frozen_root) / "narrator-worker" / "narrator_worker_entry.py"
    return Path(__file__).resolve().parents[2] / "packaging" / "narrator_worker_entry.py"


def install_narrator_runtime(status: StatusCallback | None = None) -> Path:
    status = status or (lambda _message: None)
    if os.name != "nt":
        if importlib.util.find_spec("chatterbox") is not None:
            return Path(sys.executable)
        raise NarratorRuntimeError(
            "Brakuje biblioteki Chatterbox. W instalacji źródłowej zainstaluj "
            "chatterbox-tts==0.1.7; instalator Windows przygotowuje ją automatycznie."
        )
    if platform.machine().lower() not in {"amd64", "x86_64"}:
        raise NarratorRuntimeError("Polski lektor wymaga 64-bitowego systemu Windows x64.")

    python_path = narrator_runtime_python()
    if _runtime_ready(python_path) and _manifest_matches():
        status("Prywatne środowisko Chatterbox jest gotowe.")
        return python_path

    runtime_dir = narrator_runtime_directory()
    runtime_dir.mkdir(parents=True, exist_ok=True)

    def translated_status(message: str) -> None:
        status(message.replace("dla AMD", "dla lektora").replace("AMD", "lektora"))

    try:
        if not _embedded_python_core_ready(python_path):
            status("Przygotowywanie prywatnego Pythona dla polskiego lektora…")
            _install_embedded_python(runtime_dir, translated_status)
        elif not _embedded_pip_ready(python_path):
            _install_embedded_python(runtime_dir, translated_status)

        status("Instalowanie odizolowanego silnika audio Chatterbox (CPU)…")
        _run_install_command(
            [
                str(python_path),
                "-m",
                "pip",
                "--isolated",
                "install",
                "--disable-pip-version-check",
                "--progress-bar",
                "off",
                "--no-cache-dir",
                "--index-url",
                "https://download.pytorch.org/whl/cpu",
                "torch==2.6.0",
                "torchaudio==2.6.0",
            ],
            status,
            "Nie udało się zainstalować odizolowanego PyTorch dla lektora.",
        )
        _run_install_command(
            [
                str(python_path),
                "-m",
                "pip",
                "--isolated",
                "install",
                "--disable-pip-version-check",
                "--progress-bar",
                "off",
                "--no-cache-dir",
                "--prefer-binary",
                "--index-url",
                "https://pypi.org/simple",
                "numpy<2",
                "librosa==0.11.0",
                "s3tokenizer",
                "transformers==5.2.0",
                "diffusers==0.29.0",
                "resemble-perth==1.0.1",
                "conformer==0.3.2",
                "safetensors==0.5.3",
                "spacy-pkuseg",
                "pykakasi==2.3.0",
                "pyloudnorm",
                "omegaconf",
            ],
            status,
            "Nie udało się zainstalować bibliotek Chatterbox.",
        )
        _run_install_command(
            [
                str(python_path),
                "-m",
                "pip",
                "--isolated",
                "install",
                "--disable-pip-version-check",
                "--progress-bar",
                "off",
                "--no-cache-dir",
                "--no-deps",
                f"chatterbox-tts=={CHATTERBOX_VERSION}",
            ],
            status,
            "Nie udało się zainstalować Chatterbox.",
        )
    except Exception as exc:
        detail = str(exc)
        for source, replacement in (
            ("dla AMD", "dla lektora"),
            ("środowisku AMD", "środowisku lektora"),
            ("środowiska AMD", "środowiska lektora"),
            ("składnika AMD", "składnika lektora"),
        ):
            detail = detail.replace(source, replacement)
        raise NarratorRuntimeError(detail) from exc

    narrator_runtime_manifest().write_text(
        json.dumps(
            {
                "schema": NARRATOR_RUNTIME_SCHEMA,
                "chatterbox_version": CHATTERBOX_VERSION,
                "device": "cpu",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    if not _runtime_ready(python_path):
        raise NarratorRuntimeError(
            "Silnik Chatterbox został pobrany, ale nie przeszedł testu importu."
        )
    status("Silnik Chatterbox jest gotowy. Synteza lektora użyje CPU.")
    return python_path


def narrator_worker_environment(threads: int | None = None) -> dict[str, str]:
    environment = os.environ.copy()
    environment["PYTHONUTF8"] = "1"
    environment["PYTHONIOENCODING"] = "utf-8"
    environment["CUDA_VISIBLE_DEVICES"] = ""
    environment["HF_HUB_OFFLINE"] = "1"
    environment["TRANSFORMERS_OFFLINE"] = "1"
    environment["HF_HUB_DISABLE_TELEMETRY"] = "1"
    if threads is not None:
        value = str(max(int(threads), 1))
        for variable in (
            "OMP_NUM_THREADS",
            "MKL_NUM_THREADS",
            "OPENBLAS_NUM_THREADS",
            "NUMEXPR_NUM_THREADS",
        ):
            environment[variable] = value
    return environment


def _manifest_matches() -> bool:
    try:
        payload = json.loads(narrator_runtime_manifest().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return bool(
        payload.get("schema") == NARRATOR_RUNTIME_SCHEMA
        and payload.get("chatterbox_version") == CHATTERBOX_VERSION
    )


def _runtime_ready(python_path: Path) -> bool:
    if not python_path.is_file():
        return False
    try:
        completed = subprocess.run(
            [
                str(python_path),
                "-c",
                "import chatterbox,torch,torchaudio; assert torch.__version__.startswith('2.6')",
            ],
            check=False,
            capture_output=True,
            timeout=45,
            env=narrator_worker_environment(),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return completed.returncode == 0
