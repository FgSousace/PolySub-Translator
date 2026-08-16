from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path

from ..local_ai_runtime import local_ai_dependency_error
from ..performance import (
    DEFAULT_CPU_USAGE,
    accelerator_batch_size,
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
        self._using_half_precision = False
        configure_thread_environment(self._cpu_allocation)
        status("Ładowanie bibliotek lokalnego AI...")
        try:
            import torch
        except (ImportError, OSError) as exc:
            raise TranslationEngineError(local_ai_dependency_error("PyTorch", exc)) from exc
        try:
            from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
        except (ImportError, OSError) as exc:
            raise TranslationEngineError(
                local_ai_dependency_error("bibliotek Transformers", exc)
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
        self._runtime_batch_limit = self.max_batch_size
        self.model.eval()
        if self.device != "cpu":
            precision = "FP16" if self._using_half_precision else "FP32"
            status(
                f"Tryb maksymalnej wydajności GPU: {precision}, "
                f"partia do {self.max_batch_size} kwestii."
            )
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
        if len(texts) > self._runtime_batch_limit:
            return self._translate_in_runtime_chunks(
                texts,
                source_language=source_language,
                target_language=target_language,
                contexts=contexts,
                accurate=accurate,
            )
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
            if self._is_accelerator_oom(exc) and self.device != "cpu" and len(texts) > 1:
                self._back_off_batch_after_oom(len(texts))
                return self.translate_batch(
                    texts,
                    source_language=source_language,
                    target_language=target_language,
                    contexts=contexts,
                    accurate=accurate,
                )

            if self.device != "cpu" and self._using_half_precision:
                self._status(
                    f"FP16 nie wykonało tej operacji ({exc}). Ponawianie na GPU w FP32..."
                )
                try:
                    self._switch_accelerator_to_float32()
                    generated = self._generate(
                        encoded_on_cpu,
                        forced_bos_token_id,
                        accurate,
                    )
                except Exception as fp32_exc:
                    if (
                        self._is_accelerator_oom(fp32_exc)
                        and self.device != "cpu"
                        and len(texts) > 1
                    ):
                        self._back_off_batch_after_oom(len(texts))
                        return self.translate_batch(
                            texts,
                            source_language=source_language,
                            target_language=target_language,
                            contexts=contexts,
                            accurate=accurate,
                        )
                    exc = fp32_exc
                else:
                    return self.tokenizer.batch_decode(generated, skip_special_tokens=True)

            if self.device != "cpu" and self._allow_cpu_fallback:
                self._status(
                    f"Urządzenie {self.device.upper()} nie wykonało tłumaczenia: {exc}. "
                    "Automatyczne przełączanie na CPU..."
                )
                self.device = "cpu"
                self._using_half_precision = False
                self.max_batch_size = self._resolved_batch_size()
                self._runtime_batch_limit = self.max_batch_size
                try:
                    float_model = getattr(self.model, "float", None)
                    if callable(float_model):
                        float_model()
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

    def _translate_in_runtime_chunks(
        self,
        texts: Sequence[str],
        *,
        source_language: str,
        target_language: str,
        contexts: Sequence[str | None] | None,
        accurate: bool,
    ) -> list[str]:
        results: list[str] = []
        context_values = list(contexts) if contexts is not None else None
        for start in range(0, len(texts), self._runtime_batch_limit):
            end = start + self._runtime_batch_limit
            results.extend(
                self.translate_batch(
                    texts[start:end],
                    source_language=source_language,
                    target_language=target_language,
                    contexts=(context_values[start:end] if context_values is not None else None),
                    accurate=accurate,
                )
            )
        return results

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
            "num_beams": 5 if accurate else 1,
            "max_new_tokens": 256,
            "use_cache": True,
        }
        if accurate:
            generation["early_stopping"] = True
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
        if self.device.startswith("cuda"):
            half_model = getattr(self.model, "half", None)
            if callable(half_model):
                try:
                    half_model()
                    self._using_half_precision = True
                except Exception as exc:
                    self._status(f"FP16 niedostępne dla tego modelu ({exc}); pozostaje FP32.")
                    float_model = getattr(self.model, "float", None)
                    if callable(float_model):
                        float_model()
                    self._using_half_precision = False
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
            self._using_half_precision = False
            try:
                float_model = getattr(self.model, "float", None)
                if callable(float_model):
                    float_model()
                self.model.to("cpu")
            except Exception as cpu_exc:
                raise TranslationEngineError(
                    f"Nie udało się uruchomić modelu także na CPU: {cpu_exc}"
                ) from cpu_exc

    def _switch_accelerator_to_float32(self) -> None:
        float_model = getattr(self.model, "float", None)
        if callable(float_model):
            float_model()
        self.model.to(self.device)
        self._using_half_precision = False
        self._empty_accelerator_cache()

    def _back_off_batch_after_oom(self, failing_batch_size: int) -> None:
        reduced = max(1, failing_batch_size // 2)
        self._runtime_batch_limit = max(1, min(self._runtime_batch_limit, reduced))
        self.max_batch_size = min(self.max_batch_size, self._runtime_batch_limit)
        self._empty_accelerator_cache()
        self._status(
            "VRAM osiągnął limit — bez przełączania na CPU zmniejszam partię do "
            f"{self._runtime_batch_limit} kwestii i ponawiam na GPU."
        )

    def _empty_accelerator_cache(self) -> None:
        try:
            if self.device.startswith("cuda") and self._torch.cuda.is_available():
                self._torch.cuda.empty_cache()
        except Exception:
            pass

    @staticmethod
    def _is_accelerator_oom(exc: BaseException) -> bool:
        detail = str(exc).casefold()
        return any(
            marker in detail
            for marker in (
                "out of memory",
                "hip out of memory",
                "cuda out of memory",
                "memory allocation failed",
            )
        )

    def _resolved_batch_size(self) -> int:
        if self.device == "cpu":
            return min(
                translation_batch_size(self._cpu_allocation, self.device),
                self.spec.batch_cap,
            )
        return accelerator_batch_size(
            self._torch,
            self.device,
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
