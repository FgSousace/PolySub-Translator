from pathlib import Path

from polysub.amd_runtime import (
    AMD_GPU_PROBE_CODE,
    AMD_RUNTIME_TARGET_PREFIX,
    ROCM_VERSION,
    AmdRuntimeStatus,
    attach_amd_runtime_devices,
    infer_amd_gfx_target,
    select_amd_runtime_plan,
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
        hip_version="7.14.0",
        devices=("AMD Radeon RX 9070 XT",),
    )
    attached = attach_amd_runtime_devices(physical, ready)[0]
    assert attached.translation_target == f"{AMD_RUNTIME_TARGET_PREFIX}0"
    assert "ROCm 7.14.0" in attached.backend


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


def test_current_radeon_families_select_the_exact_official_target() -> None:
    expected = {
        "AMD Radeon RX 9070 XT": "gfx1201",
        "AMD Radeon RX 9060 XT": "gfx1200",
        "AMD Radeon RX 7900 XTX": "gfx1100",
        "AMD Radeon RX 7800 XT": "gfx1101",
        "AMD Radeon RX 7600 XT": "gfx1102",
        "AMD Radeon RX 6800 XT": "gfx1030",
        "AMD Radeon 890M Graphics": "gfx1150",
        "AMD Radeon 780M Graphics": "gfx1103",
    }
    assert ROCM_VERSION == "7.14.0"
    for name, target in expected.items():
        assert infer_amd_gfx_target(name) == target
    compile(AMD_GPU_PROBE_CODE, "<amd-gpu-probe>", "exec")


def test_rx_9070_xt_plan_uses_small_gfx1201_pytorch_extra() -> None:
    plan = select_amd_runtime_plan(("AMD Radeon RX 9070 XT",))

    assert plan is not None
    assert plan.target == "gfx1201"
    assert plan.torch_requirement == "torch[device-gfx1201]==2.12.0+rocm7.14.0"


def test_mixed_supported_radeons_use_device_all() -> None:
    plan = select_amd_runtime_plan(
        ("AMD Radeon RX 9070 XT", "AMD Radeon RX 7900 XTX")
    )

    assert plan is not None
    assert plan.target == "all"
    assert "[device-all]" in plan.torch_requirement


def test_unsupported_old_radeon_does_not_fake_rocm_support() -> None:
    assert infer_amd_gfx_target("AMD Radeon RX 580") is None
    assert select_amd_runtime_plan(("AMD Radeon RX 580",)) is None
