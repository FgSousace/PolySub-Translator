import sys
from contextlib import nullcontext
from types import ModuleType, SimpleNamespace

import pytest

from polysub.engines.base import TranslationEngineError
from polysub.engines.local_model import TransformersTranslationEngine
from polysub.translation_models import get_model_spec


class FakeTensor:
    def __init__(self, device: str = "cpu") -> None:
        self.device = device

    def to(self, device):
        return FakeTensor(str(device))


class FakeTokenizer:
    lang_code_to_id = {"pol_Latn": 17, "pl_PL": 23}
    unk_token_id = -1

    @classmethod
    def from_pretrained(cls, _source, **_kwargs):
        return cls()

    def __call__(self, texts, **_kwargs):
        self.last_texts = list(texts)
        return {"input_ids": FakeTensor()}

    def convert_tokens_to_ids(self, _token):
        return 99

    def batch_decode(self, _generated, **_kwargs):
        return ["przetłumaczone"]


class FakeModel:
    @classmethod
    def from_pretrained(cls, _source, **_kwargs):
        return cls()

    def to(self, device):
        self.device = str(device)
        return self

    def eval(self):
        return self

    def generate(self, **kwargs):
        self.last_generation = kwargs
        return [1]


def _install_fake_modules(monkeypatch) -> None:
    torch = ModuleType("torch")
    torch.cuda = SimpleNamespace(is_available=lambda: False)
    torch.xpu = SimpleNamespace(is_available=lambda: False)
    torch.inference_mode = nullcontext
    torch.set_num_threads = lambda _value: None
    torch.set_num_interop_threads = lambda _value: None
    transformers = ModuleType("transformers")
    transformers.AutoModelForSeq2SeqLM = FakeModel
    transformers.AutoTokenizer = FakeTokenizer
    monkeypatch.setitem(sys.modules, "torch", torch)
    monkeypatch.setitem(sys.modules, "transformers", transformers)


def test_madlad_adds_target_language_instruction(monkeypatch) -> None:
    _install_fake_modules(monkeypatch)
    engine = TransformersTranslationEngine(get_model_spec("madlad400-3b"), device="cpu")

    result = engine.translate_batch(
        ["Hello world"],
        source_language="en",
        target_language="pl",
    )

    assert result == ["przetłumaczone"]
    assert engine.tokenizer.last_texts == ["<2pl> Hello world"]
    assert "forced_bos_token_id" not in engine.model.last_generation


def test_nllb_sets_source_and_forced_target_language(monkeypatch) -> None:
    _install_fake_modules(monkeypatch)
    engine = TransformersTranslationEngine(
        get_model_spec("nllb-200-distilled-600m"),
        device="cpu",
    )

    engine.translate_batch(["Hello"], source_language="en", target_language="pl")

    assert engine.tokenizer.src_lang == "eng_Latn"
    assert engine.model.last_generation["forced_bos_token_id"] == 17


def test_mbart50_sets_its_own_language_codes(monkeypatch) -> None:
    _install_fake_modules(monkeypatch)
    engine = TransformersTranslationEngine(
        get_model_spec("mbart50-many-to-many"),
        device="cpu",
    )

    engine.translate_batch(["Hello"], source_language="en", target_language="pl")

    assert engine.tokenizer.src_lang == "en_XX"
    assert engine.model.last_generation["forced_bos_token_id"] == 23


def test_marian_multilingual_target_prefix_is_added(monkeypatch) -> None:
    _install_fake_modules(monkeypatch)
    engine = TransformersTranslationEngine(get_model_spec("opus-en-pl"), device="cpu")

    engine.translate_batch(["Hello"], source_language="en", target_language="pl")

    assert engine.tokenizer.last_texts == [">>pol<< Hello"]


def test_pair_specific_model_rejects_other_languages(monkeypatch) -> None:
    _install_fake_modules(monkeypatch)
    engine = TransformersTranslationEngine(get_model_spec("opus-en-pl"), device="cpu")

    with pytest.raises(TranslationEngineError, match="nie obsługuje pary"):
        engine.translate_batch(["Hallo"], source_language="de", target_language="pl")
