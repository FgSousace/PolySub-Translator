import sys
from contextlib import nullcontext
from types import ModuleType, SimpleNamespace

from polysub.engines.m2m100 import M2M100Engine


class FakeTensor:
    def __init__(self, device="cpu") -> None:
        self.device = device

    def to(self, device):
        return FakeTensor(str(device))


class FakeTokenizer:
    src_lang = ""

    @classmethod
    def from_pretrained(cls, _model_name):
        return cls()

    def get_lang_id(self, _language):
        return 7

    def __call__(self, *_args, **_kwargs):
        return {"input_ids": FakeTensor()}

    def batch_decode(self, _generated, **_kwargs):
        return ["przetłumaczone"]


def _install_fake_modules(monkeypatch, model_class) -> None:
    thread_calls = []
    torch = ModuleType("torch")
    torch.cuda = SimpleNamespace(is_available=lambda: True)
    torch.xpu = SimpleNamespace(is_available=lambda: False)
    torch.inference_mode = nullcontext
    torch.set_num_threads = lambda value: thread_calls.append(("intra", value))
    torch.set_num_interop_threads = lambda value: thread_calls.append(("interop", value))
    transformers = ModuleType("transformers")
    transformers.M2M100ForConditionalGeneration = model_class
    transformers.M2M100Tokenizer = FakeTokenizer
    monkeypatch.setitem(sys.modules, "torch", torch)
    monkeypatch.setitem(sys.modules, "transformers", transformers)
    return thread_calls


def test_cpu_limit_configures_real_torch_threads_and_larger_batch(monkeypatch) -> None:
    class FakeModel:
        @classmethod
        def from_pretrained(cls, _model_name):
            return cls()

        def to(self, _device):
            return self

        def eval(self):
            return self

    monkeypatch.setattr("polysub.performance.os.cpu_count", lambda: 16)
    thread_calls = _install_fake_modules(monkeypatch, FakeModel)
    statuses = []

    engine = M2M100Engine(
        device="cpu",
        cpu_usage_limit=100,
        status=statuses.append,
    )

    assert thread_calls == [("intra", 16), ("interop", 1)]
    assert engine.max_batch_size == 16
    assert engine.name == "m2m100"
    assert any("16 z 16 logicznych wątków" in status for status in statuses)


def test_model_loading_falls_back_to_cpu_when_selected_gpu_fails(monkeypatch) -> None:
    class FakeModel:
        @classmethod
        def from_pretrained(cls, _model_name):
            return cls()

        def to(self, device):
            if str(device).startswith("cuda"):
                raise RuntimeError("GPU niedostępne")
            return self

        def eval(self):
            return self

        def generate(self, **_kwargs):
            return [1]

    _install_fake_modules(monkeypatch, FakeModel)
    statuses = []

    engine = M2M100Engine(device="cuda:0", status=statuses.append)

    assert engine.device == "cpu"
    assert any("przełączanie na CPU" in status for status in statuses)


def test_translation_retries_on_cpu_after_gpu_generation_error(monkeypatch) -> None:
    class FakeModel:
        @classmethod
        def from_pretrained(cls, _model_name):
            return cls()

        def to(self, device):
            self.device = str(device)
            return self

        def eval(self):
            return self

        def generate(self, **kwargs):
            if kwargs["input_ids"].device.startswith("cuda"):
                raise RuntimeError("brak pamięci")
            return [1]

    _install_fake_modules(monkeypatch, FakeModel)
    statuses = []
    engine = M2M100Engine(device="cuda:0", status=statuses.append)

    result = engine.translate_batch(
        ["translated"],
        source_language="en",
        target_language="pl",
    )

    assert result == ["przetłumaczone"]
    assert engine.device == "cpu"
    assert any("nie wykonało tłumaczenia" in status for status in statuses)
