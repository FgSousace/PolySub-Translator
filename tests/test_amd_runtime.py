import zipfile
from pathlib import Path

import polysub.amd_runtime as amd_runtime
from polysub.amd_runtime import (
    AMD_GPU_INVENTORY_CODE,
    AMD_GPU_PROBE_CODE,
    AMD_RUNTIME_TARGET_PREFIX,
    ROCM_VERSION,
    AmdRuntimeStatus,
    amd_worker_environment,
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
        runtime_indices=(1,),
    )
    attached = attach_amd_runtime_devices(physical, ready)[0]
    assert attached.translation_target == f"{AMD_RUNTIME_TARGET_PREFIX}1"
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
        runtime_indices=(1, 3),
    )
    attached = attach_amd_runtime_devices(devices, ready)
    assert [device.translation_target for device in attached] == [
        f"{AMD_RUNTIME_TARGET_PREFIX}1",
        f"{AMD_RUNTIME_TARGET_PREFIX}3",
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
    compile(AMD_GPU_INVENTORY_CODE, "<amd-gpu-inventory>", "exec")
    compile(AMD_GPU_PROBE_CODE, "<amd-gpu-probe>", "exec")


def test_rx_9070_xt_behind_ryzen_igpu_keeps_its_real_hip_index() -> None:
    physical = [
        ComputeDevice(
            id="amd-igpu",
            name="AMD Radeon(TM) Graphics",
            kind="gpu",
            vendor="AMD",
            backend="wykryta przez system",
        ),
        ComputeDevice(
            id="amd-dgpu",
            name="AMD Radeon RX 9070 XT",
            kind="gpu",
            vendor="AMD",
            backend="wykryta przez system",
        ),
    ]
    ready = AmdRuntimeStatus(
        installed=True,
        ready=True,
        hip_version="7.14.0",
        devices=("AMD Radeon RX 9070 XT",),
        architectures=("gfx1201:sramecc-:xnack-",),
        runtime_indices=(1,),
        target="gfx1201",
    )

    attached = attach_amd_runtime_devices(physical, ready)

    assert attached[0].translation_target is None
    assert attached[1].translation_target == f"{AMD_RUNTIME_TARGET_PREFIX}1"


def test_amd_worker_masks_igpu_and_remaps_selected_radeon_to_cuda_zero() -> None:
    environment = amd_worker_environment(1)

    assert environment["HIP_VISIBLE_DEVICES"] == "1"
    assert "CUDA_VISIBLE_DEVICES" not in environment


def test_probe_skips_ryzen_igpu_and_accepts_masked_rx_9070_xt(
    monkeypatch,
    tmp_path: Path,
) -> None:
    python_path = tmp_path / "python.exe"
    python_path.touch()
    masks: list[str | None] = []

    def fake_run(_python, code, *, timeout, environment):
        del timeout
        masks.append(environment.get("HIP_VISIBLE_DEVICES"))
        if code == AMD_GPU_INVENTORY_CODE:
            return {"hip": "7.14.0", "count": 2}, ""
        if environment.get("HIP_VISIBLE_DEVICES") == "0":
            return None, "iGPU nie zawiera kernela gfx1036"
        return {
            "available": True,
            "hip": "7.14.0",
            "name": "AMD Radeon RX 9070 XT",
            "architecture": "gfx1201:sramecc-:xnack-",
            "value": 64.0,
        }, ""

    monkeypatch.setattr(amd_runtime, "amd_runtime_python", lambda: python_path)
    monkeypatch.setattr(
        amd_runtime,
        "_load_runtime_manifest",
        lambda: {"target": "gfx1201"},
    )
    monkeypatch.setattr(amd_runtime, "_run_amd_json_command", fake_run)

    result = amd_runtime.probe_amd_runtime(timeout=45.0)

    assert result.ready
    assert result.devices == ("AMD Radeon RX 9070 XT",)
    assert result.runtime_indices == (1,)
    assert masks == [None, "0", "1"]


def test_rx_9070_xt_plan_uses_small_gfx1201_pytorch_extra() -> None:
    plan = select_amd_runtime_plan(("AMD Radeon RX 9070 XT",))

    assert plan is not None
    assert plan.target == "gfx1201"
    assert plan.torch_requirement == "torch[device-gfx1201]==2.12.0+rocm7.14.0"


def test_rocm_install_command_allows_amds_source_metapackage(tmp_path: Path) -> None:
    plan = select_amd_runtime_plan(("AMD Radeon RX 9070 XT",))

    assert plan is not None
    command = amd_runtime._amd_torch_install_command(tmp_path / "python.exe", plan)

    assert "--only-binary" not in command
    assert "--no-build-isolation" in command
    assert "--prefer-binary" in command
    assert command[command.index("--index-url") + 1] == amd_runtime.ROCM_INDEX_URL
    assert command[-1] == plan.torch_requirement


def test_rocm_build_backend_is_installed_from_binary_wheels(tmp_path: Path) -> None:
    command = amd_runtime._amd_build_backend_install_command(tmp_path / "python.exe")

    assert command[0] == str(tmp_path / "python.exe")
    assert command[command.index("--only-binary") + 1] == ":all:"
    assert command[command.index("--index-url") + 1] == "https://pypi.org/simple"
    assert "setuptools>=70.2,<82" in command
    assert "wheel>=0.44,<1" in command


def test_embedded_pip_uses_a_pinned_wheel_instead_of_downloaded_script(
    monkeypatch,
    tmp_path: Path,
) -> None:
    runtime_dir = tmp_path / "runtime"
    site_packages = runtime_dir / "Lib" / "site-packages"
    site_packages.mkdir(parents=True)
    downloads: list[tuple[str, Path, str | None]] = []

    def fake_download(url, destination, _status, *, expected_sha256=None):
        downloads.append((url, destination, expected_sha256))
        destination.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(destination, "w") as archive:
            archive.writestr("pip/__init__.py", "__version__ = '25.2'\n")

    monkeypatch.setattr(amd_runtime, "_download_file", fake_download)
    monkeypatch.setattr(amd_runtime, "_embedded_pip_ready", lambda _path: True)
    monkeypatch.setattr(amd_runtime, "amd_runtime_python", lambda: runtime_dir / "python.exe")

    amd_runtime._bootstrap_embedded_pip(runtime_dir, lambda _message: None)

    assert downloads == [
        (
            amd_runtime.PIP_WHEEL_URL,
            tmp_path / "amd-runtime-downloads" / "pip-25.2-py3-none-any.whl",
            amd_runtime.PIP_WHEEL_SHA256,
        )
    ]
    assert (site_packages / "pip" / "__init__.py").is_file()
    assert "get-pip.py" not in amd_runtime.PIP_WHEEL_URL


def test_automatic_rocm_setup_repairs_a_previous_failed_install(
    monkeypatch,
    tmp_path: Path,
) -> None:
    python_path = tmp_path / "python.exe"
    python_path.touch()
    probes = iter(
        (
            AmdRuntimeStatus(
                installed=True,
                ready=False,
                python_path=python_path,
                message="Poprzednia instalacja jest nieukończona.",
            ),
            AmdRuntimeStatus(
                installed=True,
                ready=True,
                python_path=python_path,
                hip_version="7.14.0",
                devices=("AMD Radeon RX 9070 XT",),
                architectures=("gfx1201",),
                runtime_indices=(1,),
                target="gfx1201",
                message="AMD ROCm gotowe.",
            ),
        )
    )
    commands: list[list[str]] = []

    monkeypatch.setattr(amd_runtime.os, "name", "nt")
    monkeypatch.setattr(amd_runtime.platform, "machine", lambda: "AMD64")
    monkeypatch.setattr(amd_runtime, "_windows_build_number", lambda: 26200)
    monkeypatch.setattr(amd_runtime, "amd_runtime_directory", lambda: tmp_path)
    monkeypatch.setattr(amd_runtime, "amd_runtime_python", lambda: python_path)
    monkeypatch.setattr(amd_runtime, "_embedded_python_core_ready", lambda _path: True)
    monkeypatch.setattr(amd_runtime, "_embedded_pip_ready", lambda _path: True)
    monkeypatch.setattr(amd_runtime, "probe_amd_runtime", lambda **_kwargs: next(probes))
    monkeypatch.setattr(
        amd_runtime,
        "_run_install_command",
        lambda command, _status, _message: commands.append(command),
    )
    monkeypatch.setattr(amd_runtime, "_write_runtime_manifest", lambda _plan: None)
    monkeypatch.setattr(amd_runtime, "write_amd_runtime_diagnostic", lambda _message: None)

    result = amd_runtime.install_amd_runtime(("AMD Radeon RX 9070 XT",))

    assert result.ready
    assert len(commands) == 3
    assert "setuptools>=70.2,<82" in commands[0]
    assert "wheel>=0.44,<1" in commands[0]
    assert "--no-build-isolation" in commands[1]
    assert "--only-binary" not in commands[1]
    assert commands[1][-1] == "torch[device-gfx1201]==2.12.0+rocm7.14.0"
    assert "transformers>=4.55.5,<6" in commands[2]


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
