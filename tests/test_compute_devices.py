from types import SimpleNamespace

from polysub.compute_devices import (
    AUTO_DEVICE_ID,
    ComputeDevice,
    HardwareGpu,
    HardwareSnapshot,
    describe_device_support,
    detect_compute_devices,
    resolve_compute_device,
)


class FakeBackend:
    def __init__(self, names=(), available=True) -> None:
        self.names = list(names)
        self.available = available

    def is_available(self):
        return self.available

    def device_count(self):
        return len(self.names)

    def get_device_name(self, index):
        return self.names[index]


class BrokenBackend:
    def is_available(self):
        raise AssertionError("niezgodny sterownik")


def test_detects_real_cpu_and_all_system_gpus_without_fixed_names() -> None:
    snapshot = HardwareSnapshot(
        "AMD Ryzen 7 9700X",
        (
            HardwareGpu("AMD Radeon RX 9070 XT", "PCI\\AMD"),
            HardwareGpu("Intel Arc A770", "PCI\\INTEL"),
        ),
    )
    torch = SimpleNamespace(
        cuda=FakeBackend(available=False),
        xpu=FakeBackend(available=False),
        version=SimpleNamespace(hip=None),
    )

    devices = detect_compute_devices(
        snapshot=snapshot,
        torch_module=torch,
        ctranslate2_module=SimpleNamespace(get_cuda_device_count=lambda: 0),
    )

    assert [device.name for device in devices] == [
        "AMD Ryzen 7 9700X",
        "AMD Radeon RX 9070 XT",
        "Intel Arc A770",
    ]
    assert devices[1].vendor == "AMD"
    assert devices[2].vendor == "Intel"
    assert all(device.id != AUTO_DEVICE_ID for device in devices)


def test_merges_torch_cuda_runtime_with_matching_physical_gpu() -> None:
    snapshot = HardwareSnapshot(
        "Intel Core i7",
        (HardwareGpu("NVIDIA GeForce RTX 4070", "PCI\\NVIDIA"),),
    )
    torch = SimpleNamespace(
        cuda=FakeBackend(["NVIDIA GeForce RTX 4070"]),
        xpu=FakeBackend(available=False),
        version=SimpleNamespace(hip=None),
    )

    devices = detect_compute_devices(
        snapshot=snapshot,
        torch_module=torch,
        ctranslate2_module=SimpleNamespace(get_cuda_device_count=lambda: 1),
    )

    assert len(devices) == 2
    gpu = devices[1]
    assert gpu.translation_target == "cuda:0"
    assert gpu.transcription_target == "cuda"
    assert gpu.backend == "CUDA"


def test_detects_intel_xpu_as_translation_device() -> None:
    snapshot = HardwareSnapshot(
        "Intel Core Ultra 7",
        (HardwareGpu("Intel Arc Graphics", "PCI\\INTEL"),),
    )
    torch = SimpleNamespace(
        cuda=FakeBackend(available=False),
        xpu=FakeBackend(["Intel Arc Graphics"]),
        version=SimpleNamespace(hip=None),
    )

    devices = detect_compute_devices(
        snapshot=snapshot,
        torch_module=torch,
        ctranslate2_module=SimpleNamespace(get_cuda_device_count=lambda: 0),
    )

    assert devices[1].translation_target == "xpu:0"
    assert devices[1].transcription_target is None
    assert "Intel XPU" in devices[1].display_label


def test_keeps_two_identical_gpu_models_as_separate_choices() -> None:
    snapshot = HardwareSnapshot(
        "AMD Threadripper",
        (
            HardwareGpu("NVIDIA GeForce RTX 4090", "PCI\\GPU1"),
            HardwareGpu("NVIDIA GeForce RTX 4090", "PCI\\GPU2"),
        ),
    )
    torch = SimpleNamespace(
        cuda=FakeBackend(["NVIDIA GeForce RTX 4090", "NVIDIA GeForce RTX 4090"]),
        xpu=FakeBackend(available=False),
        version=SimpleNamespace(hip=None),
    )

    devices = detect_compute_devices(
        snapshot=snapshot,
        torch_module=torch,
        ctranslate2_module=SimpleNamespace(get_cuda_device_count=lambda: 2),
    )

    assert len(devices) == 3
    assert devices[1].translation_target == "cuda:0"
    assert devices[1].transcription_index == 0
    assert devices[2].translation_target == "cuda:1"
    assert devices[2].transcription_index == 1
    assert devices[1].id != devices[2].id
    assert devices[2].name.endswith("(urządzenie 2)")


def test_auto_selects_supported_gpu_and_cpu_for_unsupported_task() -> None:
    devices = [
        ComputeDevice(
            id="cpu",
            name="AMD Ryzen",
            kind="cpu",
            vendor="AMD",
            backend="CPU",
            translation_target="cpu",
            transcription_target="cpu",
        ),
        ComputeDevice(
            id="gpu:1",
            name="Intel Arc",
            kind="gpu",
            vendor="Intel",
            backend="Intel XPU",
            translation_target="xpu:0",
        ),
    ]

    translation = resolve_compute_device(devices, AUTO_DEVICE_ID, "translation")
    transcription = resolve_compute_device(devices, AUTO_DEVICE_ID, "transcription")

    assert translation.runtime_device == "xpu:0"
    assert translation.display_name == "Intel Arc"
    assert transcription.runtime_device == "cpu"
    assert not transcription.used_fallback


def test_manual_unsupported_gpu_has_explicit_cpu_fallback() -> None:
    devices = [
        ComputeDevice(
            id="cpu",
            name="Intel Core i5",
            kind="cpu",
            vendor="Intel",
            backend="CPU",
            translation_target="cpu",
            transcription_target="cpu",
        ),
        ComputeDevice(
            id="gpu:amd",
            name="AMD Radeon",
            kind="gpu",
            vendor="AMD",
            backend="wykryta przez system",
        ),
    ]

    result = resolve_compute_device(devices, "gpu:amd", "translation")

    assert result.runtime_device == "cpu"
    assert result.used_fallback
    assert "AMD Radeon" in result.fallback_reason
    assert "procesora" in result.fallback_reason
    assert "CPU awaryjnie" in describe_device_support(devices[1])


def test_broken_optional_backends_do_not_hide_detected_hardware() -> None:
    snapshot = HardwareSnapshot(
        "Intel Core i5",
        (HardwareGpu("AMD Radeon RX 7800 XT", "PCI\\AMD"),),
    )
    torch = SimpleNamespace(
        cuda=BrokenBackend(),
        xpu=BrokenBackend(),
        version=SimpleNamespace(hip=None),
    )

    devices = detect_compute_devices(
        snapshot=snapshot,
        torch_module=torch,
        ctranslate2_module=SimpleNamespace(
            get_cuda_device_count=lambda: (_ for _ in ()).throw(
                AssertionError("niezgodny sterownik")
            )
        ),
    )

    assert [device.name for device in devices] == [
        "Intel Core i5",
        "AMD Radeon RX 7800 XT",
    ]
    assert devices[1].translation_target is None
    assert devices[1].transcription_target is None
