"""JSON-lines worker executed by the optional AMD ROCm Python environment."""

from __future__ import annotations

import json
import sys
import traceback


def emit(payload: dict[str, object]) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def main() -> None:
    engine = None
    for raw_line in sys.stdin:
        try:
            request = json.loads(raw_line)
            command = request.get("command")
            if command == "init":
                from polysub.engines import create_local_engine
                from polysub.translation_models import get_model_spec

                spec = get_model_spec(str(request["model_id"]))
                device_index = max(int(request.get("device_index", 0)), 0)
                engine = create_local_engine(
                    spec,
                    model_source=str(request["model_source"]),
                    device=f"cuda:{device_index}",
                    status=lambda message: emit({"type": "status", "message": message}),
                    allow_cpu_fallback=False,
                    cpu_usage_limit=int(request.get("cpu_usage_limit", 100)),
                )
                emit({"type": "ready", "max_batch_size": engine.max_batch_size})
            elif command == "translate":
                if engine is None:
                    raise RuntimeError("Worker AMD nie został zainicjalizowany.")
                result = engine.translate_batch(
                    request.get("texts") or [],
                    source_language=str(request["source_language"]),
                    target_language=str(request["target_language"]),
                    accurate=bool(request.get("accurate", False)),
                )
                emit({"type": "result", "texts": result})
            else:
                raise RuntimeError(f"Nieznane polecenie workera AMD: {command!r}")
        except Exception as exc:
            emit(
                {
                    "type": "error",
                    "message": str(exc),
                    "traceback": traceback.format_exc(limit=4),
                }
            )


if __name__ == "__main__":
    main()
