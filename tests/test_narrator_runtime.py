import json
from pathlib import Path

import polysub.narrator_runtime as narrator_runtime


def test_narrator_worker_environment_forces_cpu(monkeypatch) -> None:
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "4")

    environment = narrator_runtime.narrator_worker_environment(threads=3)

    assert environment["CUDA_VISIBLE_DEVICES"] == ""
    assert environment["PYTHONUTF8"] == "1"
    assert environment["HF_HUB_OFFLINE"] == "1"
    assert environment["TRANSFORMERS_OFFLINE"] == "1"
    assert environment["OMP_NUM_THREADS"] == "3"
    assert environment["MKL_NUM_THREADS"] == "3"


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
    monkeypatch.setattr(narrator_runtime, "narrator_runtime_directory", lambda: runtime_dir)
    monkeypatch.setattr(
        narrator_runtime,
        "_runtime_ready",
        lambda _python: next(ready_checks),
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
    assert "--no-deps" in commands[2]
    assert commands[2][-1] == "chatterbox-tts==0.1.7"
    manifest = json.loads(narrator_runtime.narrator_runtime_manifest().read_text(encoding="utf-8"))
    assert manifest == {
        "schema": narrator_runtime.NARRATOR_RUNTIME_SCHEMA,
        "chatterbox_version": "0.1.7",
        "device": "cpu",
    }
