from __future__ import annotations

import importlib
import json
import os
import platform
import re
import shlex
import shutil
import subprocess
from dataclasses import dataclass, replace
from hashlib import sha256
from pathlib import Path
from typing import Any, Literal

AUTO_DEVICE_ID = "auto"
AUTO_DEVICE_LABEL = "Automatycznie — najlepsze dostępne urządzenie"
TaskKind = Literal["translation", "transcription"]


@dataclass(frozen=True)
class HardwareGpu:
    name: str
    hardware_id: str = ""


@dataclass(frozen=True)
class HardwareSnapshot:
    cpu_name: str
    gpus: tuple[HardwareGpu, ...] = ()


@dataclass(frozen=True)
class ComputeDevice:
    id: str
    name: str
    kind: Literal["cpu", "gpu"]
    vendor: str
    backend: str
    translation_target: str | None = None
    transcription_target: str | None = None
    transcription_index: int = 0

    @property
    def display_label(self) -> str:
        prefix = "CPU" if self.kind == "cpu" else "GPU"
        if self.backend:
            return f"{prefix} — {self.name} • {self.backend}"
        return f"{prefix} — {self.name}"

    def supports(self, task: TaskKind) -> bool:
        if task == "translation":
            return self.translation_target is not None
        return self.transcription_target is not None


@dataclass(frozen=True)
class DeviceResolution:
    requested_id: str
    selected_id: str
    display_name: str
    runtime_device: str
    device_index: int = 0
    fallback_reason: str | None = None

    @property
    def used_fallback(self) -> bool:
        return self.fallback_reason is not None


def detect_compute_devices(
    *,
    snapshot: HardwareSnapshot | None = None,
    torch_module: Any | None = None,
    ctranslate2_module: Any | None = None,
) -> list[ComputeDevice]:
    """Return real devices detected on this computer and their usable AI backends."""
    hardware = snapshot or detect_hardware_snapshot()
    cpu_name = _clean_name(hardware.cpu_name) or "Procesor systemowy"
    devices = [
        ComputeDevice(
            id="cpu",
            name=cpu_name,
            kind="cpu",
            vendor=_vendor_from_name(cpu_name),
            backend="CPU",
            translation_target="cpu",
            transcription_target="cpu",
        )
    ]

    physical_gpus = _unique_physical_gpus(hardware.gpus)
    for index, gpu in enumerate(physical_gpus):
        devices.append(
            ComputeDevice(
                id=_hardware_device_id(gpu, index),
                name=gpu.name,
                kind="gpu",
                vendor=_vendor_from_name(gpu.name),
                backend="wykryta przez system",
            )
        )

    torch = torch_module if torch_module is not None else _optional_import("torch")
    if torch is not None:
        devices = _add_torch_accelerators(devices, torch)

    ctranslate2 = (
        ctranslate2_module
        if ctranslate2_module is not None
        else _optional_import("ctranslate2")
    )
    if ctranslate2 is not None:
        devices = _add_ctranslate2_accelerators(devices, ctranslate2)

    if os.name == "nt":
        # AMD's native Windows PyTorch wheel cannot coexist in-process with the
        # NVIDIA CUDA wheel bundled by the installer. Only advertise ROCm after
        # the isolated worker environment passes a real torch/GPU probe.
        try:
            from .amd_runtime import attach_amd_runtime_devices, probe_amd_runtime

            devices = attach_amd_runtime_devices(devices, probe_amd_runtime())
        except Exception:
            pass

    return _make_labels_unique(devices)


def resolve_compute_device(
    devices: list[ComputeDevice],
    requested_id: str,
    task: TaskKind,
) -> DeviceResolution:
    cpu = next((device for device in devices if device.kind == "cpu"), None)
    if cpu is None:
        cpu = ComputeDevice(
            id="cpu",
            name="Procesor systemowy",
            kind="cpu",
            vendor="Inne",
            backend="CPU",
            translation_target="cpu",
            transcription_target="cpu",
        )

    if requested_id == AUTO_DEVICE_ID:
        candidates = [
            device for device in devices if device.kind == "gpu" and device.supports(task)
        ]
        selected = min(candidates, key=_automatic_priority, default=cpu)
        return _resolution_for(selected, requested_id, task)

    selected = next((device for device in devices if device.id == requested_id), None)
    if selected is None:
        return DeviceResolution(
            requested_id=requested_id,
            selected_id=cpu.id,
            display_name=cpu.name,
            runtime_device="cpu",
            fallback_reason="Wybrane urządzenie nie jest już dostępne — użyto procesora.",
        )
    if selected.supports(task):
        return _resolution_for(selected, requested_id, task)

    task_name = "tłumaczenia" if task == "translation" else "rozpoznawania mowy"
    return DeviceResolution(
        requested_id=requested_id,
        selected_id=cpu.id,
        display_name=cpu.name,
        runtime_device="cpu",
        fallback_reason=(
            f"{selected.name} została wykryta, ale obecny backend nie obsługuje na niej "
            f"{task_name}. Użyto procesora."
        ),
    )


def describe_device_support(device: ComputeDevice) -> str:
    if device.kind == "cpu":
        return "Tłumaczenie: CPU • rozpoznawanie mowy: CPU"
    translation = device.backend if device.translation_target else "CPU awaryjnie"
    transcription = device.backend if device.transcription_target else "CPU awaryjnie"
    return f"Tłumaczenie: {translation} • rozpoznawanie mowy: {transcription}"


def detect_hardware_snapshot() -> HardwareSnapshot:
    if os.name == "nt":
        snapshot = _windows_hardware_snapshot()
        if snapshot is not None:
            return snapshot
    if platform.system() == "Darwin":
        snapshot = _macos_hardware_snapshot()
        if snapshot is not None:
            return snapshot
    return _portable_hardware_snapshot()


def _resolution_for(
    device: ComputeDevice,
    requested_id: str,
    task: TaskKind,
) -> DeviceResolution:
    runtime_device = (
        device.translation_target if task == "translation" else device.transcription_target
    )
    return DeviceResolution(
        requested_id=requested_id,
        selected_id=device.id,
        display_name=device.name,
        runtime_device=runtime_device or "cpu",
        device_index=device.transcription_index if task == "transcription" else 0,
    )


def _automatic_priority(device: ComputeDevice) -> tuple[int, str]:
    backend = device.backend.lower()
    if "cuda" in backend or "rocm" in backend:
        return 0, device.name.casefold()
    if "xpu" in backend or "openvino" in backend:
        return 1, device.name.casefold()
    return 2, device.name.casefold()


def _add_torch_accelerators(
    devices: list[ComputeDevice],
    torch: Any,
) -> list[ComputeDevice]:
    result = list(devices)
    cuda = getattr(torch, "cuda", None)
    if cuda is not None and _safe_backend_available(cuda):
        backend = "ROCm" if getattr(getattr(torch, "version", None), "hip", None) else "CUDA"
        count = _safe_device_count(cuda)
        for index in range(count):
            name = _safe_device_name(cuda, index, f"GPU {index + 1}")
            result = _merge_runtime_gpu(
                result,
                name=name,
                vendor=_vendor_from_name(name),
                backend=backend,
                translation_target=f"cuda:{index}",
                device_ordinal=index,
            )

    xpu = getattr(torch, "xpu", None)
    if xpu is not None and _safe_backend_available(xpu):
        count = _safe_device_count(xpu)
        for index in range(count):
            name = _safe_device_name(xpu, index, f"Intel GPU {index + 1}")
            result = _merge_runtime_gpu(
                result,
                name=name,
                vendor="Intel",
                backend="Intel XPU",
                translation_target=f"xpu:{index}",
                device_ordinal=index,
            )
    return result


def _add_ctranslate2_accelerators(
    devices: list[ComputeDevice],
    ctranslate2: Any,
) -> list[ComputeDevice]:
    try:
        count = max(int(ctranslate2.get_cuda_device_count()), 0)
    except Exception:
        # Optional runtime probes can raise driver-specific exceptions. A broken
        # accelerator must not prevent the always-available CPU path from loading.
        return devices
    if count == 0:
        return devices

    result = list(devices)
    candidates = [
        device
        for device in result
        if device.kind == "gpu" and device.vendor == "NVIDIA"
    ]
    for index in range(count):
        name = candidates[index].name if index < len(candidates) else f"NVIDIA GPU {index + 1}"
        result = _merge_runtime_gpu(
            result,
            name=name,
            vendor="NVIDIA",
            backend="CUDA",
            transcription_target="cuda",
            transcription_index=index,
            device_ordinal=index,
        )
    return result


def _merge_runtime_gpu(
    devices: list[ComputeDevice],
    *,
    name: str,
    vendor: str,
    backend: str,
    translation_target: str | None = None,
    transcription_target: str | None = None,
    transcription_index: int = 0,
    device_ordinal: int = 0,
) -> list[ComputeDevice]:
    result = list(devices)
    match_index = _find_matching_gpu(result, name, vendor, device_ordinal)
    if match_index is None:
        runtime_id = _hardware_device_id(
            HardwareGpu(name, f"runtime:{backend}:{device_ordinal}:{name}"),
            device_ordinal,
        )
        result.append(
            ComputeDevice(
                id=runtime_id,
                name=name,
                kind="gpu",
                vendor=vendor,
                backend=backend,
                translation_target=translation_target,
                transcription_target=transcription_target,
                transcription_index=transcription_index,
            )
        )
        return result

    current = result[match_index]
    backends = {part.strip() for part in current.backend.split("+")}
    backends.discard("wykryta przez system")
    backends.add(backend)
    result[match_index] = replace(
        current,
        backend=" + ".join(sorted(backends)),
        translation_target=translation_target or current.translation_target,
        transcription_target=transcription_target or current.transcription_target,
        transcription_index=(
            transcription_index if transcription_target else current.transcription_index
        ),
    )
    return result


def _find_matching_gpu(
    devices: list[ComputeDevice],
    name: str,
    vendor: str,
    device_ordinal: int,
) -> int | None:
    normalized = _normalize_device_name(name)
    exact_candidates: list[int] = []
    vendor_candidates: list[int] = []
    for index, device in enumerate(devices):
        if device.kind != "gpu":
            continue
        current = _normalize_device_name(device.name)
        if current == normalized or current in normalized or normalized in current:
            exact_candidates.append(index)
        if device.vendor == vendor:
            vendor_candidates.append(index)
    if device_ordinal < len(exact_candidates):
        return exact_candidates[device_ordinal]
    if device_ordinal < len(vendor_candidates):
        return vendor_candidates[device_ordinal]
    return None


def _windows_hardware_snapshot() -> HardwareSnapshot | None:
    script = (
        "[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false);"
        "$cpu=@(Get-CimInstance Win32_Processor | ForEach-Object {$_.Name});"
        "$gpus=@(Get-CimInstance Win32_VideoController | ForEach-Object {"
        "[pscustomobject]@{Name=$_.Name;Id=$_.PNPDeviceID}});"
        "[pscustomobject]@{Cpu=$cpu;Gpus=$gpus}|ConvertTo-Json -Compress -Depth 4"
    )
    try:
        completed = subprocess.run(
            ["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", script],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=12,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if completed.returncode != 0 or not completed.stdout.strip():
            return None
        payload = json.loads(completed.stdout)
    except (json.JSONDecodeError, OSError, subprocess.SubprocessError):
        return None

    cpu_values = payload.get("Cpu", []) if isinstance(payload, dict) else []
    if isinstance(cpu_values, str):
        cpu_values = [cpu_values]
    cpu_name = " + ".join(_clean_name(str(value)) for value in cpu_values if value)
    raw_gpus = payload.get("Gpus", []) if isinstance(payload, dict) else []
    if isinstance(raw_gpus, dict):
        raw_gpus = [raw_gpus]
    gpus = tuple(
        HardwareGpu(_clean_name(str(value.get("Name", ""))), str(value.get("Id", "")))
        for value in raw_gpus
        if isinstance(value, dict) and _is_real_gpu_name(str(value.get("Name", "")))
    )
    return HardwareSnapshot(cpu_name or _fallback_cpu_name(), gpus)


def _macos_hardware_snapshot() -> HardwareSnapshot | None:
    try:
        completed = subprocess.run(
            ["system_profiler", "SPDisplaysDataType", "-json"],
            check=False,
            capture_output=True,
            text=True,
            timeout=12,
        )
        payload = json.loads(completed.stdout)
    except (json.JSONDecodeError, OSError, subprocess.SubprocessError):
        return None
    adapters = payload.get("SPDisplaysDataType", []) if isinstance(payload, dict) else []
    gpus = tuple(
        HardwareGpu(_clean_name(str(adapter.get("sppci_model", ""))))
        for adapter in adapters
        if isinstance(adapter, dict) and adapter.get("sppci_model")
    )
    return HardwareSnapshot(_fallback_cpu_name(), gpus)


def _portable_hardware_snapshot() -> HardwareSnapshot:
    gpus: list[HardwareGpu] = []
    lspci = shutil.which("lspci")
    if lspci:
        try:
            completed = subprocess.run(
                [lspci, "-mm"],
                check=False,
                capture_output=True,
                text=True,
                timeout=8,
            )
            for line in completed.stdout.splitlines():
                fields = shlex.split(line)
                if len(fields) < 4 or not any(
                    marker in fields[1].casefold() for marker in ("vga", "3d", "display")
                ):
                    continue
                name = _clean_name(" ".join(fields[2:4]))
                if _is_real_gpu_name(name):
                    gpus.append(HardwareGpu(name, fields[0]))
        except (OSError, subprocess.SubprocessError, ValueError):
            pass
    return HardwareSnapshot(_fallback_cpu_name(), tuple(gpus))


def _fallback_cpu_name() -> str:
    if platform.system() == "Linux":
        try:
            cpu_info = Path("/proc/cpuinfo").read_text(encoding="utf-8", errors="replace")
            match = re.search(r"^(?:model name|hardware)\s*:\s*(.+)$", cpu_info, re.MULTILINE)
            if match and _clean_name(match.group(1)):
                return _clean_name(match.group(1))
        except OSError:
            pass
    candidates = (
        platform.processor(),
        os.getenv("PROCESSOR_IDENTIFIER", ""),
        platform.machine(),
    )
    return next((_clean_name(value) for value in candidates if _clean_name(value)), "CPU")


def _optional_import(name: str) -> Any | None:
    try:
        return importlib.import_module(name)
    except Exception:
        # Some vendor runtimes fail during import when the installed driver and
        # library versions do not match. Treat them as unavailable accelerators.
        return None


def _safe_backend_available(backend: Any) -> bool:
    try:
        return bool(backend.is_available())
    except Exception:
        return False


def _safe_device_count(backend: Any) -> int:
    try:
        return max(int(backend.device_count()), 0)
    except Exception:
        return 0


def _safe_device_name(backend: Any, index: int, fallback: str) -> str:
    try:
        return _clean_name(str(backend.get_device_name(index))) or fallback
    except Exception:
        return fallback


def _unique_physical_gpus(gpus: tuple[HardwareGpu, ...]) -> list[HardwareGpu]:
    result: list[HardwareGpu] = []
    seen: set[tuple[str, str]] = set()
    for gpu in gpus:
        name = _clean_name(gpu.name)
        if not _is_real_gpu_name(name):
            continue
        key = (_normalize_device_name(name), gpu.hardware_id.casefold())
        if key in seen:
            continue
        seen.add(key)
        result.append(HardwareGpu(name, gpu.hardware_id))
    return result


def _make_labels_unique(devices: list[ComputeDevice]) -> list[ComputeDevice]:
    counts: dict[str, int] = {}
    result: list[ComputeDevice] = []
    for device in devices:
        key = device.name.casefold()
        counts[key] = counts.get(key, 0) + 1
        if counts[key] == 1:
            result.append(device)
        else:
            result.append(replace(device, name=f"{device.name} (urządzenie {counts[key]})"))
    return result


def _hardware_device_id(gpu: HardwareGpu, index: int) -> str:
    source = gpu.hardware_id or f"{gpu.name}:{index}"
    digest = sha256(source.encode("utf-8", errors="replace")).hexdigest()[:12]
    return f"gpu:{digest}"


def _vendor_from_name(name: str) -> str:
    normalized = name.casefold()
    if "nvidia" in normalized or "geforce" in normalized or "quadro" in normalized:
        return "NVIDIA"
    if any(value in normalized for value in ("amd", "radeon", "advanced micro devices")):
        return "AMD"
    if "intel" in normalized or " arc " in f" {normalized} ":
        return "Intel"
    if "apple" in normalized:
        return "Apple"
    return "Inne"


def _normalize_device_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", name.casefold())


def _clean_name(name: str) -> str:
    return " ".join(name.strip().split())


def _is_real_gpu_name(name: str) -> bool:
    normalized = _clean_name(name).casefold()
    if not normalized:
        return False
    virtual_markers = (
        "basic display",
        "remote display",
        "indirect display",
        "virtual display",
    )
    return not any(marker in normalized for marker in virtual_markers)
