from polysub.engines.deepl import DeepLEngine


class FakeResponse:
    status_code = 200
    text = ""

    def json(self):
        return {"translations": [{"text": "Cześć"}]}


class FakeSession:
    def __init__(self) -> None:
        self.request = None

    def post(self, url, **kwargs):
        self.request = (url, kwargs)
        return FakeResponse()


def test_deepl_uses_free_endpoint_and_does_not_send_source_language() -> None:
    engine = DeepLEngine("secret:fx")
    session = FakeSession()
    engine.session = session

    assert engine.translate_batch(["Hello"], source_language="en", target_language="pl") == [
        "Cześć"
    ]
    url, kwargs = session.request
    assert url == "https://api-free.deepl.com/v2/translate"
    assert kwargs["json"]["target_lang"] == "PL"
    assert "source_lang" not in kwargs["json"]
    assert kwargs["headers"]["Authorization"].endswith("secret:fx")
