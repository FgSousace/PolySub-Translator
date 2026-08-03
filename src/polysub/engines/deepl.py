from __future__ import annotations

import os
from collections.abc import Sequence

import requests

from .base import TranslationEngine, TranslationEngineError

TARGET_OVERRIDES = {"en": "EN-US", "pt": "PT-PT", "zh": "ZH-HANS"}


class DeepLEngine(TranslationEngine):
    name = "deepl"
    display_name = "DeepL API"
    max_batch_size = 40
    supports_context = True

    def __init__(self, api_key: str | None = None, timeout: float = 60.0) -> None:
        self.api_key = (api_key or os.getenv("DEEPL_API_KEY", "")).strip()
        if not self.api_key:
            raise TranslationEngineError(
                "Brak klucza DeepL API. Wpisz go w aplikacji lub ustaw DEEPL_API_KEY."
            )
        self.timeout = timeout
        suffix = "api-free.deepl.com" if self.api_key.endswith(":fx") else "api.deepl.com"
        self.endpoint = f"https://{suffix}/v2/translate"
        self.session = requests.Session()

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
        contexts = list(contexts or [None] * len(texts))
        if len(contexts) != len(texts):
            raise TranslationEngineError("Liczba kontekstów nie zgadza się z liczbą tekstów.")

        # Context differs per subtitle, therefore review mode uses one request per cue.
        if accurate and any(contexts):
            return [
                self._request([text], target_language, context=context)[0]
                for text, context in zip(texts, contexts, strict=True)
            ]
        return self._request(list(texts), target_language, context=None)

    def _request(self, texts: list[str], target_language: str, context: str | None) -> list[str]:
        target = TARGET_OVERRIDES.get(target_language.lower(), target_language.upper())
        payload: dict[str, object] = {
            "text": texts,
            "target_lang": target,
            "preserve_formatting": True,
            "split_sentences": "nonewlines",
        }
        if context:
            payload["context"] = context[:8_000]

        try:
            response = self.session.post(
                self.endpoint,
                headers={
                    "Authorization": f"DeepL-Auth-Key {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise TranslationEngineError(f"Błąd połączenia z DeepL: {exc}") from exc

        if response.status_code >= 400:
            detail = _safe_error(response)
            raise TranslationEngineError(f"DeepL zwrócił błąd {response.status_code}: {detail}")
        try:
            data = response.json()
            translated = [item["text"] for item in data["translations"]]
        except (ValueError, KeyError, TypeError) as exc:
            raise TranslationEngineError("DeepL zwrócił nieprawidłową odpowiedź.") from exc
        if len(translated) != len(texts):
            raise TranslationEngineError("DeepL zwrócił inną liczbę tłumaczeń niż wysłano.")
        return translated


def _safe_error(response: requests.Response) -> str:
    try:
        payload = response.json()
        return str(payload.get("message") or payload.get("detail") or "nieznany błąd")[:500]
    except ValueError:
        return response.text[:500] or "nieznany błąd"
