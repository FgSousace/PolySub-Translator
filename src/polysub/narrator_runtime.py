"""Isolated Chatterbox runtime used by the optional Polish narrator."""

from __future__ import annotations

import importlib.util
import json
import os
import platform
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .amd_runtime import (
    ROCM_INDEX_URL,
    ROCM_VERSION,
    _embedded_pip_ready,
    _embedded_python_core_ready,
    _install_embedded_python,
    _run_install_command,
    amd_worker_environment,
    install_amd_runtime,
    select_amd_runtime_plan,
)
from .compute_devices import detect_hardware_snapshot

CHATTERBOX_VERSION = "0.1.7"
AMD_TORCHAUDIO_VERSION = "2.11.0"
NARRATOR_RUNTIME_SCHEMA = 2
StatusCallback = Callable[[str], None]


class NarratorRuntimeError(RuntimeError):
    pass


@dataclass(frozen=True)
class NarratorRuntimeSelection:
    python_path: Path
    device: str = "cpu"
    backend: str = "cpu"
    device_index: int | None = None
    label: str = "CPU"


_ACTIVE_RUNTIME: NarratorRuntimeSelection | None = None


def narrator_runtime_directory() -> Path:
    base = os.getenv("LOCALAPPDATA")
    parent = Path(base) / "PolySub Translator" if base else Path.home() / ".polysub-translator"
    return parent / f"narrator-runtime-{CHATTERBOX_VERSION}-cpu"


def narrator_runtime_python() -> Path:
    executable = "python.exe" if os.name == "nt" else "python"
    return narrator_runtime_directory() / executable


def narrator_runtime_manifest(python_path: Path | None = None) -> Path:
    root = Path(python_path).parent if python_path is not None else narrator_runtime_directory()
    return root / "polysub-narrator-runtime.json"


def narrator_worker_script() -> Path:
    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root:
        return Path(frozen_root) / "narrator-worker" / "narrator_worker_entry.py"
    return Path(__file__).resolve().parents[2] / "packaging" / "narrator_worker_entry.py"


def active_narrator_runtime() -> NarratorRuntimeSelection:
    return _ACTIVE_RUNTIME or NarratorRuntimeSelection(
        python_path=narrator_runtime_python(),
        device="cpu",
        backend="cpu",
        label="CPU",
    )


def install_narrator_runtime(status: StatusCallback | None = None) -> Path:
    """Prepare Chatterbox, preferring a supported Radeon through native Windows ROCm."""

    global _ACTIVE_RUNTIME

    status = status or (lambda _message: None)
    if os.name != "nt":
        if importlib.util.find_spec("chatterbox") is not None:
            _ACTIVE_RUNTIME = NarratorRuntimeSelection(
                python_path=Path(sys.executable),
                device="cpu",
                backend="cpu",
                label="CPU",
            )
            return Path(sys.executable)
        raise NarratorRuntimeError(
            "Brakuje biblioteki Chatterbox. W instalacji źródłowej zainstaluj "
            "chatterbox-tts==0.1.7; instalator Windows przygotowuje ją automatycznie."
        )
    if platform.machine().lower() not in {"amd64", "x86_64"}:
        raise NarratorRuntimeError("Polski lektor wymaga 64-bitowego systemu Windows x64.")

    gpu_names = _detected_gpu_names()
    amd_plan = select_amd_runtime_plan(gpu_names)
    if amd_plan is not None:
        status(
            "Wykryto zgodnego Radeona — Chatterbox spróbuje użyć natywnego AMD ROCm "
            "zamiast procesora."
        )
        try:
            amd_status = install_amd_runtime(gpu_names, status)
            python_path = amd_status.python_path
            if python_path is None:
                raise NarratorRuntimeError("Środowisko AMD ROCm nie zwróciło interpretera Python.")
            device_index = amd_status.runtime_indices[0] if amd_status.runtime_indices else 0
            if not (
                _runtime_ready(
                    python_path,
                    backend="rocm",
                    device_index=device_index,
                )
                and _manifest_matches(
                    python_path,
                    backend="rocm",
                    device_index=device_index,
                )
            ):
                _install_amd_narrator_stack(python_path, status)
                _write_manifest(
                    python_path,
                    backend="rocm",
                    device="cuda:0",
                    device_index=device_index,
                )
            if not _runtime_ready(
                python_path,
                backend="rocm",
                device_index=device_index,
            ):
                raise NarratorRuntimeError(
                    "Chatterbox został zainstalowany w środowisku AMD, ale test "
                    "ROCm/GPU nie przeszedł."
                )
            gpu_label = amd_status.devices[0] if amd_status.devices else "AMD Radeon"
            _ACTIVE_RUNTIME = NarratorRuntimeSelection(
                python_path=python_path,
                device="cuda:0",
                backend="rocm",
                device_index=device_index,
                label=f"{gpu_label} • ROCm {amd_status.hip_version or ROCM_VERSION}",
            )
            status(
                f"Chatterbox jest gotowy na GPU: {_ACTIVE_RUNTIME.label}. "
                "W razie błędu konkretnej operacji worker automatycznie przełączy się na CPU."
            )
            return python_path
        except Exception as exc:
            status(
                "Nie udało się przygotować Chatterbox na Radeonie — automatyczne przełączanie "
                f"na CPU. Szczegóły: {str(exc)[-900:]}"
            )

    python_path = narrator_runtime_python()
    if (
        _runtime_ready(python_path, backend="cpu")
        and _manifest_matches(python_path, backend="cpu")
    ):
        _ACTIVE_RUNTIME = NarratorRuntimeSelection(
            python_path=python_path,
            device="cpu",
            backend="cpu",
            label="CPU",
        )
        status("Prywatne środowisko Chatterbox CPU jest gotowe.")
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

        _install_cpu_narrator_stack(python_path, status)
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

    _write_manifest(
        python_path,
        backend="cpu",
        device="cpu",
        device_index=None,
    )
    if not _runtime_ready(python_path, backend="cpu"):
        raise NarratorRuntimeError(
            "Silnik Chatterbox został pobrany, ale nie przeszedł testu importu."
        )
    _ACTIVE_RUNTIME = NarratorRuntimeSelection(
        python_path=python_path,
        device="cpu",
        backend="cpu",
        label="CPU",
    )
    status("Silnik Chatterbox jest gotowy. Synteza lektora użyje CPU.")
    return python_path


def narrator_worker_environment(threads: int | None = None) -> dict[str, str]:
    selection = active_narrator_runtime()
    if selection.backend == "rocm":
        environment = amd_worker_environment(selection.device_index)
        environment["POLYSUB_NARRATOR_DEVICE"] = selection.device
        environment["POLYSUB_NARRATOR_BACKEND"] = "rocm"
    else:
        environment = os.environ.copy()
        environment["CUDA_VISIBLE_DEVICES"] = ""
        environment.pop("HIP_VISIBLE_DEVICES", None)
        environment["POLYSUB_NARRATOR_DEVICE"] = "cpu"
        environment["POLYSUB_NARRATOR_BACKEND"] = "cpu"

    environment["PYTHONUTF8"] = "1"
    environment["PYTHONIOENCODING"] = "utf-8"
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


def _detected_gpu_names() -> tuple[str, ...]:
    try:
        snapshot = detect_hardware_snapshot()
    except Exception:
        return ()
    return tuple(gpu.name for gpu in snapshot.gpus if str(gpu.name).strip())


def _install_cpu_narrator_stack(
    python_path: Path,
    status: StatusCallback,
) -> None:
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
    _install_common_chatterbox_dependencies(python_path, status)
    _install_chatterbox_wheel(python_path, status)


def _install_amd_narrator_stack(
    python_path: Path,
    status: StatusCallback,
) -> None:
    status(f"Instalowanie oficjalnego torchaudio ROCm {ROCM_VERSION} dla Chatterbox…")
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
            "--prefer-binary",
            "--index-url",
            ROCM_INDEX_URL,
            f"torchaudio=={AMD_TORCHAUDIO_VERSION}+rocm{ROCM_VERSION}",
        ],
        status,
        "Nie udało się zainstalować oficjalnego torchaudio ROCm dla lektora.",
    )
    _install_common_chatterbox_dependencies(python_path, status)
    _install_chatterbox_wheel(python_path, status)


def _install_common_chatterbox_dependencies(
    python_path: Path,
    status: StatusCallback,
) -> None:
    status("Instalowanie bibliotek Chatterbox…")
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
            "tiktoken",
        ],
        status,
        "Nie udało się zainstalować bibliotek Chatterbox.",
    )


def _install_chatterbox_wheel(
    python_path: Path,
    status: StatusCallback,
) -> None:
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


def _write_manifest(
    python_path: Path,
    *,
    backend: str,
    device: str,
    device_index: int | None,
) -> None:
    narrator_runtime_manifest(python_path).write_text(
        json.dumps(
            {
                "schema": NARRATOR_RUNTIME_SCHEMA,
                "chatterbox_version": CHATTERBOX_VERSION,
                "backend": backend,
                "device": device,
                "device_index": device_index,
                "rocm_version": ROCM_VERSION if backend == "rocm" else None,
                "torchaudio_version": AMD_TORCHAUDIO_VERSION if backend == "rocm" else "2.6.0",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def _manifest_matches(
    python_path: Path,
    *,
    backend: str,
    device_index: int | None = None,
) -> bool:
    try:
        payload = json.loads(narrator_runtime_manifest(python_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if not (
        payload.get("schema") == NARRATOR_RUNTIME_SCHEMA
        and payload.get("chatterbox_version") == CHATTERBOX_VERSION
        and payload.get("backend") == backend
    ):
        return False
    if backend == "rocm":
        return bool(
            payload.get("rocm_version") == ROCM_VERSION
            and int(payload.get("device_index", -1)) == int(device_index or 0)
        )
    return payload.get("device") == "cpu"


def _runtime_ready(
    python_path: Path,
    *,
    backend: str,
    device_index: int | None = None,
) -> bool:
    if not python_path.is_file():
        return False
    if backend == "rocm":
        environment = amd_worker_environment(device_index)
        code = (
            "import chatterbox,torch,torchaudio;"
            "assert torch.version.hip;"
            "assert torch.cuda.is_available();"
            "x=torch.ones((16,16),device='cuda:0');"
            "y=(x@x)[0,0].item();"
            "assert abs(float(y)-16.0)<0.01"
        )
    else:
        environment = os.environ.copy()
        environment["CUDA_VISIBLE_DEVICES"] = ""
        environment.pop("HIP_VISIBLE_DEVICES", None)
        code = (
            "import chatterbox,torch,torchaudio;"
            "assert torch.__version__.startswith('2.6')"
        )
    environment["PYTHONUTF8"] = "1"
    environment["PYTHONIOENCODING"] = "utf-8"
    try:
        completed = subprocess.run(
            [str(python_path), "-c", code],
            check=False,
            capture_output=True,
            timeout=60 if backend == "rocm" else 45,
            env=environment,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return completed.returncode == 0
