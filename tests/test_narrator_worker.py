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


def test_chatterbox_worker_uses_native_v3_api_when_available(tmp_path: Path) -> None:
    worker = _load_worker_module()
    (tmp_path / worker.V3_T3_FILENAME).write_bytes(b"v3")
    calls: list[tuple[Path, str, str | None]] = []

    class CurrentChatterbox:
        @classmethod
        def from_local(cls, model_dir, device, t3_model=None):
            calls.append((Path(model_dir), device, t3_model))
            return "current-v3-model"

    mtl_module = SimpleNamespace(ChatterboxMultilingualTTS=CurrentChatterbox)

    model = worker._load_chatterbox_multilingual_v3(
        tmp_path,
        device="cpu",
        mtl_module=mtl_module,
    )

    assert model == "current-v3-model"
    assert calls == [(tmp_path, "cpu", "v3")]


def test_chatterbox_worker_loads_v3_with_released_017_api(tmp_path: Path) -> None:
    worker = _load_worker_module()
    (tmp_path / worker.V3_T3_FILENAME).write_bytes(b"v3")
    (tmp_path / "conds.pt").write_bytes(b"voice")
    events: list[tuple[str, str]] = []

    class Component:
        def __init__(self, name):
            self.name = name

        def load_state_dict(self, _state):
            events.append(("state", self.name))

        def to(self, device):
            events.append(("device", str(device)))
            return self

        def eval(self):
            return self

    class FakeTorch:
        @staticmethod
        def device(name):
            return f"torch:{name}"

        @staticmethod
        def load(path, *, map_location, weights_only):
            assert map_location == "torch:cpu"
            assert weights_only is True
            events.append(("torch", Path(path).name))
            return {"weight": Path(path).name}

    class FakeT3Config:
        @staticmethod
        def multilingual():
            return "multilingual"

    class FakeConditionals:
        @staticmethod
        def load(path, *, map_location):
            assert map_location == "torch:cpu"
            events.append(("conditionals", Path(path).name))
            return Component("conditionals")

    class Released017Chatterbox:
        @classmethod
        def from_local(cls, model_dir, device):
            raise AssertionError("The 0.1.7 API would hardcode the V2 checkpoint")

        def __init__(self, t3, s3gen, voice_encoder, tokenizer, device, *, conds):
            self.t3 = t3
            self.s3gen = s3gen
            self.voice_encoder = voice_encoder
            self.tokenizer = tokenizer
            self.device = device
            self.conds = conds

    def load_safetensors(path):
        events.append(("safetensors", Path(path).name))
        return {"weight": "v3"}

    mtl_module = SimpleNamespace(
        ChatterboxMultilingualTTS=Released017Chatterbox,
        Conditionals=FakeConditionals,
        MTLTokenizer=lambda path: ("tokenizer", path),
        S3Gen=lambda: Component("s3gen"),
        T3=lambda _config: Component("t3"),
        T3Config=FakeT3Config,
        VoiceEncoder=lambda: Component("voice-encoder"),
        load_safetensors=load_safetensors,
        torch=FakeTorch,
    )

    model = worker._load_chatterbox_multilingual_v3(
        tmp_path,
        device="cpu",
        mtl_module=mtl_module,
    )

    assert model.device == "cpu"
    assert ("safetensors", worker.V3_T3_FILENAME) in events
    assert ("torch", "ve.pt") in events
    assert ("torch", "s3gen.pt") in events
    assert ("conditionals", "conds.pt") in events
    assert model.tokenizer == (
        "tokenizer",
        str(tmp_path / "grapheme_mtl_merged_expanded_v1.json"),
    )
