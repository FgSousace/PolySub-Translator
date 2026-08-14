from __future__ import annotations

import threading
import tkinter as tk
import webbrowser
from collections.abc import Callable
from tkinter import messagebox, ttk
from typing import TypeAlias

from .branding import PRODUCT_NAME
from .model_downloads import (
    ModelDownloadError,
    ModelStatus,
    download_model,
    format_bytes,
    format_download_progress,
    model_status,
    remove_model,
)
from .narrator_models import NARRATOR_MODEL_CATALOG, NarratorModelSpec
from .translation_models import DEFAULT_MODEL_ID, MODEL_CATALOG, TranslationModelSpec
from .whisper_models import (
    DEFAULT_WHISPER_MODEL_ID,
    WHISPER_MODEL_CATALOG,
    WhisperModelSpec,
)

CatalogModel: TypeAlias = TranslationModelSpec | WhisperModelSpec | NarratorModelSpec
ModelSelectionCallback = Callable[[str], None]


class ModelManagerWindow(tk.Toplevel):
    def __init__(
        self,
        parent: tk.Misc,
        *,
        selected_model_id: str = DEFAULT_MODEL_ID,
        selected_whisper_id: str = DEFAULT_WHISPER_MODEL_ID,
        initial_tab: str = "translation",
        source_language: str | None = None,
        target_language: str | None = None,
        on_use: ModelSelectionCallback | None = None,
        on_use_whisper: ModelSelectionCallback | None = None,
        on_close: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self.title(f"{PRODUCT_NAME} — modele AI")
        self.geometry("1220x760")
        self.minsize(920, 620)
        if parent.winfo_viewable():
            self.transient(parent)
        self._source_language = source_language
        self._target_language = target_language
        self._on_use = on_use
        self._on_use_whisper = on_use_whisper
        self._on_close = on_close
        self._busy = False
        self._statuses: dict[str, ModelStatus] = {}
        self._trees: dict[str, ttk.Treeview] = {}
        self._tab_ids: dict[str, str] = {}
        self._catalogs: dict[str, tuple[CatalogModel, ...]] = {
            "translation": MODEL_CATALOG,
            "whisper": WHISPER_MODEL_CATALOG,
            "narrator": NARRATOR_MODEL_CATALOG,
        }
        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.refresh()
        self._select_if_present("translation", selected_model_id)
        self._select_if_present("whisper", selected_whisper_id)
        self.show_tab(initial_tab)
        self._selection_changed()
        self.grab_set()

    def show_tab(self, kind: str) -> None:
        if kind in self._catalogs:
            self.notebook.select(tuple(self._catalogs).index(kind))
            self._selection_changed()

    def _build_ui(self) -> None:
        self.rowconfigure(1, weight=1)
        self.columnconfigure(0, weight=1)

        intro = ttk.Frame(self, padding=(18, 16, 18, 10))
        intro.grid(row=0, column=0, sticky="ew")
        intro.columnconfigure(0, weight=1)
        ttk.Label(
            intro,
            text="Modele tłumaczenia, rozpoznawania mowy i polskiego lektora",
            font=("Segoe UI", 15, "bold"),
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            intro,
            text=(
                "Ocena dokładności 1–5 jest praktyczną wskazówką dla napisów. "
                "Pobieranie można wznowić, a pasek pokazuje zapisane MB/GB i procent. "
                "Modele pochodzą z repozytoriów wskazanych w ich kartach."
            ),
            wraplength=1140,
        ).grid(row=1, column=0, sticky="w", pady=(5, 0))

        self.notebook = ttk.Notebook(self)
        self.notebook.grid(row=1, column=0, sticky="nsew", padx=18)
        tabs = (
            ("translation", f"Tłumaczenie ({len(MODEL_CATALOG)})"),
            ("whisper", f"Whisper ({len(WHISPER_MODEL_CATALOG)})"),
            ("narrator", f"Lektor ({len(NARRATOR_MODEL_CATALOG)})"),
        )
        for kind, label in tabs:
            frame = ttk.Frame(self.notebook, padding=(0, 8, 0, 0))
            frame.rowconfigure(0, weight=1)
            frame.columnconfigure(0, weight=1)
            tree = self._build_tree(frame)
            self._trees[kind] = tree
            self.notebook.add(frame, text=label)
            self._tab_ids[str(frame)] = kind
        self.model_tree = self._trees["translation"]
        self.notebook.bind("<<NotebookTabChanged>>", lambda _event: self._selection_changed())

        details = ttk.LabelFrame(self, text="Wybrany model", padding=12)
        details.grid(row=2, column=0, sticky="ew", padx=18, pady=(12, 0))
        details.columnconfigure(0, weight=1)
        self.details_var = tk.StringVar()
        ttk.Label(details, textvariable=self.details_var, wraplength=1150).grid(
            row=0, column=0, sticky="w"
        )
        self.operation_var = tk.StringVar(value="Wybierz model z listy.")
        ttk.Label(details, textvariable=self.operation_var, wraplength=1150).grid(
            row=1, column=0, sticky="w", pady=(6, 0)
        )
        self.progress_var = tk.DoubleVar(value=0)
        self.progress = ttk.Progressbar(
            details,
            mode="determinate",
            maximum=100,
            variable=self.progress_var,
        )
        self.progress.grid(row=2, column=0, sticky="ew", pady=(8, 0))

        actions = ttk.Frame(self, padding=(18, 12, 18, 18))
        actions.grid(row=3, column=0, sticky="ew")
        actions.columnconfigure(5, weight=1)
        self.download_button = ttk.Button(
            actions, text="Pobierz / wznów", command=self._download_selected
        )
        self.download_button.grid(row=0, column=0, padx=(0, 8))
        self.remove_button = ttk.Button(actions, text="Usuń z dysku", command=self._remove_selected)
        self.remove_button.grid(row=0, column=1, padx=(0, 8))
        self.use_button = ttk.Button(
            actions, text="Użyj w oknie głównym", command=self._use_selected
        )
        self.use_button.grid(row=0, column=2, padx=(0, 8))
        self.card_button = ttk.Button(
            actions,
            text="Karta i licencja modelu",
            command=self._open_model_card,
        )
        self.card_button.grid(row=0, column=3, padx=(0, 8))
        self.refresh_button = ttk.Button(actions, text="Odśwież", command=self.refresh)
        self.refresh_button.grid(row=0, column=4)
        ttk.Button(actions, text="Zamknij", command=self._close).grid(row=0, column=6, padx=(12, 0))

    def _build_tree(self, parent: ttk.Frame) -> ttk.Treeview:
        columns = ("rank", "name", "size", "accuracy", "speed", "license", "status")
        tree = ttk.Treeview(parent, columns=columns, show="headings", selectmode="browse")
        headings = {
            "rank": "#",
            "name": "Model",
            "size": "Pobieranie",
            "accuracy": "Dokładność",
            "speed": "Tempo / rodzaj",
            "license": "Licencja",
            "status": "Stan",
        }
        widths = {
            "rank": 42,
            "name": 270,
            "size": 90,
            "accuracy": 160,
            "speed": 120,
            "license": 145,
            "status": 210,
        }
        for column in columns:
            tree.heading(column, text=headings[column])
            tree.column(
                column,
                width=widths[column],
                minwidth=widths[column],
                anchor="center" if column != "name" else "w",
                stretch=column in {"name", "status"},
            )
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        tree.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        tree.bind("<<TreeviewSelect>>", lambda _event: self._selection_changed())
        return tree

    def refresh(self) -> None:
        if self._busy:
            return
        selected = {kind: self._selected_model_id(kind) for kind in self._catalogs}
        self._statuses = {
            model.id: model_status(model)
            for catalog in self._catalogs.values()
            for model in catalog
        }
        for kind, catalog in self._catalogs.items():
            tree = self._trees[kind]
            for model in catalog:
                speed = getattr(model, "speed", None)
                if not speed:
                    if isinstance(model, NarratorModelSpec):
                        speed = "Jeden głos"
                    elif (
                        isinstance(model, TranslationModelSpec)
                        and model.family.value == "marian"
                    ):
                        speed = "Para językowa"
                    else:
                        speed = "Wielojęzyczny"
                values = (
                    model.rank,
                    model.display_name,
                    model.size_label,
                    model.accuracy_label,
                    speed,
                    model.license_name,
                    self._statuses[model.id].status_label,
                )
                if tree.exists(model.id):
                    tree.item(model.id, values=values)
                else:
                    tree.insert("", "end", iid=model.id, values=values)
            self._select_if_present(kind, selected[kind] or catalog[0].id)
        self._selection_changed()

    def _active_kind(self) -> str:
        return self._tab_ids.get(self.notebook.select(), "translation")

    def _selected_model_id(self, kind: str | None = None) -> str | None:
        tree = self._trees[kind or self._active_kind()]
        selection = tree.selection()
        return selection[0] if selection else None

    def _selected_model(self) -> CatalogModel | None:
        kind = self._active_kind()
        model_id = self._selected_model_id(kind)
        if model_id is None:
            return None
        return next((model for model in self._catalogs[kind] if model.id == model_id), None)

    def _select_if_present(self, kind: str, model_id: str) -> None:
        tree = self._trees[kind]
        if tree.exists(model_id):
            tree.selection_set(model_id)
            tree.focus(model_id)
            tree.see(model_id)

    def _selection_changed(self) -> None:
        model = self._selected_model()
        if model is None:
            self.details_var.set("Wybierz model z listy.")
            self._set_action_states(None)
            return
        current = self._statuses.get(model.id)
        note = getattr(model, "note", "")
        pair_message = self._pair_message(model)
        details = (
            f"{model.display_name} · {model.repo_id} · {model.accuracy_label}. "
            f"Najlepszy do: {model.best_for}. {model.hardware_label}. "
            f"Licencja: {model.license_name}."
        )
        if note:
            details += f" {note}"
        if pair_message:
            details += f" {pair_message}"
        self.details_var.set(details)
        self.use_button.configure(
            text=(
                "Używany automatycznie po tłumaczeniu"
                if isinstance(model, NarratorModelSpec)
                else "Użyj w oknie głównym"
            )
        )
        if not self._busy:
            self.operation_var.set(current.status_label if current else "Sprawdzanie stanu…")
            self._show_stored_size(current)
        self._set_action_states(model)

    def _pair_message(self, model: CatalogModel) -> str:
        if not isinstance(model, TranslationModelSpec):
            return ""
        if not self._source_language or not self._target_language:
            return "Zgodność pary zostanie sprawdzona po wybraniu języków."
        if model.supports_pair(self._source_language, self._target_language):
            return f"Obsługuje {self._source_language} → {self._target_language}."
        return f"Nie obsługuje {self._source_language} → {self._target_language}."

    def _show_stored_size(self, current: ModelStatus | None) -> None:
        if current is None:
            self.progress_var.set(0)
            return
        model = self._selected_model()
        total = max(getattr(model, "estimated_download_bytes", 0), 1)
        self.progress_var.set(min(current.downloaded_bytes / total * 100, 100))

    def _set_action_states(self, model: CatalogModel | None) -> None:
        if self._busy or model is None:
            for button in (
                self.download_button,
                self.remove_button,
                self.use_button,
                self.card_button,
                self.refresh_button,
            ):
                button.configure(state="disabled")
            return
        current = self._statuses.get(model.id)
        installed = bool(current and current.installed)
        can_use = False
        if isinstance(model, TranslationModelSpec):
            pair_supported = (
                not self._source_language
                or not self._target_language
                or model.supports_pair(self._source_language, self._target_language)
            )
            can_use = installed and pair_supported and self._on_use is not None
        elif isinstance(model, WhisperModelSpec):
            can_use = installed and self._on_use_whisper is not None
        self.download_button.configure(state="disabled" if installed else "normal")
        self.remove_button.configure(
            state="normal" if current and (installed or current.partial) else "disabled"
        )
        self.use_button.configure(state="normal" if can_use else "disabled")
        self.card_button.configure(state="normal")
        self.refresh_button.configure(state="normal")

    def _download_selected(self) -> None:
        model = self._selected_model()
        if model is None:
            return
        note = getattr(model, "note", "")
        warning = (
            f"Model: {model.display_name}\n"
            f"Pobieranie: około {model.size_label}\n"
            f"Dokładność: {model.accuracy_label}\n"
            f"Wymagania: {model.hardware_label}\n"
            f"Licencja: {model.license_name}\n"
        )
        if note:
            warning += f"Uwaga: {note}\n"
        warning += (
            "\nPliki zostaną pobrane z repozytorium podanego w karcie modelu. "
            "Przerwane pobieranie można wznowić."
        )
        if not messagebox.askyesno("Pobrać model AI?", warning, parent=self):
            return
        self._set_busy(True, f"Rozpoczynanie pobierania {model.display_name}…")
        threading.Thread(target=self._download_worker, args=(model,), daemon=True).start()

    def _download_worker(self, model: CatalogModel) -> None:
        try:
            download_model(
                model,
                status=lambda message: self.after(0, self.operation_var.set, message),
                progress=lambda done, total: self.after(
                    0, self._download_progress, model, done, total
                ),
            )
        except Exception as exc:
            self.after(0, self._operation_failed, "Pobieranie nie powiodło się", str(exc))
            return
        self.after(0, self._download_finished, model)

    def _download_progress(self, model: CatalogModel, downloaded: int, total: int) -> None:
        percent = min(max(downloaded / max(total, 1) * 100, 0), 100)
        self.progress_var.set(percent)
        self.operation_var.set(
            f"Pobieranie {model.display_name}: {format_download_progress(downloaded, total)}"
        )

    def _download_finished(self, model: CatalogModel) -> None:
        self._set_busy(False, f"Model {model.display_name} został pobrany.")
        self.refresh()
        messagebox.showinfo(
            "Model gotowy", f"{model.display_name} jest gotowy do użycia.", parent=self
        )

    def _remove_selected(self) -> None:
        model = self._selected_model()
        if model is None:
            return
        current = self._statuses.get(model.id)
        size = format_bytes(current.size_bytes) if current else "nieznany rozmiar"
        shared_repo_note = (
            "\n\nUwaga: zostanie usunięty lokalny cache repozytorium Chatterbox, "
            "w tym inne jego warianty zapisane w tym samym cache Hugging Face."
            if isinstance(model, NarratorModelSpec)
            else ""
        )
        if not messagebox.askyesno(
            "Usunąć model z dysku?",
            f"Usunąć {model.display_name} ({size})?\n\n"
            f"Model można później pobrać ponownie.{shared_repo_note}",
            parent=self,
        ):
            return
        self._set_busy(True, f"Usuwanie {model.display_name}…")
        threading.Thread(target=self._remove_worker, args=(model,), daemon=True).start()

    def _remove_worker(self, model: CatalogModel) -> None:
        try:
            removed = remove_model(model)
        except Exception as exc:
            self.after(0, self._operation_failed, "Usuwanie nie powiodło się", str(exc))
            return
        self.after(0, self._remove_finished, model, removed)

    def _remove_finished(self, model: CatalogModel, removed: int) -> None:
        self._set_busy(False, f"Usunięto {model.display_name}; zwolniono {format_bytes(removed)}.")
        self.refresh()

    def _operation_failed(self, title: str, message: str) -> None:
        self._set_busy(False, message)
        self.refresh()
        messagebox.showerror(title, message, parent=self)

    def _set_busy(self, busy: bool, message: str) -> None:
        self._busy = busy
        self.operation_var.set(message)
        if not busy:
            self.progress_var.set(0)
        self._set_action_states(self._selected_model())

    def _use_selected(self) -> None:
        model = self._selected_model()
        if isinstance(model, TranslationModelSpec) and self._on_use is not None:
            self._on_use(model.id)
            self._close()
        elif isinstance(model, WhisperModelSpec) and self._on_use_whisper is not None:
            self._on_use_whisper(model.id)
            self._close()

    def _open_model_card(self) -> None:
        model = self._selected_model()
        if model is not None:
            webbrowser.open(model.model_card_url)

    def _close(self) -> None:
        if self._busy:
            messagebox.showwarning(
                "Pobieranie trwa",
                "Poczekaj na zakończenie operacji. Przerwane pobieranie można wznowić "
                "po ponownym uruchomieniu programu.",
                parent=self,
            )
            return
        self.grab_release()
        self.destroy()
        if self._on_close is not None:
            self._on_close()


def run_model_manager() -> None:
    root = tk.Tk()
    root.withdraw()
    ModelManagerWindow(root, on_close=root.destroy)
    root.mainloop()


__all__ = ["ModelManagerWindow", "run_model_manager", "ModelDownloadError"]
