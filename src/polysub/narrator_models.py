from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NarratorModelSpec:
    rank: int
    id: str
    repo_id: str
    display_name: str
    download_gb: float
    recommended_ram_gb: int
    recommended_vram_gb: int
    accuracy_score: int
    quality: str
    best_for: str
    license_name: str
    language_code: str
    download_patterns: tuple[str, ...]
    required_files: tuple[str, ...]

    @property
    def estimated_download_bytes(self) -> int:
        return int(self.download_gb * 1_000_000_000)

    @property
    def size_label(self) -> str:
        if self.download_gb < 1:
            return f"{self.download_gb * 1000:.0f} MB"
        return f"{self.download_gb:g} GB"

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


CHATTERBOX_MULTILINGUAL_V3 = NarratorModelSpec(
    rank=1,
    id="chatterbox-multilingual-v3",
    repo_id="ResembleAI/chatterbox",
    display_name="Chatterbox Multilingual V3 — polski lektor",
    download_gb=3.25,
    recommended_ram_gb=8,
    recommended_vram_gb=6,
    accuracy_score=5,
    quality="Naturalny głos wielojęzyczny",
    best_for="jeden polski głos lektora na tle ściszonej oryginalnej ścieżki",
    license_name="MIT",
    language_code="pl",
    download_patterns=(
        "ve.pt",
        "t3_mtl23ls_v3.safetensors",
        "s3gen.pt",
        "grapheme_mtl_merged_expanded_v1.json",
        "conds.pt",
        "Cangjie5_TC.json",
    ),
    required_files=(
        "ve.pt",
        "t3_mtl23ls_v3.safetensors",
        "s3gen.pt",
        "grapheme_mtl_merged_expanded_v1.json",
        "conds.pt",
        "Cangjie5_TC.json",
    ),
)

NARRATOR_MODEL_CATALOG: tuple[NarratorModelSpec, ...] = (CHATTERBOX_MULTILINGUAL_V3,)
NARRATOR_MODEL_BY_ID = {model.id: model for model in NARRATOR_MODEL_CATALOG}


def get_narrator_model_spec(model_id: str) -> NarratorModelSpec:
    try:
        return NARRATOR_MODEL_BY_ID[model_id]
    except KeyError as exc:
        raise ValueError(f"Nieznany model lektora: {model_id}") from exc
