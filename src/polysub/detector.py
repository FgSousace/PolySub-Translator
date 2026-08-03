from __future__ import annotations

import os
import re
from pathlib import Path

import requests
from langdetect import DetectorFactory, LangDetectException, detect_langs

from .languages import language_name
from .models import DetectionResult

DetectorFactory.seed = 0
FASTTEXT_MODEL_URL = "https://dl.fbaipublicfiles.com/fasttext/supervised-models/lid.176.ftz"


class LanguageDetectionError(RuntimeError):
    pass


def detect_language(text: str) -> DetectionResult:
    sample = _prepare_sample(text)
    if len(sample) < 3:
        raise LanguageDetectionError("Za mało tekstu, aby wiarygodnie wykryć język.")
    fasttext_result = _detect_with_fasttext(sample)
    if fasttext_result:
        return fasttext_result
    try:
        candidates = detect_langs(sample)
    except LangDetectException as exc:
        raise LanguageDetectionError("Nie udało się wykryć języka napisów.") from exc
    if not candidates:
        raise LanguageDetectionError("Nie udało się wykryć języka napisów.")
    best = candidates[0]
    code = best.lang.lower()
    return DetectionResult(code=code, confidence=float(best.prob), name=language_name(code))


def _detect_with_fasttext(sample: str) -> DetectionResult | None:
    try:
        import fasttext
    except ImportError:
        return None

    model_path = _fasttext_model_path()
    if not model_path.exists():
        try:
            model_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = model_path.with_suffix(".tmp")
            with requests.get(FASTTEXT_MODEL_URL, stream=True, timeout=30) as response:
                response.raise_for_status()
                with temporary.open("wb") as handle:
                    for chunk in response.iter_content(chunk_size=64 * 1024):
                        if chunk:
                            handle.write(chunk)
            temporary.replace(model_path)
        except (OSError, requests.RequestException):
            return None
    try:
        model = fasttext.load_model(str(model_path))
        labels, probabilities = model.predict(sample.replace("\n", " "), k=1)
    except Exception:
        return None
    if not labels:
        return None
    code = labels[0].removeprefix("__label__").lower()
    return DetectionResult(code=code, confidence=float(probabilities[0]), name=language_name(code))


def _fasttext_model_path() -> Path:
    configured = os.getenv("POLYSUB_FASTTEXT_MODEL")
    if configured:
        return Path(configured)
    cache_root = os.getenv("LOCALAPPDATA")
    if cache_root:
        return Path(cache_root) / "PolySub" / "lid.176.ftz"
    return Path.home() / ".cache" / "polysub" / "lid.176.ftz"


def _prepare_sample(text: str) -> str:
    text = re.sub(r"<[^>]+>|\{\\[^}]+\}", " ", text)
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    # A few thousand characters are sufficient and keep detection quick.
    return text[:12_000]
