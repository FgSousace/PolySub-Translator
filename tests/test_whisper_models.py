from polysub.whisper_models import (
    DEFAULT_WHISPER_MODEL_ID,
    WHISPER_MODEL_CATALOG,
    get_whisper_model_spec,
)


def test_whisper_catalog_is_ranked_multilingual_and_has_accuracy_levels() -> None:
    assert [model.rank for model in WHISPER_MODEL_CATALOG] == list(range(1, 7))
    assert len({model.id for model in WHISPER_MODEL_CATALOG}) == 6
    assert all(".en" not in model.repo_id for model in WHISPER_MODEL_CATALOG)
    assert {model.accuracy_score for model in WHISPER_MODEL_CATALOG} == {1, 2, 3, 4, 5}
    assert all("tokenizer.json" in model.required_files for model in WHISPER_MODEL_CATALOG)
    assert "vocabulary.json" in WHISPER_MODEL_CATALOG[0].required_files
    assert all(
        "vocabulary.txt" in model.required_files for model in WHISPER_MODEL_CATALOG[1:]
    )
    assert get_whisper_model_spec(DEFAULT_WHISPER_MODEL_ID).runtime_alias == "medium"
