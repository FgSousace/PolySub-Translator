from __future__ import annotations

from collections.abc import Callable, Sequence

from ..local_ai_runtime import local_ai_dependency_error
from ..performance import (
    DEFAULT_CPU_USAGE,
    accelerator_batch_size,
    configure_thread_environment,
    configure_torch_threads,
    cpu_allocation,
    translation_batch_size,
)
from .base import TranslationEngine, TranslationEngineError

StatusCallback = Callable[[str], None]


class M2M100Engine(TranslationEngine):
    name = "m2m100"
    display_name = "Lokalny AI (M2M100)"
    max_batch_size = 8
    supports_context = False

    def __init__(
        self,
        model_name: str = "facebook/m2m100_418M",
        device: str | None = None,
        status: StatusCallback | None = None,
        allow_cpu_fallback: bool = True,
        cpu_usage_limit: int = DEFAULT_CPU_USAGE,
        engine_id: str = "m2m100-418m",
        display_name: str | None = None,
        batch_cap: int = 16,
    ) -> None:
        status = status or (lambda _message: None)
        self._status = status
        self._allow_cpu_fallback = allow_cpu_fallback
        self._batch_cap = max(int(batch_cap), 1)
        self._using_half_precision = False
        # Keep the historical checkpoint identifier for the default model so work
        # interrupted in PolySub 0.4.6 or older can still be resumed.
        self.name = "m2m100" if engine_id == "m2m100-418m" else f"local:{engine_id}"
        self.display_name = display_name or self.display_name
        self._cpu_allocation = cpu_allocation(cpu_usage_limit)
        configure_thread_environment(self._cpu_allocation)
        status("Ładowanie bibliotek lokalnego AI...")
        try:
            import torch
        except (ImportError, OSError) as exc:
            raise TranslationEngineError(local_ai_dependency_error("PyTorch", exc)) from exc
        try:
            from transformers import M2M100ForConditionalGeneration, M2M100Tokenizer
        except (ImportError, OSError) as exc:
            raise TranslationEngineError(
                local_ai_dependency_error("bibliotek Transformers/M2M100", exc)
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
        try:
            status("Pobieranie lub odczytywanie tokenizera M2M100...")
            self.tokenizer = M2M100Tokenizer.from_pretrained(model_name)
            status("Pobieranie lub odczytywanie modelu M2M100...")
            self.model = M2M100ForConditionalGeneration.from_pretrained(model_name)
        except Exception as exc:  # model loaders expose several backend-specific exceptions
            raise TranslationEngineError(
                f"Nie udało się wczytać modelu {model_name}: {exc}"
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
        status("Lokalny model AI jest gotowy.")

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
        source = source_language.lower().split("-", 1)[0]
        target = target_language.lower().split("-", 1)[0]
        try:
            self.tokenizer.src_lang = source
            target_id = self.tokenizer.get_lang_id(target)
        except (KeyError, ValueError) as exc:
            raise TranslationEngineError(
                f"Lokalny model nie obsługuje pary językowej {source} → {target}."
            ) from exc

        encoded_on_cpu = self.tokenizer(
            list(texts),
            return_tensors="pt",
            padding=True,
            truncation=True,
            max_length=512,
        )
        try:
            generated = self._generate(encoded_on_cpu, target_id, accurate)
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
                    generated = self._generate(encoded_on_cpu, target_id, accurate)
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
                    generated = self._generate(encoded_on_cpu, target_id, accurate)
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

    def _generate(self, encoded_on_cpu, target_id: int, accurate: bool):
        encoded = {key: value.to(self.device) for key, value in encoded_on_cpu.items()}
        generation = {
            "forced_bos_token_id": target_id,
            "num_beams": 5 if accurate else 1,
            "max_new_tokens": 256,
            "use_cache": True,
        }
        if accurate:
            generation["early_stopping"] = True
        with self._torch.inference_mode():
            return self.model.generate(**encoded, **generation)

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
                self._batch_cap,
            )
        return accelerator_batch_size(
            self._torch,
            self.device,
            self._batch_cap,
        )
