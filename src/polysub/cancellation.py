"""Cooperative cancellation shared by the GUI and translation service.

Required Notice: PolySub Translator™ — Copyright © 2026 fgSousace.
Licensed for noncommercial use only under PolyForm Noncommercial 1.0.0.
"""

from __future__ import annotations

import threading


class TranslationCancelled(RuntimeError):
    """Raised when a user stops an active translation."""


class CancellationToken:
    """A thread-safe, cooperative stop signal."""

    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def is_cancelled(self) -> bool:
        return self._event.is_set()

    def raise_if_cancelled(self) -> None:
        if self.is_cancelled:
            raise TranslationCancelled("Tłumaczenie zostało anulowane przez użytkownika.")
