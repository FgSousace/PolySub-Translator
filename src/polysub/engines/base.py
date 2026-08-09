from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence


class TranslationEngineError(RuntimeError):
    pass


class TranslationEngine(ABC):
    name = "engine"
    display_name = "Silnik tłumaczenia"
    max_batch_size = 8
    supports_context = False

    def cancel(self) -> None:
        """Request cancellation of an in-flight operation when the backend supports it."""

        return None

    @abstractmethod
    def translate_batch(
        self,
        texts: Sequence[str],
        *,
        source_language: str,
        target_language: str,
        contexts: Sequence[str | None] | None = None,
        accurate: bool = False,
    ) -> list[str]:
        raise NotImplementedError
