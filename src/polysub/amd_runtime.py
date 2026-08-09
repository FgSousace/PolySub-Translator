"""Optional, isolated AMD ROCm runtime for native Windows acceleration.

The main executable ships a CUDA build of PyTorch for NVIDIA. AMD's Windows
ROCm build is mutually exclusive with that wheel, so it is installed into a
separate Python 3.12 virtual environment and used through a worker process.

Required Notice: PolySub Translator™ — Copyright © 2026 fgSousace.
Licensed for noncommercial use only under PolyForm Noncommercial 1.0.0.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from pathlib import Path

from .compute_devices import ComputeDevice

ROCM_VERSION = "7.2.1"
ROCM_DRIVER_VERSION = "26.2.2"
AMD_RUNTIME_TARGET_PREFIX = "rocm-worker:"
AMD_ROCM_GUIDE_URL = (
    "https://rocm.docs.amd.com/projects/radeon-ryzen/en/latest/docs/install/"
    "installrad/windows/install-pytorch.html"
)

OFFICIALLY_SUPPORTED_WINDOWS_GPUS = (
    "Radeon RX 9070",
    "Radeon RX 9070 XT",
    "Radeon AI PRO R9700",
    "Radeon RX 9060 XT",
    "Radeon RX 7900 XTX",
    "Radeon PRO W7900",
    "Radeon PRO W7900 Dual Slot",
    "Radeon RX 7700",
)

_ROCM_BASE = f"https://repo.radeon.com/rocm/windows/rocm-rel-{ROCM_VERSION}"
ROCM_SDK_URLS = (
    f"{_ROCM_BASE}/rocm_sdk_core-{ROCM_VERSION}-py3-none-win_amd64.whl",
    f"{_ROCM_BASE}/rocm_sdk_devel-{ROCM_VERSION}-py3-none-win_amd64.whl",
    f"{_ROCM_BASE}/rocm_sdk_libraries_custom-{ROCM_VERSION}-py3-none-win_amd64.whl",
    f"{_ROCM_BASE}/rocm-{ROCM_VERSION}.tar.gz",
)
ROCM_TORCH_URLS = (
    f"{_ROCM_BASE}/torch-2.9.1%2Brocm{ROCM_VERSION}-cp312-cp312-win_amd64.whl",
    f"{_ROCM_BASE}/torchaudio-2.9.1%2Brocm{ROCM_VERSION}-cp312-cp312-win_amd64.whl",
    f"{_ROCM_BASE}/torchvision-0.24.1%2Brocm{ROCM_VERSION}-cp312-cp312-win_amd64.whl",
)

StatusCallback = Callable[[str], None]


class AmdRuntimeError(RuntimeError):
    pass


@dataclass(frozen=True)
class AmdRuntimeStatus:
    installed: bool
    ready: bool
    python_path: Path | None = None
    hip_version: str | None = None
    devices: tuple[str, ...] = ()
    message: str = ""


def amd_runtime_directory() -> Path:
    base = os.getenv("LOCALAPPDATA")
    if base:
        return Path(base) / "PolySub Translator" / "amd-rocm-runtime"
    return Path.home() / ".polysub-translator" / "amd-rocm-runtime"


def amd_runtime_python() -> Path:
    scripts = "Scripts" if os.name == "nt" else "bin"
    executable = "python.exe" if os.name == "nt" else "python"
    return amd_runtime_directory() / scripts / executable


def probe_amd_runtime(*, timeout: float = 25.0) -> AmdRuntimeStatus:
    python_path = amd_runtime_python()
    if not python_path.is_file():
        return AmdRuntimeStatus(
            installed=False,
            ready=False,
            message="Opcjonalne środowisko AMD ROCm nie jest jeszcze zainstalowane.",
        )
    probe = (
        "import json, torch; "
        "count=torch.cuda.device_count() if torch.cuda.is_available() else 0; "
        "print(json.dumps({'available': bool(torch.cuda.is_available()), "
        "'hip': str(torch.version.hip or ''), "
        "'devices': [torch.cuda.get_device_name(i) for i in range(count)]}))"
    )
    try:
        completed = subprocess.run(
            [str(python_path), "-c", probe],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return AmdRuntimeStatus(
            installed=True,
            ready=False,
            python_path=python_path,
            message=f"Nie udało się sprawdzić środowiska AMD ROCm: {exc}",
        )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()[-700:]
        return AmdRuntimeStatus(
            installed=True,
            ready=False,
            python_path=python_path,
            message=f"Środowisko AMD ROCm nie przeszło testu: {detail or 'brak danych'}",
        )
    try:
        payload = json.loads(completed.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError, TypeError) as exc:
        return AmdRuntimeStatus(
            installed=True,
            ready=False,
            python_path=python_path,
            message=f"Środowisko AMD zwróciło nieprawidłowy wynik: {exc}",
        )
    hip = str(payload.get("hip") or "")
    devices = tuple(str(name) for name in payload.get("devices") or ())
    ready = bool(payload.get("available") and hip and devices)
    return AmdRuntimeStatus(
        installed=True,
        ready=ready,
        python_path=python_path,
        hip_version=hip or None,
        devices=devices,
        message=(
            f"AMD ROCm {hip} gotowe: {', '.join(devices)}."
            if ready
            else "PyTorch ROCm jest zainstalowany, ale nie wykrył zgodnej karty AMD."
        ),
    )


def attach_amd_runtime_devices(
    devices: Sequence[ComputeDevice],
    runtime: AmdRuntimeStatus,
) -> list[ComputeDevice]:
    """Attach external ROCm targets to physical Radeon entries without faking support."""

    result = list(devices)
    if not runtime.ready:
        return result
    available_names = list(runtime.devices)
    used_indices: set[int] = set()
    for position, device in enumerate(result):
        if device.kind != "gpu" or device.vendor != "AMD":
            continue
        runtime_index = _matching_device_index(
            device.name,
            available_names,
            excluded=used_indices,
        )
        if runtime_index is None:
            continue
        used_indices.add(runtime_index)
        backend = f"ROCm {runtime.hip_version or ROCM_VERSION} (osobny proces)"
        result[position] = replace(
            device,
            backend=backend,
            translation_target=f"{AMD_RUNTIME_TARGET_PREFIX}{runtime_index}",
        )
    return result


def install_amd_runtime(status: StatusCallback | None = None) -> AmdRuntimeStatus:
    """Install AMD's official Windows wheels into an isolated user environment."""

    if os.name != "nt":
        raise AmdRuntimeError("Automatyczna instalacja AMD ROCm jest dostępna tylko w Windows 11.")
    status = status or (lambda _message: None)
    base_python = _find_python_312()
    if base_python is None:
        raise AmdRuntimeError(
            "Nie znaleziono 64-bitowego Pythona 3.12. Zainstaluj Python 3.12, "
            "uruchom ponownie PolySub i spróbuj jeszcze raz."
        )
    runtime_dir = amd_runtime_directory()
    runtime_dir.parent.mkdir(parents=True, exist_ok=True)
    python_path = amd_runtime_python()
    if not python_path.is_file():
        status("Tworzenie odizolowanego środowiska Python 3.12 dla AMD…")
        _run_install_command(
            [str(base_python), "-m", "venv", str(runtime_dir)],
            status,
            "Nie udało się utworzyć środowiska AMD.",
        )
    status("Aktualizowanie instalatora pakietów AMD…")
    _run_install_command(
        [str(python_path), "-m", "pip", "install", "--upgrade", "pip", "wheel"],
        status,
        "Nie udało się zaktualizować pip w środowisku AMD.",
    )
    status(f"Pobieranie oficjalnego AMD ROCm {ROCM_VERSION} — kilka dużych plików…")
    _run_install_command(
        [str(python_path), "-m", "pip", "install", "--no-cache-dir", *ROCM_SDK_URLS],
        status,
        "Nie udało się zainstalować bibliotek AMD ROCm.",
    )
    status("Pobieranie oficjalnego PyTorch dla Radeonów…")
    _run_install_command(
        [str(python_path), "-m", "pip", "install", "--no-cache-dir", *ROCM_TORCH_URLS],
        status,
        "Nie udało się zainstalować PyTorch ROCm.",
    )
    status("Instalowanie bibliotek modeli tłumaczeniowych w środowisku AMD…")
    _run_install_command(
        [
            str(python_path),
            "-m",
            "pip",
            "install",
            "--no-cache-dir",
            "numpy<2",
            "transformers>=4.55.5,<5",
            "huggingface-hub>=0.25,<2",
            "tokenizers>=0.21,<1",
            "safetensors>=0.4,<1",
            "sentencepiece>=0.2,<1",
            "requests>=2.31,<3",
        ],
        status,
        "Nie udało się zainstalować bibliotek modeli w środowisku AMD.",
    )
    status("Testowanie karty Radeon i środowiska ROCm…")
    result = probe_amd_runtime(timeout=90.0)
    if not result.ready:
        raise AmdRuntimeError(result.message)
    return result


def amd_worker_script() -> Path:
    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root:
        return Path(frozen_root) / "amd-worker" / "amd_worker_entry.py"
    return Path(__file__).resolve().parents[2] / "packaging" / "amd_worker_entry.py"


def amd_worker_pythonpath() -> Path:
    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root:
        return Path(frozen_root) / "amd-worker" / "src"
    return Path(__file__).resolve().parents[1]


def _find_python_312() -> Path | None:
    commands = (
        ["py", "-3.12"],
        ["python3.12"],
        ["python"],
    )
    check = "import json,sys; print(json.dumps({'exe':sys.executable,'v':sys.version_info[:2]}))"
    for prefix in commands:
        try:
            completed = subprocess.run(
                [*prefix, "-c", check],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=15,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            payload = json.loads(completed.stdout.strip().splitlines()[-1])
            executable = Path(payload["exe"])
            if (
                completed.returncode == 0
                and tuple(payload["v"]) == (3, 12)
                and executable.is_file()
            ):
                return executable
        except (OSError, subprocess.SubprocessError, ValueError, KeyError, IndexError):
            continue
    return None


def _run_install_command(
    command: list[str],
    status: StatusCallback,
    failure_message: str,
) -> None:
    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except OSError as exc:
        raise AmdRuntimeError(f"{failure_message} {exc}") from exc
    recent: list[str] = []
    assert process.stdout is not None
    for line in process.stdout:
        cleaned = line.strip()
        if not cleaned:
            continue
        recent.append(cleaned)
        recent = recent[-12:]
        lowered = cleaned.lower()
        if any(marker in lowered for marker in ("downloading", "installing", "successfully")):
            status(cleaned[:240])
    return_code = process.wait()
    if return_code != 0:
        detail = "\n".join(recent)[-1200:]
        raise AmdRuntimeError(f"{failure_message}\n\n{detail}")


def _matching_device_index(
    name: str,
    available: Sequence[str],
    *,
    excluded: set[int] | None = None,
) -> int | None:
    normalized = _normalized_gpu_name(name)
    for index, candidate in enumerate(available):
        if excluded and index in excluded:
            continue
        other = _normalized_gpu_name(candidate)
        if normalized == other or normalized in other or other in normalized:
            return index
    return None


def _normalized_gpu_name(name: str) -> str:
    return "".join(character for character in name.casefold() if character.isalnum())
