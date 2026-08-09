from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

MODERN_INTERFACE = "modern"
CLASSIC_INTERFACE = "classic"
DEFAULT_INTERFACE = MODERN_INTERFACE
DEFAULT_THEME = "midnight"

INTERFACE_LABELS = {
    MODERN_INTERFACE: "Nowoczesny",
    CLASSIC_INTERFACE: "Klasyczny 0.4.7",
}
INTERFACE_IDS_BY_LABEL = {label: key for key, label in INTERFACE_LABELS.items()}


@dataclass(frozen=True)
class ThemePalette:
    id: str
    label: str
    description: str
    dark: bool
    window: str
    surface: str
    panel: str
    elevated: str
    input: str
    text: str
    muted: str
    accent: str
    accent_hover: str
    accent_text: str
    border: str
    selected: str
    warning: str
    warning_text: str
    danger: str


THEMES = (
    ThemePalette(
        "system",
        "Automatyczny — system",
        "Dopasowuje jasny lub ciemny wygląd do ustawień Windows.",
        False,
        "#f3f6fb",
        "#ffffff",
        "#ffffff",
        "#f7f9fc",
        "#ffffff",
        "#172033",
        "#667085",
        "#2563eb",
        "#1d4ed8",
        "#ffffff",
        "#d8dfeb",
        "#e8f0ff",
        "#fff4d6",
        "#714600",
        "#c83d4d",
    ),
    ThemePalette(
        "oled",
        "OLED Black",
        "Prawdziwa czerń, wysoki kontrast i minimalna poświata.",
        True,
        "#000000",
        "#050505",
        "#0a0a0a",
        "#111111",
        "#111111",
        "#f7f7f8",
        "#a1a1aa",
        "#3b82f6",
        "#60a5fa",
        "#ffffff",
        "#252525",
        "#10264b",
        "#332400",
        "#ffd76a",
        "#fb7185",
    ),
    ThemePalette(
        "midnight",
        "Midnight Blue — zalecany",
        "Nowoczesny granat z czytelnymi niebieskimi akcentami.",
        True,
        "#0b1220",
        "#111a2b",
        "#162238",
        "#1b2942",
        "#0e1728",
        "#edf4ff",
        "#9aacc4",
        "#4f8cff",
        "#72a4ff",
        "#ffffff",
        "#283a56",
        "#18345f",
        "#3a2b0e",
        "#ffd778",
        "#ff6b7d",
    ),
    ThemePalette(
        "graphite",
        "Graphite Pro",
        "Spokojna, profesjonalna szarość do długiej pracy.",
        True,
        "#16181d",
        "#1d2026",
        "#242830",
        "#2b3039",
        "#191c21",
        "#f0f1f3",
        "#a6abb4",
        "#8b9cff",
        "#a7b3ff",
        "#ffffff",
        "#383e49",
        "#343c69",
        "#3a301b",
        "#f2d27e",
        "#ff7888",
    ),
    ThemePalette(
        "cyber",
        "Cyber Neon",
        "Ciemne tło z energicznym turkusowym neonem.",
        True,
        "#061114",
        "#0a191d",
        "#0d2227",
        "#123039",
        "#07171b",
        "#e7fffd",
        "#82b5b3",
        "#00d8c8",
        "#34f0df",
        "#001413",
        "#1d464b",
        "#0b4544",
        "#3b3005",
        "#ffe36e",
        "#ff6688",
    ),
    ThemePalette(
        "aurora",
        "Aurora Violet",
        "Fioletowy, filmowy motyw z miękkim kontrastem.",
        True,
        "#120d20",
        "#1a132c",
        "#241a3c",
        "#30234e",
        "#171025",
        "#f7efff",
        "#b4a0ca",
        "#a970ff",
        "#c195ff",
        "#ffffff",
        "#423259",
        "#3a2662",
        "#3f2c12",
        "#ffd27a",
        "#ff7398",
    ),
    ThemePalette(
        "emerald",
        "Emerald Matrix",
        "Głęboka zieleń z nowoczesnym szmaragdowym akcentem.",
        True,
        "#07140f",
        "#0c1d16",
        "#10271e",
        "#163428",
        "#091811",
        "#ecfff6",
        "#91b7a4",
        "#25c783",
        "#45dfa0",
        "#03130c",
        "#24503d",
        "#154d37",
        "#3a3010",
        "#f7d86c",
        "#ff7288",
    ),
    ThemePalette(
        "crimson",
        "Crimson Studio",
        "Grafitowe studio z eleganckim czerwonym akcentem.",
        True,
        "#170d10",
        "#211317",
        "#2b191e",
        "#382128",
        "#1b1013",
        "#fff1f3",
        "#c09ba3",
        "#e84d67",
        "#ff7088",
        "#ffffff",
        "#503038",
        "#552431",
        "#422d12",
        "#ffd177",
        "#ff6b75",
    ),
    ThemePalette(
        "arctic",
        "Arctic Light",
        "Bardzo jasny, czysty motyw z chłodnym błękitem.",
        False,
        "#eef5fa",
        "#f8fbfd",
        "#ffffff",
        "#f3f8fb",
        "#ffffff",
        "#132a3a",
        "#63798a",
        "#1677b8",
        "#0f6096",
        "#ffffff",
        "#ccdae4",
        "#dceeff",
        "#fff2cf",
        "#715000",
        "#c63e55",
    ),
    ThemePalette(
        "sand",
        "Warm Sand",
        "Ciepły, łagodny motyw do wieczornego czytania.",
        False,
        "#f5efe5",
        "#fffaf2",
        "#fffdf8",
        "#f8f0e4",
        "#fffdf8",
        "#34291e",
        "#796958",
        "#b56732",
        "#945027",
        "#ffffff",
        "#dfd1bd",
        "#f1dfca",
        "#f8e7bd",
        "#6d4b13",
        "#bd4250",
    ),
)

THEMES_BY_ID = {theme.id: theme for theme in THEMES}
THEME_IDS_BY_LABEL = {theme.label: theme.id for theme in THEMES}


@dataclass(frozen=True)
class AppearanceSettings:
    interface: str = DEFAULT_INTERFACE
    theme: str = DEFAULT_THEME

    def normalized(self) -> AppearanceSettings:
        interface = self.interface if self.interface in INTERFACE_LABELS else DEFAULT_INTERFACE
        theme = self.theme if self.theme in THEMES_BY_ID else DEFAULT_THEME
        return AppearanceSettings(interface=interface, theme=theme)


def default_settings_path() -> Path:
    override = os.getenv("POLYSUB_SETTINGS_DIR")
    if override:
        return Path(override).expanduser() / "appearance.json"
    if os.name == "nt":
        base = os.getenv("LOCALAPPDATA") or os.getenv("APPDATA")
        if base:
            return Path(base) / "PolySub Translator" / "appearance.json"
    config_home = os.getenv("XDG_CONFIG_HOME")
    base = Path(config_home).expanduser() if config_home else Path.home() / ".config"
    return base / "polysub-translator" / "appearance.json"


class AppearanceSettingsStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_settings_path()

    def load(self) -> AppearanceSettings:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return AppearanceSettings()
        if not isinstance(payload, dict):
            return AppearanceSettings()
        return AppearanceSettings(
            interface=str(payload.get("interface", DEFAULT_INTERFACE)),
            theme=str(payload.get("theme", DEFAULT_THEME)),
        ).normalized()

    def save(self, settings: AppearanceSettings) -> None:
        normalized = settings.normalized()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(asdict(normalized), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.path)


def resolve_theme(theme_id: str) -> ThemePalette:
    theme = THEMES_BY_ID.get(theme_id, THEMES_BY_ID[DEFAULT_THEME])
    if theme.id != "system" or not _windows_prefers_dark_mode():
        return theme
    return THEMES_BY_ID[DEFAULT_THEME]


def _windows_prefers_dark_mode() -> bool:
    if os.name != "nt":
        return False
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        ) as key:
            value, _kind = winreg.QueryValueEx(key, "AppsUseLightTheme")
        return int(value) == 0
    except (ImportError, OSError, TypeError, ValueError):
        return False
