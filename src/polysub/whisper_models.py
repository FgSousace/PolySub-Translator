from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WhisperModelSpec:
    rank: int
    id: str
    repo_id: str
    runtime_alias: str
    display_name: str
    download_gb: float
    recommended_ram_gb: int
    recommended_vram_gb: int
    accuracy_score: int
    quality: str
    speed: str
    best_for: str
    license_name: str = "MIT"
    required_files: tuple[str, ...] = (
        "config.json",
        "model.bin",
        "tokenizer.json",
        "vocabulary.txt",
    )
    download_patterns: tuple[str, ...] = ()

    @property
    def estimated_download_bytes(self) -> int:
        return int(self.download_gb * 1_000_000_000)

    @property
    def size_label(self) -> str:
        if self.download_gb < 1:
            return f"{self.download_gb * 1000:.0f} MB"
        return f"{self.download_gb:g} GB"

    @property
    def selection_label(self) -> str:
        return f"{self.display_name} · dokładność {self.accuracy_score}/5 · około {self.size_label}"

    @property
    def accuracy_label(self) -> str:
        return f"{self.accuracy_score}/5 · {self.quality}"

    @property
    def hardware_label(self) -> str:
        return (
            f"RAM co najmniej {self.recommended_ram_gb} GB; "
            f"dla GPU zalecane {self.recommended_vram_gb} GB VRAM"
        )

    @property
    def model_card_url(self) -> str:
        return f"https://huggingface.co/{self.repo_id}"


WHISPER_MODEL_CATALOG: tuple[WhisperModelSpec, ...] = (
    WhisperModelSpec(
        1,
        "whisper-large-v3",
        "Systran/faster-whisper-large-v3",
        "large-v3",
        "Whisper Large v3",
        3.1,
        8,
        5,
        5,
        "Najwyższa",
        "Wolny",
        "trudne nagrania, akcenty i najwyższa dokładność polskiego",
        required_files=(
            "config.json",
            "model.bin",
            "preprocessor_config.json",
            "tokenizer.json",
            "vocabulary.json",
        ),
    ),
    WhisperModelSpec(
        2,
        "whisper-large-v2",
        "Systran/faster-whisper-large-v2",
        "large-v2",
        "Whisper Large v2",
        3.1,
        8,
        5,
        5,
        "Bardzo wysoka",
        "Wolny",
        "starszy, bardzo dokładny wariant wielojęzyczny",
    ),
    WhisperModelSpec(
        3,
        "whisper-medium",
        "Systran/faster-whisper-medium",
        "medium",
        "Whisper Medium",
        1.55,
        6,
        3,
        4,
        "Wysoka",
        "Średni",
        "zalecany balans dla filmów i polskiej mowy",
    ),
    WhisperModelSpec(
        4,
        "whisper-small",
        "Systran/faster-whisper-small",
        "small",
        "Whisper Small",
        0.49,
        4,
        2,
        3,
        "Dobra",
        "Szybki",
        "czysty dialog i słabszy komputer",
    ),
    WhisperModelSpec(
        5,
        "whisper-base",
        "Systran/faster-whisper-base",
        "base",
        "Whisper Base",
        0.15,
        3,
        1,
        2,
        "Podstawowa",
        "Bardzo szybki",
        "podgląd i wyraźna mowa bez hałasu",
    ),
    WhisperModelSpec(
        6,
        "whisper-tiny",
        "Systran/faster-whisper-tiny",
        "tiny",
        "Whisper Tiny",
        0.08,
        2,
        1,
        1,
        "Niska",
        "Najszybszy",
        "szybki szkic napisów; niezalecany do trudnego audio",
    ),
)

DEFAULT_WHISPER_MODEL_ID = "whisper-medium"
WHISPER_MODEL_BY_ID = {model.id: model for model in WHISPER_MODEL_CATALOG}
WHISPER_MODEL_BY_LABEL = {model.selection_label: model for model in WHISPER_MODEL_CATALOG}


def get_whisper_model_spec(model_id: str) -> WhisperModelSpec:
    try:
        return WHISPER_MODEL_BY_ID[model_id]
    except KeyError as exc:
        raise ValueError(f"Nieznany model Whisper: {model_id}") from exc
