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
from .engines import DeepLEngine, M2M100Engine
from .languages import language_name, language_options, parse_language_option
from .models import TranslationMode
from .performance import DEFAULT_CPU_USAGE, cpu_allocation
from .service import TranslationOptions, TranslationService
from .subtitles import SRTDocument, default_output_path
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

ENGINE_LABELS = {
    "Lokalny AI (M2M100)": "local",
    "DeepL API": "deepl",
}

SPEECH_MODEL_LABELS = {
    "Szybsze — Whisper small": "small",
    "Dokładniejsze — Whisper medium": "medium",
}

CPU_USAGE_LABELS = {
    "100% — maksymalna wydajność": 100,
    "75% — wysokie obciążenie": 75,
    "50% — połowa procesora": 50,
    "25% — lekkie obciążenie": 25,
}


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


def recommended_window_size(screen_width: int, screen_height: int) -> tuple[int, int]:
    """Fit the main window to the usable screen without hiding its bottom actions."""
    available_width = max(screen_width - 40, min(screen_width, 360))
    available_height = max(screen_height - 80, min(screen_height, 420))
    return min(1000, available_width), min(900, available_height)


def format_elapsed(seconds: float) -> str:
    elapsed = max(int(seconds), 0)
    hours, remainder = divmod(elapsed, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


class PolySubApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("PolySub Translator")
        width, height = recommended_window_size(
            self.winfo_screenwidth(),
            self.winfo_screenheight(),
        )
        left = max((self.winfo_screenwidth() - width) // 2, 0)
        top = max((self.winfo_screenheight() - height) // 2, 0)
        self.geometry(f"{width}x{height}+{left}+{top}")
        self.minsize(min(700, width), min(560, height))
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
        self._build_style()
        self._build_ui()
        self.after(200, self._start_device_detection)
        self.after(1200, self._start_update_check)

    def _build_style(self) -> None:
        style = ttk.Style(self)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure("Title.TLabel", font=("Segoe UI", 22, "bold"))
        style.configure("Heading.TLabel", font=("Segoe UI", 11, "bold"))
        style.configure("Primary.TButton", font=("Segoe UI", 11, "bold"), padding=(16, 10))
        style.configure("Mode.TRadiobutton", font=("Segoe UI", 11, "bold"), padding=8)

    def _build_ui(self) -> None:
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

        main_host = ttk.Frame(self)
        main_host.grid(row=0, column=0, sticky="nsew")
        main_host.rowconfigure(0, weight=1)
        main_host.columnconfigure(0, weight=1)

        frame_background = ttk.Style(self).lookup("TFrame", "background") or "#f0f0f0"
        self.content_canvas = tk.Canvas(
            main_host,
            background=frame_background,
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

        container = ttk.Frame(self.content_canvas, padding=(24, 20, 18, 12))
        self.content_window = self.content_canvas.create_window(
            (0, 0),
            window=container,
            anchor="nw",
        )
        container.bind("<Configure>", self._sync_scroll_region)
        self.content_canvas.bind("<Configure>", self._resize_scroll_content)
        self.bind("<MouseWheel>", self._scroll_main_content, add="+")

        ttk.Label(container, text="PolySub Translator", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            container,
            text="Wykrywa język, tłumaczy napisy i nie zmienia timestampów.",
        ).pack(anchor="w", pady=(2, 5))

        version_frame = ttk.Frame(container)
        version_frame.pack(fill="x", pady=(0, 16))
        version_frame.columnconfigure(0, weight=1)
        self.version_status_var = tk.StringVar(
            value=f"Wersja {__version__} • automatyczne sprawdzanie aktualizacji"
        )
        ttk.Label(version_frame, textvariable=self.version_status_var).grid(
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

        file_frame = ttk.LabelFrame(container, text="1. Napisy lub film", padding=14)
        file_frame.pack(fill="x")
        file_frame.columnconfigure(0, weight=1)
        self.file_var = tk.StringVar(value="Nie wybrano pliku")
        ttk.Label(file_frame, textvariable=self.file_var, wraplength=650).grid(
            row=0, column=0, sticky="ew"
        )
        self.file_button = ttk.Button(
            file_frame, text="Wybierz SRT lub film", command=self._choose_file
        )
        self.file_button.grid(row=0, column=1, sticky="e", padx=(12, 0))
        ttk.Label(
            file_frame,
            text="Gdy film nie ma napisów:",
        ).grid(row=1, column=0, sticky="e", pady=(10, 0), padx=(0, 8))
        self.speech_model_var = tk.StringVar(value="Dokładniejsze — Whisper medium")
        ttk.Combobox(
            file_frame,
            textvariable=self.speech_model_var,
            values=list(SPEECH_MODEL_LABELS),
            state="readonly",
            width=32,
        ).grid(row=1, column=1, sticky="e", pady=(10, 0))

        language_frame = ttk.LabelFrame(container, text="2. Języki", padding=14)
        language_frame.pack(fill="x", pady=12)
        language_frame.columnconfigure(1, weight=1)
        language_frame.columnconfigure(3, weight=1)
        ttk.Label(language_frame, text="Wykryty język:").grid(row=0, column=0, sticky="w")
        self.source_var = tk.StringVar(value="—")
        self.source_combo = ttk.Combobox(
            language_frame, textvariable=self.source_var, values=language_options(), state="normal"
        )
        self.source_combo.grid(row=0, column=1, sticky="ew", padx=(8, 24))
        ttk.Label(language_frame, text="Język docelowy:").grid(row=0, column=2, sticky="w")
        self.target_var = tk.StringVar(value=f"{language_name('pl')} (pl)")
        self.target_combo = ttk.Combobox(
            language_frame, textvariable=self.target_var, values=language_options(), state="normal"
        )
        self.target_combo.grid(row=0, column=3, sticky="ew", padx=(8, 0))
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
        self.engine_var = tk.StringVar(value="Lokalny AI (M2M100)")
        engine_combo = ttk.Combobox(
            engine_frame,
            textvariable=self.engine_var,
            values=list(ENGINE_LABELS),
            state="readonly",
        )
        engine_combo.pack(fill="x")
        engine_combo.bind("<<ComboboxSelected>>", lambda _event: self._update_api_state())
        ttk.Label(engine_frame, text="Klucz DeepL API (nie jest zapisywany):").pack(
            anchor="w", pady=(12, 3)
        )
        self.api_key_var = tk.StringVar(value=os.getenv("DEEPL_API_KEY", ""))
        self.api_entry = ttk.Entry(engine_frame, textvariable=self.api_key_var, show="•")
        self.api_entry.pack(fill="x")

        mode_frame = ttk.LabelFrame(settings, text="4. Tryb tłumaczenia", padding=14)
        mode_frame.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        self.mode_var = tk.StringVar(value=TranslationMode.AUTOMATIC.value)
        ttk.Radiobutton(
            mode_frame,
            text="⚡ Tłumacz automatycznie",
            value=TranslationMode.AUTOMATIC.value,
            variable=self.mode_var,
            style="Mode.TRadiobutton",
        ).pack(anchor="w")
        ttk.Label(mode_frame, text="Szybko, bez dodatkowych pytań.").pack(anchor="w", padx=28)
        ttk.Radiobutton(
            mode_frame,
            text="🎯 Tłumacz z weryfikacją",
            value=TranslationMode.REVIEW.value,
            variable=self.mode_var,
            style="Mode.TRadiobutton",
        ).pack(anchor="w", pady=(10, 0))
        ttk.Label(mode_frame, text="Kontekst i edycja niejasnych kwestii.").pack(
            anchor="w", padx=28
        )

        compute_frame = ttk.LabelFrame(
            container,
            text="5. Urządzenie obliczeniowe",
            padding=12,
        )
        compute_frame.pack(fill="x", pady=(12, 0))
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
            command=self._start_device_detection,
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

        context_frame = ttk.LabelFrame(
            container, text="7. Postacie i kontekst (opcjonalnie)", padding=12
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

        self._build_activity_panel()
        self._build_action_bar()
        self._update_api_state()

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
        action_frame.grid(row=2, column=0, sticky="ew")
        action_frame.columnconfigure(0, weight=1)
        action_frame.columnconfigure(1, weight=1)
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
        self.start_button = ttk.Button(
            action_frame,
            text="Rozpocznij tłumaczenie",
            command=self._start_translation,
            style="Primary.TButton",
        )
        self.start_button.grid(
            row=1,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(8, 0),
        )

    def _build_activity_panel(self) -> None:
        activity = ttk.LabelFrame(self, text="Postęp operacji", padding=(18, 10))
        activity.grid(row=1, column=0, sticky="ew", padx=18, pady=(8, 0))
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

    def _choose_file(self) -> None:
        selected = filedialog.askopenfilename(
            title="Wybierz napisy lub film",
            filetypes=[
                ("Napisy SubRip", "*.srt"),
                ("Pliki wideo", "*.mp4 *.m4v *.mkv *.mov *.avi *.webm"),
                ("Wszystkie pliki", "*"),
            ],
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
        self.file_var.set(str(selected_path))

        if selected_path.suffix.lower() in VIDEO_EXTENSIONS:
            self._start_video_import(selected_path)
            return

        self._start_subtitle_import(selected_path)

    def _start_subtitle_import(self, subtitle_path: Path) -> None:
        self.file_button.configure(state="disabled")
        self.start_button.configure(state="disabled")
        self.attach_button.configure(state="disabled")
        self.burn_button.configure(state="disabled")
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
        self.file_button.configure(state="normal")
        self._finish_activity(f"Napisy gotowe do tłumaczenia: {subtitle_path.name}")

    def _subtitle_import_failed(self, message: str) -> None:
        self.file_button.configure(state="normal")
        self.start_button.configure(state="normal")
        self._update_attach_button()
        self._fail_activity("Nie udało się wczytać napisów")
        messagebox.showerror("Nie można wczytać pliku", message, parent=self)

    def _start_video_import(self, video_path: Path) -> None:
        self.file_button.configure(state="disabled")
        self.start_button.configure(state="disabled")
        self.attach_button.configure(state="disabled")
        self.burn_button.configure(state="disabled")
        self._begin_activity(
            [
                "Analiza filmu",
                "Przygotowanie napisów",
                "Wykrywanie języka",
                "Przygotowanie dokumentu",
            ],
            f"Sprawdzanie filmu {video_path.name}",
        )
        model_size = SPEECH_MODEL_LABELS[self.speech_model_var.get()]
        device_resolution = self._resolve_selected_device("transcription")
        cpu_usage_limit = self._selected_cpu_usage_limit()
        thread = threading.Thread(
            target=self._video_import_worker,
            args=(video_path, model_size, device_resolution, cpu_usage_limit),
            daemon=True,
        )
        thread.start()

    def _video_import_worker(
        self,
        video_path: Path,
        model_size: str,
        device_resolution: DeviceResolution,
        cpu_usage_limit: int,
    ) -> None:
        try:
            if device_resolution.fallback_reason:
                self.after(0, self._video_status, device_resolution.fallback_reason)
            importer = VideoSubtitleImporter(
                model_size=model_size,
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
        self._show_stage(
            4,
            f"{method}. Przygotowano {len(result.document.cues):,} kwestii.".replace(",", " "),
            determinate=True,
        )
        self.file_button.configure(state="normal")
        self._finish_activity(f"Napisy z filmu gotowe: {result.subtitle_path.name}")

    def _video_import_failed(self, message: str) -> None:
        self.file_button.configure(state="normal")
        self.start_button.configure(state="normal")
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
        self.start_button.configure(state="normal")

    def _update_api_state(self) -> None:
        state = "normal" if ENGINE_LABELS[self.engine_var.get()] == "deepl" else "disabled"
        self.api_entry.configure(state=state)
        if hasattr(self, "device_status_var"):
            self._update_device_description()

    def _start_translation(self) -> None:
        if self.document is None or self.source_path is None:
            messagebox.showwarning(
                "Brak pliku", "Najpierw wybierz plik SRT albo film.", parent=self
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
        if ENGINE_LABELS[self.engine_var.get()] == "deepl" and not self.api_key_var.get().strip():
            messagebox.showwarning("Brak klucza", "Wpisz klucz DeepL API.", parent=self)
            return

        engine_kind = ENGINE_LABELS[self.engine_var.get()]
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

        self.start_button.configure(state="disabled")
        self.file_button.configure(state="disabled")
        self.attach_button.configure(state="disabled")
        self.burn_button.configure(state="disabled")
        self.translated_subtitle_path = None
        self.translated_target_language = None
        api_key = self.api_key_var.get()
        mode = TranslationMode(self.mode_var.get())
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
                device_resolution,
                cpu_usage_limit,
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
        device_resolution: DeviceResolution,
        cpu_usage_limit: int,
    ) -> None:
        try:
            if engine_kind == "local" and device_resolution.fallback_reason:
                self.after(0, self._engine_status, device_resolution.fallback_reason)
            engine = (
                DeepLEngine(api_key)
                if engine_kind == "deepl"
                else M2M100Engine(
                    device=device_resolution.runtime_device,
                    status=lambda message: self.after(0, self._engine_status, message),
                    cpu_usage_limit=cpu_usage_limit,
                )
            )
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
            )
            self.after(0, self._translation_finished, result, output, mode, target)
        except Exception as exc:
            self.after(0, self._translation_failed, str(exc))

    def _engine_status(self, message: str) -> None:
        self._show_stage(1, message)

    def _translation_service_status(self, message: str) -> None:
        lowered = message.lower()
        if "wznowienia" in lowered or "wcześniejsz" in lowered:
            self._show_stage(2, message)
        elif lowered.startswith("tłumaczenie "):
            self._show_stage(3, message, determinate=True)
        elif "kontrola" in lowered or "analizowanie jakości" in lowered:
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
        self.start_button.configure(state="normal")
        self.file_button.configure(state="normal")
        if mode is TranslationMode.REVIEW:
            finished_message = (
                f"Tłumaczenie gotowe — {len(result.review_items)} kwestii oznaczono."
            )
            self._show_stage(6, finished_message, determinate=True)
            self._finish_activity(finished_message)
            ReviewWindow(
                self,
                self.document,
                result.document,
                result.review_items,
                output,
                result.checkpoint_path,
                on_saved=lambda saved_path: self._translated_subtitle_ready(
                    saved_path, target_language
                ),
            )
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
            f"Zapisano plik:\n{output}{suffix}",
            parent=self,
        )

    def _translation_failed(self, message: str) -> None:
        self.start_button.configure(state="normal")
        self.file_button.configure(state="normal")
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
        output_path: Path,
        checkpoint_path: Path | None,
        on_saved: Callable[[Path], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self.title("Weryfikacja tłumaczenia — PolySub")
        self.geometry("1180x720")
        self.minsize(900, 600)
        self.original = original
        self.translated = translated
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
                    source.timing,
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
        self.translated.assert_structure_matches(self.original)
        self.translated.save(self.output_path)
        if self.checkpoint_path:
            self.checkpoint_path.unlink(missing_ok=True)
        if self.on_saved:
            self.on_saved(self.output_path)
        messagebox.showinfo("Zapisano", f"Gotowy plik:\n{self.output_path}", parent=self)

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
