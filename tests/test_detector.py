from polysub.detector import detect_language


def test_detects_english_sample() -> None:
    result = detect_language(
        "This is a longer English subtitle sample. The characters are talking about their day."
    )

    assert result.code == "en"
    assert result.confidence > 0.80


def test_detects_polish_sample() -> None:
    result = detect_language(
        "To jest dłuższy przykład polskich napisów. Bohaterowie rozmawiają o swoim dniu."
    )

    assert result.code == "pl"
