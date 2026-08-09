from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import requests

RELEASE_API_URL = "https://api.github.com/repos/FgSousace/PolySub-Translator/releases/latest"
RELEASE_PAGE_URL = "https://github.com/FgSousace/PolySub-Translator/releases/latest"
INSTALLER_ASSET_NAME = "PolySub-Translator-Setup.exe"
VERSION_PATTERN = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)(?:[-+].*)?$")


class UpdateCheckError(RuntimeError):
    pass


@dataclass(frozen=True)
class UpdateInfo:
    current_version: str
    latest_version: str
    update_available: bool
    release_url: str
    installer_url: str


def parse_version(value: str) -> tuple[int, int, int]:
    match = VERSION_PATTERN.fullmatch(value.strip())
    if not match:
        raise UpdateCheckError(f"Nieprawidłowy numer wersji: {value!r}")
    return tuple(int(part) for part in match.groups())


def normalize_version(value: str) -> str:
    major, minor, patch = parse_version(value)
    return f"{major}.{minor}.{patch}"


def is_newer_version(candidate: str, current: str) -> bool:
    return parse_version(candidate) > parse_version(current)


def check_for_updates(
    current_version: str,
    *,
    timeout: float = 8.0,
    session: requests.Session | None = None,
) -> UpdateInfo:
    requester: Any = session or requests
    try:
        response = requester.get(
            RELEASE_API_URL,
            headers={
                "Accept": "application/vnd.github+json",
                "Cache-Control": "no-cache",
                "User-Agent": f"PolySub-Translator/{current_version}",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=timeout,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise UpdateCheckError("GitHub zwrócił nieprawidłowe dane wersji.")
        latest_version = normalize_version(str(payload["tag_name"]))
        normalized_current = normalize_version(current_version)
    except UpdateCheckError:
        raise
    except (KeyError, TypeError, ValueError, requests.RequestException) as exc:
        raise UpdateCheckError(f"Nie udało się sprawdzić aktualizacji: {exc}") from exc

    release_url = _trusted_github_url(payload.get("html_url")) or RELEASE_PAGE_URL
    installer_url = release_url
    assets = payload.get("assets", [])
    if isinstance(assets, list):
        for asset in assets:
            if not isinstance(asset, dict) or asset.get("name") != INSTALLER_ASSET_NAME:
                continue
            installer_url = (
                _trusted_github_url(asset.get("browser_download_url")) or release_url
            )
            break

    return UpdateInfo(
        current_version=normalized_current,
        latest_version=latest_version,
        update_available=is_newer_version(latest_version, normalized_current),
        release_url=release_url,
        installer_url=installer_url,
    )


def _trusted_github_url(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    parsed = urlparse(value)
    if parsed.scheme != "https" or parsed.hostname != "github.com":
        return None
    return value
