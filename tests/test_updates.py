from types import SimpleNamespace

import pytest
import requests

from polysub.updates import (
    RELEASE_PAGE_URL,
    UpdateCheckError,
    check_for_updates,
    is_newer_version,
    normalize_version,
)


class FakeSession:
    def __init__(self, payload=None, error=None) -> None:
        self.payload = payload
        self.error = error
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if self.error:
            raise self.error
        return SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: self.payload,
        )


def test_semantic_versions_are_compared_numerically() -> None:
    assert normalize_version("v0.4.4") == "0.4.4"
    assert is_newer_version("0.10.0", "0.9.9")
    assert not is_newer_version("0.4.3", "0.4.3")


def test_update_check_returns_direct_setup_download() -> None:
    installer = (
        "https://github.com/FgSousace/PolySub-Translator/"
        "releases/download/v0.4.4/PolySub-Translator-Setup.exe"
    )
    session = FakeSession(
        {
            "tag_name": "v0.4.4",
            "html_url": "https://github.com/FgSousace/PolySub-Translator/releases/tag/v0.4.4",
            "assets": [
                {
                    "name": "PolySub-Translator-Setup.exe",
                    "browser_download_url": installer,
                }
            ],
        }
    )

    result = check_for_updates("0.4.3", session=session)

    assert result.update_available
    assert result.latest_version == "0.4.4"
    assert result.installer_url == installer
    assert session.calls[0][1]["timeout"] == 8.0
    assert session.calls[0][1]["headers"]["Cache-Control"] == "no-cache"


def test_version_045_detects_published_049_release() -> None:
    session = FakeSession(
        {
            "tag_name": "v0.4.9",
            "html_url": (
                "https://github.com/FgSousace/PolySub-Translator/releases/tag/v0.4.9"
            ),
            "assets": [],
        }
    )

    result = check_for_updates("0.4.5", session=session)

    assert result.update_available
    assert result.latest_version == "0.4.9"


def test_version_049_detects_published_050_release() -> None:
    installer = (
        "https://github.com/FgSousace/PolySub-Translator/"
        "releases/download/v0.5.0/PolySub-Translator-Setup.exe"
    )
    session = FakeSession(
        {
            "tag_name": "v0.5.0",
            "html_url": "https://github.com/FgSousace/PolySub-Translator/releases/tag/v0.5.0",
            "assets": [
                {
                    "name": "PolySub-Translator-Setup.exe",
                    "browser_download_url": installer,
                }
            ],
        }
    )

    result = check_for_updates("0.4.9", session=session)

    assert result.update_available
    assert result.latest_version == "0.5.0"
    assert result.installer_url == installer


def test_version_050_prefers_versioned_051_installer_name() -> None:
    versioned_installer = (
        "https://github.com/FgSousace/PolySub-Translator/"
        "releases/download/v0.5.1/PolySub-Translator-Setup-0.5.1.exe"
    )
    session = FakeSession(
        {
            "tag_name": "v0.5.1",
            "html_url": "https://github.com/FgSousace/PolySub-Translator/releases/tag/v0.5.1",
            "assets": [
                {
                    "name": "PolySub-Translator-Setup.exe",
                    "browser_download_url": "https://github.com/legacy.exe",
                },
                {
                    "name": "PolySub-Translator-Setup-0.5.1.exe",
                    "browser_download_url": versioned_installer,
                },
            ],
        }
    )

    result = check_for_updates("0.5.0", session=session)

    assert result.update_available
    assert result.latest_version == "0.5.1"
    assert result.installer_url == versioned_installer


def test_version_051_finds_versioned_052_installer() -> None:
    versioned_installer = (
        "https://github.com/FgSousace/PolySub-Translator/"
        "releases/download/v0.5.2/PolySub-Translator-Setup-0.5.2.exe"
    )
    session = FakeSession(
        {
            "tag_name": "v0.5.2",
            "html_url": "https://github.com/FgSousace/PolySub-Translator/releases/tag/v0.5.2",
            "assets": [
                {
                    "name": "PolySub-Translator-Setup-0.5.2.exe",
                    "browser_download_url": versioned_installer,
                }
            ],
        }
    )

    result = check_for_updates("0.5.1", session=session)

    assert result.update_available
    assert result.latest_version == "0.5.2"
    assert result.installer_url == versioned_installer


def test_untrusted_download_url_falls_back_to_release_page() -> None:
    session = FakeSession(
        {
            "tag_name": "v0.4.3",
            "html_url": "https://example.com/fake-release",
            "assets": [
                {
                    "name": "PolySub-Translator-Setup.exe",
                    "browser_download_url": "https://example.com/fake.exe",
                }
            ],
        }
    )

    result = check_for_updates("0.4.3", session=session)

    assert not result.update_available
    assert result.release_url == RELEASE_PAGE_URL
    assert result.installer_url == RELEASE_PAGE_URL


def test_network_error_is_reported_as_update_error() -> None:
    session = FakeSession(error=requests.ConnectionError("offline"))

    with pytest.raises(UpdateCheckError, match="Nie udało się sprawdzić"):
        check_for_updates("0.4.3", session=session)


def test_invalid_release_version_is_rejected() -> None:
    session = FakeSession({"tag_name": "latest", "assets": []})

    with pytest.raises(UpdateCheckError, match="Nieprawidłowy numer wersji"):
        check_for_updates("0.4.3", session=session)
