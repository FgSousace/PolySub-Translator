from polysub.translation_models import (
    DEFAULT_MODEL_ID,
    MODEL_CATALOG,
    ModelFamily,
    compatible_models,
    get_model_spec,
)


def test_catalog_contains_exactly_twenty_ranked_unique_models() -> None:
    assert len(MODEL_CATALOG) == 20
    assert [model.rank for model in MODEL_CATALOG] == list(range(1, 21))
    assert len({model.id for model in MODEL_CATALOG}) == 20
    assert len({model.repo_id for model in MODEL_CATALOG}) == 20


def test_default_model_preserves_previous_m2m100_behavior() -> None:
    model = get_model_spec(DEFAULT_MODEL_ID)

    assert model.repo_id == "facebook/m2m100_418M"
    assert model.family is ModelFamily.M2M100
    assert model.supports_pair("en-US", "pl-PL")


def test_pair_specific_models_are_only_offered_for_their_pair() -> None:
    english_to_polish = get_model_spec("opus-en-pl")

    assert english_to_polish.supports_pair("en", "pl")
    assert not english_to_polish.supports_pair("de", "pl")
    assert english_to_polish.target_token("pl") == "pol"
    assert english_to_polish in compatible_models("en", "pl")
    assert english_to_polish not in compatible_models("pl", "en")


def test_nllb_and_mbart_language_tokens_are_resolved() -> None:
    nllb = get_model_spec("nllb-200-distilled-600m")
    mbart = get_model_spec("mbart50-many-to-many")

    assert nllb.source_token("en") == "eng_Latn"
    assert nllb.target_token("pl") == "pol_Latn"
    assert mbart.source_token("en") == "en_XX"
    assert mbart.target_token("pl") == "pl_PL"

