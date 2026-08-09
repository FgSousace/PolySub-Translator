from pathlib import Path

from polysub.amd_runtime import (
    AMD_RUNTIME_TARGET_PREFIX,
    AmdRuntimeStatus,
    attach_amd_runtime_devices,
)
from polysub.compute_devices import ComputeDevice


def test_rocm_target_is_added_only_after_a_real_ready_probe() -> None:
    physical = [
        ComputeDevice(
            id="gpu-amd",
            name="AMD Radeon RX 9070 XT",
            kind="gpu",
            vendor="AMD",
            backend="wykryta przez system",
        )
    ]
    unavailable = AmdRuntimeStatus(installed=False, ready=False)
    assert attach_amd_runtime_devices(physical, unavailable)[0].translation_target is None

    ready = AmdRuntimeStatus(
        installed=True,
        ready=True,
        python_path=Path("python.exe"),
        hip_version="7.2.53211",
        devices=("AMD Radeon RX 9070 XT",),
    )
    attached = attach_amd_runtime_devices(physical, ready)[0]
    assert attached.translation_target == f"{AMD_RUNTIME_TARGET_PREFIX}0"
    assert "ROCm 7.2.53211" in attached.backend


def test_rocm_probe_does_not_attach_to_an_unmatched_radeon() -> None:
    devices = [
        ComputeDevice(
            id="gpu-amd-old",
            name="AMD Radeon RX 580",
            kind="gpu",
            vendor="AMD",
            backend="wykryta przez system",
        )
    ]
    ready = AmdRuntimeStatus(
        installed=True,
        ready=True,
        devices=("AMD Radeon RX 9070 XT",),
    )
    assert attach_amd_runtime_devices(devices, ready)[0].translation_target is None


def test_two_identical_radeons_receive_distinct_worker_indices() -> None:
    devices = [
        ComputeDevice(
            id=f"gpu-amd-{index}",
            name="AMD Radeon RX 9070 XT",
            kind="gpu",
            vendor="AMD",
            backend="wykryta przez system",
        )
        for index in range(2)
    ]
    ready = AmdRuntimeStatus(
        installed=True,
        ready=True,
        devices=("AMD Radeon RX 9070 XT", "AMD Radeon RX 9070 XT"),
    )
    attached = attach_amd_runtime_devices(devices, ready)
    assert [device.translation_target for device in attached] == [
        f"{AMD_RUNTIME_TARGET_PREFIX}0",
        f"{AMD_RUNTIME_TARGET_PREFIX}1",
    ]
