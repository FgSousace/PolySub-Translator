import json

from polysub.appearance import (
    CLASSIC_INTERFACE,
    DEFAULT_INTERFACE,
    DEFAULT_THEME,
    MODERN_INTERFACE,
    THEMES,
    AppearanceSettings,
    AppearanceSettingsStore,
    resolve_theme,
)


def test_catalog_contains_ten_unique_complete_themes() -> None:
    assert len(THEMES) == 10
    assert len({theme.id for theme in THEMES}) == 10
    assert len({theme.label for theme in THEMES}) == 10
    assert {"system", "oled", "midnight", "graphite", "cyber"}.issubset(
        {theme.id for theme in THEMES}
    )
    for theme in THEMES:
        assert theme.description
        assert theme.window.startswith("#")
        assert theme.text.startswith("#")
        assert theme.accent.startswith("#")


def test_default_appearance_is_modern_midnight() -> None:
    settings = AppearanceSettings()

    assert settings.interface == MODERN_INTERFACE == DEFAULT_INTERFACE
    assert settings.theme == "midnight" == DEFAULT_THEME
    assert resolve_theme(settings.theme).id == "midnight"


def test_settings_store_round_trip(tmp_path) -> None:
    path = tmp_path / "nested" / "appearance.json"
    store = AppearanceSettingsStore(path)
    expected = AppearanceSettings(interface=CLASSIC_INTERFACE, theme="oled")

    store.save(expected)

    assert store.load() == expected
    assert json.loads(path.read_text(encoding="utf-8")) == {
        "interface": "classic",
        "theme": "oled",
    }


def test_settings_store_recovers_from_invalid_or_unknown_values(tmp_path) -> None:
    path = tmp_path / "appearance.json"
    store = AppearanceSettingsStore(path)
    path.write_text('{"interface": "future", "theme": "missing"}', encoding="utf-8")

    assert store.load() == AppearanceSettings()

    path.write_text("not-json", encoding="utf-8")
    assert store.load() == AppearanceSettings()

