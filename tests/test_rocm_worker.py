import io
import json
from pathlib import Path

import polysub.engines.rocm_worker as rocm_worker
from polysub.engines.rocm_worker import RocmWorkerEngine
from polysub.translation_models import DEFAULT_MODEL_ID, get_model_spec


class FakeProcess:
    def __init__(self) -> None:
        self.stdin = io.StringIO()
        self.stdout = io.StringIO('{"type":"ready","max_batch_size":4}\n')
        self._running = True

    def poll(self):
        return None if self._running else 0

    def terminate(self) -> None:
        self._running = False

    def wait(self, timeout=None):
        del timeout
        self._running = False
        return 0

    def kill(self) -> None:
        self._running = False


def test_worker_masks_ryzen_igpu_and_uses_selected_radeon_as_cuda_zero(
    monkeypatch,
    tmp_path: Path,
) -> None:
    python_path = tmp_path / "python.exe"
    worker_path = tmp_path / "amd_worker_entry.py"
    python_source = tmp_path / "src"
    python_path.touch()
    worker_path.touch()
    python_source.mkdir()
    captured: dict[str, object] = {}
    process = FakeProcess()

    def fake_popen(command, **kwargs):
        captured["command"] = command
        captured["environment"] = kwargs["env"]
        return process

    monkeypatch.setattr(rocm_worker, "amd_runtime_python", lambda: python_path)
    monkeypatch.setattr(rocm_worker, "amd_worker_script", lambda: worker_path)
    monkeypatch.setattr(rocm_worker, "amd_worker_pythonpath", lambda: python_source)
    monkeypatch.setattr(rocm_worker.subprocess, "Popen", fake_popen)

    engine = RocmWorkerEngine(
        get_model_spec(DEFAULT_MODEL_ID),
        model_source=tmp_path / "model",
        device_index=1,
    )

    environment = captured["environment"]
    assert isinstance(environment, dict)
    assert environment["HIP_VISIBLE_DEVICES"] == "1"
    assert "CUDA_VISIBLE_DEVICES" not in environment
    init_request = json.loads(process.stdin.getvalue().splitlines()[0])
    assert init_request["device_index"] == 0
    engine.close()
