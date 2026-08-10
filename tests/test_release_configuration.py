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
    installer_version = re.search(r'#define MyAppVersion "([^"]+)"', installer)

    assert project["project"]["version"] == __version__
    assert __version__ == "0.5.2"
    assert installer_version is not None
    assert installer_version.group(1) == __version__
    assert "OutputBaseFilename=PolySub-Translator-Setup-{#MyAppVersion}" in installer


def test_windows_release_assets_include_the_application_version() -> None:
    workflow = (PROJECT_ROOT / ".github" / "workflows" / "build-windows.yml").read_text(
        encoding="utf-8"
    )

    assert "PolySub-Translator-Setup-$env:POLYSUB_VERSION.exe" in workflow
    assert "PolySub-Translator-Installer-$env:POLYSUB_VERSION.zip" in workflow


def test_cli_accepts_every_catalog_model() -> None:
    parser = build_parser()
    model_action = next(action for action in parser._actions if action.dest == "local_model")

    assert model_action.default == DEFAULT_MODEL_ID
    assert tuple(model_action.choices) == tuple(model.id for model in MODEL_CATALOG)
