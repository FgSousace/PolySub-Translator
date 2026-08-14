from __future__ import annotations

import ctypes
import os
import threading
import time
import tkinter as tk
import webbrowser
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

from . import __version__
from .amd_runtime import (
    AMD_RUNTIME_TARGET_PREFIX,
    ROCM_VERSION,
    amd_runtime_log_path,
    install_amd_runtime,
    select_amd_runtime_plan,
    write_amd_runtime_diagnostic,
)
from .appearance import (
    DEFAULT_INTERFACE,
    DEFAULT_THEME,
    INTERFACE_IDS_BY_LABEL,
    INTERFACE_LABELS,
    MODERN_INTERFACE,
    THEME_IDS_BY_LABEL,
    THEMES,
    AppearanceSettings,
    AppearanceSettingsStore,
    ThemePalette,
    resolve_theme,
)
from .branding import ABOUT_TEXT, AUTHOR, COPYRIGHT, PRODUCT_NAME
from .cancellation import CancellationToken, TranslationCancelled
from .compute_devices import (
    AUTO_DEVICE_ID,
    AUTO_DEVICE_LABEL,
    ComputeDevice,
    DeviceResolution,
    TaskKind,
    describe_device_support,
    detect_compute_devices,
    resolve_compute_device,
)
from .detector import detect_language
from .engines import DeepLEngine, RocmWorkerEngine, create_local_engine
from .languages import language_name, language_options, parse_language_option
from .model_downloads import model_status
from .model_manager_window import ModelManagerWindow
from .models import TranslationMode
from .narrator import (
    ChatterboxNarrator,
    NarrationResult,
    narrator_video_output_path,
)
from .narrator_models import CHATTERBOX_MULTILINGUAL_V3
from .performance import DEFAULT_CPU_USAGE, cpu_allocation
from .service import TranslationOptions, TranslationService
from .subtitle_timing import (
    SubtitleTimingError,
    SubtitleTimingMode,
    SubtitleTimingSettings,
    optimize_subtitle_timing,
)
from .subtitles import SRTDocument, default_output_path
from .translation_models import (
    DEFAULT_MODEL_ID,
    MODEL_CATALOG,
    TranslationModelSpec,
    get_model_spec,
)
from .updates import UpdateCheckError, UpdateInfo, check_for_updates
from .video import (
    VIDEO_EXTENSIONS,
    VideoBurnResult,
    VideoImportResult,
    VideoSubtitleBurner,
    VideoSubtitleImporter,
    VideoSubtitleMuxer,
    burned_video_output_path,
    fast_mux_output_path,
    format_media_duration,
    translated_video_subtitle_path,
)
from .whisper_models import (
    DEFAULT_WHISPER_MODEL_ID,
    WHISPER_MODEL_CATALOG,
    WhisperModelSpec,
    get_whisper_model_spec,
)

LOCAL_ENGINE_LABEL = "Lokalny AI — wybierz model"

ENGINE_LABELS = {
    LOCAL_ENGINE_LABEL: "local",
    "DeepL API": "deepl",
}

MODEL_LABEL_TO_ID = {model.selection_label: model.id for model in MODEL_CATALOG}
MODEL_ID_TO_LABEL = {model.id: model.selection_label for model in MODEL_CATALOG}
MODEL_NOT_READY_LABEL = "Brak pobranych modeli — otwórz menedżer"

SUPPORTED_INPUT_EXTENSIONS = {".srt", *VIDEO_EXTENSIONS}
SUPPORTED_INPUT_PATTERN = " ".join(
    f"*{extension}" for extension in sorted(SUPPORTED_INPUT_EXTENSIONS)
)
VIDEO_INPUT_PATTERN = " ".join(f"*{extension}" for extension in sorted(VIDEO_EXTENSIONS))
INPUT_FILE_TYPES = (
    ("Wszystkie obsługiwane napisy i filmy", SUPPORTED_INPUT_PATTERN),
    ("Napisy SubRip", "*.srt"),
    ("Pliki wideo", VIDEO_INPUT_PATTERN),
    ("Wszystkie pliki", "*.*"),
)

WHISPER_LABEL_TO_ID = {model.selection_label: model.id for model in WHISPER_MODEL_CATALOG}
WHISPER_ID_TO_LABEL = {model.id: model.selection_label for model in WHISPER_MODEL_CATALOG}
WHISPER_NOT_READY_LABEL = "Brak pobranego Whispera — otwórz menedżer"

CPU_USAGE_LABELS = {
    "100% — maksymalna wydajność": 100,
    "75% — wysokie obciążenie": 75,
    "50% — połowa procesora": 50,
    "25% — lekkie obciążenie": 25,
}

TIMING_PROFILE_CARDS = (
    (SubtitleTimingMode.DYNAMIC, "⚡ Krótsze", "1,0 s • szybkie dialogi"),
    (SubtitleTimingMode.RECOMMENDED, "★ Zalecane", "1,5 s • najlepszy balans"),
    (SubtitleTimingMode.COMFORTABLE, "◷ Dłuższe", "2,0 s • spokojne czytanie"),
    (SubtitleTimingMode.ORIGINAL, "↺ Oryginalne", "Czasy źródłowe 1:1"),
    (SubtitleTimingMode.CUSTOM, "⚙ Własne", "Ustaw własne tempo"),
)


def enable_windows_dpi_awareness() -> None:
    if os.name != "nt":
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError):
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except (AttributeError, OSError):
            pass


def recommended_window_size(
    screen_width: int,
    screen_height: int,
    *,
    target_width: int = 1000,
) -> tuple[int, int]:
    """Fit the main window to the usable screen without hiding its bottom actions."""
    available_width = max(screen_width - 40, min(screen_width, 360))
    available_height = max(screen_height - 80, min(screen_height, 420))
    return min(target_width, available_width), min(900, available_height)


def format_elapsed(seconds: float) -> str:
    elapsed = max(int(seconds), 0)
    hours, remainder = divmod(elapsed, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


class PolySubApp(tk.Tk):
    def __init__(
        self,
        *,
        appearance_settings: AppearanceSettings | None = None,
        appearance_store: AppearanceSettingsStore | None = None,
        schedule_background_tasks: bool = True,
    ) -> None:
        super().__init__()
        self._appearance_store = appearance_store or AppearanceSettingsStore()
        self.appearance = (
            appearance_settings or self._appearance_store.load()
        ).normalized()
        self.theme: ThemePalette = resolve_theme(self.appearance.theme)
        self.appearance_interface_var = tk.StringVar(
            value=INTERFACE_LABELS[self.appearance.interface]
        )
        self.appearance_theme_var = tk.StringVar(
            value=next(
                theme.label for theme in THEMES if theme.id == self.appearance.theme
            )
        )
        self.appearance_description_var = tk.StringVar()
        self._appearance_dialog: tk.Toplevel | None = None
        self._modern_nav_buttons: dict[str, ttk.Button] = {}
        self._content_sections: dict[str, tk.Widget] = {}
        self.title(PRODUCT_NAME)
        width, height = recommended_window_size(
            self.winfo_screenwidth(),
            self.winfo_screenheight(),
            target_width=1220 if self.appearance.interface == MODERN_INTERFACE else 1000,
        )
        left = max((self.winfo_screenwidth() - width) // 2, 0)
        top = max((self.winfo_screenheight() - height) // 2, 0)
        self.geometry(f"{width}x{height}+{left}+{top}")
        minimum_width = 860 if self.appearance.interface == MODERN_INTERFACE else 700
        self.minsize(min(minimum_width, width), min(560, height))
        self.document: SRTDocument | None = None
        self.source_path: Path | None = None
        self.media_path: Path | None = None
        self.translated_subtitle_path: Path | None = None
        self.translated_target_language: str | None = None
        self._activity_stages: list[str] = []
        self._activity_active = False
        self._activity_started_at = 0.0
        self._heartbeat_job: str | None = None
        self._last_log_message: str | None = None
        self._update_check_running = False
        self._update_download_url: str | None = None
        self._compute_devices: list[ComputeDevice] = []
        self._device_label_to_id: dict[str, str] = {}
        self._selected_device_id = AUTO_DEVICE_ID
        self._device_detection_running = False
        self._model_manager_window: ModelManagerWindow | None = None
        self._timing_controls_locked = False
        self._translation_cancel_token: CancellationToken | None = None
        self._active_translation_engine = None
        self._translation_running = False
        self._amd_runtime_setup_running = False
        self._amd_runtime_attempted = False
        self._build_style()
        self._build_ui()
        self._apply_theme_to_widgets()
        if schedule_background_tasks:
            self.after(200, self._start_device_detection)
            self.after(1200, self._start_update_check)

    def _build_style(self) -> None:
        style = ttk.Style(self)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        palette = self.theme
        self.configure(background=palette.window)
        style.configure(
            ".",
            background=palette.surface,
            foreground=palette.text,
            fieldbackground=palette.input,
            bordercolor=palette.border,
            lightcolor=palette.border,
            darkcolor=palette.border,
            troughcolor=palette.elevated,
            font=("Segoe UI", 10),
        )
        style.configure("TFrame", background=palette.surface)
        style.configure("Content.TFrame", background=palette.window)
        style.configure("Hero.TFrame", background=palette.window)
        style.configure("Sidebar.TFrame", background=palette.panel)
        style.configure("TLabel", background=palette.surface, foreground=palette.text)
        style.configure(
            "Muted.TLabel",
            background=palette.surface,
            foreground=palette.muted,
        )
        style.configure(
            "Sidebar.TLabel",
            background=palette.panel,
            foreground=palette.text,
        )
        style.configure(
            "SidebarMuted.TLabel",
            background=palette.panel,
            foreground=palette.muted,
        )
        style.configure(
            "Title.TLabel",
            background=palette.surface,
            foreground=palette.text,
            font=("Segoe UI", 22, "bold"),
        )
        style.configure(
            "HeroTitle.TLabel",
            background=palette.window,
            foreground=palette.text,
            font=("Segoe UI", 24, "bold"),
        )
        style.configure(
            "HeroMuted.TLabel",
            background=palette.window,
            foreground=palette.muted,
        )
        style.configure(
            "Brand.TLabel",
            background=palette.panel,
            foreground=palette.text,
            font=("Segoe UI", 16, "bold"),
        )
        style.configure(
            "Eyebrow.TLabel",
            background=palette.surface,
            foreground=palette.accent,
            font=("Segoe UI", 9, "bold"),
        )
        style.configure(
            "HeroEyebrow.TLabel",
            background=palette.window,
            foreground=palette.accent,
            font=("Segoe UI", 9, "bold"),
        )
        style.configure(
            "Heading.TLabel",
            background=palette.surface,
            foreground=palette.text,
            font=("Segoe UI", 11, "bold"),
        )
        style.configure(
            "TLabelframe",
            background=palette.surface,
            bordercolor=palette.border,
            relief="solid",
            borderwidth=1,
        )
        style.configure(
            "TLabelframe.Label",
            background=palette.surface,
            foreground=palette.text,
            font=("Segoe UI", 10, "bold"),
        )
        style.configure(
            "TButton",
            background=palette.elevated,
            foreground=palette.text,
            bordercolor=palette.border,
            padding=(11, 7),
        )
        style.map(
            "TButton",
            background=[("active", palette.selected), ("pressed", palette.selected)],
            foreground=[("disabled", palette.muted)],
        )
        style.configure(
            "Primary.TButton",
            background=palette.accent,
            foreground=palette.accent_text,
            bordercolor=palette.accent,
            font=("Segoe UI", 11, "bold"),
            padding=(16, 11),
        )
        style.map(
            "Primary.TButton",
            background=[
                ("active", palette.accent_hover),
                ("pressed", palette.accent_hover),
                ("disabled", palette.border),
            ],
            foreground=[("disabled", palette.muted)],
        )
        style.configure(
            "Nav.TButton",
            background=palette.panel,
            foreground=palette.muted,
            bordercolor=palette.panel,
            anchor="w",
            padding=(14, 10),
            font=("Segoe UI", 10, "bold"),
        )
        style.map(
            "Nav.TButton",
            background=[("active", palette.elevated), ("pressed", palette.selected)],
            foreground=[("active", palette.text)],
        )
        style.configure(
            "SelectedNav.TButton",
            background=palette.selected,
            foreground=palette.accent_hover,
            bordercolor=palette.accent,
            anchor="w",
            padding=(14, 10),
            font=("Segoe UI", 10, "bold"),
        )
        style.map(
            "SelectedNav.TButton",
            background=[("active", palette.selected), ("pressed", palette.selected)],
            foreground=[("active", palette.accent_hover)],
        )
        style.configure(
            "Mode.TCheckbutton",
            background=palette.surface,
            foreground=palette.text,
            font=("Segoe UI", 11, "bold"),
            padding=8,
        )
        style.map(
            "Mode.TCheckbutton",
            background=[("active", palette.surface)],
            foreground=[("active", palette.accent_hover)],
            indicatorcolor=[("selected", palette.accent)],
        )
        style.configure(
            "Danger.TButton",
            background=palette.danger,
            foreground=palette.accent_text,
            bordercolor=palette.danger,
            font=("Segoe UI", 10, "bold"),
            padding=(14, 11),
        )
        style.configure(
            "TCombobox",
            fieldbackground=palette.input,
            background=palette.elevated,
            foreground=palette.text,
            arrowcolor=palette.text,
            bordercolor=palette.border,
            padding=5,
        )
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", palette.input), ("disabled", palette.elevated)],
            foreground=[("readonly", palette.text), ("disabled", palette.muted)],
            selectbackground=[("readonly", palette.input)],
            selectforeground=[("readonly", palette.text)],
        )
        for widget_style in ("TEntry", "TSpinbox"):
            style.configure(
                widget_style,
                fieldbackground=palette.input,
                foreground=palette.text,
                insertcolor=palette.text,
                bordercolor=palette.border,
                padding=5,
            )
        style.configure(
            "Treeview",
            background=palette.input,
            fieldbackground=palette.input,
            foreground=palette.text,
            bordercolor=palette.border,
            rowheight=27,
        )
        style.map(
            "Treeview",
            background=[("selected", palette.accent)],
            foreground=[("selected", palette.accent_text)],
        )
        style.configure(
            "Treeview.Heading",
            background=palette.elevated,
            foreground=palette.text,
            bordercolor=palette.border,
            font=("Segoe UI", 9, "bold"),
        )
        style.map("Treeview.Heading", background=[("active", palette.selected)])
        style.configure(
            "TProgressbar",
            background=palette.accent,
            troughcolor=palette.elevated,
            bordercolor=palette.border,
        )
        self.option_add("*TCombobox*Listbox.background", palette.input)
        self.option_add("*TCombobox*Listbox.foreground", palette.text)
        self.option_add("*TCombobox*Listbox.selectBackground", palette.accent)
        self.option_add("*TCombobox*Listbox.selectForeground", palette.accent_text)

    def _build_ui(self) -> None:
        modern = self.appearance.interface == MODERN_INTERFACE
        self.rowconfigure(0, weight=1)
        self.rowconfigure(1, weight=0)
        self.rowconfigure(2, weight=0)
        self.columnconfigure(0, weight=0 if modern else 1)
        self.columnconfigure(1, weight=1 if modern else 0)

        self._content_sections = {}
        self._modern_nav_buttons = {}
        if modern:
            self._build_modern_sidebar()

        content_column = 1 if modern else 0
        self._content_column = content_column
        main_host = ttk.Frame(self, style="Content.TFrame")
        main_host.grid(row=0, column=content_column, sticky="nsew")
        main_host.rowconfigure(0, weight=1)
        main_host.columnconfigure(0, weight=1)

        self.content_canvas = tk.Canvas(
            main_host,
            background=self.theme.window,
            borderwidth=0,
            highlightthickness=0,
        )
        content_scrollbar = ttk.Scrollbar(
            main_host,
            orient="vertical",
            command=self.content_canvas.yview,
        )
        self.content_canvas.configure(yscrollcommand=content_scrollbar.set)
        self.content_canvas.grid(row=0, column=0, sticky="nsew")
        content_scrollbar.grid(row=0, column=1, sticky="ns")

        container = ttk.Frame(
            self.content_canvas,
            style="Content.TFrame",
            padding=(28 if modern else 24, 24 if modern else 20, 24, 16),
        )
        self.content_container = container
        self.content_window = self.content_canvas.create_window(
            (0, 0),
            window=container,
            anchor="nw",
        )
        container.bind("<Configure>", self._sync_scroll_region)
        self.content_canvas.bind("<Configure>", self._resize_scroll_content)
        self.bind("<MouseWheel>", self._scroll_main_content)

        if modern:
            ttk.Label(container, text="POLYSUB TRANSLATOR", style="HeroEyebrow.TLabel").pack(
                anchor="w"
            )
        ttk.Label(
            container,
            text=PRODUCT_NAME,
            style="HeroTitle.TLabel" if modern else "Title.TLabel",
        ).pack(anchor="w")
        ttk.Label(
            container,
            text=(
                "Nowoczesne centrum tłumaczenia filmów i napisów."
                if modern
                else "Wykrywa język, tłumaczy napisy i pilnuje ich czytelnej synchronizacji."
            ),
            style="HeroMuted.TLabel" if modern else "TLabel",
        ).pack(anchor="w", pady=(2, 5))

        version_frame = ttk.Frame(container, style="Hero.TFrame" if modern else "TFrame")
        version_frame.pack(fill="x", pady=(0, 16))
        version_frame.columnconfigure(0, weight=1)
        self.version_status_var = tk.StringVar(
            value=f"Wersja {__version__} • automatyczne sprawdzanie aktualizacji"
        )
        ttk.Label(
            version_frame,
            textvariable=self.version_status_var,
            style="HeroMuted.TLabel" if modern else "TLabel",
        ).grid(
            row=0,
            column=0,
            sticky="w",
        )
        self.download_update_button = ttk.Button(
            version_frame,
            text="Pobierz aktualizację",
            command=self._open_update_download,
        )
        self.download_update_button.grid(row=0, column=1, sticky="e", padx=(10, 6))
        self.download_update_button.grid_remove()
        self.check_update_button = ttk.Button(
            version_frame,
            text="Sprawdź aktualizacje",
            command=self._start_update_check,
        )
        self.check_update_button.grid(row=0, column=2, sticky="e")
        self.appearance_button = ttk.Button(
            version_frame,
            text="Wygląd…",
            command=self._open_appearance_dialog,
        )
        self.appearance_button.grid(row=0, column=3, sticky="e", padx=(6, 0))
        self.about_button = ttk.Button(
            version_frame,
            text="O programie",
            command=self._show_about,
        )
        self.about_button.grid(row=0, column=4, sticky="e", padx=(6, 0))

        file_frame = ttk.LabelFrame(container, text="1. Napisy lub film", padding=14)
        file_frame.pack(fill="x")
        self._content_sections["start"] = file_frame
        file_frame.columnconfigure(0, weight=1)
        self.file_var = tk.StringVar(value="Nie wybrano pliku")
        ttk.Label(file_frame, textvariable=self.file_var, wraplength=650).grid(
            row=0, column=0, sticky="ew"
        )
        self.file_button = ttk.Button(
            file_frame, text="Wybierz napisy lub film…", command=self._choose_file
        )
        self.file_button.grid(row=0, column=1, sticky="e", padx=(12, 0))
        self.file_details_var = tk.StringVar(
            value="Obsługiwane wejście: napisy SRT oraz filmy MP4, MKV, MOV, AVI, M4V i WEBM."
        )
        ttk.Label(
            file_frame,
            textvariable=self.file_details_var,
            style="Muted.TLabel",
            wraplength=650,
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(7, 0))
        ttk.Label(
            file_frame,
            text="Gdy film nie ma napisów:",
        ).grid(row=2, column=0, sticky="e", pady=(10, 0), padx=(0, 8))
        self.speech_model_var = tk.StringVar(value=WHISPER_NOT_READY_LABEL)
        self.speech_model_combo = ttk.Combobox(
            file_frame,
            textvariable=self.speech_model_var,
            values=(WHISPER_NOT_READY_LABEL,),
            state="readonly",
            width=54,
        )
        self.speech_model_combo.grid(row=2, column=1, sticky="e", pady=(10, 0))

        language_frame = ttk.LabelFrame(container, text="2. Języki", padding=14)
        language_frame.pack(fill="x", pady=12)
        self._content_sections["translation"] = language_frame
        language_frame.columnconfigure(1, weight=1)
        language_frame.columnconfigure(3, weight=1)
        ttk.Label(language_frame, text="Wykryty język:").grid(row=0, column=0, sticky="w")
        self.source_var = tk.StringVar(value="—")
        self.source_combo = ttk.Combobox(
            language_frame, textvariable=self.source_var, values=language_options(), state="normal"
        )
        self.source_combo.grid(row=0, column=1, sticky="ew", padx=(8, 24))
        self.source_combo.bind(
            "<<ComboboxSelected>>",
            lambda _event: self._refresh_model_status(),
        )
        self.source_combo.bind("<FocusOut>", lambda _event: self._refresh_model_status())
        ttk.Label(language_frame, text="Język docelowy:").grid(row=0, column=2, sticky="w")
        self.target_var = tk.StringVar(value=f"{language_name('pl')} (pl)")
        self.target_combo = ttk.Combobox(
            language_frame, textvariable=self.target_var, values=language_options(), state="normal"
        )
        self.target_combo.grid(row=0, column=3, sticky="ew", padx=(8, 0))
        self.target_combo.bind(
            "<<ComboboxSelected>>",
            lambda _event: self._refresh_model_status(),
        )
        self.target_combo.bind("<FocusOut>", lambda _event: self._refresh_model_status())
        self.detected_var = tk.StringVar(value="Wybierz plik, aby wykryć język.")
        ttk.Label(language_frame, textvariable=self.detected_var).grid(
            row=1, column=0, columnspan=4, sticky="w", pady=(8, 0)
        )

        settings = ttk.Frame(container)
        settings.pack(fill="both", expand=True)
        settings.columnconfigure(0, weight=1)
        settings.columnconfigure(1, weight=1)

        engine_frame = ttk.LabelFrame(settings, text="3. Silnik", padding=14)
        engine_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        self._content_sections["models"] = engine_frame
        self.engine_var = tk.StringVar(value=LOCAL_ENGINE_LABEL)
        self.engine_combo = ttk.Combobox(
            engine_frame,
            textvariable=self.engine_var,
            values=list(ENGINE_LABELS),
            state="readonly",
        )
        self.engine_combo.pack(fill="x")
        self.engine_combo.bind(
            "<<ComboboxSelected>>",
            lambda _event: self._update_api_state(),
        )
        ttk.Label(engine_frame, text="Model lokalnego AI:").pack(
            anchor="w",
            pady=(10, 3),
        )
        model_row = ttk.Frame(engine_frame)
        model_row.pack(fill="x")
        model_row.columnconfigure(0, weight=1)
        self.model_var = tk.StringVar(value=MODEL_NOT_READY_LABEL)
        self.model_combo = ttk.Combobox(
            model_row,
            textvariable=self.model_var,
            values=(MODEL_NOT_READY_LABEL,),
            state="readonly",
        )
        self.model_combo.grid(row=0, column=0, sticky="ew")
        self.model_combo.bind(
            "<<ComboboxSelected>>",
            lambda _event: self._model_selection_changed(),
        )
        self.model_manager_button = ttk.Button(
            model_row,
            text="Pobierz / usuń…",
            command=self._open_model_manager,
        )
        self.model_manager_button.grid(row=0, column=1, padx=(8, 0))
        self.model_status_var = tk.StringVar(value="Sprawdzanie modelu…")
        ttk.Label(
            engine_frame,
            textvariable=self.model_status_var,
            wraplength=420,
        ).pack(anchor="w", pady=(5, 0))
        ttk.Label(engine_frame, text="Klucz DeepL API (nie jest zapisywany):").pack(
            anchor="w", pady=(10, 3)
        )
        self.api_key_var = tk.StringVar(value=os.getenv("DEEPL_API_KEY", ""))
        self.api_entry = ttk.Entry(engine_frame, textvariable=self.api_key_var, show="•")
        self.api_entry.pack(fill="x")

        mode_frame = ttk.LabelFrame(settings, text="4. Tryb tłumaczenia", padding=14)
        mode_frame.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        self.mode_var = tk.StringVar(value="")
        self.automatic_mode_checked = tk.BooleanVar(value=False)
        self.review_mode_checked = tk.BooleanVar(value=False)
        self.automatic_mode_checkbox = ttk.Checkbutton(
            mode_frame,
            text="⚡ Tłumacz automatycznie",
            variable=self.automatic_mode_checked,
            command=lambda: self._select_translation_mode(TranslationMode.AUTOMATIC),
            style="Mode.TCheckbutton",
        )
        self.automatic_mode_checkbox.pack(anchor="w")
        ttk.Label(mode_frame, text="Szybko, bez dodatkowych pytań.").pack(anchor="w", padx=28)
        self.review_mode_checkbox = ttk.Checkbutton(
            mode_frame,
            text="🎯 Tłumacz z weryfikacją",
            variable=self.review_mode_checked,
            command=lambda: self._select_translation_mode(TranslationMode.REVIEW),
            style="Mode.TCheckbutton",
        )
        self.review_mode_checkbox.pack(anchor="w", pady=(10, 0))
        ttk.Label(mode_frame, text="Kontekst i edycja niejasnych kwestii.").pack(
            anchor="w", padx=28
        )
        ttk.Label(
            mode_frame,
            text="Wymagane: zaznacz dokładnie jeden tryb przed rozpoczęciem.",
            style="Muted.TLabel",
            wraplength=360,
        ).pack(anchor="w", pady=(10, 0))

        compute_frame = ttk.LabelFrame(
            container,
            text="5. Urządzenie obliczeniowe",
            padding=12,
        )
        compute_frame.pack(fill="x", pady=(12, 0))
        self._content_sections["film"] = compute_frame
        compute_frame.columnconfigure(0, weight=1)
        self.device_var = tk.StringVar(value="Automatycznie — wykrywanie sprzętu…")
        self.device_combo = ttk.Combobox(
            compute_frame,
            textvariable=self.device_var,
            values=(self.device_var.get(),),
            state="readonly",
        )
        self.device_combo.grid(row=0, column=0, sticky="ew")
        self.device_combo.bind(
            "<<ComboboxSelected>>",
            lambda _event: self._device_selection_changed(),
        )
        self.refresh_devices_button = ttk.Button(
            compute_frame,
            text="Odśwież listę sprzętu",
            command=self._retry_device_detection,
        )
        self.refresh_devices_button.grid(row=0, column=1, padx=(10, 0))
        self.device_status_var = tk.StringVar(
            value="Trwa przygotowywanie automatycznego wykrywania CPU i GPU."
        )
        ttk.Label(
            compute_frame,
            textvariable=self.device_status_var,
            wraplength=820,
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(7, 0))
        amd_row = ttk.Frame(compute_frame)
        amd_row.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(9, 0))
        amd_row.columnconfigure(0, weight=1)
        self.amd_runtime_status_var = tk.StringVar(
            value="AMD Radeon: automatyczne wykrywanie i przygotowanie ROCm w tle."
        )
        self.amd_runtime_status_label = ttk.Label(
            amd_row,
            textvariable=self.amd_runtime_status_var,
            style="Muted.TLabel",
            wraplength=820,
        )
        self.amd_runtime_status_label.grid(row=0, column=0, columnspan=2, sticky="w")

        cpu_frame = ttk.LabelFrame(
            container,
            text="6. Wykorzystanie procesora",
            padding=12,
        )
        cpu_frame.pack(fill="x", pady=(12, 0))
        cpu_frame.columnconfigure(0, weight=1)
        self.cpu_usage_var = tk.StringVar(value=next(iter(CPU_USAGE_LABELS)))
        self.cpu_usage_combo = ttk.Combobox(
            cpu_frame,
            textvariable=self.cpu_usage_var,
            values=list(CPU_USAGE_LABELS),
            state="readonly",
        )
        self.cpu_usage_combo.grid(row=0, column=0, sticky="ew")
        self.cpu_usage_combo.bind(
            "<<ComboboxSelected>>",
            lambda _event: self._update_cpu_usage_description(),
        )
        self.cpu_usage_status_var = tk.StringVar()
        ttk.Label(
            cpu_frame,
            textvariable=self.cpu_usage_status_var,
            wraplength=820,
        ).grid(row=1, column=0, sticky="w", pady=(7, 0))
        self._update_cpu_usage_description()

        timing_frame = ttk.LabelFrame(
            container,
            text="7. Czas wyświetlania napisów",
            padding=12,
        )
        timing_frame.pack(fill="x", pady=(12, 0))
        for column in range(3):
            timing_frame.columnconfigure(column, weight=1, uniform="timing-profile")
        ttk.Label(
            timing_frame,
            text=(
                "Wybierz tempo czytania. Program zachowa początek każdej wypowiedzi "
                "i wykorzysta tylko wolne miejsce przed następną."
            ),
            wraplength=820,
        ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 10))

        self.timing_var = tk.StringVar(value=SubtitleTimingMode.RECOMMENDED.value)
        self.timing_profile_buttons: dict[SubtitleTimingMode, tk.Button] = {}
        primary_profiles = TIMING_PROFILE_CARDS[:3]
        for column, (mode, title, detail) in enumerate(primary_profiles):
            button = tk.Button(
                timing_frame,
                text=f"{title}\n{detail}",
                command=lambda selected=mode: self._select_timing_mode(selected),
                font=("Segoe UI", 10, "bold"),
                justify="center",
                cursor="hand2",
                borderwidth=0,
                relief="flat",
                padx=10,
                pady=11,
                highlightthickness=1,
            )
            button.grid(
                row=1,
                column=column,
                sticky="nsew",
                padx=(0 if column == 0 else 4, 0 if column == 2 else 4),
            )
            self.timing_profile_buttons[mode] = button

        secondary_profiles = ttk.Frame(timing_frame)
        secondary_profiles.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        secondary_profiles.columnconfigure(0, weight=1, uniform="timing-secondary")
        secondary_profiles.columnconfigure(1, weight=1, uniform="timing-secondary")
        for column, (mode, title, detail) in enumerate(TIMING_PROFILE_CARDS[3:]):
            button = tk.Button(
                secondary_profiles,
                text=f"{title}\n{detail}",
                command=lambda selected=mode: self._select_timing_mode(selected),
                font=("Segoe UI", 9, "bold"),
                justify="center",
                cursor="hand2",
                borderwidth=0,
                relief="flat",
                padx=10,
                pady=8,
                highlightthickness=1,
            )
            button.grid(
                row=0,
                column=column,
                sticky="nsew",
                padx=(0, 4) if column == 0 else (4, 0),
            )
            self.timing_profile_buttons[mode] = button

        self.timing_custom_frame = ttk.Frame(timing_frame, padding=(10, 8, 10, 2))
        self.timing_custom_frame.grid(
            row=3,
            column=0,
            columnspan=3,
            sticky="ew",
            pady=(8, 0),
        )
        self.timing_custom_frame.columnconfigure(1, weight=1)
        self.timing_custom_frame.columnconfigure(3, weight=1)
        ttk.Label(self.timing_custom_frame, text="Minimalny czas:").grid(
            row=0,
            column=0,
            sticky="w",
        )
        minimum_input = ttk.Frame(self.timing_custom_frame)
        minimum_input.grid(row=0, column=1, sticky="w", padx=(7, 20))
        self.minimum_duration_var = tk.StringVar(value="1.5")
        self.minimum_duration_spinbox = ttk.Spinbox(
            minimum_input,
            from_=0.5,
            to=5.0,
            increment=0.1,
            textvariable=self.minimum_duration_var,
            width=8,
            command=self._update_timing_description,
        )
        self.minimum_duration_spinbox.grid(row=0, column=0, sticky="w")
        ttk.Label(minimum_input, text="s").grid(row=0, column=1, sticky="w", padx=(5, 0))
        ttk.Label(self.timing_custom_frame, text="Tempo czytania:").grid(
            row=0,
            column=2,
            sticky="w",
        )
        speed_input = ttk.Frame(self.timing_custom_frame)
        speed_input.grid(row=0, column=3, sticky="w", padx=(7, 0))
        self.max_cps_var = tk.StringVar(value="17")
        self.max_cps_spinbox = ttk.Spinbox(
            speed_input,
            from_=8,
            to=30,
            increment=1,
            textvariable=self.max_cps_var,
            width=8,
            command=self._update_timing_description,
        )
        self.max_cps_spinbox.grid(row=0, column=0, sticky="w")
        ttk.Label(speed_input, text="znaków/s").grid(
            row=0, column=1, sticky="w", padx=(5, 0)
        )
        for widget in (self.minimum_duration_spinbox, self.max_cps_spinbox):
            widget.bind("<KeyRelease>", lambda _event: self._update_timing_description())
            widget.bind("<FocusOut>", lambda _event: self._update_timing_description())

        self.timing_status_var = tk.StringVar()
        self.timing_status_label = tk.Label(
            timing_frame,
            textvariable=self.timing_status_var,
            background="#eaf3ff",
            foreground="#174a7e",
            font=("Segoe UI", 9, "bold"),
            justify="left",
            anchor="w",
            padx=12,
            pady=10,
            highlightthickness=1,
            highlightbackground="#bdd7f2",
            wraplength=820,
        )
        self.timing_status_label.grid(
            row=4,
            column=0,
            columnspan=3,
            sticky="ew",
            pady=(10, 0),
        )
        self._update_timing_description()

        context_frame = ttk.LabelFrame(
            container, text="8. Postacie i kontekst (opcjonalnie)", padding=12
        )
        context_frame.pack(fill="both", expand=True, pady=12)
        ttk.Label(
            context_frame,
            text="Przykład: Anna — kobieta; Marek — mężczyzna; zachowaj nieformalny ton.",
        ).pack(anchor="w")
        self.context_text = scrolledtext.ScrolledText(
            context_frame, height=4, wrap="word", font=("Segoe UI", 10)
        )
        self.context_text.pack(fill="both", expand=True, pady=(6, 0))

        if modern:
            appearance_frame = self._build_appearance_panel(container)
            appearance_frame.pack(fill="x", pady=(0, 12))
            self._content_sections["settings"] = appearance_frame

        self._build_activity_panel()
        self._build_action_bar()
        self._refresh_model_choices()
        self._refresh_whisper_choices()
        self._update_api_state()
        self._refresh_primary_action()
        if modern:
            self.after_idle(lambda: self._set_modern_nav_selection("start"))

    def _build_modern_sidebar(self) -> None:
        sidebar = ttk.Frame(
            self,
            style="Sidebar.TFrame",
            width=224,
            padding=(18, 22, 18, 18),
        )
        sidebar.grid(row=0, column=0, rowspan=3, sticky="nsew")
        sidebar.grid_propagate(False)

        ttk.Label(sidebar, text="PS", style="Brand.TLabel").pack(anchor="w")
        ttk.Label(
            sidebar,
            text=PRODUCT_NAME,
            style="Brand.TLabel",
        ).pack(anchor="w", pady=(2, 0))
        ttk.Label(
            sidebar,
            text=f"Wersja {__version__} • {AUTHOR}",
            style="SidebarMuted.TLabel",
        ).pack(anchor="w", pady=(2, 24))

        navigation = (
            ("start", "⌂  Start"),
            ("translation", "✦  Tłumaczenie"),
            ("models", "◫  Modele AI"),
            ("film", "▶  Film i sprzęt"),
            ("settings", "⚙  Ustawienia"),
        )
        for key, label in navigation:
            button = ttk.Button(
                sidebar,
                text=label,
                style="Nav.TButton",
                command=lambda section=key: self._scroll_to_section(section),
            )
            button.pack(fill="x", pady=2)
            self._modern_nav_buttons[key] = button

        ttk.Frame(sidebar, style="Sidebar.TFrame").pack(fill="both", expand=True)
        ttk.Label(
            sidebar,
            text="SZYBKI MOTYW",
            style="SidebarMuted.TLabel",
            font=("Segoe UI", 8, "bold"),
        ).pack(anchor="w", pady=(0, 6))
        quick_theme = ttk.Combobox(
            sidebar,
            textvariable=self.appearance_theme_var,
            values=[theme.label for theme in THEMES],
            state="readonly",
            width=23,
        )
        quick_theme.pack(fill="x")
        quick_theme.bind(
            "<<ComboboxSelected>>",
            lambda _event: self._theme_selection_changed(),
        )

    def _build_appearance_panel(self, parent: tk.Misc) -> ttk.LabelFrame:
        frame = ttk.LabelFrame(parent, text="9. Wygląd aplikacji", padding=14)
        frame.columnconfigure(1, weight=1)
        ttk.Label(frame, text="Interfejs:").grid(row=0, column=0, sticky="w")
        self.appearance_interface_combo = ttk.Combobox(
            frame,
            textvariable=self.appearance_interface_var,
            values=list(INTERFACE_IDS_BY_LABEL),
            state="readonly",
        )
        self.appearance_interface_combo.grid(
            row=0,
            column=1,
            sticky="ew",
            padx=(10, 0),
        )
        ttk.Label(frame, text="Motyw:").grid(row=1, column=0, sticky="w", pady=(10, 0))
        self.appearance_theme_combo = ttk.Combobox(
            frame,
            textvariable=self.appearance_theme_var,
            values=[theme.label for theme in THEMES],
            state="readonly",
        )
        self.appearance_theme_combo.grid(
            row=1,
            column=1,
            sticky="ew",
            padx=(10, 0),
            pady=(10, 0),
        )
        self.appearance_theme_combo.bind(
            "<<ComboboxSelected>>",
            lambda _event: self._theme_selection_changed(),
        )
        ttk.Label(
            frame,
            textvariable=self.appearance_description_var,
            style="Muted.TLabel",
            wraplength=780,
        ).grid(row=2, column=0, columnspan=2, sticky="w", pady=(8, 0))
        actions = ttk.Frame(frame)
        actions.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        ttk.Button(
            actions,
            text="Zastosuj wybrany interfejs",
            command=self._apply_interface_selection,
            style="Primary.TButton",
        ).pack(side="left")
        ttk.Button(
            actions,
            text="Przywróć wygląd domyślny",
            command=self._reset_appearance,
        ).pack(side="left", padx=(8, 0))
        self._update_appearance_description()
        return frame

    def _scroll_to_section(self, section: str) -> None:
        target = self._content_sections.get(section)
        if target is None:
            return
        self.update_idletasks()
        canvas_bounds = self.content_canvas.bbox("all")
        if not canvas_bounds:
            return
        content_height = max(canvas_bounds[3] - canvas_bounds[1], 1)
        viewport = max(self.content_canvas.winfo_height(), 1)
        relative_y = max(
            target.winfo_rooty() - self.content_container.winfo_rooty() - 8,
            0,
        )
        maximum_y = max(content_height - viewport, 0)
        self.content_canvas.yview_moveto(min(relative_y, maximum_y) / content_height)
        self._set_modern_nav_selection(section)

    def _set_modern_nav_selection(self, section: str) -> None:
        for key, button in self._modern_nav_buttons.items():
            button.configure(
                style="SelectedNav.TButton" if key == section else "Nav.TButton"
            )

    def _selected_theme_id(self) -> str:
        return THEME_IDS_BY_LABEL.get(self.appearance_theme_var.get(), DEFAULT_THEME)

    def _selected_interface_id(self) -> str:
        return INTERFACE_IDS_BY_LABEL.get(
            self.appearance_interface_var.get(),
            DEFAULT_INTERFACE,
        )

    def _update_appearance_description(self) -> None:
        theme_id = self._selected_theme_id()
        theme = next((item for item in THEMES if item.id == theme_id), THEMES[0])
        interface = INTERFACE_LABELS[self._selected_interface_id()]
        self.appearance_description_var.set(
            f"{interface} • {theme.label}. {theme.description} Ustawienie zostanie zapamiętane."
        )

    def _theme_selection_changed(self) -> None:
        self._apply_appearance(
            self.appearance.interface,
            self._selected_theme_id(),
        )

    def _apply_interface_selection(self) -> None:
        self._apply_appearance(
            self._selected_interface_id(),
            self._selected_theme_id(),
        )

    def _reset_appearance(self) -> None:
        self.appearance_interface_var.set(INTERFACE_LABELS[MODERN_INTERFACE])
        default_label = next(theme.label for theme in THEMES if theme.id == DEFAULT_THEME)
        self.appearance_theme_var.set(default_label)
        self._apply_appearance(MODERN_INTERFACE, DEFAULT_THEME)

    def _apply_appearance(self, interface: str, theme_id: str) -> None:
        requested = AppearanceSettings(interface=interface, theme=theme_id).normalized()
        interface_changed = requested.interface != self.appearance.interface
        if interface_changed and self._activity_active:
            self.appearance_interface_var.set(INTERFACE_LABELS[self.appearance.interface])
            messagebox.showwarning(
                "Operacja jest w toku",
                "Interfejs możesz przełączyć po zakończeniu bieżącej operacji. Motyw nadal "
                "można zmienić od razu.",
                parent=self,
            )
            requested = AppearanceSettings(
                interface=self.appearance.interface,
                theme=requested.theme,
            )
            interface_changed = False

        self.appearance = requested
        self.theme = resolve_theme(requested.theme)
        self.appearance_interface_var.set(INTERFACE_LABELS[requested.interface])
        self.appearance_theme_var.set(
            next(theme.label for theme in THEMES if theme.id == requested.theme)
        )
        try:
            self._appearance_store.save(requested)
        except OSError:
            self.status_var.set("Nie udało się zapisać ustawień wyglądu.")

        if interface_changed:
            self._rebuild_interface()
        else:
            self._build_style()
            self._apply_theme_to_widgets()
            self._update_appearance_description()

    def _open_appearance_dialog(self) -> None:
        if self._appearance_dialog is not None:
            try:
                if self._appearance_dialog.winfo_exists():
                    self._appearance_dialog.lift()
                    self._appearance_dialog.focus_force()
                    return
            except tk.TclError:
                self._appearance_dialog = None

        dialog = tk.Toplevel(self)
        self._appearance_dialog = dialog
        dialog.title(f"Wygląd aplikacji — {PRODUCT_NAME}")
        dialog.geometry("560x330")
        dialog.minsize(500, 300)
        dialog.transient(self)
        dialog.columnconfigure(0, weight=1)
        container = ttk.Frame(dialog, padding=20)
        container.grid(row=0, column=0, sticky="nsew")
        container.columnconfigure(1, weight=1)
        ttk.Label(container, text="Interfejs i motyw", style="Title.TLabel").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 14)
        )
        interface_var = tk.StringVar(value=self.appearance_interface_var.get())
        theme_var = tk.StringVar(value=self.appearance_theme_var.get())
        description_var = tk.StringVar()

        ttk.Label(container, text="Interfejs:").grid(row=1, column=0, sticky="w")
        ttk.Combobox(
            container,
            textvariable=interface_var,
            values=list(INTERFACE_IDS_BY_LABEL),
            state="readonly",
        ).grid(row=1, column=1, sticky="ew", padx=(12, 0))
        ttk.Label(container, text="Motyw:").grid(row=2, column=0, sticky="w", pady=(12, 0))
        theme_combo = ttk.Combobox(
            container,
            textvariable=theme_var,
            values=[theme.label for theme in THEMES],
            state="readonly",
        )
        theme_combo.grid(row=2, column=1, sticky="ew", padx=(12, 0), pady=(12, 0))

        def update_description(_event=None) -> None:
            selected_id = THEME_IDS_BY_LABEL.get(theme_var.get(), DEFAULT_THEME)
            selected_theme = next(
                (theme for theme in THEMES if theme.id == selected_id),
                THEMES[0],
            )
            description_var.set(selected_theme.description)

        theme_combo.bind("<<ComboboxSelected>>", update_description)
        update_description()
        ttk.Label(
            container,
            textvariable=description_var,
            style="Muted.TLabel",
            wraplength=500,
        ).grid(row=3, column=0, columnspan=2, sticky="w", pady=(12, 20))

        actions = ttk.Frame(container)
        actions.grid(row=4, column=0, columnspan=2, sticky="e")

        def apply_selection() -> None:
            self._apply_appearance(
                INTERFACE_IDS_BY_LABEL.get(interface_var.get(), DEFAULT_INTERFACE),
                THEME_IDS_BY_LABEL.get(theme_var.get(), DEFAULT_THEME),
            )
            try:
                dialog.destroy()
            except tk.TclError:
                pass
            self._appearance_dialog = None

        ttk.Button(actions, text="Anuluj", command=dialog.destroy).pack(side="left")
        ttk.Button(
            actions,
            text="Zastosuj",
            command=apply_selection,
            style="Primary.TButton",
        ).pack(side="left", padx=(8, 0))
        dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)
        self._apply_theme_to_widgets(dialog)

    def _show_about(self) -> None:
        messagebox.showinfo(
            f"O programie — {PRODUCT_NAME}",
            f"{ABOUT_TEXT}\n\nWersja: {__version__}",
            parent=self,
        )

    def _capture_interface_state(self) -> dict[str, object]:
        variable_names = (
            "file_var",
            "file_details_var",
            "speech_model_var",
            "source_var",
            "target_var",
            "detected_var",
            "engine_var",
            "model_var",
            "api_key_var",
            "mode_var",
            "cpu_usage_var",
            "timing_var",
            "minimum_duration_var",
            "max_cps_var",
            "version_status_var",
            "stage_text",
            "elapsed_text",
            "progress_text",
            "status_var",
        )
        values = {
            name: getattr(self, name).get()
            for name in variable_names
            if hasattr(self, name)
        }
        context = self.context_text.get("1.0", "end-1c") if hasattr(self, "context_text") else ""
        log = self.activity_log.get("1.0", "end-1c") if hasattr(self, "activity_log") else ""
        return {"variables": values, "context": context, "log": log}

    def _rebuild_interface(self) -> None:
        state = self._capture_interface_state()
        if self._model_manager_window is not None:
            try:
                self._model_manager_window.destroy()
            except tk.TclError:
                pass
            self._model_manager_window = None
        for child in self.winfo_children():
            try:
                child.destroy()
            except tk.TclError:
                pass
        self._appearance_dialog = None
        self._build_style()
        self._build_ui()
        self._restore_interface_state(state)
        self._apply_theme_to_widgets()

    def _restore_interface_state(self, state: dict[str, object]) -> None:
        values = state.get("variables", {})
        if isinstance(values, dict):
            for name, value in values.items():
                variable = getattr(self, name, None)
                if isinstance(variable, tk.Variable):
                    variable.set(value)
        context = state.get("context")
        if isinstance(context, str) and context:
            self.context_text.insert("1.0", context)
        log = state.get("log")
        if isinstance(log, str) and log:
            self.activity_log.configure(state="normal")
            self.activity_log.insert("1.0", log)
            self.activity_log.configure(state="disabled")

        self._update_api_state()
        self._sync_mode_checkboxes()
        self._update_cpu_usage_description()
        self._update_timing_description()
        self._refresh_model_choices(MODEL_LABEL_TO_ID.get(str(values.get("model_var", ""))))
        self._refresh_whisper_choices(
            WHISPER_LABEL_TO_ID.get(str(values.get("speech_model_var", "")))
        )
        self._refresh_model_status()
        self._restore_device_widgets()
        self._update_attach_button()
        self._refresh_primary_action()
        if self._update_download_url:
            self.download_update_button.grid()
        self._update_appearance_description()

    def _restore_device_widgets(self) -> None:
        self._device_label_to_id = {AUTO_DEVICE_LABEL: AUTO_DEVICE_ID}
        self._device_label_to_id.update(
            {device.display_label: device.id for device in self._compute_devices}
        )
        self.device_combo.configure(values=list(self._device_label_to_id))
        selected = next(
            (
                label
                for label, device_id in self._device_label_to_id.items()
                if device_id == self._selected_device_id
            ),
            AUTO_DEVICE_LABEL,
        )
        self.device_var.set(selected)
        self._selected_device_id = self._device_label_to_id[selected]
        self._update_device_description()

    def _apply_theme_to_widgets(self, root: tk.Misc | None = None) -> None:
        palette = self.theme
        root = root or self
        try:
            if isinstance(root, (tk.Tk, tk.Toplevel)):
                root.configure(background=palette.window)
            elif isinstance(root, tk.Canvas):
                root.configure(background=palette.window)
            elif isinstance(root, tk.Text):
                root.configure(
                    background=palette.input,
                    foreground=palette.text,
                    insertbackground=palette.text,
                    selectbackground=palette.accent,
                    selectforeground=palette.accent_text,
                    highlightbackground=palette.border,
                    highlightcolor=palette.accent,
                    relief="flat",
                )
            elif isinstance(root, ttk.Treeview):
                root.tag_configure(
                    "flagged",
                    background=palette.warning,
                    foreground=palette.warning_text,
                )
            for child in root.winfo_children():
                self._apply_theme_to_widgets(child)
        except tk.TclError:
            return

        if root is self and hasattr(self, "timing_profile_buttons"):
            self._update_timing_description()

    def _installed_models(self) -> list[TranslationModelSpec]:
        return [model for model in MODEL_CATALOG if model_status(model).installed]

    def _installed_whisper_models(self) -> list[WhisperModelSpec]:
        return [model for model in WHISPER_MODEL_CATALOG if model_status(model).installed]

    def _refresh_whisper_choices(self, preferred_model_id: str | None = None) -> None:
        if not hasattr(self, "speech_model_combo"):
            return
        current_id = preferred_model_id or WHISPER_LABEL_TO_ID.get(self.speech_model_var.get())
        installed = self._installed_whisper_models()
        labels = [model.selection_label for model in installed]
        self.speech_model_combo.configure(values=labels or (WHISPER_NOT_READY_LABEL,))
        selected = next((model for model in installed if model.id == current_id), None)
        if selected is None and installed:
            selected = next(
                (model for model in installed if model.id == DEFAULT_WHISPER_MODEL_ID),
                installed[0],
            )
        self.speech_model_var.set(selected.selection_label if selected else WHISPER_NOT_READY_LABEL)

    def _selected_whisper_model(self) -> WhisperModelSpec | None:
        model_id = WHISPER_LABEL_TO_ID.get(self.speech_model_var.get())
        if model_id is None:
            return None
        model = get_whisper_model_spec(model_id)
        return model if model_status(model).installed else None

    def _refresh_model_choices(self, preferred_model_id: str | None = None) -> None:
        if not hasattr(self, "model_combo"):
            return
        current_id = preferred_model_id or MODEL_LABEL_TO_ID.get(self.model_var.get())
        installed = self._installed_models()
        labels = [model.selection_label for model in installed]
        self.model_combo.configure(values=labels or (MODEL_NOT_READY_LABEL,))
        selected = next((model for model in installed if model.id == current_id), None)
        if selected is None and installed:
            selected = next(
                (model for model in installed if model.id == DEFAULT_MODEL_ID),
                installed[0],
            )
        self.model_var.set(selected.selection_label if selected else MODEL_NOT_READY_LABEL)

    def _selected_model(self) -> TranslationModelSpec | None:
        model_id = MODEL_LABEL_TO_ID.get(self.model_var.get())
        if model_id is None:
            return None
        model = get_model_spec(model_id)
        return model if model_status(model).installed else None

    def _model_selection_changed(self) -> None:
        self._refresh_model_status()

    def _refresh_model_status(self) -> None:
        if not hasattr(self, "model_status_var"):
            return
        model = self._selected_model()
        if model is None:
            self.model_status_var.set(
                "Brak gotowego modelu lokalnego. Kliknij »Pobierz / usuń…«, "
                f"aby pobrać jeden z {len(MODEL_CATALOG)} modeli AI."
            )
            return
        status = model_status(model)
        source = parse_language_option(self.source_var.get())
        target = parse_language_option(self.target_var.get())
        if source and target:
            compatibility = (
                f"obsługuje {source} → {target}"
                if model.supports_pair(source, target)
                else f"nie obsługuje {source} → {target}"
            )
        else:
            compatibility = "zgodność zostanie sprawdzona po wybraniu języków"
        self.model_status_var.set(
            f"{status.status_label} · {model.quality} · {compatibility}."
        )

    def _open_model_manager(self, initial_tab: str = "translation") -> None:
        if self._model_manager_window is not None:
            try:
                if self._model_manager_window.winfo_exists():
                    self._model_manager_window.show_tab(initial_tab)
                    self._model_manager_window.lift()
                    self._model_manager_window.focus_force()
                    return
            except tk.TclError:
                self._model_manager_window = None
        self._model_manager_window = ModelManagerWindow(
            self,
            selected_model_id=(self._selected_model() or get_model_spec(DEFAULT_MODEL_ID)).id,
            selected_whisper_id=(
                self._selected_whisper_model() or get_whisper_model_spec(DEFAULT_WHISPER_MODEL_ID)
            ).id,
            initial_tab=initial_tab,
            source_language=parse_language_option(self.source_var.get()),
            target_language=parse_language_option(self.target_var.get()),
            on_use=self._select_model,
            on_use_whisper=self._select_whisper_model,
            on_close=self._model_manager_closed,
        )
        self._apply_theme_to_widgets(self._model_manager_window)

    def _select_model(self, model_id: str) -> None:
        self._refresh_model_choices(model_id)
        self._refresh_model_status()

    def _select_whisper_model(self, model_id: str) -> None:
        self._refresh_whisper_choices(model_id)

    def _model_manager_closed(self) -> None:
        self._model_manager_window = None
        self._refresh_model_choices()
        self._refresh_whisper_choices()
        self._refresh_model_status()

    def _select_translation_mode(self, mode: TranslationMode) -> None:
        selected_var = (
            self.automatic_mode_checked
            if mode is TranslationMode.AUTOMATIC
            else self.review_mode_checked
        )
        if selected_var.get():
            self.mode_var.set(mode.value)
            self.automatic_mode_checked.set(mode is TranslationMode.AUTOMATIC)
            self.review_mode_checked.set(mode is TranslationMode.REVIEW)
        else:
            self.mode_var.set("")
            self.automatic_mode_checked.set(False)
            self.review_mode_checked.set(False)

    def _sync_mode_checkboxes(self) -> None:
        self.automatic_mode_checked.set(
            self.mode_var.get() == TranslationMode.AUTOMATIC.value
        )
        self.review_mode_checked.set(self.mode_var.get() == TranslationMode.REVIEW.value)

    def _selected_translation_mode(self) -> TranslationMode | None:
        try:
            return TranslationMode(self.mode_var.get())
        except ValueError:
            return None

    def _start_device_detection(self) -> None:
        if self._device_detection_running:
            return
        self._device_detection_running = True
        self.refresh_devices_button.configure(state="disabled")
        self.device_status_var.set(
            "Wykrywanie prawdziwego procesora, kart graficznych i backendów…"
        )
        thread = threading.Thread(target=self._device_detection_worker, daemon=True)
        thread.start()

    def _retry_device_detection(self) -> None:
        if not self._amd_runtime_setup_running:
            self._amd_runtime_attempted = False
        self._start_device_detection()

    def _start_automatic_amd_runtime(self, gpu_names: tuple[str, ...]) -> None:
        if self._amd_runtime_setup_running or self._amd_runtime_attempted:
            return
        plan = select_amd_runtime_plan(gpu_names)
        self._amd_runtime_attempted = True
        if plan is None:
            self.amd_runtime_status_var.set(
                "Radeon wykryty, ale AMD nie publikuje dla niego zgodnego pakietu ROCm "
                f"{ROCM_VERSION} na Windows. Program użyje CPU."
            )
            return
        self._amd_runtime_setup_running = True
        self.amd_runtime_status_var.set(
            f"Radeon wykryty — automatyczne przygotowywanie ROCm {ROCM_VERSION} "
            f"dla {plan.target}. Możesz nadal używać programu; do zakończenia działa CPU."
        )
        self._append_activity(
            f"Automatyczna konfiguracja AMD ROCm {ROCM_VERSION} ({plan.target}) rozpoczęta."
        )
        thread = threading.Thread(
            target=self._amd_runtime_setup_worker,
            args=(gpu_names,),
            daemon=True,
        )
        thread.start()

    def _amd_runtime_setup_worker(self, gpu_names: tuple[str, ...]) -> None:
        try:
            runtime = install_amd_runtime(
                gpu_names,
                status=lambda message: self.after(0, self._amd_runtime_setup_status, message)
            )
        except Exception as exc:
            write_amd_runtime_diagnostic(f"BŁĄD AUTOMATU AMD: {exc}")
            self.after(0, self._amd_runtime_setup_failed, str(exc))
            return
        self.after(0, self._amd_runtime_setup_finished, runtime.message)

    def _amd_runtime_setup_status(self, message: str) -> None:
        self.amd_runtime_status_var.set(message)
        self.device_status_var.set(f"Konfiguracja AMD: {message}")
        self._append_activity(f"AMD: {message}")

    def _amd_runtime_setup_finished(self, message: str) -> None:
        self._amd_runtime_setup_running = False
        self.amd_runtime_status_var.set(message)
        self._append_activity(f"AMD ROCm gotowe — {message}")
        self._start_device_detection()

    def _amd_runtime_setup_failed(self, message: str) -> None:
        self._amd_runtime_setup_running = False
        log_path = amd_runtime_log_path()
        self.amd_runtime_status_var.set(
            f"AMD ROCm nie zostało uruchomione — program użyje CPU. {message} "
            f"Log: {log_path}"
        )
        self.device_status_var.set("Akceleracja AMD niedostępna — aktywny bezpieczny CPU.")
        self._append_activity(f"AMD ROCm: konfiguracja nieudana — {message}")
        messagebox.showwarning(
            "AMD Radeon pozostaje na CPU",
            f"Automatyczne uruchomienie ROCm nie powiodło się:\n\n{message}\n\n"
            f"Pełna diagnostyka została zapisana tutaj:\n{log_path}\n\n"
            "Po aktualizacji sterownika lub internetu kliknij „Odśwież listę sprzętu”.",
            parent=self,
        )

    def _device_detection_worker(self) -> None:
        try:
            devices = detect_compute_devices()
        except Exception as exc:
            self.after(0, self._device_detection_failed, str(exc))
            return
        self.after(0, self._device_detection_finished, devices)

    def _device_detection_finished(self, devices: list[ComputeDevice]) -> None:
        self._device_detection_running = False
        self.refresh_devices_button.configure(state="normal")
        self._compute_devices = devices
        self._device_label_to_id = {AUTO_DEVICE_LABEL: AUTO_DEVICE_ID}
        self._device_label_to_id.update(
            {device.display_label: device.id for device in devices}
        )
        labels = list(self._device_label_to_id)
        self.device_combo.configure(values=labels)
        selected = next(
            (
                label
                for label, device_id in self._device_label_to_id.items()
                if device_id == self._selected_device_id
            ),
            AUTO_DEVICE_LABEL,
        )
        self.device_var.set(selected)
        self._selected_device_id = self._device_label_to_id[selected]
        self._update_device_description()
        ready_amd = [
            device.name
            for device in devices
            if device.vendor == "AMD" and "ROCm" in device.backend
        ]
        if ready_amd:
            self._amd_runtime_attempted = True
            self.amd_runtime_status_var.set(
                f"AMD ROCm gotowe: {', '.join(ready_amd)}."
            )
        else:
            amd_names = tuple(
                device.name
                for device in devices
                if device.kind == "gpu" and device.vendor == "AMD"
            )
            if amd_names and not self._amd_runtime_setup_running:
                self.amd_runtime_status_var.set(
                    "Radeon wykryty — PolySub automatycznie sprawdza właściwy pakiet ROCm. "
                    "Do zakończenia przygotowania dostępny jest CPU."
                )
                if os.name == "nt":
                    self.after(50, self._start_automatic_amd_runtime, amd_names)

    def _device_detection_failed(self, _message: str) -> None:
        self._device_detection_running = False
        self.refresh_devices_button.configure(state="normal")
        self._compute_devices = []
        self._device_label_to_id = {AUTO_DEVICE_LABEL: AUTO_DEVICE_ID}
        self.device_combo.configure(values=(AUTO_DEVICE_LABEL,))
        self.device_var.set(AUTO_DEVICE_LABEL)
        self._selected_device_id = AUTO_DEVICE_ID
        self.device_status_var.set(
            "Nie udało się odczytać listy sprzętu — program bezpiecznie użyje CPU."
        )

    def _device_selection_changed(self) -> None:
        self._selected_device_id = self._device_label_to_id.get(
            self.device_var.get(),
            AUTO_DEVICE_ID,
        )
        self._update_device_description()

    def _update_device_description(self) -> None:
        prefix = (
            "DeepL tłumaczy na swoim serwerze. Dla filmu: "
            if ENGINE_LABELS.get(self.engine_var.get()) == "deepl"
            else ""
        )
        if self._selected_device_id == AUTO_DEVICE_ID:
            translation = resolve_compute_device(
                self._compute_devices,
                AUTO_DEVICE_ID,
                "translation",
            )
            transcription = resolve_compute_device(
                self._compute_devices,
                AUTO_DEVICE_ID,
                "transcription",
            )
            self.device_status_var.set(
                f"{prefix}Auto wybierze do tłumaczenia: {translation.display_name}; "
                f"do rozpoznawania mowy: {transcription.display_name}."
            )
            return
        selected = next(
            (
                device
                for device in self._compute_devices
                if device.id == self._selected_device_id
            ),
            None,
        )
        if selected is None:
            self.device_status_var.set(
                f"{prefix}Wybrane urządzenie zniknęło — zostanie użyty tryb Auto."
            )
            return
        self.device_status_var.set(f"{prefix}{describe_device_support(selected)}")

    def _resolve_selected_device(self, task: TaskKind) -> DeviceResolution:
        return resolve_compute_device(
            self._compute_devices,
            self._selected_device_id,
            task,
        )

    def _preferred_burn_vendor(self) -> str | None:
        if self._selected_device_id == AUTO_DEVICE_ID:
            return None
        selected = next(
            (
                device
                for device in self._compute_devices
                if device.id == self._selected_device_id
            ),
            None,
        )
        if selected is None:
            return None
        return "CPU" if selected.kind == "cpu" else selected.vendor

    def _selected_cpu_usage_limit(self) -> int:
        return CPU_USAGE_LABELS.get(self.cpu_usage_var.get(), DEFAULT_CPU_USAGE)

    def _update_cpu_usage_description(self) -> None:
        allocation = cpu_allocation(self._selected_cpu_usage_limit())
        self.cpu_usage_status_var.set(
            f"Model może użyć {allocation.threads} z "
            f"{allocation.logical_processors} logicznych wątków. "
            "Nie zmienia to jakości tłumaczenia."
        )

    def _selected_timing_mode(self) -> SubtitleTimingMode:
        try:
            return SubtitleTimingMode(self.timing_var.get())
        except ValueError:
            self.timing_var.set(SubtitleTimingMode.RECOMMENDED.value)
            return SubtitleTimingMode.RECOMMENDED

    def _select_timing_mode(self, mode: SubtitleTimingMode) -> None:
        if self._timing_controls_locked:
            return
        self.timing_var.set(mode.value)
        self._update_timing_description()

    def _update_timing_card_styles(self, selected_mode: SubtitleTimingMode) -> None:
        palette = self.theme
        for mode, button in self.timing_profile_buttons.items():
            selected = mode is selected_mode
            button.configure(
                background=palette.selected if selected else palette.panel,
                foreground=palette.accent_hover if selected else palette.text,
                activebackground=palette.selected if selected else palette.elevated,
                activeforeground=palette.accent_hover,
                highlightbackground=palette.accent if selected else palette.border,
                highlightcolor=palette.accent if selected else palette.border,
                highlightthickness=2 if selected else 1,
                disabledforeground=palette.muted,
                relief="flat",
            )

    def _update_timing_description(self) -> None:
        mode = self._selected_timing_mode()
        self._update_timing_card_styles(mode)
        is_custom = mode is SubtitleTimingMode.CUSTOM
        if is_custom:
            self.timing_custom_frame.grid()
        else:
            self.timing_custom_frame.grid_remove()
        custom_state = "normal" if is_custom and not self._timing_controls_locked else "disabled"
        self.minimum_duration_spinbox.configure(state=custom_state)
        self.max_cps_spinbox.configure(state=custom_state)
        if mode is SubtitleTimingMode.ORIGINAL:
            self.timing_status_var.set(
                "↺ ORYGINALNE • wszystkie czasy źródłowe pozostaną dokładnie 1:1.\n"
                "Ochrona przed zbyt krótkimi lub nachodzącymi napisami będzie wyłączona."
            )
            self.timing_status_label.configure(
                background=self.theme.warning,
                foreground=self.theme.warning_text,
                highlightbackground=self.theme.warning_text,
            )
            return
        if mode is SubtitleTimingMode.DYNAMIC:
            settings = SubtitleTimingSettings.dynamic()
            heading = "⚡ KRÓTSZE • dynamiczne sceny"
        elif mode is SubtitleTimingMode.COMFORTABLE:
            settings = SubtitleTimingSettings.comfortable()
            heading = "◷ DŁUŻSZE • wygodne czytanie"
        elif mode is SubtitleTimingMode.CUSTOM:
            try:
                settings = self._selected_timing_settings()
            except SubtitleTimingError:
                self.timing_status_var.set(
                    "⚙ WŁASNE • wpisz minimum 0,5–5 s oraz tempo 8–30 znaków/s.\n"
                    "Początek każdej nowej wypowiedzi nadal pozostanie chroniony."
                )
                self.timing_status_label.configure(
                    background=self.theme.panel,
                    foreground=self.theme.danger,
                    highlightbackground=self.theme.danger,
                )
                return
            heading = "⚙ WŁASNE • Twoje tempo czytania"
        else:
            settings = SubtitleTimingSettings.recommended()
            heading = "★ ZALECANE • najlepszy balans"
        minimum = f"{settings.minimum_duration_ms / 1_000:g}".replace(".", ",")
        safety_gap = f"{settings.safety_gap_ms / 1_000:g}".replace(".", ",")
        self.timing_status_var.set(
            f"{heading} • minimum {minimum} s • maks. "
            f"{settings.max_chars_per_second:g} znaków/s • odstęp {safety_gap} s, "
            "gdy jest miejsce.\n"
            "✓ Start dialogu pozostaje bez zmian, a stary napis nie wejdzie na nową wypowiedź."
        )
        self.timing_status_label.configure(
            background=self.theme.selected,
            foreground=self.theme.text,
            highlightbackground=self.theme.accent,
        )

    def _selected_timing_settings(self) -> SubtitleTimingSettings:
        mode = self._selected_timing_mode()
        if mode is not SubtitleTimingMode.CUSTOM:
            return SubtitleTimingSettings.for_mode(mode)
        try:
            minimum = float(self.minimum_duration_var.get().strip().replace(",", "."))
            max_cps = float(self.max_cps_var.get().strip().replace(",", "."))
        except ValueError as exc:
            raise SubtitleTimingError(
                "Własny czas i liczba znaków na sekundę muszą być liczbami."
            ) from exc
        return SubtitleTimingSettings.custom(
            minimum_duration_seconds=minimum,
            max_chars_per_second=max_cps,
        )

    def _start_update_check(self) -> None:
        if self._update_check_running:
            return
        self._update_check_running = True
        self.check_update_button.configure(state="disabled")
        self.version_status_var.set(f"Wersja {__version__} • sprawdzanie aktualizacji…")
        thread = threading.Thread(target=self._update_check_worker, daemon=True)
        thread.start()

    def _update_check_worker(self) -> None:
        try:
            update_info = check_for_updates(__version__)
        except UpdateCheckError as exc:
            self.after(0, self._update_check_failed, str(exc))
            return
        self.after(0, self._update_check_finished, update_info)

    def _update_check_finished(self, update_info: UpdateInfo) -> None:
        self._update_check_running = False
        self.check_update_button.configure(state="normal")
        if update_info.update_available:
            self._update_download_url = update_info.installer_url
            self.version_status_var.set(
                f"Aktualizacja dostępna: {update_info.latest_version} "
                f"• zainstalowana {update_info.current_version}"
            )
            self.download_update_button.configure(
                text=f"Pobierz wersję {update_info.latest_version}"
            )
            self.download_update_button.grid()
            return

        self._update_download_url = None
        self.download_update_button.grid_remove()
        self.version_status_var.set(f"Wersja {__version__} jest aktualna")

    def _update_check_failed(self, _message: str) -> None:
        self._update_check_running = False
        self.check_update_button.configure(state="normal")
        self._update_download_url = None
        self.download_update_button.grid_remove()
        self.version_status_var.set(
            f"Wersja {__version__} • nie udało się sprawdzić aktualizacji"
        )

    def _open_update_download(self) -> None:
        if self._update_download_url is None:
            return
        try:
            opened = webbrowser.open(self._update_download_url)
        except webbrowser.Error:
            opened = False
        if not opened:
            messagebox.showwarning(
                "Nie udało się otworzyć pobierania",
                "Otwórz stronę najnowszej wersji w przeglądarce:\n\n"
                "https://github.com/FgSousace/PolySub-Translator/releases/latest",
                parent=self,
            )

    def _build_action_bar(self) -> None:
        action_frame = ttk.Frame(self, padding=(24, 10, 24, 16))
        action_frame.grid(row=2, column=self._content_column, sticky="ew")
        action_frame.columnconfigure(0, weight=1)
        action_frame.columnconfigure(1, weight=1)
        action_frame.columnconfigure(2, weight=1)
        self.attach_button = ttk.Button(
            action_frame,
            text="Dodaj przełączaną ścieżkę — szybko",
            command=self._attach_subtitles,
            state="disabled",
        )
        self.attach_button.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.burn_button = ttk.Button(
            action_frame,
            text="Wypal napisy na obrazie — TV",
            command=self._burn_subtitles,
            state="disabled",
        )
        self.burn_button.grid(row=0, column=1, sticky="ew", padx=(6, 0))
        self.narrator_button = ttk.Button(
            action_frame,
            text="Utwórz film z polskim lektorem",
            command=self._create_narrator,
            state="disabled",
        )
        self.narrator_button.grid(row=0, column=2, sticky="ew", padx=(12, 0))
        self.start_button = ttk.Button(
            action_frame,
            text="Wyszukaj napisy w filmie lub wybierz plik",
            command=self._primary_action,
            style="Primary.TButton",
        )
        self.start_button.grid(
            row=1,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=(0, 6),
            pady=(8, 0),
        )
        self.cancel_translation_button = ttk.Button(
            action_frame,
            text="Anuluj tłumaczenie",
            command=self._cancel_translation,
            state="disabled",
            style="Danger.TButton",
        )
        self.cancel_translation_button.grid(
            row=1,
            column=2,
            sticky="ew",
            padx=(6, 0),
            pady=(8, 0),
        )
        ttk.Label(
            action_frame,
            text=f"{PRODUCT_NAME} • {COPYRIGHT} • wyłącznie użytek niekomercyjny",
            style="Muted.TLabel",
            anchor="center",
        ).grid(row=2, column=0, columnspan=3, sticky="ew", pady=(8, 0))

    def _build_activity_panel(self) -> None:
        activity = ttk.LabelFrame(self, text="Postęp operacji", padding=(18, 10))
        activity.grid(
            row=1,
            column=self._content_column,
            sticky="ew",
            padx=18,
            pady=(8, 0),
        )
        activity.columnconfigure(0, weight=1)

        stage_header = ttk.Frame(activity)
        stage_header.grid(row=0, column=0, sticky="ew")
        stage_header.columnconfigure(0, weight=1)
        self.stage_text = tk.StringVar(value="Etapy: oczekiwanie na zadanie")
        ttk.Label(stage_header, textvariable=self.stage_text, style="Heading.TLabel").grid(
            row=0,
            column=0,
            sticky="w",
        )
        self.elapsed_text = tk.StringVar(value="Czas: 00:00:00")
        ttk.Label(stage_header, textvariable=self.elapsed_text).grid(
            row=0,
            column=1,
            sticky="e",
        )

        self.stage_progress_var = tk.IntVar(value=0)
        self.stage_progress_bar = ttk.Progressbar(
            activity,
            variable=self.stage_progress_var,
            maximum=1,
            mode="determinate",
        )
        self.stage_progress_bar.grid(row=1, column=0, sticky="ew", pady=(5, 8))

        self.progress_text = tk.StringVar(value="Bieżący etap: oczekiwanie")
        ttk.Label(activity, textvariable=self.progress_text).grid(row=2, column=0, sticky="w")
        self.progress_var = tk.IntVar(value=0)
        self.progress_bar = ttk.Progressbar(
            activity,
            variable=self.progress_var,
            maximum=1,
            mode="determinate",
        )
        self.progress_bar.grid(row=3, column=0, sticky="ew", pady=(5, 6))

        self.status_var = tk.StringVar(value="Gotowy")
        ttk.Label(activity, textvariable=self.status_var).grid(row=4, column=0, sticky="w")

        self.activity_log = scrolledtext.ScrolledText(
            activity,
            height=4,
            wrap="word",
            font=("Consolas", 9),
            state="disabled",
        )
        self.activity_log.grid(row=5, column=0, sticky="ew", pady=(7, 0))

    def _sync_scroll_region(self, _event=None) -> None:
        self.content_canvas.configure(scrollregion=self.content_canvas.bbox("all"))

    def _resize_scroll_content(self, event) -> None:
        self.content_canvas.itemconfigure(self.content_window, width=event.width)

    def _scroll_main_content(self, event) -> None:
        widget = self.winfo_containing(self.winfo_pointerx(), self.winfo_pointery())
        if widget is None or widget.winfo_toplevel() is not self:
            return
        if isinstance(widget, tk.Text):
            return
        current = widget
        while current is not self and current is not self.content_canvas:
            current = current.master
        if current is not self.content_canvas:
            return
        delta = -1 if event.delta > 0 else 1
        self.content_canvas.yview_scroll(delta * 3, "units")

    def _begin_activity(self, stages: list[str], message: str) -> None:
        if self._heartbeat_job is not None:
            self.after_cancel(self._heartbeat_job)
        self._activity_stages = stages
        self._activity_active = True
        self._activity_started_at = time.monotonic()
        self._last_log_message = None
        self.activity_log.configure(state="normal")
        self.activity_log.delete("1.0", "end")
        self.activity_log.configure(state="disabled")
        self.stage_progress_bar.configure(maximum=max(len(stages), 1))
        self.stage_progress_var.set(0)
        self.elapsed_text.set("Czas: 00:00:00")
        self._show_stage(1, message)
        self._tick_elapsed()

    def _show_stage(
        self,
        index: int,
        message: str | None = None,
        *,
        determinate: bool = False,
    ) -> None:
        total = max(len(self._activity_stages), 1)
        index = min(max(index, 1), total)
        title = (
            self._activity_stages[index - 1]
            if self._activity_stages
            else "Przetwarzanie"
        )
        self.stage_progress_var.set(index)
        self.stage_text.set(f"Etap {index} z {total} — {title}")
        detail = message or title
        self.status_var.set(detail)
        if determinate:
            self._prepare_determinate_progress(detail)
        else:
            self._start_indeterminate_progress(detail)
        self._append_activity(detail)

    def _start_indeterminate_progress(self, message: str) -> None:
        self.progress_bar.stop()
        self.progress_bar.configure(mode="indeterminate", maximum=1)
        self.progress_var.set(0)
        self.progress_text.set(message)
        self.progress_bar.start(12)

    def _prepare_determinate_progress(self, message: str) -> None:
        self.progress_bar.stop()
        self.progress_bar.configure(mode="determinate", maximum=1)
        self.progress_var.set(0)
        self.progress_text.set(message)

    def _append_activity(self, message: str) -> None:
        clean = " ".join(message.strip().split())
        if not clean or clean == self._last_log_message:
            return
        self._last_log_message = clean
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.activity_log.configure(state="normal")
        self.activity_log.insert("end", f"[{timestamp}] {clean}\n")
        self.activity_log.see("end")
        self.activity_log.configure(state="disabled")

    def _tick_elapsed(self) -> None:
        if not self._activity_active:
            self._heartbeat_job = None
            return
        elapsed = time.monotonic() - self._activity_started_at
        self.elapsed_text.set(f"Czas: {format_elapsed(elapsed)} • program działa")
        self._heartbeat_job = self.after(1000, self._tick_elapsed)

    def _finish_activity(self, message: str) -> None:
        elapsed = time.monotonic() - self._activity_started_at
        self._activity_active = False
        if self._heartbeat_job is not None:
            self.after_cancel(self._heartbeat_job)
            self._heartbeat_job = None
        total = max(len(self._activity_stages), 1)
        self.stage_progress_var.set(total)
        self.stage_text.set(f"Zakończono wszystkie etapy: {total} z {total}")
        self.elapsed_text.set(f"Łączny czas: {format_elapsed(elapsed)}")
        self.progress_bar.stop()
        self.progress_bar.configure(mode="determinate")
        maximum = max(int(float(self.progress_bar.cget("maximum"))), 1)
        self.progress_var.set(maximum)
        self.progress_text.set(message)
        self.status_var.set(message)
        self._append_activity(f"Gotowe — {message}")

    def _fail_activity(self, message: str) -> None:
        elapsed = time.monotonic() - self._activity_started_at
        self._activity_active = False
        if self._heartbeat_job is not None:
            self.after_cancel(self._heartbeat_job)
            self._heartbeat_job = None
        self.progress_bar.stop()
        self.stage_text.set(f"Operacja przerwana — {self.stage_text.get()}")
        self.elapsed_text.set(f"Czas do błędu: {format_elapsed(elapsed)}")
        self.status_var.set(message)
        self._append_activity(f"BŁĄD — {message}")

    def _cancel_activity(self, message: str) -> None:
        elapsed = time.monotonic() - self._activity_started_at
        self._activity_active = False
        if self._heartbeat_job is not None:
            self.after_cancel(self._heartbeat_job)
            self._heartbeat_job = None
        self.progress_bar.stop()
        self.stage_text.set("Tłumaczenie anulowane — postęp zapisano")
        self.elapsed_text.set(f"Czas do anulowania: {format_elapsed(elapsed)}")
        self.progress_text.set(message)
        self.status_var.set(message)
        self._append_activity(f"ANULOWANO — {message}")

    def _primary_action(self) -> None:
        if self.document is None or self.source_path is None:
            self._choose_file()
            return
        self._start_translation()

    def _refresh_primary_action(self) -> None:
        if not hasattr(self, "start_button"):
            return
        if self._translation_running:
            self.start_button.configure(text="Tłumaczenie w toku…", state="disabled")
        elif self.document is None or self.source_path is None:
            self.start_button.configure(
                text="Wyszukaj napisy w filmie lub wybierz plik",
                state="normal",
            )
        else:
            self.start_button.configure(text="Rozpocznij tłumaczenie", state="normal")

    def _choose_file(self) -> None:
        selected = filedialog.askopenfilename(
            title="Wybierz napisy lub film",
            filetypes=INPUT_FILE_TYPES,
        )
        if not selected:
            return
        selected_path = Path(selected)
        self.document = None
        self.source_path = None
        self.media_path = None
        self.translated_subtitle_path = None
        self.translated_target_language = None
        self.attach_button.configure(state="disabled")
        self.burn_button.configure(state="disabled")
        self.narrator_button.configure(state="disabled")
        self.file_var.set(str(selected_path))
        self.file_details_var.set(
            f"Wybrano: {selected_path.name} • format "
            f"{selected_path.suffix.lower() or 'bez rozszerzenia'} • trwa sprawdzanie pliku…"
        )
        self._refresh_primary_action()

        if not selected_path.is_file():
            self.file_details_var.set("Wybranego pliku nie ma już na dysku.")
            messagebox.showerror(
                "Nie znaleziono pliku",
                f"Plik nie istnieje:\n{selected_path}",
                parent=self,
            )
            return

        if selected_path.suffix.lower() not in SUPPORTED_INPUT_EXTENSIONS:
            supported = ", ".join(sorted(SUPPORTED_INPUT_EXTENSIONS))
            self.file_details_var.set(
                f"Nieobsługiwany format {selected_path.suffix or '(brak)'}."
            )
            messagebox.showwarning(
                "Nieobsługiwany typ pliku",
                "Możesz wyświetlić i wybrać dowolny plik, ale tłumaczenie obsługuje "
                f"obecnie: {supported}.\n\nWybrano: {selected_path.name}",
                parent=self,
            )
            return

        if selected_path.suffix.lower() in VIDEO_EXTENSIONS:
            self._start_video_import(selected_path)
            return

        self._start_subtitle_import(selected_path)

    def _start_subtitle_import(self, subtitle_path: Path) -> None:
        self.file_button.configure(state="disabled")
        self.start_button.configure(state="disabled")
        self.attach_button.configure(state="disabled")
        self.burn_button.configure(state="disabled")
        self.narrator_button.configure(state="disabled")
        self._begin_activity(
            ["Wczytywanie pliku", "Wykrywanie języka", "Przygotowanie dokumentu"],
            f"Otwieranie pliku {subtitle_path.name}",
        )
        thread = threading.Thread(
            target=self._subtitle_import_worker,
            args=(subtitle_path,),
            daemon=True,
        )
        thread.start()

    def _subtitle_import_worker(self, subtitle_path: Path) -> None:
        try:
            document = SRTDocument.load(subtitle_path)
            self.after(
                0,
                self._show_stage,
                2,
                "Analizowanie tekstu i wykrywanie języka...",
            )
            detected = detect_language(document.combined_text)
        except Exception as exc:
            self.after(0, self._subtitle_import_failed, str(exc))
            return
        self.after(0, self._subtitle_import_finished, document, subtitle_path, detected)

    def _subtitle_import_finished(
        self,
        document: SRTDocument,
        subtitle_path: Path,
        detected,
    ) -> None:
        self._show_stage(
            3,
            f"Przygotowano {len(document.cues):,} kwestii i {document.total_words:,} słów".replace(
                ",", " "
            ),
            determinate=True,
        )
        self._document_ready(document, subtitle_path, detected)
        size_kib = subtitle_path.stat().st_size / 1024
        self.file_details_var.set(
            f"Napisy SRT gotowe • {len(document.cues):,} kwestii • "
            f"{document.total_words:,} słów • {size_kib:.1f} KiB".replace(",", " ")
        )
        self.file_button.configure(state="normal")
        self._finish_activity(f"Napisy gotowe do tłumaczenia: {subtitle_path.name}")

    def _subtitle_import_failed(self, message: str) -> None:
        self.file_button.configure(state="normal")
        self.file_details_var.set("Plik nie został wczytany. Sprawdź jego format i kodowanie.")
        self._refresh_primary_action()
        self._update_attach_button()
        self._fail_activity("Nie udało się wczytać napisów")
        messagebox.showerror("Nie można wczytać pliku", message, parent=self)

    def _start_video_import(self, video_path: Path) -> None:
        self.file_button.configure(state="disabled")
        self.start_button.configure(state="disabled")
        self.attach_button.configure(state="disabled")
        self.burn_button.configure(state="disabled")
        self.narrator_button.configure(state="disabled")
        self._begin_activity(
            [
                "Analiza filmu",
                "Przygotowanie napisów",
                "Wykrywanie języka",
                "Przygotowanie dokumentu",
            ],
            f"Sprawdzanie filmu {video_path.name}",
        )
        whisper_model = self._selected_whisper_model()
        whisper_status = model_status(whisper_model) if whisper_model else None
        model_source = whisper_status.snapshot_path if whisper_status else None
        model_name = whisper_model.display_name if whisper_model else "niepobrany"
        device_resolution = self._resolve_selected_device("transcription")
        cpu_usage_limit = self._selected_cpu_usage_limit()
        thread = threading.Thread(
            target=self._video_import_worker,
            args=(video_path, model_source, model_name, device_resolution, cpu_usage_limit),
            daemon=True,
        )
        thread.start()

    def _video_import_worker(
        self,
        video_path: Path,
        model_source: Path | None,
        model_name: str,
        device_resolution: DeviceResolution,
        cpu_usage_limit: int,
    ) -> None:
        try:
            if device_resolution.fallback_reason:
                self.after(0, self._video_status, device_resolution.fallback_reason)
            importer = VideoSubtitleImporter(
                model_size=model_source,
                model_name=model_name,
                device=device_resolution.runtime_device,
                device_index=device_resolution.device_index,
                cpu_usage_limit=cpu_usage_limit,
            )
            result = importer.import_video(
                video_path,
                status=lambda message: self.after(0, self._video_status, message),
                progress=lambda done, total: self.after(
                    0, self._set_media_progress, done, total
                ),
            )
            self.after(
                0,
                self._show_stage,
                3,
                "Wykrywanie języka przygotowanych napisów...",
            )
            detected = detect_language(result.document.combined_text)
            self.after(0, self._video_import_finished, video_path, result, detected)
        except Exception as exc:
            self.after(0, self._video_import_failed, str(exc))

    def _video_status(self, message: str) -> None:
        if "wbudowanej" in message.lower():
            self._show_stage(1, message)
            return
        self._show_stage(2, message)

    def _video_import_finished(
        self,
        video_path: Path,
        result: VideoImportResult,
        detected,
    ) -> None:
        self.media_path = video_path
        method = (
            "Wyciągnięto wbudowane napisy"
            if result.method == "embedded"
            else "Utworzono napisy z rozpoznanej mowy"
        )
        self._document_ready(
            result.document,
            result.subtitle_path,
            detected,
            file_label=f"{video_path.name}  →  {result.subtitle_path.name}",
            status=f"{method}: {result.subtitle_path.name}",
        )
        source_description = (
            "wbudowana ścieżka napisów"
            if result.method == "embedded"
            else "napisy utworzone przez rozpoznawanie mowy"
        )
        self.file_details_var.set(
            f"Film {video_path.suffix.upper().lstrip('.')} • {source_description} • "
            f"{len(result.document.cues):,} kwestii • "
            f"{result.document.total_words:,} słów".replace(",", " ")
        )
        self._show_stage(
            4,
            f"{method}. Przygotowano {len(result.document.cues):,} kwestii.".replace(",", " "),
            determinate=True,
        )
        self.file_button.configure(state="normal")
        self._finish_activity(f"Napisy z filmu gotowe: {result.subtitle_path.name}")

    def _video_import_failed(self, message: str) -> None:
        self.file_button.configure(state="normal")
        self.file_details_var.set("Nie udało się przygotować napisów z wybranego filmu.")
        self._refresh_primary_action()
        self._fail_activity("Nie udało się przygotować filmu")
        messagebox.showerror("Import filmu nie powiódł się", message, parent=self)

    def _document_ready(
        self,
        document: SRTDocument,
        source_path: Path,
        detected,
        *,
        file_label: str | None = None,
        status: str = "Napisy gotowe do tłumaczenia",
    ) -> None:
        self.document = document
        self.source_path = source_path
        self.file_var.set(file_label or str(source_path))
        self.source_var.set(f"{detected.name} ({detected.code})")
        self.detected_var.set(
            f"Wykryto: {detected.name} • pewność {detected.confidence:.0%} • "
            f"{document.total_words:,} słów".replace(",", " ")
        )
        self._set_progress(0, document.total_words)
        self.status_var.set(status)
        self._refresh_primary_action()
        self._refresh_model_status()

    def _update_api_state(self) -> None:
        is_deepl = ENGINE_LABELS[self.engine_var.get()] == "deepl"
        self.api_entry.configure(state="normal" if is_deepl else "disabled")
        self.model_combo.configure(state="disabled" if is_deepl else "readonly")
        self._refresh_model_status()
        if hasattr(self, "device_status_var"):
            self._update_device_description()

    def _lock_translation_settings(self, locked: bool) -> None:
        self._timing_controls_locked = locked
        if locked:
            self.engine_combo.configure(state="disabled")
            self.model_combo.configure(state="disabled")
            self.model_manager_button.configure(state="disabled")
            self.api_entry.configure(state="disabled")
            self.device_combo.configure(state="disabled")
            self.refresh_devices_button.configure(state="disabled")
            self.cpu_usage_combo.configure(state="disabled")
            self.automatic_mode_checkbox.configure(state="disabled")
            self.review_mode_checkbox.configure(state="disabled")
            for button in self.timing_profile_buttons.values():
                button.configure(state="disabled", cursor="arrow")
            self._update_timing_description()
            return
        self.engine_combo.configure(state="readonly")
        self.model_manager_button.configure(state="normal")
        self.device_combo.configure(state="readonly")
        self.refresh_devices_button.configure(
            state="disabled" if self._device_detection_running else "normal"
        )
        self.cpu_usage_combo.configure(state="readonly")
        self.automatic_mode_checkbox.configure(state="normal")
        self.review_mode_checkbox.configure(state="normal")
        for button in self.timing_profile_buttons.values():
            button.configure(state="normal", cursor="hand2")
        self._update_timing_description()
        self._update_api_state()

    def _start_translation(self) -> None:
        if self.document is None or self.source_path is None:
            messagebox.showwarning(
                "Brak pliku", "Najpierw wybierz plik SRT albo film.", parent=self
            )
            return
        mode = self._selected_translation_mode()
        if mode is None:
            messagebox.showwarning(
                "Wybierz tryb tłumaczenia",
                "Zaznacz jeden checkbox: »Tłumacz automatycznie« albo "
                "»Tłumacz z weryfikacją«.",
                parent=self,
            )
            return
        source = parse_language_option(self.source_var.get())
        target = parse_language_option(self.target_var.get())
        if not source or not target:
            messagebox.showwarning("Brak języka", "Wybierz język źródłowy i docelowy.", parent=self)
            return
        if source == target:
            messagebox.showwarning(
                "Te same języki", "Język źródłowy i docelowy muszą być różne.", parent=self
            )
            return
        engine_kind = ENGINE_LABELS[self.engine_var.get()]
        if engine_kind == "deepl" and not self.api_key_var.get().strip():
            messagebox.showwarning("Brak klucza", "Wpisz klucz DeepL API.", parent=self)
            return
        try:
            subtitle_timing = self._selected_timing_settings()
        except SubtitleTimingError as exc:
            messagebox.showwarning("Nieprawidłowy czas napisów", str(exc), parent=self)
            return

        local_model: TranslationModelSpec | None = None
        local_model_source: Path | None = None
        if engine_kind == "local":
            local_model = self._selected_model()
            if local_model is None:
                messagebox.showwarning(
                    "Brak pobranego modelu AI",
                    "Główna lista pokazuje tylko modele pobrane i gotowe. "
                    "Otwórz Menedżer modeli AI, pobierz model, a potem wybierz go z listy.",
                    parent=self,
                )
                self._open_model_manager()
                return
            if not local_model.supports_pair(source, target):
                messagebox.showwarning(
                    "Model nie obsługuje tej pary",
                    f"{local_model.display_name} nie obsługuje tłumaczenia "
                    f"{source} → {target}.\n\nWybierz inny model z listy albo otwórz "
                    "Menedżer modeli AI.",
                    parent=self,
                )
                return
            local_status = model_status(local_model)
            local_model_source = local_status.snapshot_path
            if not local_status.installed or local_model_source is None:
                self._refresh_model_choices()
                messagebox.showwarning(
                    "Model nie jest gotowy",
                    "Wybrany model nie ma kompletnego pliku na dysku. "
                    "Dokończ pobieranie w Menedżerze modeli AI.",
                    parent=self,
                )
                return

        device_resolution = self._resolve_selected_device("translation")
        if (
            engine_kind == "local"
            and self._selected_device_id != AUTO_DEVICE_ID
            and device_resolution.fallback_reason
            and not messagebox.askyesno(
                "Wybrane GPU nie ma zgodnego backendu",
                f"{device_resolution.fallback_reason}\n\nKontynuować tłumaczenie na CPU?",
                parent=self,
            )
        ):
            return

        self._translation_running = True
        self._translation_cancel_token = CancellationToken()
        self._active_translation_engine = None
        self._refresh_primary_action()
        self.cancel_translation_button.configure(state="normal")
        self.file_button.configure(state="disabled")
        self._lock_translation_settings(True)
        self.attach_button.configure(state="disabled")
        self.burn_button.configure(state="disabled")
        self.narrator_button.configure(state="disabled")
        self.translated_subtitle_path = None
        self.translated_target_language = None
        api_key = self.api_key_var.get()
        context_notes = self.context_text.get("1.0", "end").strip()
        cpu_usage_limit = self._selected_cpu_usage_limit()
        final_processing_stage = (
            "Przygotowanie weryfikacji"
            if mode is TranslationMode.REVIEW
            else "Zapisywanie wyniku"
        )
        self._begin_activity(
            [
                "Przygotowanie silnika",
                "Sprawdzanie wznowienia",
                "Tłumaczenie napisów",
                "Kontrola jakości",
                final_processing_stage,
                "Gotowe",
            ],
            (
                f"Przygotowywanie tłumaczenia na {device_resolution.display_name}..."
                if engine_kind == "local"
                else "Łączenie z serwerem DeepL..."
            ),
        )
        thread = threading.Thread(
            target=self._translation_worker,
            args=(
                source,
                target,
                engine_kind,
                api_key,
                mode,
                context_notes,
                subtitle_timing,
                local_model,
                local_model_source,
                device_resolution,
                cpu_usage_limit,
                self._translation_cancel_token,
            ),
            daemon=True,
        )
        thread.start()

    def _translation_worker(
        self,
        source: str,
        target: str,
        engine_kind: str,
        api_key: str,
        mode: TranslationMode,
        context_notes: str,
        subtitle_timing: SubtitleTimingSettings,
        local_model: TranslationModelSpec | None,
        local_model_source: Path | None,
        device_resolution: DeviceResolution,
        cpu_usage_limit: int,
        cancellation: CancellationToken,
    ) -> None:
        try:
            cancellation.raise_if_cancelled()
            if engine_kind == "local" and device_resolution.fallback_reason:
                self.after(0, self._engine_status, device_resolution.fallback_reason)
            if engine_kind == "deepl":
                engine = DeepLEngine(api_key)
            else:
                if local_model is None:
                    raise RuntimeError("Nie wybrano lokalnego modelu AI.")
                if local_model_source is None:
                    raise RuntimeError(
                        "Model nie jest pobrany. Otwórz Menedżer modeli AI i dokończ pobieranie."
                    )
                if device_resolution.runtime_device.startswith(AMD_RUNTIME_TARGET_PREFIX):
                    device_index = int(
                        device_resolution.runtime_device.removeprefix(
                            AMD_RUNTIME_TARGET_PREFIX
                        )
                    )
                    engine = RocmWorkerEngine(
                        local_model,
                        model_source=local_model_source,
                        device_index=device_index,
                        status=lambda message: self.after(
                            0, self._engine_status, message
                        ),
                        cpu_usage_limit=cpu_usage_limit,
                    )
                else:
                    engine = create_local_engine(
                        local_model,
                        model_source=local_model_source,
                        device=device_resolution.runtime_device,
                        status=lambda message: self.after(
                            0, self._engine_status, message
                        ),
                        cpu_usage_limit=cpu_usage_limit,
                    )
            self._active_translation_engine = engine
            cancellation.raise_if_cancelled()
            self.after(
                0,
                self._show_stage,
                2,
                f"Silnik {engine.display_name} gotowy. Sprawdzanie punktu wznowienia...",
            )
            options = TranslationOptions(
                source_language=source,
                target_language=target,
                mode=mode,
                context_notes=context_notes,
                subtitle_timing=subtitle_timing,
            )
            service = TranslationService(engine)
            output = self._translation_output_path(target)
            result = service.translate(
                self.document,
                options,
                progress=lambda done, total: self.after(0, self._set_progress, done, total),
                status=lambda message: self.after(
                    0,
                    self._translation_service_status,
                    message,
                ),
                output_path=output if mode is TranslationMode.AUTOMATIC else None,
                cancellation=cancellation,
            )
            self.after(0, self._translation_finished, result, output, mode, target)
        except TranslationCancelled:
            self.after(0, self._translation_cancelled)
        except Exception as exc:
            if cancellation.is_cancelled:
                self.after(0, self._translation_cancelled)
            else:
                self.after(0, self._translation_failed, str(exc))
        finally:
            if "engine" in locals() and isinstance(engine, RocmWorkerEngine):
                engine.close()
            self._active_translation_engine = None

    def _cancel_translation(self) -> None:
        token = self._translation_cancel_token
        if not self._translation_running or token is None:
            return
        token.cancel()
        engine = self._active_translation_engine
        if engine is not None:
            try:
                engine.cancel()
            except Exception:
                pass
        self.cancel_translation_button.configure(state="disabled")
        message = (
            "Anulowanie… bieżąca partia może najpierw dokończyć obliczenia. "
            "Ukończone partie zostaną zachowane."
        )
        self.status_var.set(message)
        self.progress_text.set(message)
        self._append_activity("Zażądano anulowania tłumaczenia.")

    def _reset_translation_state(self) -> None:
        self._translation_running = False
        self._translation_cancel_token = None
        self._active_translation_engine = None
        self.cancel_translation_button.configure(state="disabled")
        self.file_button.configure(state="normal")
        self._lock_translation_settings(False)
        self._refresh_primary_action()

    def _translation_cancelled(self) -> None:
        self._reset_translation_state()
        self._refresh_model_choices()
        self._refresh_model_status()
        self._update_attach_button()
        self._cancel_activity(
            "Tłumaczenie anulowano. Zapisano ukończone partie — następna próba "
            "wznowi pracę od tego miejsca."
        )

    def _engine_status(self, message: str) -> None:
        self._show_stage(1, message)

    def _translation_service_status(self, message: str) -> None:
        lowered = message.lower()
        if "wznowienia" in lowered or "wcześniejsz" in lowered:
            self._show_stage(2, message)
        elif lowered.startswith("tłumaczenie "):
            self._show_stage(3, message, determinate=True)
        elif any(
            marker in lowered
            for marker in (
                "kontrola",
                "analizowanie jakości",
                "czasu wyświetlania",
                "dopasowano czas",
                "timestampów",
            )
        ):
            self._show_stage(4, message)
        else:
            self._show_stage(5, message)

    def _translation_finished(
        self,
        result,
        output: Path,
        mode: TranslationMode,
        target_language: str,
    ) -> None:
        self._reset_translation_state()
        self._refresh_model_choices(
            MODEL_LABEL_TO_ID.get(self.model_var.get())
        )
        if mode is TranslationMode.REVIEW:
            finished_message = (
                f"Tłumaczenie gotowe — {len(result.review_items)} kwestii oznaczono."
            )
            self._show_stage(6, finished_message, determinate=True)
            self._finish_activity(finished_message)
            review_window = ReviewWindow(
                self,
                self.document,
                result.document,
                result.review_items,
                result.timing_stats,
                result.timing_settings,
                output,
                result.checkpoint_path,
                on_saved=lambda saved_path: self._translated_subtitle_ready(
                    saved_path, target_language
                ),
            )
            self._apply_theme_to_widgets(review_window)
            return
        self._translated_subtitle_ready(output, target_language)
        finished_message = f"Gotowe: {output.name}"
        self._show_stage(6, finished_message, determinate=True)
        self._finish_activity(finished_message)
        suffix = (
            "\n\nMożesz teraz szybko dodać przełączaną ścieżkę albo wypalić "
            "napisy na obrazie, aby zawsze były widoczne na telewizorze."
            if self.media_path is not None
            else ""
        )
        messagebox.showinfo(
            "Tłumaczenie gotowe",
            f"Zapisano plik:\n{output}\n\n{result.timing_stats.summary}{suffix}",
            parent=self,
        )

    def _translation_failed(self, message: str) -> None:
        self._reset_translation_state()
        self._refresh_model_choices()
        self._refresh_model_status()
        self._update_attach_button()
        self._fail_activity("Tłumaczenie przerwane z powodu błędu")
        messagebox.showerror("Tłumaczenie nie powiodło się", message, parent=self)

    def _translated_subtitle_ready(self, subtitle_path: Path, target_language: str) -> None:
        self.translated_subtitle_path = subtitle_path
        self.translated_target_language = target_language
        self._update_attach_button()

    def _update_attach_button(self) -> None:
        ready = (
            self.media_path is not None
            and self.translated_subtitle_path is not None
            and self.translated_subtitle_path.is_file()
            and self.translated_target_language is not None
        )
        self.attach_button.configure(state="normal" if ready else "disabled")
        self.burn_button.configure(state="normal" if ready else "disabled")
        narrator_ready = ready and self.translated_target_language == "pl"
        self.narrator_button.configure(state="normal" if narrator_ready else "disabled")

    def _create_narrator(self) -> None:
        if (
            self.media_path is None
            or self.translated_subtitle_path is None
            or self.translated_target_language != "pl"
        ):
            messagebox.showwarning(
                "Brak polskich napisów",
                "Najpierw przetłumacz napisy filmu na język polski.",
                parent=self,
            )
            return
        chatterbox_status = model_status(CHATTERBOX_MULTILINGUAL_V3)
        if chatterbox_status.snapshot_path is None:
            if messagebox.askyesno(
                "Chatterbox nie jest pobrany",
                "Do lektora potrzebny jest Chatterbox Multilingual V3 (około 3,25 GB). "
                "Otworzyć zakładkę Lektor w menedżerze modeli?",
                parent=self,
            ):
                self._open_model_manager("narrator")
            return

        default_output = narrator_video_output_path(self.media_path)
        selected = filedialog.asksaveasfilename(
            parent=self,
            title="Zapisz film z polskim lektorem",
            initialdir=str(default_output.parent),
            initialfile=default_output.name,
            defaultextension=".mkv",
            filetypes=[("Film Matroska", "*.mkv")],
        )
        if not selected:
            return
        if not messagebox.askyesno(
            "Utworzyć polskiego lektora?",
            "Chatterbox przeczyta wszystkie polskie kwestie jednym głosem, a oryginalny "
            "dźwięk zostanie ściszony do 28%. Obraz nie będzie ponownie kodowany.\n\n"
            "Przy pierwszym użyciu Windows przygotuje dodatkowe, odizolowane środowisko "
            "Chatterbox. Synteza działa bezpiecznie na CPU i może potrwać dłużej niż film.",
            parent=self,
        ):
            return

        self.file_button.configure(state="disabled")
        self.start_button.configure(state="disabled")
        self.attach_button.configure(state="disabled")
        self.burn_button.configure(state="disabled")
        self.narrator_button.configure(state="disabled")
        self._begin_activity(
            [
                "Przygotowanie Chatterbox",
                "Wczytanie głosu",
                "Synteza kwestii",
                "Synchronizacja lektora",
                "Miksowanie dźwięku",
                "Gotowe",
            ],
            "Sprawdzanie modelu i prywatnego środowiska lektora…",
        )
        thread = threading.Thread(
            target=self._narrator_worker,
            args=(
                Path(selected),
                chatterbox_status.snapshot_path,
                self._selected_cpu_usage_limit(),
            ),
            daemon=True,
        )
        thread.start()

    def _narrator_worker(
        self,
        output_path: Path,
        model_path: Path,
        cpu_usage_limit: int,
    ) -> None:
        try:
            if self.media_path is None or self.translated_subtitle_path is None:
                raise RuntimeError("Brakuje filmu albo polskich napisów.")
            result = ChatterboxNarrator().render(
                self.media_path,
                self.translated_subtitle_path,
                model_path,
                output_path=output_path,
                original_volume=0.28,
                cpu_usage_limit=cpu_usage_limit,
                status=lambda message: self.after(0, self._narrator_status, message),
                progress=lambda done, total: self.after(
                    0, self._set_narrator_progress, done, total
                ),
            )
            self.after(0, self._narrator_finished, result)
        except Exception as exc:
            self.after(0, self._narrator_failed, str(exc))

    def _narrator_status(self, message: str) -> None:
        lowered = message.lower()
        if "wczytywanie" in lowered:
            stage = 2
        elif "kwestia" in lowered:
            stage = 3
        elif "układanie" in lowered:
            stage = 4
        elif "miksowanie" in lowered:
            stage = 5
        else:
            stage = 1
        self._show_stage(stage, message)

    def _set_narrator_progress(self, processed: int, total: int) -> None:
        self.progress_bar.stop()
        self.progress_bar.configure(mode="determinate", maximum=max(total, 1))
        self.progress_var.set(processed)
        percent = min(max(processed / max(total, 1) * 100, 0.0), 100.0)
        self.progress_text.set(
            f"Postęp lektora: {percent:.1f}% • przygotowano {processed} z {total} kwestii"
        )

    def _narrator_finished(self, result: NarrationResult) -> None:
        self._finish_attach_operation()
        finished_message = f"Film z polskim lektorem gotowy: {result.output_path.name}"
        self._show_stage(6, finished_message, determinate=True)
        self._finish_activity(finished_message)
        messagebox.showinfo(
            "Film z lektorem gotowy",
            "Utworzono jeden polski głos Chatterbox i zmiksowano go ze ściszonym "
            f"oryginałem ({result.original_volume:.0%}).\n\n{result.output_path}",
            parent=self,
        )

    def _narrator_failed(self, message: str) -> None:
        self._finish_attach_operation()
        self._fail_activity("Nie udało się utworzyć polskiego lektora")
        messagebox.showerror("Tworzenie lektora nie powiodło się", message, parent=self)

    def _attach_subtitles(self) -> None:
        if (
            self.media_path is None
            or self.translated_subtitle_path is None
            or self.translated_target_language is None
        ):
            messagebox.showwarning(
                "Brak gotowych napisów",
                "Najpierw przetłumacz napisy filmu i zapisz wynik.",
                parent=self,
            )
            return

        default_output = fast_mux_output_path(
            self.media_path,
            self.translated_target_language,
        )
        preferred_type = (
            [("Film MP4", "*.mp4"), ("Film Matroska", "*.mkv")]
            if default_output.suffix == ".mp4"
            else [("Film Matroska", "*.mkv"), ("Film MP4", "*.mp4")]
        )
        selected = filedialog.asksaveasfilename(
            parent=self,
            title="Zapisz film z dołączonymi napisami",
            initialdir=str(default_output.parent),
            initialfile=default_output.name,
            defaultextension=default_output.suffix,
            filetypes=preferred_type,
        )
        if not selected:
            return

        self.file_button.configure(state="disabled")
        self.start_button.configure(state="disabled")
        self.attach_button.configure(state="disabled")
        self.burn_button.configure(state="disabled")
        self.narrator_button.configure(state="disabled")
        self._begin_activity(
            [
                "Sprawdzanie plików",
                "Przygotowanie FFmpeg",
                "Dołączanie napisów",
                "Gotowe",
            ],
            "Sprawdzanie filmu i przygotowanych napisów...",
        )
        thread = threading.Thread(
            target=self._attach_subtitles_worker,
            args=(Path(selected),),
            daemon=True,
        )
        thread.start()

    def _attach_subtitles_worker(self, output_path: Path) -> None:
        try:
            target_language = self.translated_target_language
            if (
                self.media_path is None
                or self.translated_subtitle_path is None
                or target_language is None
            ):
                raise RuntimeError("Brakuje filmu albo gotowych napisów.")
            output = VideoSubtitleMuxer().mux(
                self.media_path,
                self.translated_subtitle_path,
                target_language=target_language,
                output_path=output_path,
                subtitle_title=language_name(target_language),
                status=lambda message: self.after(0, self._mux_status, message),
            )
            self.after(0, self._attach_subtitles_finished, output)
        except Exception as exc:
            self.after(0, self._attach_subtitles_failed, str(exc))

    def _mux_status(self, message: str) -> None:
        lowered = message.lower()
        if "sprawdzanie" in lowered:
            self._show_stage(1, message)
        elif "przygotowywanie" in lowered:
            self._show_stage(2, message)
        else:
            self._show_stage(3, message)

    def _attach_subtitles_finished(self, output_path: Path) -> None:
        self._finish_attach_operation()
        finished_message = f"Film z napisami gotowy: {output_path.name}"
        self._show_stage(4, finished_message, determinate=True)
        self._finish_activity(finished_message)
        messagebox.showinfo(
            "Film gotowy",
            "Dołączono przełączaną ścieżkę napisów bez ponownego kodowania obrazu "
            f"i dźwięku:\n\n{output_path}",
            parent=self,
        )

    def _attach_subtitles_failed(self, message: str) -> None:
        self._finish_attach_operation()
        self._fail_activity("Nie udało się dołączyć napisów")
        messagebox.showerror("Dołączanie napisów nie powiodło się", message, parent=self)

    def _burn_subtitles(self) -> None:
        if (
            self.media_path is None
            or self.translated_subtitle_path is None
            or self.translated_target_language is None
        ):
            messagebox.showwarning(
                "Brak gotowych napisów",
                "Najpierw przetłumacz napisy filmu i zapisz wynik.",
                parent=self,
            )
            return

        default_output = burned_video_output_path(
            self.media_path,
            self.translated_target_language,
        )
        selected = filedialog.asksaveasfilename(
            parent=self,
            title="Zapisz film z napisami wypalonymi na obrazie",
            initialdir=str(default_output.parent),
            initialfile=default_output.name,
            defaultextension=".mp4",
            filetypes=[("Film MP4", "*.mp4"), ("Film Matroska", "*.mkv")],
        )
        if not selected:
            return

        self.file_button.configure(state="disabled")
        self.start_button.configure(state="disabled")
        self.attach_button.configure(state="disabled")
        self.burn_button.configure(state="disabled")
        self.narrator_button.configure(state="disabled")
        self._begin_activity(
            [
                "Sprawdzanie plików",
                "Wykrywanie akceleracji",
                "Wypalanie napisów",
                "Finalizowanie filmu",
                "Gotowe",
            ],
            "Sprawdzanie filmu i przygotowanych napisów...",
        )
        thread = threading.Thread(
            target=self._burn_subtitles_worker,
            args=(Path(selected), self._selected_cpu_usage_limit(), self._preferred_burn_vendor()),
            daemon=True,
        )
        thread.start()

    def _burn_subtitles_worker(
        self,
        output_path: Path,
        cpu_usage_limit: int,
        preferred_vendor: str | None,
    ) -> None:
        try:
            target_language = self.translated_target_language
            if (
                self.media_path is None
                or self.translated_subtitle_path is None
                or target_language is None
            ):
                raise RuntimeError("Brakuje filmu albo gotowych napisów.")
            result = VideoSubtitleBurner(cpu_usage_limit=cpu_usage_limit).burn(
                self.media_path,
                self.translated_subtitle_path,
                target_language=target_language,
                output_path=output_path,
                preferred_vendor=preferred_vendor,
                status=lambda message: self.after(0, self._burn_status, message),
                progress=lambda done, total: self.after(
                    0,
                    self._set_burn_progress,
                    done,
                    total,
                ),
            )
            self.after(0, self._burn_subtitles_finished, result)
        except Exception as exc:
            self.after(0, self._burn_subtitles_failed, str(exc))

    def _burn_status(self, message: str) -> None:
        lowered = message.lower()
        if "sprawdzanie" in lowered:
            self._show_stage(1, message)
        elif "przygotowywanie" in lowered or "wykrywanie" in lowered:
            self._show_stage(2, message)
        elif "finalizowanie" in lowered:
            self._show_stage(4, message)
        else:
            self._show_stage(3, message)

    def _burn_subtitles_finished(self, result: VideoBurnResult) -> None:
        self._finish_attach_operation()
        acceleration = "akceleracja sprzętowa" if result.hardware_accelerated else "CPU"
        finished_message = f"Film z trwałymi napisami gotowy: {result.output_path.name}"
        self._show_stage(5, finished_message, determinate=True)
        self._finish_activity(finished_message)
        messagebox.showinfo(
            "Film z trwałymi napisami gotowy",
            "Napisy zostały wypalone bezpośrednio na obrazie i będą zawsze widoczne.\n\n"
            f"Koder: {result.encoder} ({acceleration})\n\n{result.output_path}",
            parent=self,
        )

    def _burn_subtitles_failed(self, message: str) -> None:
        self._finish_attach_operation()
        self._fail_activity("Nie udało się wypalić napisów na obrazie")
        messagebox.showerror("Wypalanie napisów nie powiodło się", message, parent=self)

    def _finish_attach_operation(self) -> None:
        self.file_button.configure(state="normal")
        self.start_button.configure(state="normal")
        self._update_attach_button()

    def _set_progress(self, processed: int, total: int) -> None:
        self.progress_bar.stop()
        self.progress_bar.configure(mode="determinate")
        self.progress_bar.configure(maximum=max(total, 1))
        self.progress_var.set(processed)
        percent = min(max(processed / max(total, 1) * 100, 0.0), 100.0)
        self.progress_text.set(
            (
                f"Postęp etapu: {percent:.1f}% • przetłumaczono "
                f"{processed:,} z {total:,} słów"
            ).replace(",", " ")
        )

    def _set_media_progress(self, processed: float, total: float) -> None:
        self.progress_bar.stop()
        self.progress_bar.configure(mode="determinate")
        self.progress_bar.configure(maximum=max(total, 1.0))
        self.progress_var.set(int(processed))
        percent = min(max(processed / max(total, 1.0) * 100, 0.0), 100.0)
        self.progress_text.set(
            f"Postęp etapu: {percent:.1f}% • rozpoznano "
            f"{format_media_duration(processed)} z {format_media_duration(total)} nagrania"
        )

    def _set_burn_progress(self, processed: float, total: float) -> None:
        self.progress_bar.stop()
        self.progress_bar.configure(mode="determinate")
        self.progress_bar.configure(maximum=max(total, 1.0))
        self.progress_var.set(int(processed))
        percent = min(max(processed / max(total, 1.0) * 100, 0.0), 100.0)
        self.progress_text.set(
            f"Postęp etapu: {percent:.1f}% • przetworzono "
            f"{format_media_duration(processed)} z {format_media_duration(total)} filmu"
        )

    def _translation_output_path(self, target_language: str) -> Path:
        if self.media_path is not None:
            return translated_video_subtitle_path(self.media_path, target_language)
        return default_output_path(self.source_path, target_language)


class ReviewWindow(tk.Toplevel):
    def __init__(
        self,
        parent,
        original,
        translated,
        review_items,
        timing_stats,
        timing_settings,
        output_path: Path,
        checkpoint_path: Path | None,
        on_saved: Callable[[Path], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self.title(f"Weryfikacja tłumaczenia — {PRODUCT_NAME}")
        self.geometry("1180x720")
        self.minsize(900, 600)
        self.original = original
        self.translated = translated
        self.timing_stats = timing_stats
        self.timing_settings = timing_settings
        self.output_path = output_path
        self.checkpoint_path = checkpoint_path
        self.on_saved = on_saved
        self.issues = {item.cue_position: item for item in review_items}
        self.current_position: int | None = None
        self._build_ui()
        self._populate()

    def _build_ui(self) -> None:
        container = ttk.Frame(self, padding=16)
        container.pack(fill="both", expand=True)
        ttk.Label(
            container,
            text="Oryginał i tłumaczenie",
            style="Heading.TLabel",
        ).pack(anchor="w")
        ttk.Label(
            container,
            text="Oznaczone kwestie wymagają szczególnej uwagi, ale możesz poprawić każdą linię.",
        ).pack(anchor="w", pady=(0, 10))

        columns = ("id", "time", "source", "translation", "status")
        self.tree = ttk.Treeview(container, columns=columns, show="headings", height=12)
        headings = {
            "id": "Nr",
            "time": "Czas",
            "source": "Oryginał",
            "translation": "Tłumaczenie",
            "status": "Kontrola",
        }
        widths = {"id": 55, "time": 190, "source": 310, "translation": 310, "status": 110}
        for column in columns:
            self.tree.heading(column, text=headings[column])
            self.tree.column(column, width=widths[column], anchor="w")
        self.tree.tag_configure("flagged", background="#fff2cc")
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", self._select_row)

        editors = ttk.Frame(container)
        editors.pack(fill="both", expand=True, pady=10)
        editors.columnconfigure(0, weight=1)
        editors.columnconfigure(1, weight=1)
        ttk.Label(editors, text="Oryginał").grid(row=0, column=0, sticky="w")
        ttk.Label(editors, text="Tłumaczenie — możesz edytować").grid(
            row=0, column=1, sticky="w", padx=(8, 0)
        )
        self.source_editor = scrolledtext.ScrolledText(editors, height=7, wrap="word")
        self.source_editor.grid(row=1, column=0, sticky="nsew", padx=(0, 4))
        self.source_editor.configure(state="disabled")
        self.target_editor = scrolledtext.ScrolledText(editors, height=7, wrap="word")
        self.target_editor.grid(row=1, column=1, sticky="nsew", padx=(4, 0))
        self.reason_var = tk.StringVar(value="Wybierz kwestię z tabeli.")
        ttk.Label(container, textvariable=self.reason_var).pack(anchor="w")

        actions = ttk.Frame(container)
        actions.pack(fill="x", pady=(10, 0))
        ttk.Button(actions, text="Zapisz poprawkę", command=self._apply_edit).pack(side="left")
        ttk.Button(actions, text="Zapisz jako...", command=self._save_as).pack(side="right")
        ttk.Button(actions, text="Zapisz gotowe napisy", command=self._save).pack(
            side="right", padx=(0, 8)
        )

    def _populate(self) -> None:
        for position, (source, target) in enumerate(
            zip(self.original.cues, self.translated.cues, strict=True)
        ):
            status = "Sprawdź" if position in self.issues else "OK"
            tags = ("flagged",) if position in self.issues else ()
            self.tree.insert(
                "",
                "end",
                iid=str(position),
                values=(
                    source.identifier,
                    target.timing,
                    source.visible_text.replace("\n", " / "),
                    target.visible_text.replace("\n", " / "),
                    status,
                ),
                tags=tags,
            )

    def _select_row(self, _event=None) -> None:
        selected = self.tree.selection()
        if not selected:
            return
        self.current_position = int(selected[0])
        source = self.original.cues[self.current_position]
        target = self.translated.cues[self.current_position]
        self.source_editor.configure(state="normal")
        self.source_editor.delete("1.0", "end")
        self.source_editor.insert("1.0", source.text)
        self.source_editor.configure(state="disabled")
        self.target_editor.delete("1.0", "end")
        self.target_editor.insert("1.0", target.text)
        issue = self.issues.get(self.current_position)
        self.reason_var.set(
            "Powód: " + "; ".join(reason.value for reason in issue.reasons)
            if issue
            else "Brak automatycznie wykrytych problemów."
        )

    def _apply_edit(self) -> None:
        if self.current_position is None:
            return
        text = self.target_editor.get("1.0", "end").strip()
        if not text:
            messagebox.showwarning("Pusta kwestia", "Tłumaczenie nie może być puste.", parent=self)
            return
        self.translated.cues[self.current_position].text = text
        source = self.original.cues[self.current_position]
        target = self.translated.cues[self.current_position]
        values = list(self.tree.item(str(self.current_position), "values"))
        values[3] = target.visible_text.replace("\n", " / ")
        values[4] = "Poprawiono"
        self.tree.item(str(self.current_position), values=values, tags=())
        self.reason_var.set(f"Zapisano poprawkę dla kwestii {source.identifier}.")

    def _save(self) -> None:
        self._apply_edit()
        timing_result = optimize_subtitle_timing(
            self.translated,
            self.timing_settings,
            timing_source=self.original,
        )
        self.translated = timing_result.document
        self.timing_stats = timing_result.stats
        self.translated.save(self.output_path)
        if self.checkpoint_path:
            self.checkpoint_path.unlink(missing_ok=True)
        if self.on_saved:
            self.on_saved(self.output_path)
        messagebox.showinfo(
            "Zapisano",
            f"Gotowy plik:\n{self.output_path}\n\n{self.timing_stats.summary}",
            parent=self,
        )

    def _save_as(self) -> None:
        selected = filedialog.asksaveasfilename(
            parent=self,
            title="Zapisz przetłumaczone napisy",
            initialfile=self.output_path.name,
            defaultextension=".srt",
            filetypes=[("Napisy SubRip", "*.srt")],
        )
        if selected:
            self.output_path = Path(selected)
            self._save()


def main() -> None:
    enable_windows_dpi_awareness()
    app = PolySubApp()
    app.mainloop()


if __name__ == "__main__":
    main()
