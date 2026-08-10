"""Proxy engine for the isolated Windows AMD ROCm worker."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Sequence
from pathlib import Path

from ..amd_runtime import (
    amd_runtime_python,
    amd_worker_environment,
    amd_worker_pythonpath,
    amd_worker_script,
)
from ..translation_models import TranslationModelSpec
from .base import TranslationEngine, TranslationEngineError


class RocmWorkerEngine(TranslationEngine):
    supports_context = False

    def __init__(
        self,
        model: TranslationModelSpec,
        *,
        model_source: Path,
        device_index: int = 0,
        status=None,
        cpu_usage_limit: int = 100,
    ) -> None:
        self.spec = model
        self.name = f"local:{model.id}:rocm"
        self.display_name = f"Lokalny AI ({model.display_name}, AMD ROCm)"
        self._status = status or (lambda _message: None)
        python_path = amd_runtime_python()
        worker = amd_worker_script()
        pythonpath = amd_worker_pythonpath()
        if not python_path.is_file() or not worker.is_file() or not pythonpath.is_dir():
            raise TranslationEngineError(
                "Brakuje kompletnego środowiska AMD ROCm albo pliku workera. "
                "Uruchom ponownie aplikację; PolySub przygotuje je automatycznie."
            )
        environment = amd_worker_environment(device_index)
        environment["PYTHONPATH"] = str(pythonpath)
        self._status(
            f"AMD ROCm: izolowanie urządzenia HIP {max(int(device_index), 0)} "
            "i uruchamianie go jako cuda:0…"
        )
        try:
            self._process = subprocess.Popen(
                [str(python_path), "-u", str(worker)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                env=environment,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except OSError as exc:
            raise TranslationEngineError(f"Nie udało się uruchomić workera AMD: {exc}") from exc
        self._send(
            {
                "command": "init",
                "model_id": model.id,
                "model_source": str(model_source),
                # HIP_VISIBLE_DEVICES masks the Ryzen iGPU and remaps the
                # selected discrete Radeon to cuda:0 inside the worker.
                "device_index": 0,
                "cpu_usage_limit": cpu_usage_limit,
            }
        )
        ready = self._read_until("ready")
        self.max_batch_size = max(int(ready.get("max_batch_size", 1)), 1)

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
        self._send(
            {
                "command": "translate",
                "texts": list(texts),
                "source_language": source_language,
                "target_language": target_language,
                "accurate": bool(accurate),
            }
        )
        response = self._read_until("result")
        translated = response.get("texts")
        if not isinstance(translated, list) or not all(
            isinstance(item, str) for item in translated
        ):
            raise TranslationEngineError("Worker AMD zwrócił nieprawidłowe tłumaczenie.")
        return translated

    def cancel(self) -> None:
        process = getattr(self, "_process", None)
        if process is not None and process.poll() is None:
            process.terminate()

    def close(self) -> None:
        process = getattr(self, "_process", None)
        if process is None:
            return
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
        for stream in (process.stdin, process.stdout):
            if stream is not None:
                try:
                    stream.close()
                except OSError:
                    pass

    def _send(self, payload: dict[str, object]) -> None:
        if self._process.poll() is not None or self._process.stdin is None:
            raise TranslationEngineError("Proces AMD ROCm został nieoczekiwanie zakończony.")
        try:
            self._process.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
            self._process.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            raise TranslationEngineError(f"Utracono połączenie z workerem AMD: {exc}") from exc

    def _read_until(self, expected_type: str) -> dict[str, object]:
        if self._process.stdout is None:
            raise TranslationEngineError("Worker AMD nie udostępnił kanału odpowiedzi.")
        diagnostics: list[str] = []
        while True:
            line = self._process.stdout.readline()
            if not line:
                code = self._process.poll()
                detail = "\n".join(diagnostics[-8:])
                raise TranslationEngineError(
                    f"Worker AMD zakończył pracę (kod {code})."
                    + (f"\n\n{detail}" if detail else "")
                )
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                diagnostics.append(line.strip())
                continue
            message_type = payload.get("type")
            if message_type == "status":
                self._status(str(payload.get("message") or "Praca workera AMD…"))
                continue
            if message_type == "error":
                raise TranslationEngineError(str(payload.get("message") or "Błąd workera AMD."))
            if message_type == expected_type:
                return payload
