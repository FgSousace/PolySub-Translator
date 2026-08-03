from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class CheckpointStore:
    path: Path
    source_fingerprint: str
    target_language: str
    engine_name: str
    mode: str

    def load(self) -> dict[int, str]:
        if not self.path.exists():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        expected = {
            "source_fingerprint": self.source_fingerprint,
            "target_language": self.target_language,
            "engine": self.engine_name,
            "mode": self.mode,
        }
        if any(data.get(key) != value for key, value in expected.items()):
            return {}
        translations = data.get("translations", {})
        return {int(position): str(text) for position, text in translations.items()}

    def save(self, translations: dict[int, str]) -> None:
        payload = {
            "source_fingerprint": self.source_fingerprint,
            "target_language": self.target_language,
            "engine": self.engine_name,
            "mode": self.mode,
            "translations": {str(key): value for key, value in sorted(translations.items())},
        }
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.path)

    def clear(self) -> None:
        self.path.unlink(missing_ok=True)


def checkpoint_for(
    source_path: Path,
    *,
    source_fingerprint: str,
    target_language: str,
    engine_name: str,
    mode: str,
) -> CheckpointStore:
    path = source_path.with_suffix(source_path.suffix + ".polysub.json")
    return CheckpointStore(path, source_fingerprint, target_language, engine_name, mode)
