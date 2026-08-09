from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path

from ..performance import (
    DEFAULT_CPU_USAGE,
    configure_thread_environment,
    configure_torch_threads,
    cpu_allocation,
    translation_batch_size,
)
from ..translation_models import ModelFamily, TranslationModelSpec
from .base import TranslationEngine, TranslationEngineError
from .m2m100 import M2M100Engine

StatusCallback = Callable[[str], None]


class TransformersTranslationEngine(TranslationEngine):
    supports_context = False

    def __init__(
        self,
        model: TranslationModelSpec,
        *,
        model_source: str | Path | None = None,
        device: str | None = None,
        status: StatusCallback | None = None,
        allow_cpu_fallback: bool = True,
        cpu_usage_limit: int = DEFAULT_CPU_USAGE,
    ) -> None:
        status = status or (lambda _message: None)
        self.spec = model
        self.name = f"local:{model.id}"
        self.display_name = f"Lokalny AI ({model.display_name})"
        self._status = status
        self._allow_cpu_fallback = allow_cpu_fallback
        self._cpu_allocation = cpu_allocation(cpu_usage_limit)
        configure_thread_environment(self._cpu_allocation)
        status("Ładowanie bibliotek lokalnego AI...")
        try:
            import torch
            from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
        except ImportError as exc:
            raise TranslationEngineError(
                'Brakuje pakietów lokalnego AI. Uruchom: pip install -e ".[local]"'
            ) from exc

        self._torch = torch
        configure_torch_threads(torch, self._cpu_allocation)
        self.device = device or self._automatic_torch_device()
        status(f"Urządzenie obliczeniowe: {self.device.upper()}.")
        status(
            "Limit CPU: "
            f"{self._cpu_allocation.threads} z "
            f"{self._cpu_allocation.logical_processors} logicznych wątków "
            f"({self._cpu_allocation.percentage}%)."
        )
        source = model_source or model.repo_id
        try:
            status(f"Odczytywanie tokenizera {model.display_name}...")
            self.tokenizer = AutoTokenizer.from_pretrained(
                source,
                trust_remote_code=False,
            )
            status(f"Odczytywanie modelu {model.display_name}...")
            self.model = AutoModelForSeq2SeqLM.from_pretrained(
                source,
                trust_remote_code=False,
            )
        except Exception as exc:
            raise TranslationEngineError(
                f"Nie udało się wczytać modelu {model.display_name}: {exc}"
            ) from exc
        self._move_model_to_selected_device()
        self.max_batch_size = self._resolved_batch_size()
        self.model.eval()
        status(f"Model {model.display_name} jest gotowy.")

    def translate_batch(
        self,
        texts: Sequence[str],
        *,
        source_language: str,
        target_language: str,
        contexts: Sequence[str | None] | None = None,
        accurate: bool = False,
    ) -> list[str]:
        if not texts:
            return []
        if not self.spec.supports_pair(source_language, target_language):
            raise TranslationEngineError(
                f"Model {self.spec.display_name} nie obsługuje pary językowej "
                f"{source_language} → {target_language}."
            )
        prepared = self._prepare_texts(texts, target_language)
        forced_bos_token_id = self._prepare_languages(source_language, target_language)
        encoded_on_cpu = self.tokenizer(
            prepared,
            return_tensors="pt",
            padding=True,
            truncation=True,
            max_length=512,
        )
        try:
            generated = self._generate(encoded_on_cpu, forced_bos_token_id, accurate)
        except Exception as exc:
            if self.device != "cpu" and self._allow_cpu_fallback:
                self._status(
                    f"Urządzenie {self.device.upper()} nie wykonało tłumaczenia: {exc}. "
                    "Automatyczne przełączanie na CPU..."
                )
                self.device = "cpu"
                self.max_batch_size = self._resolved_batch_size()
                try:
                    self.model.to("cpu")
                    generated = self._generate(
                        encoded_on_cpu,
                        forced_bos_token_id,
                        accurate,
                    )
                except Exception as cpu_exc:
                    raise TranslationEngineError(
                        f"Lokalne tłumaczenie nie powiodło się także na CPU: {cpu_exc}"
                    ) from cpu_exc
            else:
                raise TranslationEngineError(
                    f"Lokalne tłumaczenie nie powiodło się: {exc}"
                ) from exc
        return self.tokenizer.batch_decode(generated, skip_special_tokens=True)

    def _prepare_texts(
        self,
        texts: Sequence[str],
        target_language: str,
    ) -> list[str]:
        target_token = self.spec.target_token(target_language)
        if self.spec.family is ModelFamily.MADLAD:
            return [f"<2{target_token}> {text}" for text in texts]
        if self.spec.family is ModelFamily.MARIAN and self.spec.target_prefix_codes:
            return [f">>{target_token}<< {text}" for text in texts]
        return list(texts)

    def _prepare_languages(self, source_language: str, target_language: str) -> int | None:
        if self.spec.family not in {ModelFamily.NLLB, ModelFamily.MBART50}:
            return None
        source_token = self.spec.source_token(source_language)
        target_token = self.spec.target_token(target_language)
        self.tokenizer.src_lang = source_token
        language_ids = getattr(self.tokenizer, "lang_code_to_id", {})
        target_id = language_ids.get(target_token) if language_ids else None
        if target_id is None:
            target_id = self.tokenizer.convert_tokens_to_ids(target_token)
        if target_id is None or target_id == getattr(self.tokenizer, "unk_token_id", -1):
            raise TranslationEngineError(
                f"Tokenizer {self.spec.display_name} nie zna języka {target_language}."
            )
        return int(target_id)

    def _generate(self, encoded_on_cpu, forced_bos_token_id: int | None, accurate: bool):
        encoded = {key: value.to(self.device) for key, value in encoded_on_cpu.items()}
        generation = {
            "num_beams": 5 if accurate else 2,
            "max_new_tokens": 256,
            "early_stopping": True,
        }
        if forced_bos_token_id is not None:
            generation["forced_bos_token_id"] = forced_bos_token_id
        with self._torch.inference_mode():
            return self.model.generate(**encoded, **generation)

    def _automatic_torch_device(self) -> str:
        try:
            if self._torch.cuda.is_available():
                return "cuda:0"
        except Exception:
            pass
        try:
            if self._torch.xpu.is_available():
                return "xpu:0"
        except Exception:
            pass
        return "cpu"

    def _move_model_to_selected_device(self) -> None:
        self._status(f"Przenoszenie modelu na urządzenie {self.device.upper()}...")
        try:
            self.model.to(self.device)
        except Exception as exc:
            if self.device == "cpu" or not self._allow_cpu_fallback:
                raise TranslationEngineError(
                    f"Nie udało się uruchomić modelu na {self.device}: {exc}"
                ) from exc
            self._status(
                f"Nie udało się użyć {self.device.upper()}: {exc}. "
                "Automatyczne przełączanie na CPU..."
            )
            self.device = "cpu"
            try:
                self.model.to("cpu")
            except Exception as cpu_exc:
                raise TranslationEngineError(
                    f"Nie udało się uruchomić modelu także na CPU: {cpu_exc}"
                ) from cpu_exc

    def _resolved_batch_size(self) -> int:
        return min(
            translation_batch_size(self._cpu_allocation, self.device),
            self.spec.batch_cap,
        )


def create_local_engine(
    model: TranslationModelSpec,
    *,
    model_source: str | Path | None = None,
    device: str | None = None,
    status: StatusCallback | None = None,
    allow_cpu_fallback: bool = True,
    cpu_usage_limit: int = DEFAULT_CPU_USAGE,
) -> TranslationEngine:
    if model.family is ModelFamily.M2M100:
        return M2M100Engine(
            model_name=str(model_source or model.repo_id),
            device=device,
            status=status,
            allow_cpu_fallback=allow_cpu_fallback,
            cpu_usage_limit=cpu_usage_limit,
            engine_id=model.id,
            display_name=f"Lokalny AI ({model.display_name})",
            batch_cap=model.batch_cap,
        )
    return TransformersTranslationEngine(
        model,
        model_source=model_source,
        device=device,
        status=status,
        allow_cpu_fallback=allow_cpu_fallback,
        cpu_usage_limit=cpu_usage_limit,
    )
