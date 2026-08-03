from __future__ import annotations

import re
from dataclasses import dataclass

MARKUP_RE = re.compile(r"(<[^>]+>|\{\\[^}]+\}|\\N|\n)")


@dataclass(frozen=True)
class ProtectedText:
    text: str
    tokens: tuple[str, ...]

    @classmethod
    def from_text(cls, value: str) -> ProtectedText:
        tokens: list[str] = []

        def replace(match: re.Match[str]) -> str:
            tokens.append(match.group(0))
            return f"__POLYSUB_{len(tokens) - 1}__"

        return cls(text=MARKUP_RE.sub(replace, value), tokens=tuple(tokens))

    def restore(self, translated: str) -> tuple[str, bool]:
        restored = translated
        success = True
        for index, token in enumerate(self.tokens):
            marker = f"__POLYSUB_{index}__"
            if marker not in restored:
                success = False
                continue
            restored = restored.replace(marker, token)

        # Never leave internal placeholders in a user-facing subtitle.
        restored = re.sub(r"__\s*POLYSUB\s*_?\s*\d+\s*__", "", restored)
        if success:
            return restored.strip(), True
        return _fallback_formatting(restored.strip(), self.tokens), False


def _fallback_formatting(translated: str, tokens: tuple[str, ...]) -> str:
    """Preserve common leading/trailing tags even if a model damages markers."""
    leading: list[str] = []
    trailing: list[str] = []
    line_breaks = 0
    for token in tokens:
        if token in {"\n", "\\N"}:
            line_breaks += 1
        elif token.startswith("</") or token in {"{\\i0}", "{\\b0}", "{\\u0}"}:
            trailing.append(token)
        else:
            leading.append(token)

    if line_breaks and "\n" not in translated and "\\N" not in translated:
        translated = _wrap_into_lines(translated, line_breaks + 1)
    return "".join(leading) + translated + "".join(trailing)


def _wrap_into_lines(text: str, line_count: int) -> str:
    words = text.split()
    if line_count <= 1 or len(words) < line_count:
        return text
    target = max(1, len(words) // line_count)
    lines: list[str] = []
    start = 0
    for _line_index in range(line_count - 1):
        end = min(len(words), start + target)
        lines.append(" ".join(words[start:end]))
        start = end
    lines.append(" ".join(words[start:]))
    return "\n".join(lines)
