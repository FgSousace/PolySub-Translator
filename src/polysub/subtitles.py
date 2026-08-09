from __future__ import annotations

import copy
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

TIMING_RE = re.compile(
    r"^\s*\d{1,3}:\d{2}:\d{2}[,.]\d{3}\s*-->\s*"
    r"\d{1,3}:\d{2}:\d{2}[,.]\d{3}(?:\s+.*)?$"
)
TAG_RE = re.compile(r"<[^>]+>|\{\\[^}]+\}")
WORD_RE = re.compile(r"[^\W_]+(?:['’\-][^\W_]+)*", re.UNICODE)
CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]")


class SubtitleFormatError(ValueError):
    pass


@dataclass
class SRTCue:
    identifier: str
    timing: str
    text: str

    @property
    def visible_text(self) -> str:
        return strip_markup(self.text)

    @property
    def word_count(self) -> int:
        return count_words(self.visible_text)


@dataclass
class SRTDocument:
    cues: list[SRTCue]
    source_path: Path | None = None
    encoding: str = "utf-8"

    @classmethod
    def load(cls, path: str | Path) -> SRTDocument:
        source = Path(path)
        raw, encoding = _read_text(source)
        return cls.parse(raw, source_path=source, encoding=encoding)

    @classmethod
    def parse(
        cls,
        content: str,
        *,
        source_path: Path | None = None,
        encoding: str = "utf-8",
    ) -> SRTDocument:
        normalized = content.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
        blocks = [block for block in re.split(r"\n{2,}", normalized.strip()) if block.strip()]
        cues: list[SRTCue] = []

        for position, block in enumerate(blocks, start=1):
            lines = block.split("\n")
            timing_index = next((i for i, line in enumerate(lines) if TIMING_RE.match(line)), None)
            if timing_index is None:
                raise SubtitleFormatError(f"Blok {position} nie zawiera poprawnego timestampa SRT.")
            identifier = "\n".join(lines[:timing_index]).strip() or str(position)
            text = "\n".join(lines[timing_index + 1 :]).strip("\n")
            if not text:
                raise SubtitleFormatError(f"Blok {position} nie zawiera tekstu napisów.")
            cues.append(
                SRTCue(identifier=identifier, timing=lines[timing_index].strip(), text=text)
            )

        if not cues:
            raise SubtitleFormatError("Plik nie zawiera żadnych napisów SRT.")
        return cls(cues=cues, source_path=source_path, encoding=encoding)

    def clone(self) -> SRTDocument:
        return copy.deepcopy(self)

    @property
    def total_words(self) -> int:
        return sum(cue.word_count for cue in self.cues)

    @property
    def combined_text(self) -> str:
        return "\n".join(cue.visible_text for cue in self.cues)

    @property
    def fingerprint(self) -> str:
        digest = hashlib.sha256()
        for cue in self.cues:
            digest.update(cue.identifier.encode("utf-8"))
            digest.update(b"\0")
            digest.update(cue.timing.encode("utf-8"))
            digest.update(b"\0")
            digest.update(cue.text.encode("utf-8"))
            digest.update(b"\0")
        return digest.hexdigest()

    def compose(self) -> str:
        blocks = [f"{cue.identifier}\n{cue.timing}\n{cue.text}" for cue in self.cues]
        return "\n\n".join(blocks) + "\n"

    def save(self, path: str | Path) -> Path:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(self.compose(), encoding="utf-8", newline="\n")
        return destination

    def assert_structure_matches(
        self,
        original: SRTDocument,
        *,
        allow_timing_changes: bool = False,
    ) -> None:
        if len(self.cues) != len(original.cues):
            raise SubtitleFormatError("Liczba kwestii zmieniła się podczas tłumaczenia.")
        for position, (translated, source) in enumerate(
            zip(self.cues, original.cues, strict=True), start=1
        ):
            if translated.identifier != source.identifier:
                raise SubtitleFormatError(f"Zmienił się numer/identyfikator kwestii {position}.")
            if not allow_timing_changes and translated.timing != source.timing:
                raise SubtitleFormatError(f"Zmienił się timestamp kwestii {position}.")


def strip_markup(text: str) -> str:
    text = text.replace("\\N", "\n")
    return TAG_RE.sub("", text)


def count_words(text: str) -> int:
    """Count readable progress units, treating CJK characters as word-like units."""
    without_cjk = CJK_RE.sub(" ", text)
    return len(WORD_RE.findall(without_cjk)) + len(CJK_RE.findall(text))


def default_output_path(source: str | Path, target_language: str) -> Path:
    path = Path(source)
    return path.with_name(f"{path.stem}.{target_language.lower()}{path.suffix}")


def _read_text(path: Path) -> tuple[str, str]:
    payload = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "cp1250", "cp1252"):
        try:
            return payload.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    return payload.decode("utf-8", errors="replace"), "utf-8-replace"
