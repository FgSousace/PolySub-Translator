from __future__ import annotations

from collections.abc import Sequence

from .base import TranslationEngine, TranslationEngineError


class M2M100Engine(TranslationEngine):
    name = "m2m100"
    display_name = "Lokalny AI (M2M100)"
    max_batch_size = 8
    supports_context = False

    def __init__(self, model_name: str = "facebook/m2m100_418M", device: str | None = None) -> None:
        try:
            import torch
            from transformers import M2M100ForConditionalGeneration, M2M100Tokenizer
        except ImportError as exc:
            raise TranslationEngineError(
                'Brakuje pakietów lokalnego AI. Uruchom: pip install -e ".[local]"'
            ) from exc

        self._torch = torch
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        try:
            self.tokenizer = M2M100Tokenizer.from_pretrained(model_name)
            self.model = M2M100ForConditionalGeneration.from_pretrained(model_name)
            self.model.to(self.device)
            self.model.eval()
        except Exception as exc:  # model loaders expose several backend-specific exceptions
            raise TranslationEngineError(
                f"Nie udało się wczytać modelu {model_name}: {exc}"
            ) from exc

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

        encoded = self.tokenizer(
            list(texts),
            return_tensors="pt",
            padding=True,
            truncation=True,
            max_length=512,
        )
        encoded = {key: value.to(self.device) for key, value in encoded.items()}
        try:
            with self._torch.inference_mode():
                generated = self.model.generate(
                    **encoded,
                    forced_bos_token_id=target_id,
                    num_beams=5 if accurate else 2,
                    max_new_tokens=256,
                    early_stopping=True,
                )
        except Exception as exc:
            raise TranslationEngineError(f"Lokalne tłumaczenie nie powiodło się: {exc}") from exc
        return self.tokenizer.batch_decode(generated, skip_special_tokens=True)
