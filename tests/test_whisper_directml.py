from pathlib import Path

from polysub import compute_devices
from polysub.compute_devices import ComputeDevice
from polysub.whisper_directml import (
    _WORKER_SOURCE,
    _attach_directml_devices,
    _last_json_object,
    _resolve_directml_request,
    _resolve_model_alias,
)


def test_directml_hook_is_installed_during_package_import() -> None:
    assert getattr(compute_devices.detect_compute_devices, "__polysub_directml__", False)


def test_directml_is_added_to_radeon_without_replacing_nvidia_cuda() -> None:
    devices = [
        ComputeDevice(
            id="cpu",
            name="CPU",
            kind="cpu",
            vendor="Inne",
            backend="CPU",
            translation_target="cpu",
            transcription_target="cpu",
        ),
        ComputeDevice(
            id="amd",
            name="AMD Radeon RX 9070 XT",
            kind="gpu",
            vendor="AMD",
            backend="ROCm",
            translation_target="cuda:0",
        ),
        ComputeDevice(
            id="nvidia",
            name="NVIDIA GeForce RTX 4070",
            kind="gpu",
            vendor="NVIDIA",
            backend="CUDA",
            translation_target="cuda:0",
            transcription_target="cuda",
            transcription_index=0,
        ),
    ]

    attached = _attach_directml_devices(devices)

    radeon = next(device for device in attached if device.id == "amd")
    nvidia = next(device for device in attached if device.id == "nvidia")
    assert radeon.transcription_target == "directml|0|AMD Radeon RX 9070 XT"
    assert radeon.transcription_index == 0
    assert "DirectML" in radeon.backend
    assert radeon.translation_target == "cuda:0"
    assert nvidia.transcription_target == "cuda"


def test_directml_request_preserves_selected_gpu_name() -> None:
    index, name = _resolve_directml_request(
        "directml|2|AMD Radeon RX 9070 XT",
        0,
    )

    assert index == 2
    assert name == "AMD Radeon RX 9070 XT"


def test_directml_uses_native_whisper_alias_for_downloaded_ct2_model() -> None:
    assert _resolve_model_alias(Path("C:/models/ctranslate2"), "Whisper Large v3") == "large-v3"
    assert _resolve_model_alias(Path("C:/models/ctranslate2"), "Whisper Medium") == "medium"
    assert _resolve_model_alias("small", "anything") == "small"


def test_worker_parser_ignores_diagnostics_before_json() -> None:
    payload = _last_json_object('warning\nprogress\n{"ok": true, "backend": "directml"}\n')

    assert payload == {"ok": True, "backend": "directml"}


def test_worker_uses_microsoft_directml_attention_and_never_cpu_fallback() -> None:
    assert "torch_directml.device" in _WORKER_SOURCE
    assert "use_dml_attn=True" in _WORKER_SOURCE
    assert '"backend": "directml"' in _WORKER_SOURCE
    assert "model.to('cpu')" not in _WORKER_SOURCE
