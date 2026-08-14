import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

WORKER_PATH = Path(__file__).resolve().parents[1] / "packaging" / "narrator_worker_entry.py"


def _load_worker_module():
    spec = importlib.util.spec_from_file_location("polysub_narrator_worker_test", WORKER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_chatterbox_worker_resolves_managed_asset_without_network(tmp_path: Path) -> None:
    worker = _load_worker_module()
    mapping = tmp_path / "Cangjie5_TC.json"
    mapping.write_text("[]", encoding="utf-8")
    tokenizer_module = SimpleNamespace(hf_hub_download=lambda *_args, **_kwargs: "network")

    worker._use_local_chatterbox_assets(tmp_path, tokenizer_module)

    assert tokenizer_module.hf_hub_download(
        "ResembleAI/chatterbox",
        filename="Cangjie5_TC.json",
    ) == str(mapping)
    with pytest.raises(FileNotFoundError):
        tokenizer_module.hf_hub_download("ResembleAI/chatterbox", "missing.json")
