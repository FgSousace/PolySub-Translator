import json
from pathlib import Path
from types import SimpleNamespace

import polysub.narrator_runtime as narrator_runtime


def test_narrator_worker_environment_forces_cpu(monkeypatch) -> None:
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "4")
    monkeypatch.setattr(narrator_runtime, "_ACTIVE_RUNTIME", None)

    environment = narrator_runtime.narrator_worker_environment(threads=3)

    assert environment["CUDA_VISIBLE_DEVICES"] == ""
    assert environment["POLYSUB_NARRATOR_DEVICE"] == "cpu"
    assert environment["POLYSUB_NARRATOR_BACKEND"] == "cpu"
    assert environment["PYTHONUTF8"] == "1"
    assert environment["HF_HUB_OFFLINE"] == "1"
    assert environment["TRANSFORMERS_OFFLINE"] == "1"
    assert environment["OMP_NUM_THREADS"] == "3"
    assert environment["MKL_NUM_THREADS"] == "3"


def test_narrator_worker_environment_masks_selected_rocm_device(monkeypatch) -> None:
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "9")
    monkeypatch.setattr(
        narrator_runtime,
        "_ACTIVE_RUNTIME",
        narrator_runtime.NarratorRuntimeSelection(
            python_path=Path("amd-python.exe"),
            device="cuda:0",
            backend="rocm",
            device_index=1,
            label="AMD Radeon RX 9070 XT",
        ),
    )

    environment = narrator_runtime.narrator_worker_environment(threads=5)

    assert "CUDA_VISIBLE_DEVICES" not in environment
    assert environment["HIP_VISIBLE_DEVICES"] == "1"
    assert environment["POLYSUB_NARRATOR_DEVICE"] == "cuda:0"
    assert environment["POLYSUB_NARRATOR_BACKEND"] == "rocm"
    assert environment["OMP_NUM_THREADS"] == "5"


def test_windows_narrator_runtime_installs_official_cpu_stack(
    monkeypatch,
    tmp_path: Path,
) -> None:
    runtime_dir = tmp_path / "narrator-runtime"
    python_path = runtime_dir / "python.exe"
    commands: list[list[str]] = []
    ready_checks = iter((False, True))

    def fake_install_embedded(target: Path, _status) -> None:
        target.mkdir(parents=True, exist_ok=True)
        (target / "python.exe").touch()

    monkeypatch.setattr(narrator_runtime.os, "name", "nt")
    monkeypatch.setattr(narrator_runtime.platform, "machine", lambda: "AMD64")
    monkeypatch.setattr(narrator_runtime, "_detected_gpu_names", lambda: ())
    monkeypatch.setattr(narrator_runtime, "narrator_runtime_directory", lambda: runtime_dir)
    monkeypatch.setattr(
        narrator_runtime,
        "_runtime_ready",
        lambda _python, **_kwargs: next(ready_checks),
    )
    monkeypatch.setattr(narrator_runtime, "_embedded_python_core_ready", lambda _python: False)
    monkeypatch.setattr(narrator_runtime, "_install_embedded_python", fake_install_embedded)
    monkeypatch.setattr(
        narrator_runtime,
        "_run_install_command",
        lambda command, _status, _message: commands.append(command),
    )

    installed = narrator_runtime.install_narrator_runtime()

    assert installed == python_path
    assert len(commands) == 3
    assert commands[0][commands[0].index("--index-url") + 1] == (
        "https://download.pytorch.org/whl/cpu"
    )
    assert "torch==2.6.0" in commands[0]
    assert "torchaudio==2.6.0" in commands[0]
    assert "transformers==5.2.0" in commands[1]
    assert "resemble-perth==1.0.1" in commands[1]
    assert "tiktoken" in commands[1]
    assert "--no-deps" in commands[2]
    assert commands[2][-1] == "chatterbox-tts==0.1.7"
    manifest = json.loads(
        narrator_runtime.narrator_runtime_manifest(python_path).read_text(encoding="utf-8")
    )
    assert manifest == {
        "schema": narrator_runtime.NARRATOR_RUNTIME_SCHEMA,
        "chatterbox_version": "0.1.7",
        "backend": "cpu",
        "device": "cpu",
        "device_index": None,
        "rocm_version": None,
        "torchaudio_version": "2.6.0",
    }


def test_windows_narrator_runtime_prefers_rx_9070_xt_rocm(
    monkeypatch,
    tmp_path: Path,
) -> None:
    runtime_dir = tmp_path / "amd-rocm-runtime"
    runtime_dir.mkdir()
    python_path = runtime_dir / "python.exe"
    python_path.touch()
    commands: list[list[str]] = []
    ready_checks = iter((False, True))

    monkeypatch.setattr(narrator_runtime.os, "name", "nt")
    monkeypatch.setattr(narrator_runtime.platform, "machine", lambda: "AMD64")
    monkeypatch.setattr(
        narrator_runtime,
        "_detected_gpu_names",
        lambda: ("AMD Radeon RX 9070 XT",),
    )
    monkeypatch.setattr(
        narrator_runtime,
        "install_amd_runtime",
        lambda _names, _status: SimpleNamespace(
            python_path=python_path,
            runtime_indices=(1,),
            devices=("AMD Radeon RX 9070 XT",),
            hip_version="7.14.0",
        ),
    )
    monkeypatch.setattr(
        narrator_runtime,
        "_runtime_ready",
        lambda _python, **_kwargs: next(ready_checks),
    )
    monkeypatch.setattr(
        narrator_runtime,
        "_run_install_command",
        lambda command, _status, _message: commands.append(command),
    )

    installed = narrator_runtime.install_narrator_runtime()

    assert installed == python_path
    assert len(commands) == 3
    assert "--no-deps" in commands[0]
    assert narrator_runtime.ROCM_INDEX_URL in commands[0]
    assert (
        f"torchaudio=={narrator_runtime.AMD_TORCHAUDIO_VERSION}"
        f"+rocm{narrator_runtime.ROCM_VERSION}"
    ) in commands[0]
    assert "transformers==5.2.0" in commands[1]
    assert commands[2][-1] == "chatterbox-tts==0.1.7"

    selection = narrator_runtime.active_narrator_runtime()
    assert selection.backend == "rocm"
    assert selection.device == "cuda:0"
    assert selection.device_index == 1
    assert "RX 9070 XT" in selection.label

    environment = narrator_runtime.narrator_worker_environment()
    assert environment["HIP_VISIBLE_DEVICES"] == "1"
    assert environment["POLYSUB_NARRATOR_DEVICE"] == "cuda:0"

    manifest = json.loads(
        narrator_runtime.narrator_runtime_manifest(python_path).read_text(encoding="utf-8")
    )
    assert manifest["backend"] == "rocm"
    assert manifest["device"] == "cuda:0"
    assert manifest["device_index"] == 1
    assert manifest["rocm_version"] == narrator_runtime.ROCM_VERSION
