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
GET_PIP_URL = "https://bootstrap.pypa.io/get-pip.py"
RUNTIME_SCHEMA_VERSION = 2

AMD_GPU_PROBE_CODE = (
    "import json, torch; "
    "ok=bool(torch.cuda.is_available()); "
    "count=torch.cuda.device_count() if ok else 0; "
    "devices=[torch.cuda.get_device_name(i) for i in range(count)]; "
    "architectures=[str(getattr(torch.cuda.get_device_properties(i), "
    "'gcnArchName', '')) for i in range(count)]; "
    "a=torch.ones((64,64),device='cuda:0') if count else None; "
    "value=float((a@a)[0,0].item()) if count else None; "
    "torch.cuda.synchronize() if count else None; "
    "print(json.dumps({'available':ok,'hip':str(torch.version.hip or ''),"
    "'devices':devices,'architectures':architectures,'value':value}))"
)

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
    try:
        completed = subprocess.run(
            [str(python_path), "-c", AMD_GPU_PROBE_CODE],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=_amd_worker_environment(),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return AmdRuntimeStatus(
            installed=True,
            ready=False,
            python_path=python_path,
            target=target,
            message=f"Nie udało się sprawdzić środowiska AMD ROCm: {exc}",
        )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()[-900:]
        return AmdRuntimeStatus(
            installed=True,
            ready=False,
            python_path=python_path,
            target=target,
            message=(
                "Środowisko AMD ROCm nie przeszło testu prawdziwych obliczeń GPU: "
                f"{detail or 'brak danych'}"
            ),
        )
    try:
        payload = json.loads(completed.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError, TypeError) as exc:
        return AmdRuntimeStatus(
            installed=True,
            ready=False,
            python_path=python_path,
            target=target,
            message=f"Środowisko AMD zwróciło nieprawidłowy wynik: {exc}",
        )
    hip = str(payload.get("hip") or "")
    devices = tuple(str(name) for name in payload.get("devices") or ())
    architectures = tuple(str(name) for name in payload.get("architectures") or ())
    result_value = payload.get("value")
    ready = bool(
        payload.get("available")
        and hip
        and devices
        and isinstance(result_value, (int, float))
        and abs(float(result_value) - 64.0) < 0.01
    )
    return AmdRuntimeStatus(
        installed=True,
        ready=ready,
        python_path=python_path,
        hip_version=hip or None,
        devices=devices,
        architectures=architectures,
        target=target,
        message=(
            f"AMD ROCm {hip} gotowe: {', '.join(devices)}. Test GPU zaliczony."
            if ready
            else "PyTorch ROCm jest zainstalowany, ale karta nie wykonała testu GPU."
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
        runtime_index = _matching_device_index(
            device.name,
            available_names,
            excluded=used_indices,
        )
        if runtime_index is None:
            continue
        used_indices.add(runtime_index)
        backend = f"ROCm {runtime.hip_version or ROCM_VERSION} (automatyczny)"
        result[position] = replace(
            device,
            backend=backend,
            translation_target=f"{AMD_RUNTIME_TARGET_PREFIX}{runtime_index}",
        )
    return result


def install_amd_runtime(
    gpu_names: Sequence[str],
    status: StatusCallback | None = None,
) -> AmdRuntimeStatus:
    """Automatically install AMD's official Windows PyTorch runtime."""

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

    status = status or (lambda _message: None)
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
            ROCM_INDEX_URL,
            plan.torch_requirement,
        ],
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
        raise AmdRuntimeError(
            f"{result.message}\n\n"
            f"Sprawdź sterownik AMD Adrenalin {ROCM_DRIVER_VERSION} lub nowszy i Windows 11 "
            f"25H2. Szczegóły: {AMD_ROCM_COMPATIBILITY_URL}"
        )
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
    get_pip = downloads / "get-pip.py"
    _download_file(GET_PIP_URL, get_pip, status)
    status("Uruchamianie instalatora pakietów w prywatnym środowisku AMD…")
    _run_install_command(
        [str(amd_runtime_python()), str(get_pip), "--disable-pip-version-check"],
        status,
        "Nie udało się przygotować pip w środowisku AMD.",
    )


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


def _amd_worker_environment() -> dict[str, str]:
    environment = os.environ.copy()
    environment["PYTHONUTF8"] = "1"
    environment["PYTHONIOENCODING"] = "utf-8"
    environment.setdefault("TORCH_BLAS_PREFER_HIPBLASLT", "1")
    return environment


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
