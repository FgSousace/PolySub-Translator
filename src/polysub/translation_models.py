from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .languages import LANGUAGES


class ModelFamily(str, Enum):
    MADLAD = "madlad"
    NLLB = "nllb"
    M2M100 = "m2m100"
    MBART50 = "mbart50"
    MARIAN = "marian"


NLLB_LANGUAGE_CODES: dict[str, str] = {
    "af": "afr_Latn",
    "am": "amh_Ethi",
    "ar": "arb_Arab",
    "ast": "ast_Latn",
    "az": "azj_Latn",
    "ba": "bak_Cyrl",
    "be": "bel_Cyrl",
    "bg": "bul_Cyrl",
    "bn": "ben_Beng",
    "br": "bre_Latn",
    "bs": "bos_Latn",
    "ca": "cat_Latn",
    "ceb": "ceb_Latn",
    "cs": "ces_Latn",
    "cy": "cym_Latn",
    "da": "dan_Latn",
    "de": "deu_Latn",
    "el": "ell_Grek",
    "en": "eng_Latn",
    "es": "spa_Latn",
    "et": "est_Latn",
    "fa": "pes_Arab",
    "ff": "fuv_Latn",
    "fi": "fin_Latn",
    "fr": "fra_Latn",
    "fy": "fry_Latn",
    "ga": "gle_Latn",
    "gd": "gla_Latn",
    "gl": "glg_Latn",
    "gu": "guj_Gujr",
    "ha": "hau_Latn",
    "he": "heb_Hebr",
    "hi": "hin_Deva",
    "hr": "hrv_Latn",
    "ht": "hat_Latn",
    "hu": "hun_Latn",
    "hy": "hye_Armn",
    "id": "ind_Latn",
    "ig": "ibo_Latn",
    "ilo": "ilo_Latn",
    "is": "isl_Latn",
    "it": "ita_Latn",
    "ja": "jpn_Jpan",
    "jv": "jav_Latn",
    "ka": "kat_Geor",
    "kk": "kaz_Cyrl",
    "km": "khm_Khmr",
    "kn": "kan_Knda",
    "ko": "kor_Hang",
    "lb": "ltz_Latn",
    "lg": "lug_Latn",
    "ln": "lin_Latn",
    "lo": "lao_Laoo",
    "lt": "lit_Latn",
    "lv": "lvs_Latn",
    "mg": "plt_Latn",
    "mk": "mkd_Cyrl",
    "ml": "mal_Mlym",
    "mn": "khk_Cyrl",
    "mr": "mar_Deva",
    "ms": "zsm_Latn",
    "my": "mya_Mymr",
    "ne": "npi_Deva",
    "nl": "nld_Latn",
    "no": "nob_Latn",
    "ns": "nso_Latn",
    "oc": "oci_Latn",
    "or": "ory_Orya",
    "pa": "pan_Guru",
    "pl": "pol_Latn",
    "ps": "pbt_Arab",
    "pt": "por_Latn",
    "ro": "ron_Latn",
    "ru": "rus_Cyrl",
    "sd": "snd_Arab",
    "si": "sin_Sinh",
    "sk": "slk_Latn",
    "sl": "slv_Latn",
    "so": "som_Latn",
    "sq": "als_Latn",
    "sr": "srp_Cyrl",
    "ss": "ssw_Latn",
    "su": "sun_Latn",
    "sv": "swe_Latn",
    "sw": "swh_Latn",
    "ta": "tam_Taml",
    "th": "tha_Thai",
    "tl": "tgl_Latn",
    "tn": "tsn_Latn",
    "tr": "tur_Latn",
    "uk": "ukr_Cyrl",
    "ur": "urd_Arab",
    "uz": "uzn_Latn",
    "vi": "vie_Latn",
    "wo": "wol_Latn",
    "xh": "xho_Latn",
    "yi": "ydd_Hebr",
    "yo": "yor_Latn",
    "zh": "zho_Hans",
    "zu": "zul_Latn",
}


MBART50_LANGUAGE_CODES: dict[str, str] = {
    "af": "af_ZA",
    "ar": "ar_AR",
    "az": "az_AZ",
    "bn": "bn_IN",
    "cs": "cs_CZ",
    "de": "de_DE",
    "en": "en_XX",
    "es": "es_XX",
    "et": "et_EE",
    "fa": "fa_IR",
    "fi": "fi_FI",
    "fr": "fr_XX",
    "gl": "gl_ES",
    "gu": "gu_IN",
    "he": "he_IL",
    "hi": "hi_IN",
    "hr": "hr_HR",
    "id": "id_ID",
    "it": "it_IT",
    "ja": "ja_XX",
    "ka": "ka_GE",
    "kk": "kk_KZ",
    "km": "km_KH",
    "ko": "ko_KR",
    "lt": "lt_LT",
    "lv": "lv_LV",
    "mk": "mk_MK",
    "ml": "ml_IN",
    "mn": "mn_MN",
    "mr": "mr_IN",
    "my": "my_MM",
    "ne": "ne_NP",
    "nl": "nl_XX",
    "pl": "pl_PL",
    "ps": "ps_AF",
    "pt": "pt_XX",
    "ro": "ro_RO",
    "ru": "ru_RU",
    "si": "si_LK",
    "sl": "sl_SI",
    "sv": "sv_SE",
    "sw": "sw_KE",
    "ta": "ta_IN",
    "th": "th_TH",
    "tl": "tl_XX",
    "tr": "tr_TR",
    "uk": "uk_UA",
    "ur": "ur_PK",
    "vi": "vi_VN",
    "xh": "xh_ZA",
    "zh": "zh_CN",
}


def normalize_language_code(code: str) -> str:
    return code.strip().lower().replace("_", "-").split("-", 1)[0]


@dataclass(frozen=True)
class TranslationModelSpec:
    rank: int
    id: str
    repo_id: str
    display_name: str
    family: ModelFamily
    download_gb: float
    recommended_ram_gb: int
    recommended_vram_gb: int
    quality: str
    license_name: str
    source_languages: frozenset[str]
    target_languages: frozenset[str]
    batch_cap: int = 8
    target_prefix_codes: tuple[tuple[str, str], ...] = ()
    note: str = ""

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
        return f"{self.rank:02d}. {self.display_name} · około {self.size_label}"

    @property
    def model_card_url(self) -> str:
        return f"https://huggingface.co/{self.repo_id}"

    @property
    def hardware_label(self) -> str:
        return (
            f"RAM co najmniej {self.recommended_ram_gb} GB; "
            f"dla GPU zalecane {self.recommended_vram_gb} GB VRAM"
        )

    def supports_pair(self, source: str, target: str) -> bool:
        source = normalize_language_code(source)
        target = normalize_language_code(target)
        return source in self.source_languages and target in self.target_languages

    def source_token(self, language: str) -> str:
        code = normalize_language_code(language)
        if self.family is ModelFamily.NLLB:
            return NLLB_LANGUAGE_CODES[code]
        if self.family is ModelFamily.MBART50:
            return MBART50_LANGUAGE_CODES[code]
        return code

    def target_token(self, language: str) -> str:
        code = normalize_language_code(language)
        if self.family is ModelFamily.NLLB:
            return NLLB_LANGUAGE_CODES[code]
        if self.family is ModelFamily.MBART50:
            return MBART50_LANGUAGE_CODES[code]
        prefixes = dict(self.target_prefix_codes)
        return prefixes.get(code, code)


ALL_APP_LANGUAGES = frozenset(LANGUAGES)
NLLB_LANGUAGES = frozenset(NLLB_LANGUAGE_CODES)
MBART50_LANGUAGES = frozenset(MBART50_LANGUAGE_CODES)


def _spec(
    rank: int,
    model_id: str,
    repo_id: str,
    display_name: str,
    family: ModelFamily,
    download_gb: float,
    ram: int,
    vram: int,
    quality: str,
    license_name: str,
    *,
    sources: frozenset[str] | None = None,
    targets: frozenset[str] | None = None,
    batch_cap: int = 8,
    target_prefix_codes: tuple[tuple[str, str], ...] = (),
    note: str = "",
) -> TranslationModelSpec:
    if sources is None or targets is None:
        if family is ModelFamily.NLLB:
            default_languages = NLLB_LANGUAGES
        elif family is ModelFamily.MBART50:
            default_languages = MBART50_LANGUAGES
        else:
            default_languages = ALL_APP_LANGUAGES
        sources = sources or default_languages
        targets = targets or default_languages
    return TranslationModelSpec(
        rank=rank,
        id=model_id,
        repo_id=repo_id,
        display_name=display_name,
        family=family,
        download_gb=download_gb,
        recommended_ram_gb=ram,
        recommended_vram_gb=vram,
        quality=quality,
        license_name=license_name,
        source_languages=sources,
        target_languages=targets,
        batch_cap=batch_cap,
        target_prefix_codes=target_prefix_codes,
        note=note,
    )


# Ranking is deliberately presented as an approximate general-quality order. A small
# pair-specific OPUS model can outperform a general model for its exact language pair.
MODEL_CATALOG: tuple[TranslationModelSpec, ...] = (
    _spec(
        1,
        "madlad400-10b",
        "google/madlad400-10b-mt",
        "MADLAD-400 10B",
        ModelFamily.MADLAD,
        43,
        64,
        48,
        "Najwyższa",
        "Apache-2.0",
        batch_cap=1,
        note="Najcięższy model; przeznaczony do bardzo mocnych komputerów.",
    ),
    _spec(
        2,
        "madlad400-7b",
        "google/madlad400-7b-mt",
        "MADLAD-400 7B",
        ModelFamily.MADLAD,
        33.3,
        48,
        40,
        "Najwyższa",
        "Apache-2.0",
        batch_cap=1,
    ),
    _spec(
        3,
        "madlad400-3b",
        "google/madlad400-3b-mt",
        "MADLAD-400 3B",
        ModelFamily.MADLAD,
        11.9,
        24,
        16,
        "Bardzo wysoka",
        "Apache-2.0",
        batch_cap=2,
    ),
    _spec(
        4,
        "nllb-200-3.3b",
        "facebook/nllb-200-3.3B",
        "NLLB-200 3.3B",
        ModelFamily.NLLB,
        17.6,
        32,
        20,
        "Bardzo wysoka",
        "CC-BY-NC-4.0",
        batch_cap=2,
        note="Model badawczy do użytku niekomercyjnego.",
    ),
    _spec(
        5,
        "nllb-200-distilled-1.3b",
        "facebook/nllb-200-distilled-1.3B",
        "NLLB-200 Distilled 1.3B",
        ModelFamily.NLLB,
        5.5,
        16,
        10,
        "Wysoka",
        "CC-BY-NC-4.0",
        batch_cap=4,
        note="Model badawczy do użytku niekomercyjnego.",
    ),
    _spec(
        6,
        "nllb-200-1.3b",
        "facebook/nllb-200-1.3B",
        "NLLB-200 1.3B",
        ModelFamily.NLLB,
        5.5,
        16,
        10,
        "Wysoka",
        "CC-BY-NC-4.0",
        batch_cap=4,
        note="Model badawczy do użytku niekomercyjnego.",
    ),
    _spec(
        7,
        "m2m100-1.2b",
        "facebook/m2m100_1.2B",
        "M2M100 1.2B",
        ModelFamily.M2M100,
        4.9,
        16,
        10,
        "Wysoka",
        "MIT",
        batch_cap=6,
    ),
    _spec(
        8,
        "nllb-200-distilled-600m",
        "facebook/nllb-200-distilled-600M",
        "NLLB-200 Distilled 600M",
        ModelFamily.NLLB,
        2.5,
        8,
        6,
        "Dobra",
        "CC-BY-NC-4.0",
        batch_cap=8,
        note="Model badawczy do użytku niekomercyjnego.",
    ),
    _spec(
        9,
        "mbart50-many-to-many",
        "facebook/mbart-large-50-many-to-many-mmt",
        "mBART-50 Many-to-Many",
        ModelFamily.MBART50,
        2.5,
        8,
        6,
        "Dobra",
        "Sprawdź kartę modelu",
        batch_cap=8,
    ),
    _spec(
        10,
        "m2m100-418m",
        "facebook/m2m100_418M",
        "M2M100 418M",
        ModelFamily.M2M100,
        1.9,
        8,
        4,
        "Dobra",
        "MIT",
        batch_cap=16,
        note="Domyślny, sprawdzony model zgodny z wcześniejszymi wersjami PolySub.",
    ),
    _spec(
        11,
        "mbart50-one-to-many",
        "facebook/mbart-large-50-one-to-many-mmt",
        "mBART-50 English-to-Many",
        ModelFamily.MBART50,
        2.5,
        8,
        6,
        "Dobra",
        "Sprawdź kartę modelu",
        sources=frozenset({"en"}),
        batch_cap=8,
    ),
    _spec(
        12,
        "mbart50-many-to-one",
        "facebook/mbart-large-50-many-to-one-mmt",
        "mBART-50 Many-to-English",
        ModelFamily.MBART50,
        2.5,
        8,
        6,
        "Dobra",
        "Sprawdź kartę modelu",
        targets=frozenset({"en"}),
        batch_cap=8,
    ),
    _spec(
        13,
        "opus-en-pl",
        "Helsinki-NLP/opus-mt-en-zlw",
        "OPUS English → Polish",
        ModelFamily.MARIAN,
        0.32,
        4,
        2,
        "Dobra dla tej pary",
        "Apache-2.0",
        sources=frozenset({"en"}),
        targets=frozenset({"pl"}),
        target_prefix_codes=(("pl", "pol"),),
        batch_cap=16,
    ),
    _spec(
        14,
        "opus-pl-en",
        "Helsinki-NLP/opus-mt-pl-en",
        "OPUS Polish → English",
        ModelFamily.MARIAN,
        0.32,
        4,
        2,
        "Dobra dla tej pary",
        "Apache-2.0",
        sources=frozenset({"pl"}),
        targets=frozenset({"en"}),
        batch_cap=16,
    ),
    _spec(
        15,
        "opus-de-pl",
        "Helsinki-NLP/opus-mt-de-pl",
        "OPUS German → Polish",
        ModelFamily.MARIAN,
        0.32,
        4,
        2,
        "Dobra dla tej pary",
        "Apache-2.0",
        sources=frozenset({"de"}),
        targets=frozenset({"pl"}),
        batch_cap=16,
    ),
    _spec(
        16,
        "opus-es-pl",
        "Helsinki-NLP/opus-mt-es-pl",
        "OPUS Spanish → Polish",
        ModelFamily.MARIAN,
        0.32,
        4,
        2,
        "Dobra dla tej pary",
        "Apache-2.0",
        sources=frozenset({"es"}),
        targets=frozenset({"pl"}),
        batch_cap=16,
    ),
    _spec(
        17,
        "opus-fr-pl",
        "Helsinki-NLP/opus-mt-fr-pl",
        "OPUS French → Polish",
        ModelFamily.MARIAN,
        0.32,
        4,
        2,
        "Dobra dla tej pary",
        "Apache-2.0",
        sources=frozenset({"fr"}),
        targets=frozenset({"pl"}),
        batch_cap=16,
    ),
    _spec(
        18,
        "opus-uk-pl",
        "Helsinki-NLP/opus-mt-uk-pl",
        "OPUS Ukrainian → Polish",
        ModelFamily.MARIAN,
        0.32,
        4,
        2,
        "Dobra dla tej pary",
        "Apache-2.0",
        sources=frozenset({"uk"}),
        targets=frozenset({"pl"}),
        batch_cap=16,
    ),
    _spec(
        19,
        "opus-ar-pl",
        "Helsinki-NLP/opus-mt-ar-pl",
        "OPUS Arabic → Polish",
        ModelFamily.MARIAN,
        0.32,
        4,
        2,
        "Podstawowa dla tej pary",
        "Apache-2.0",
        sources=frozenset({"ar"}),
        targets=frozenset({"pl"}),
        batch_cap=16,
    ),
    _spec(
        20,
        "opus-ja-pl",
        "Helsinki-NLP/opus-mt-ja-pl",
        "OPUS Japanese → Polish",
        ModelFamily.MARIAN,
        0.32,
        4,
        2,
        "Podstawowa dla tej pary",
        "Apache-2.0",
        sources=frozenset({"ja"}),
        targets=frozenset({"pl"}),
        batch_cap=16,
    ),
)

DEFAULT_MODEL_ID = "m2m100-418m"
MODEL_BY_ID = {model.id: model for model in MODEL_CATALOG}
MODEL_BY_LABEL = {model.selection_label: model for model in MODEL_CATALOG}


def get_model_spec(model_id: str) -> TranslationModelSpec:
    try:
        return MODEL_BY_ID[model_id]
    except KeyError as exc:
        raise ValueError(f"Nieznany model tłumaczeniowy: {model_id}") from exc


def compatible_models(source: str, target: str) -> list[TranslationModelSpec]:
    return [model for model in MODEL_CATALOG if model.supports_pair(source, target)]
