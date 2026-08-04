from __future__ import annotations

from collections.abc import Callable, Sequence

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
    ) -> None:
        status = status or (lambda _message: None)
        self._status = status
        self._allow_cpu_fallback = allow_cpu_fallback
        status("Ładowanie bibliotek lokalnego AI...")
        try:
            import torch
            from transformers import M2M100ForConditionalGeneration, M2M100Tokenizer
        except ImportError as exc:
            raise TranslationEngineError(
                'Brakuje pakietów lokalnego AI. Uruchom: pip install -e ".[local]"'
            ) from exc

        self._torch = torch
        self.device = device or self._automatic_torch_device()
        status(f"Urządzenie obliczeniowe: {self.device.upper()}.")
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
        self.model.eval()
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
            if self.device != "cpu" and self._allow_cpu_fallback:
                self._status(
                    f"Urządzenie {self.device.upper()} nie wykonało tłumaczenia: {exc}. "
                    "Automatyczne przełączanie na CPU..."
                )
                self.device = "cpu"
                try:
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

    def _generate(self, encoded_on_cpu, target_id: int, accurate: bool):
        encoded = {key: value.to(self.device) for key, value in encoded_on_cpu.items()}
        with self._torch.inference_mode():
            return self.model.generate(
                **encoded,
                forced_bos_token_id=target_id,
                num_beams=5 if accurate else 2,
                max_new_tokens=256,
                early_stopping=True,
            )
