"""Automatic, isolated AMD ROCm runtime for native Windows acceleration.

The Windows executable contains the NVIDIA CUDA build of PyTorch. AMD's ROCm
build cannot coexist with it in one Python process, so PolySub prepares a small
embedded Python runtime in the user's profile and starts AMD translation in a
separate worker process. The setup is automatic after a supported Radeon is
detected and never modifies the system Python installation.

Required Notice: PolySub Translator™ — Copyright © 2026 fgSousace.
Licensed for noncommercial use only under PolyForm Noncommercial 1.0.0.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import subprocess
import sys
import zipfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path

from .compute_devices import ComputeDevice

ROCM_VERSION = "7.14.0"
ROCM_PYTORCH_VERSION = "2.12.0"
ROCM_DRIVER_VERSION = "26.6.4"
ROCM_WINDOWS_BUILD = 26200
ROCM_INDEX_URL = "https://repo.amd.com/rocm/whl-multi-arch/"
AMD_RUNTIME_TARGET_PREFIX = "rocm-worker:"
AMD_ROCM_GUIDE_URL = "https://rocm.docs.amd.com/en/latest/install/rocm.html"
AMD_ROCM_COMPATIBILITY_URL = (
    "https://rocm.docs.amd.com/en/latest/compatibility/compatibility-matrix.html"
)

EMBEDDED_PYTHON_VERSION = "3.12.10"
EMBEDDED_PYTHON_URL = (
    "https://www.python.org/ftp/python/3.12.10/"
    "python-3.12.10-embed-amd64.zip"
)
EMBEDDED_PYTHON_SHA256 = (
    "4acbed6dd1c744b0376e3b1cf57ce906f9dc9e95e68824584c8099a63025a3c3"
)
PIP_WHEEL_VERSION = "25.2"
PIP_WHEEL_URL = (
    "https://files.pythonhosted.org/packages/b7/3f/"
    "945ef7ab14dc4f9d7f40288d2df998d1837ee0888ec3659c813487572faa/"
    "pip-25.2-py3-none-any.whl"
)
PIP_WHEEL_SHA256 = "6d67a2b4e7f14d8b31b8b52648866fa717f45a1eb70e83002f4331d07e953717"
RUNTIME_SCHEMA_VERSION = 3

# Query the HIP runtime without initializing a specific adapter. On Ryzen CPUs
# with an iGPU, Windows ROCm can enumerate that iGPU before the discrete Radeon.
AMD_GPU_INVENTORY_CODE = """
import json
import torch

try:
    count = max(int(torch._C._cuda_getDeviceCount()), 0)
except Exception:
    count = 0
print(json.dumps({
    "hip": str(torch.version.hip or ""),
    "count": count,
}))
"""

# This code runs once per physical HIP index with HIP_VISIBLE_DEVICES set. The
# selected adapter therefore becomes cuda:0 even when a Ryzen iGPU originally
# occupied index 0 and the RX 9070 XT was index 1.
AMD_GPU_PROBE_CODE = """
import json
import torch

try:
    count = max(int(torch._C._cuda_getDeviceCount()), 0)
except Exception:
    count = 0
name = torch.cuda.get_device_name(0) if count else ""
properties = torch.cuda.get_device_properties(0) if count else None
architecture = str(getattr(properties, "gcnArchName", ""))
matrix = torch.ones((64, 64), device="cuda:0") if count else None
value = float((matrix @ matrix)[0, 0].item()) if count else None
torch.cuda.synchronize(0) if count else None
print(json.dumps({
    "available": bool(count),
    "hip": str(torch.version.hip or ""),
    "name": str(name),
    "architecture": architecture,
    "value": value,
}))
"""

# Current Windows targets published by AMD for Radeon/Ryzen graphics. Exact
# model-to-target selection keeps the download smaller than device-all.
SUPPORTED_GFX_TARGETS = (
    "gfx1201",
    "gfx1200",
    "gfx1100",
    "gfx1101",
    "gfx1102",
    "gfx1103",
    "gfx1030",
    "gfx1150",
    "gfx1151",
    "gfx1152",
    "gfx1153",
)

OFFICIALLY_SUPPORTED_WINDOWS_GPUS = (
    "Radeon RX 9070 XT / 9070 / 9070 GRE",
    "Radeon RX 9060 XT / 9060",
    "Radeon RX 7900 XTX / XT / GRE",
    "Radeon RX 7800 XT / 7700 XT / 7700",
    "Radeon RX 7600 XT / 7600",
    "Radeon RX 6950 XT / 6900 XT / 6800 XT / 6800",
    "Radeon AI PRO R9000, PRO W7000 i PRO W6000",
    "Radeon 8060S/8050S/8040S/890M/880M/860M/840M/820M/780M/760M/740M",
)

StatusCallback = Callable[[str], None]


class AmdRuntimeError(RuntimeError):
    pass


@dataclass(frozen=True)
class AmdRuntimePlan:
    target: str
    gpu_names: tuple[str, ...]

    @property
    def torch_requirement(self) -> str:
        device_extra = "device-all" if self.target == "all" else f"device-{self.target}"
        return (
            f"torch[{device_extra}]=={ROCM_PYTORCH_VERSION}+rocm{ROCM_VERSION}"
        )


@dataclass(frozen=True)
class AmdRuntimeStatus:
    installed: bool
    ready: bool
    python_path: Path | None = None
    hip_version: str | None = None
    devices: tuple[str, ...] = ()
    architectures: tuple[str, ...] = ()
    runtime_indices: tuple[int, ...] = ()
    target: str | None = None
    message: str = ""


def amd_runtime_directory() -> Path:
    base = os.getenv("LOCALAPPDATA")
    parent = Path(base) / "PolySub Translator" if base else Path.home() / ".polysub-translator"
    # A new path intentionally avoids reusing the obsolete v0.4.9 ROCm 7.2.1 venv.
    return parent / "amd-rocm-runtime-7.14"


def amd_runtime_python() -> Path:
    executable = "python.exe" if os.name == "nt" else "python"
    return amd_runtime_directory() / executable


def amd_runtime_manifest() -> Path:
    return amd_runtime_directory() / "polysub-runtime.json"


def amd_runtime_log_path() -> Path:
    return amd_runtime_directory().parent / "amd-runtime-diagnostics.log"


def write_amd_runtime_diagnostic(message: str) -> None:
    """Persist setup/probe details so an automatic failure is never silent."""

    try:
        path = amd_runtime_log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with path.open("a", encoding="utf-8") as output:
            output.write(f"[{timestamp}] {message.strip()}\n")
    except OSError:
        pass


def infer_amd_gfx_target(gpu_name: str) -> str | None:
    """Map Windows adapter names to AMD's current official wheel target."""

    name = re.sub(r"[^A-Z0-9]+", " ", gpu_name.upper()).strip()
    compact = name.replace(" ", "")

    if any(token in compact for token in ("RX9070", "R9700", "R9600D")):
        return "gfx1201"
    if "RX9060" in compact:
        return "gfx1200"
    if any(token in compact for token in ("RX7900", "PROW7900", "PROW7800")):
        return "gfx1100"
    if any(token in compact for token in ("RX7800", "RX7700", "PROW7700", "PROV710")):
        return "gfx1101"
    if "RX7600" in compact:
        return "gfx1102"
    if any(
        token in compact
        for token in ("RX6950", "RX6900", "RX6800", "PROW6900", "PROW6800")
    ):
        return "gfx1030"
    if any(token in compact for token in ("8065S", "8060S", "8050S")):
        return "gfx1151"
    if any(token in compact for token in ("8040S", "890M", "880M")):
        return "gfx1150"
    if any(token in compact for token in ("860M", "840M", "820M")):
        return "gfx1152"
    if any(token in compact for token in ("780M", "760M", "740M")):
        return "gfx1103"
    return None


def select_amd_runtime_plan(gpu_names: Sequence[str]) -> AmdRuntimePlan | None:
    matched: list[str] = []
    targets: list[str] = []
    for gpu_name in gpu_names:
        target = infer_amd_gfx_target(gpu_name)
        if target is None:
            continue
        matched.append(str(gpu_name))
        if target not in targets:
            targets.append(target)
    if not targets:
        return None
    # One runtime can serve several adapters. Use device-all only when the PC
    # actually contains supported AMD GPUs from more than one architecture.
    selected_target = targets[0] if len(targets) == 1 else "all"
    return AmdRuntimePlan(target=selected_target, gpu_names=tuple(matched))


def probe_amd_runtime(*, timeout: float = 45.0) -> AmdRuntimeStatus:
    python_path = amd_runtime_python()
    manifest = _load_runtime_manifest()
    target = str(manifest.get("target") or "") or None
    if not python_path.is_file():
        return AmdRuntimeStatus(
            installed=False,
            ready=False,
            target=target,
            message="Automatyczne środowisko AMD ROCm nie jest jeszcze zainstalowane.",
        )
    inventory, inventory_error = _run_amd_json_command(
        python_path,
        AMD_GPU_INVENTORY_CODE,
        timeout=max(min(timeout, 60.0), 10.0),
        environment=amd_worker_environment(),
    )
    if inventory is None:
        return AmdRuntimeStatus(
            installed=True,
            ready=False,
            python_path=python_path,
            target=target,
            message=(
                "Nie udało się odczytać urządzeń ze środowiska AMD ROCm: "
                f"{inventory_error or 'brak danych'}"
            ),
        )
    hip = str(inventory.get("hip") or "")
    try:
        device_count = max(int(inventory.get("count") or 0), 0)
    except (TypeError, ValueError):
        device_count = 0
    if not hip or device_count < 1:
        return AmdRuntimeStatus(
            installed=True,
            ready=False,
            python_path=python_path,
            hip_version=hip or None,
            target=target,
            message=(
                "PyTorch ROCm jest zainstalowany, ale HIP nie wykrył żadnego urządzenia."
            ),
        )

    working_names: list[str] = []
    working_architectures: list[str] = []
    working_indices: list[int] = []
    diagnostics: list[str] = []
    per_device_timeout = max(min(float(timeout) / device_count, 90.0), 15.0)
    for physical_index in range(device_count):
        payload, error = _run_amd_json_command(
            python_path,
            AMD_GPU_PROBE_CODE,
            timeout=per_device_timeout,
            environment=amd_worker_environment(physical_index),
        )
        if payload is None:
            diagnostics.append(f"GPU {physical_index}: {error or 'brak odpowiedzi'}")
            continue
        name = str(payload.get("name") or f"AMD GPU {physical_index}")
        architecture = str(payload.get("architecture") or "")
        result_value = payload.get("value")
        ready = bool(
            payload.get("available")
            and payload.get("hip")
            and isinstance(result_value, (int, float))
            and abs(float(result_value) - 64.0) < 0.01
        )
        if not ready:
            diagnostics.append(f"GPU {physical_index} ({name}): test macierzy nieudany")
            continue
        if not _runtime_device_matches_target(name, architecture, target):
            diagnostics.append(
                f"GPU {physical_index} ({name}, {architecture or 'bez architektury'}): "
                f"nie pasuje do pakietu {target}"
            )
            continue
        working_names.append(name)
        working_architectures.append(architecture)
        working_indices.append(physical_index)

    if not working_indices:
        detail = "; ".join(diagnostics[-3:])[-1200:]
        return AmdRuntimeStatus(
            installed=True,
            ready=False,
            python_path=python_path,
            hip_version=hip or None,
            target=target,
            message=(
                f"ROCm {hip} wykrył {device_count} urządzeń, ale żadne nie wykonało "
                f"testu GPU dla pakietu {target or 'automatycznego'}. "
                f"{detail or 'Brak dodatkowej diagnostyki.'}"
            ),
        )

    descriptions = ", ".join(
        f"{name} (indeks HIP {index})"
        for name, index in zip(working_names, working_indices, strict=True)
    )
    skipped_count = max(device_count - len(working_indices), 0)
    skipped_note = (
        f" Pominięto {skipped_count} niezgodne urządzenie/iGPU."
        if skipped_count
        else ""
    )
    return AmdRuntimeStatus(
        installed=True,
        ready=True,
        python_path=python_path,
        hip_version=hip or None,
        devices=tuple(working_names),
        architectures=tuple(working_architectures),
        runtime_indices=tuple(working_indices),
        target=target,
        message=(
            f"AMD ROCm {hip} gotowe: {descriptions}. Test GPU zaliczony."
            f"{skipped_note}"
        ),
    )


def attach_amd_runtime_devices(
    devices: Sequence[ComputeDevice],
    runtime: AmdRuntimeStatus,
) -> list[ComputeDevice]:
    """Attach external ROCm targets only after the real GPU probe succeeds."""

    result = list(devices)
    if not runtime.ready:
        return result
    available_names = list(runtime.devices)
    used_indices: set[int] = set()
    for position, device in enumerate(result):
        if device.kind != "gpu" or device.vendor != "AMD":
            continue
        matched_position = _matching_device_index(
            device.name,
            available_names,
            excluded=used_indices,
        )
        if matched_position is None:
            continue
        used_indices.add(matched_position)
        physical_index = (
            runtime.runtime_indices[matched_position]
            if matched_position < len(runtime.runtime_indices)
            else matched_position
        )
        backend = (
            f"ROCm {runtime.hip_version or ROCM_VERSION} "
            f"(automatyczny, izolowany indeks {physical_index})"
        )
        result[position] = replace(
            device,
            backend=backend,
            translation_target=f"{AMD_RUNTIME_TARGET_PREFIX}{physical_index}",
        )
    return result


def install_amd_runtime(
    gpu_names: Sequence[str],
    status: StatusCallback | None = None,
) -> AmdRuntimeStatus:
    """Automatically install AMD's official Windows PyTorch runtime."""

    external_status = status or (lambda _message: None)

    def report(message: str) -> None:
        write_amd_runtime_diagnostic(message)
        external_status(message)

    status = report
    status(f"Start automatycznej diagnostyki AMD dla: {', '.join(gpu_names)}")

    if os.name != "nt":
        raise AmdRuntimeError("Automatyczna instalacja AMD ROCm jest dostępna tylko w Windows 11.")
    if platform.machine().lower() not in {"amd64", "x86_64"}:
        raise AmdRuntimeError("AMD ROCm wymaga 64-bitowego systemu Windows na procesorze x64.")
    plan = select_amd_runtime_plan(gpu_names)
    if plan is None:
        names = ", ".join(gpu_names) or "nieznany Radeon"
        raise AmdRuntimeError(
            f"{names} nie ma obecnie oficjalnego pakietu ROCm {ROCM_VERSION} dla Windows. "
            "PolySub bezpiecznie użyje procesora."
        )
    build = _windows_build_number()
    if build and build < ROCM_WINDOWS_BUILD:
        raise AmdRuntimeError(
            f"AMD ROCm {ROCM_VERSION} wymaga oficjalnie Windows 11 25H2 "
            f"(build {ROCM_WINDOWS_BUILD} lub nowszy). Wykryto build {build}."
        )

    existing = probe_amd_runtime(timeout=75.0)
    if existing.ready and _runtime_supports_plan(existing, plan):
        status(existing.message)
        return existing

    runtime_dir = amd_runtime_directory()
    runtime_dir.mkdir(parents=True, exist_ok=True)
    python_path = amd_runtime_python()
    if not _embedded_python_core_ready(python_path):
        if python_path.exists():
            status("Naprawianie przerwanego pobierania środowiska Python dla AMD…")
        _install_embedded_python(runtime_dir, status)
    elif not _embedded_pip_ready(python_path):
        status("Naprawianie przerwanego przygotowania środowiska AMD…")
        _configure_embedded_python_paths(runtime_dir)
        _bootstrap_embedded_pip(runtime_dir, status)

    status(
        f"Radeon wykryty automatycznie — przygotowywanie ROCm {ROCM_VERSION} "
        f"dla {plan.target}…"
    )
    status("Przygotowywanie narzędzi instalacyjnych dla AMD ROCm…")
    _run_install_command(
        _amd_build_backend_install_command(python_path),
        status,
        "Nie udało się przygotować setuptools i wheel dla AMD ROCm.",
    )
    _run_install_command(
        _amd_torch_install_command(python_path, plan),
        status,
        "Nie udało się zainstalować oficjalnego PyTorch ROCm.",
    )
    status("Instalowanie bibliotek modeli tłumaczeniowych w środowisku AMD…")
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
            "--only-binary",
            ":all:",
            "--index-url",
            "https://pypi.org/simple",
            "numpy>=1.26,<3",
            "transformers>=4.55.5,<6",
            "huggingface-hub>=0.25,<2",
            "tokenizers>=0.21,<1",
            "safetensors>=0.4,<1",
            "sentencepiece>=0.2,<1",
            "requests>=2.31,<3",
        ],
        status,
        "Nie udało się zainstalować bibliotek modeli w środowisku AMD.",
    )
    _write_runtime_manifest(plan)
    status("Testowanie rzeczywistych obliczeń na karcie Radeon…")
    result = probe_amd_runtime(timeout=180.0)
    if not result.ready:
        status(result.message)
        raise AmdRuntimeError(
            f"{result.message}\n\n"
            f"Sprawdź sterownik AMD Adrenalin {ROCM_DRIVER_VERSION} lub nowszy i Windows 11 "
            f"25H2. Szczegóły: {AMD_ROCM_COMPATIBILITY_URL}"
        )
    status(result.message)
    return result


def _amd_build_backend_install_command(python_path: Path) -> list[str]:
    """Install the backend required by AMD's source-only ``rocm`` shim.

    AMD's multi-architecture repository publishes ``rocm`` as an sdist whose
    ``pyproject.toml`` selects ``setuptools.build_meta``.  Embedded Python does
    not ship setuptools, and pip's temporary build environment can fail to
    expose that backend on Windows.  Install trusted binary build tools in the
    isolated PolySub runtime before resolving the AMD dependency tree.
    """

    return [
        str(python_path),
        "-m",
        "pip",
        "--isolated",
        "install",
        "--disable-pip-version-check",
        "--progress-bar",
        "off",
        "--no-cache-dir",
        "--only-binary",
        ":all:",
        "--index-url",
        "https://pypi.org/simple",
        "setuptools>=70.2,<82",
        "wheel>=0.44,<1",
    ]


def _amd_torch_install_command(
    python_path: Path,
    plan: AmdRuntimePlan,
) -> list[str]:
    """Build AMD's documented pip command without rejecting ROCm's source shim.

    AMD publishes the small ``rocm`` metapackage as ``rocm-<version>.tar.gz`` in
    the multi-architecture index.  ``--only-binary :all:`` therefore makes the
    otherwise official torch extra impossible to resolve and produces
    ``No matching distribution found for rocm``.  Prefer wheels for the large
    components, but allow that trusted AMD source package exactly as AMD's own
    Windows installation command does.  Build isolation is disabled only for
    this private runtime after a compatible ``setuptools.build_meta`` backend
    has been installed explicitly above.  This avoids pip's
    ``BackendUnavailable`` failure in the Windows embedded distribution.
    """

    return [
        str(python_path),
        "-m",
        "pip",
        "--isolated",
        "install",
        "--disable-pip-version-check",
        "--progress-bar",
        "off",
        "--no-cache-dir",
        "--no-build-isolation",
        "--prefer-binary",
        "--index-url",
        ROCM_INDEX_URL,
        plan.torch_requirement,
    ]


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


def _install_embedded_python(runtime_dir: Path, status: StatusCallback) -> None:
    status(f"Pobieranie własnego środowiska Python {EMBEDDED_PYTHON_VERSION} dla AMD…")
    downloads = runtime_dir.parent / "amd-runtime-downloads"
    downloads.mkdir(parents=True, exist_ok=True)
    python_archive = downloads / Path(EMBEDDED_PYTHON_URL).name
    _download_file(
        EMBEDDED_PYTHON_URL,
        python_archive,
        status,
        expected_sha256=EMBEDDED_PYTHON_SHA256,
    )
    try:
        with zipfile.ZipFile(python_archive) as archive:
            archive.extractall(runtime_dir)
    except (OSError, zipfile.BadZipFile) as exc:
        raise AmdRuntimeError(f"Nie udało się rozpakować środowiska Python dla AMD: {exc}") from exc

    _configure_embedded_python_paths(runtime_dir)
    _bootstrap_embedded_pip(runtime_dir, status)


def _configure_embedded_python_paths(runtime_dir: Path) -> None:
    pth_files = tuple(runtime_dir.glob("python*._pth"))
    if not pth_files:
        raise AmdRuntimeError("Pobrane środowisko Python nie zawiera pliku konfiguracji ._pth.")
    pth = pth_files[0]
    lines = [line.strip() for line in pth.read_text(encoding="utf-8").splitlines()]
    lines = [line for line in lines if line and line != "#import site"]
    if "Lib\\site-packages" not in lines:
        lines.append("Lib\\site-packages")
    if "import site" not in lines:
        lines.append("import site")
    pth.write_text("\n".join(lines) + "\n", encoding="utf-8")
    (runtime_dir / "Lib" / "site-packages").mkdir(parents=True, exist_ok=True)


def _bootstrap_embedded_pip(runtime_dir: Path, status: StatusCallback) -> None:
    downloads = runtime_dir.parent / "amd-runtime-downloads"
    downloads.mkdir(parents=True, exist_ok=True)
    pip_wheel = downloads / f"pip-{PIP_WHEEL_VERSION}-py3-none-any.whl"
    _download_file(
        PIP_WHEEL_URL,
        pip_wheel,
        status,
        expected_sha256=PIP_WHEEL_SHA256,
    )
    status("Przygotowywanie instalatora pakietów w prywatnym środowisku AMD…")
    site_packages = runtime_dir / "Lib" / "site-packages"
    try:
        with zipfile.ZipFile(pip_wheel) as archive:
            archive.extractall(site_packages)
    except (OSError, zipfile.BadZipFile) as exc:
        raise AmdRuntimeError(f"Nie udało się przygotować pip w środowisku AMD: {exc}") from exc
    # This bootstrapper is shared by the AMD and narrator runtimes.  Verify the
    # interpreter that belongs to the directory we just prepared instead of
    # accidentally probing the AMD runtime unconditionally.
    executable = "python.exe" if os.name == "nt" else "python"
    if not _embedded_pip_ready(runtime_dir / executable):
        raise AmdRuntimeError("Pip z oficjalnego, zweryfikowanego koła nie uruchamia się.")


def _embedded_pip_ready(python_path: Path) -> bool:
    try:
        completed = subprocess.run(
            [str(python_path), "-m", "pip", "--version"],
            check=False,
            capture_output=True,
            timeout=20,
            env=_amd_worker_environment(),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return completed.returncode == 0


def _embedded_python_core_ready(python_path: Path) -> bool:
    if not python_path.is_file():
        return False
    try:
        completed = subprocess.run(
            [
                str(python_path),
                "-c",
                "import ssl,sys,zipfile; assert sys.version_info[:2] == (3, 12)",
            ],
            check=False,
            capture_output=True,
            timeout=20,
            env=_amd_worker_environment(),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return completed.returncode == 0


def _download_file(
    url: str,
    destination: Path,
    status: StatusCallback,
    *,
    expected_sha256: str | None = None,
) -> None:
    if destination.is_file() and (
        expected_sha256 is None or _file_sha256(destination) == expected_sha256.lower()
    ):
        return
    temporary = destination.with_suffix(destination.suffix + ".part")
    try:
        import requests

        with requests.get(url, stream=True, timeout=(20, 180)) as response:
            response.raise_for_status()
            total = max(int(response.headers.get("content-length") or 0), 0)
            downloaded = 0
            next_report = 0
            with temporary.open("wb") as output:
                for block in response.iter_content(chunk_size=1024 * 1024):
                    if not block:
                        continue
                    output.write(block)
                    downloaded += len(block)
                    if downloaded >= next_report:
                        if total:
                            percent = min(downloaded * 100 // total, 100)
                            status(
                                f"Pobieranie składnika AMD: {percent}% "
                                f"({downloaded // 1048576}/{total // 1048576} MB)"
                            )
                            next_report = downloaded + max(total // 20, 8 * 1048576)
                        else:
                            status(f"Pobieranie składnika AMD: {downloaded // 1048576} MB")
                            next_report = downloaded + 32 * 1048576
        if expected_sha256 and _file_sha256(temporary) != expected_sha256.lower():
            raise AmdRuntimeError(
                f"Pobrany plik {destination.name} ma nieprawidłową sumę SHA-256."
            )
        temporary.replace(destination)
    except AmdRuntimeError:
        temporary.unlink(missing_ok=True)
        raise
    except Exception as exc:
        temporary.unlink(missing_ok=True)
        raise AmdRuntimeError(f"Nie udało się pobrać {url}: {exc}") from exc


def _run_install_command(
    command: list[str],
    status: StatusCallback,
    failure_message: str,
) -> None:
    environment = _amd_worker_environment()
    environment["PIP_NO_INPUT"] = "1"
    environment["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=environment,
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
        recent = recent[-16:]
        lowered = cleaned.lower()
        if any(
            marker in lowered
            for marker in ("downloading", "installing", "successfully", "collecting")
        ):
            status(cleaned[:260])
    return_code = process.wait()
    if return_code != 0:
        detail = "\n".join(recent)[-1800:]
        raise AmdRuntimeError(f"{failure_message}\n\n{detail}")


def _write_runtime_manifest(plan: AmdRuntimePlan) -> None:
    manifest = {
        "schema": RUNTIME_SCHEMA_VERSION,
        "rocm_version": ROCM_VERSION,
        "pytorch_version": ROCM_PYTORCH_VERSION,
        "python_version": EMBEDDED_PYTHON_VERSION,
        "target": plan.target,
        "gpu_names": list(plan.gpu_names),
    }
    path = amd_runtime_manifest()
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_runtime_manifest() -> dict[str, object]:
    try:
        payload = json.loads(amd_runtime_manifest().read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _runtime_supports_plan(runtime: AmdRuntimeStatus, plan: AmdRuntimePlan) -> bool:
    if runtime.target == "all" or runtime.target == plan.target:
        return True
    return bool(plan.target != "all" and plan.target in runtime.architectures)


def amd_worker_environment(device_index: int | None = None) -> dict[str, str]:
    environment = os.environ.copy()
    environment["PYTHONUTF8"] = "1"
    environment["PYTHONIOENCODING"] = "utf-8"
    environment.setdefault("TORCH_BLAS_PREFER_HIPBLASLT", "1")
    # AMD documents HIP_VISIBLE_DEVICES as the native Windows selector. Clear
    # CUDA_VISIBLE_DEVICES so two aliases cannot apply conflicting filters.
    environment.pop("CUDA_VISIBLE_DEVICES", None)
    if device_index is None:
        environment.pop("HIP_VISIBLE_DEVICES", None)
    else:
        selected = str(max(int(device_index), 0))
        environment["HIP_VISIBLE_DEVICES"] = selected
    return environment


def _amd_worker_environment() -> dict[str, str]:
    """Backward-compatible internal alias for unmasked setup commands."""

    return amd_worker_environment()


def _run_amd_json_command(
    python_path: Path,
    code: str,
    *,
    timeout: float,
    environment: dict[str, str],
) -> tuple[dict[str, object] | None, str]:
    try:
        completed = subprocess.run(
            [str(python_path), "-c", code],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=environment,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return None, str(exc)
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()[-1000:]
        return None, detail or f"proces zakończył się kodem {completed.returncode}"
    try:
        payload = json.loads(completed.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError, TypeError) as exc:
        return None, f"nieprawidłowa odpowiedź JSON: {exc}"
    if not isinstance(payload, dict):
        return None, "odpowiedź środowiska AMD nie jest obiektem JSON"
    return payload, ""


def _runtime_device_matches_target(
    name: str,
    architecture: str,
    target: str | None,
) -> bool:
    if not target or target == "all":
        return True
    architecture_base = architecture.casefold().split(":", 1)[0]
    return architecture_base == target.casefold() or infer_amd_gfx_target(name) == target


def _windows_build_number() -> int:
    getter = getattr(sys, "getwindowsversion", None)
    if getter is None:
        return 0
    try:
        return max(int(getter().build), 0)
    except (AttributeError, TypeError, ValueError):
        return 0


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


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
