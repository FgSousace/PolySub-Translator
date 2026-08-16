import re
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib

from polysub import __version__
from polysub.cli import build_parser
from polysub.translation_models import DEFAULT_MODEL_ID, MODEL_CATALOG

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_version_is_consistent_in_python_project_and_installer() -> None:
    project = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    installer = (PROJECT_ROOT / "packaging" / "PolySubTranslator.iss").read_text(
        encoding="utf-8"
    )
    version_info = (PROJECT_ROOT / "packaging" / "version_info.txt").read_text(
        encoding="utf-8"
    )
    installer_version = re.search(r'#define MyAppVersion "([^"]+)"', installer)
    numeric_version = ", ".join(__version__.split(".")) + ", 0"

    assert project["project"]["version"] == __version__
    assert __version__ == "0.5.9"
    assert installer_version is not None
    assert installer_version.group(1) == __version__
    assert "OutputBaseFilename=PolySub-Translator-Setup-{#MyAppVersion}" in installer
    assert f"filevers=({numeric_version})" in version_info
    assert f"prodvers=({numeric_version})" in version_info
    assert f"StringStruct(u'FileVersion', u'{__version__}')" in version_info


def test_windows_release_assets_include_the_application_version() -> None:
    workflow = (PROJECT_ROOT / ".github" / "workflows" / "build-windows.yml").read_text(
        encoding="utf-8"
    )

    assert "PolySub-Translator-Setup-$env:POLYSUB_VERSION.exe" in workflow
    assert "PolySub-Translator-Installer-$env:POLYSUB_VERSION.zip" in workflow
    assert "--self-test-local-ai" in workflow


def test_windows_package_avoids_upx_and_scans_release_with_defender() -> None:
    spec = (PROJECT_ROOT / "packaging" / "PolySubTranslator.spec").read_text(
        encoding="utf-8"
    )
    workflow = (PROJECT_ROOT / ".github" / "workflows" / "build-windows.yml").read_text(
        encoding="utf-8"
    )
    scanner = (PROJECT_ROOT / "scripts" / "scan_windows_release.ps1").read_text(
        encoding="utf-8"
    )

    assert "upx=True" not in spec
    assert spec.count("upx=False") == 2
    assert "tiktoken" in spec
    assert "scan_windows_release.ps1" in workflow
    assert "-DisableRemediation" in scanner
    assert "MpCmdRun.exe" in scanner


def test_historical_release_notes_are_separate_and_version_specific() -> None:
    notes_dir = PROJECT_ROOT / "packaging" / "release-notes"
    notes = sorted(notes_dir.glob("v*.md"))
    expected = {f"v0.4.{minor}" for minor in range(1, 10)} | {
        "v0.5.0",
        "v0.5.1",
        "v0.5.2",
        "v0.5.3",
        "v0.5.4",
        "v0.5.5",
        "v0.5.6",
        "v0.5.7",
        "v0.5.8",
    }

    assert {path.stem for path in notes} == expected
    for path in notes:
        body = path.read_text(encoding="utf-8")
        headings = re.findall(r"^## PolySub Translator (\d+\.\d+\.\d+)$", body, re.MULTILINE)
        assert headings == [path.stem.removeprefix("v")]
        assert "Wcześniej dodane" not in body
        assert "Wcześniej poprawione" not in body

    workflow = (PROJECT_ROOT / ".github" / "workflows" / "build-windows.yml").read_text(
        encoding="utf-8"
    )
    assert "Keep every release description version-specific" in workflow
    assert "gh release edit $tag --notes-file" in workflow

    current_body = (PROJECT_ROOT / "packaging" / "RELEASE_NOTES.md").read_text(
        encoding="utf-8"
    )
    current_headings = re.findall(
        r"^## PolySub Translator (\d+\.\d+\.\d+)$",
        current_body,
        re.MULTILINE,
    )
    assert current_headings == [__version__]
    assert "Wcześniej dodane" not in current_body
    assert "Wcześniej poprawione" not in current_body


def test_author_name_uses_a_capital_f_in_every_user_facing_file() -> None:
    author = "FgSousace"
    lowercase_variant = author[0].lower() + author[1:]
    text_suffixes = {
        ".iss",
        ".json",
        ".md",
        ".ps1",
        ".py",
        ".spec",
        ".toml",
        ".txt",
        ".yaml",
        ".yml",
    }
    ignored_directories = {".git", ".pytest_cache", ".ruff_cache", ".venv"}
    paths = (
        path
        for path in PROJECT_ROOT.rglob("*")
        if path.is_file()
        and path.suffix.casefold() in text_suffixes
        and not ignored_directories.intersection(path.parts)
    )

    for path in paths:
        assert lowercase_variant not in path.read_text(encoding="utf-8"), path


def test_cli_accepts_every_catalog_model() -> None:
    parser = build_parser()
    model_action = next(action for action in parser._actions if action.dest == "local_model")

    assert model_action.default == DEFAULT_MODEL_ID
    assert tuple(model_action.choices) == tuple(model.id for model in MODEL_CATALOG)
