from __future__ import annotations

import threading
import tkinter as tk
import webbrowser
from collections.abc import Callable
from tkinter import messagebox, ttk

from .branding import PRODUCT_NAME
from .model_downloads import (
    ModelDownloadError,
    ModelStatus,
    download_model,
    format_bytes,
    model_status,
    remove_model,
)
from .translation_models import (
    DEFAULT_MODEL_ID,
    MODEL_CATALOG,
    TranslationModelSpec,
    get_model_spec,
)

ModelSelectionCallback = Callable[[str], None]


class ModelManagerWindow(tk.Toplevel):
    def __init__(
        self,
        parent: tk.Misc,
        *,
        selected_model_id: str = DEFAULT_MODEL_ID,
        source_language: str | None = None,
        target_language: str | None = None,
        on_use: ModelSelectionCallback | None = None,
        on_close: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self.title(f"{PRODUCT_NAME} — modele AI do tłumaczenia")
        self.geometry("1040x700")
        self.minsize(820, 560)
        if parent.winfo_viewable():
            self.transient(parent)
        self._source_language = source_language
        self._target_language = target_language
        self._on_use = on_use
        self._on_close = on_close
        self._busy = False
        self._statuses: dict[str, ModelStatus] = {}
        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.refresh()
        if selected_model_id in {model.id for model in MODEL_CATALOG}:
            self.model_tree.selection_set(selected_model_id)
            self.model_tree.focus(selected_model_id)
            self.model_tree.see(selected_model_id)
        self._selection_changed()
        self.grab_set()

    def _build_ui(self) -> None:
        self.rowconfigure(1, weight=1)
        self.columnconfigure(0, weight=1)

        intro = ttk.Frame(self, padding=(18, 16, 18, 10))
        intro.grid(row=0, column=0, sticky="ew")
        intro.columnconfigure(0, weight=1)
        ttk.Label(
            intro,
            text="20 opcjonalnych modeli AI — od najmocniejszych do najlżejszych",
            font=("Segoe UI", 15, "bold"),
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            intro,
            text=(
                "Ranking jest orientacyjny. Mały model OPUS może być lepszy od modelu "
                "ogólnego dla swojej konkretnej pary językowej. Modele są pobierane "
                "bezpośrednio z oficjalnych repozytoriów Hugging Face."
            ),
            wraplength=940,
        ).grid(row=1, column=0, sticky="w", pady=(5, 0))

        table_host = ttk.Frame(self, padding=(18, 0))
        table_host.grid(row=1, column=0, sticky="nsew")
        table_host.rowconfigure(0, weight=1)
        table_host.columnconfigure(0, weight=1)
        columns = ("rank", "name", "size", "quality", "license", "status")
        self.model_tree = ttk.Treeview(
            table_host,
            columns=columns,
            show="headings",
            selectmode="browse",
        )
        headings = {
            "rank": "#",
            "name": "Model",
            "size": "Pobieranie",
            "quality": "Jakość",
            "license": "Licencja",
            "status": "Stan",
        }
        widths = {
            "rank": 42,
            "name": 260,
            "size": 88,
            "quality": 120,
            "license": 135,
            "status": 150,
        }
        for column in columns:
            self.model_tree.heading(column, text=headings[column])
            self.model_tree.column(
                column,
                width=widths[column],
                minwidth=widths[column],
                anchor="center" if column != "name" else "w",
                stretch=column in {"name", "status"},
            )
        scrollbar = ttk.Scrollbar(
            table_host,
            orient="vertical",
            command=self.model_tree.yview,
        )
        self.model_tree.configure(yscrollcommand=scrollbar.set)
        self.model_tree.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.model_tree.bind("<<TreeviewSelect>>", lambda _event: self._selection_changed())

        details = ttk.LabelFrame(self, text="Wybrany model", padding=12)
        details.grid(row=2, column=0, sticky="ew", padx=18, pady=(12, 0))
        details.columnconfigure(0, weight=1)
        self.details_var = tk.StringVar()
        ttk.Label(details, textvariable=self.details_var, wraplength=970).grid(
            row=0,
            column=0,
            sticky="w",
        )
        self.operation_var = tk.StringVar(value="Wybierz model z listy.")
        ttk.Label(details, textvariable=self.operation_var, wraplength=970).grid(
            row=1,
            column=0,
            sticky="w",
            pady=(6, 0),
        )
        self.progress = ttk.Progressbar(details, mode="indeterminate")
        self.progress.grid(row=2, column=0, sticky="ew", pady=(8, 0))

        actions = ttk.Frame(self, padding=(18, 12, 18, 18))
        actions.grid(row=3, column=0, sticky="ew")
        actions.columnconfigure(5, weight=1)
        self.download_button = ttk.Button(
            actions,
            text="Pobierz wybrany",
            command=self._download_selected,
        )
        self.download_button.grid(row=0, column=0, padx=(0, 8))
        self.remove_button = ttk.Button(
            actions,
            text="Usuń z dysku",
            command=self._remove_selected,
        )
        self.remove_button.grid(row=0, column=1, padx=(0, 8))
        self.use_button = ttk.Button(
            actions,
            text="Użyj wybranego",
            command=self._use_selected,
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
        ttk.Button(actions, text="Zamknij", command=self._close).grid(
            row=0,
            column=6,
            padx=(12, 0),
        )

    def refresh(self) -> None:
        if self._busy:
            return
        previous = self._selected_model_id()
        self._statuses = {model.id: model_status(model) for model in MODEL_CATALOG}
        for model in MODEL_CATALOG:
            values = (
                model.rank,
                model.display_name,
                model.size_label,
                model.quality,
                model.license_name,
                self._statuses[model.id].status_label,
            )
            if self.model_tree.exists(model.id):
                self.model_tree.item(model.id, values=values)
            else:
                self.model_tree.insert("", "end", iid=model.id, values=values)
        selected = previous or DEFAULT_MODEL_ID
        if self.model_tree.exists(selected):
            self.model_tree.selection_set(selected)
        self._selection_changed()

    def _selected_model_id(self) -> str | None:
        selection = self.model_tree.selection()
        return selection[0] if selection else None

    def _selected_model(self) -> TranslationModelSpec | None:
        model_id = self._selected_model_id()
        return get_model_spec(model_id) if model_id else None

    def _selection_changed(self) -> None:
        model = self._selected_model()
        if model is None:
            self.details_var.set("Wybierz model z listy.")
            self._set_action_states(None)
            return
        status = self._statuses.get(model.id)
        pair_message = self._pair_message(model)
        note = f" {model.note}" if model.note else ""
        self.details_var.set(
            f"#{model.rank} {model.display_name} · {model.repo_id} · {model.hardware_label}. "
            f"Licencja: {model.license_name}.{note} {pair_message}"
        )
        if not self._busy:
            self.operation_var.set(status.status_label if status else "Sprawdzanie stanu…")
        self._set_action_states(model)

    def _pair_message(self, model: TranslationModelSpec) -> str:
        if not self._source_language or not self._target_language:
            return "Zgodność zostanie sprawdzona po wybraniu języków."
        if model.supports_pair(self._source_language, self._target_language):
            return (
                f"Obsługuje wybraną parę {self._source_language} → "
                f"{self._target_language}."
            )
        return (
            f"Nie obsługuje wybranej pary {self._source_language} → "
            f"{self._target_language}."
        )

    def _set_action_states(self, model: TranslationModelSpec | None) -> None:
        if self._busy or model is None:
            state = "disabled"
            self.download_button.configure(state=state)
            self.remove_button.configure(state=state)
            self.use_button.configure(state=state)
            self.card_button.configure(state=state)
            self.refresh_button.configure(state=state)
            return
        status = self._statuses.get(model.id)
        installed = bool(status and status.installed)
        pair_supported = (
            not self._source_language
            or not self._target_language
            or model.supports_pair(self._source_language, self._target_language)
        )
        self.download_button.configure(state="disabled" if installed else "normal")
        self.remove_button.configure(
            state="normal" if status and (installed or status.partial) else "disabled"
        )
        self.use_button.configure(
            state="normal"
            if installed and pair_supported and self._on_use is not None
            else "disabled"
        )
        self.card_button.configure(state="normal")
        self.refresh_button.configure(state="normal")

    def _download_selected(self) -> None:
        model = self._selected_model()
        if model is None:
            return
        model_note = f"Uwaga: {model.note}" if model.note else ""
        warning = (
            f"Model: {model.display_name}\n"
            f"Pobieranie: około {model.size_label}\n"
            f"Wymagania: {model.hardware_label}\n"
            f"Licencja: {model.license_name}\n"
            f"{model_note}\n\n"
            "Pliki zostaną pobrane z oficjalnego repozytorium Hugging Face. "
            "Przerwane pobieranie można wznowić."
        )
        if model.download_gb >= 10:
            warning += (
                "\n\nTo bardzo duży model. Upewnij się, że komputer ma wystarczająco "
                "dużo wolnego miejsca i pamięci."
            )
        if not messagebox.askyesno("Pobrać model AI?", warning, parent=self):
            return
        self._set_busy(True, f"Rozpoczynanie pobierania {model.display_name}…")
        threading.Thread(target=self._download_worker, args=(model,), daemon=True).start()

    def _download_worker(self, model: TranslationModelSpec) -> None:
        try:
            download_model(
                model,
                status=lambda message: self.after(0, self.operation_var.set, message),
            )
        except Exception as exc:
            self.after(0, self._operation_failed, "Pobieranie nie powiodło się", str(exc))
            return
        self.after(0, self._download_finished, model)

    def _download_finished(self, model: TranslationModelSpec) -> None:
        self._set_busy(False, f"Model {model.display_name} został pobrany.")
        self.refresh()
        messagebox.showinfo(
            "Model gotowy",
            f"{model.display_name} jest gotowy do tłumaczenia.",
            parent=self,
        )

    def _remove_selected(self) -> None:
        model = self._selected_model()
        if model is None:
            return
        status = self._statuses.get(model.id)
        size = format_bytes(status.size_bytes) if status else "nieznany rozmiar"
        if not messagebox.askyesno(
            "Usunąć model z dysku?",
            f"Usunąć {model.display_name} ({size})?\n\nModel można później pobrać ponownie.",
            parent=self,
        ):
            return
        self._set_busy(True, f"Usuwanie {model.display_name}…")
        threading.Thread(target=self._remove_worker, args=(model,), daemon=True).start()

    def _remove_worker(self, model: TranslationModelSpec) -> None:
        try:
            removed = remove_model(model)
        except Exception as exc:
            self.after(0, self._operation_failed, "Usuwanie nie powiodło się", str(exc))
            return
        self.after(0, self._remove_finished, model, removed)

    def _remove_finished(self, model: TranslationModelSpec, removed: int) -> None:
        self._set_busy(
            False,
            f"Usunięto {model.display_name}; zwolniono {format_bytes(removed)}.",
        )
        self.refresh()

    def _operation_failed(self, title: str, message: str) -> None:
        self._set_busy(False, message)
        self.refresh()
        messagebox.showerror(title, message, parent=self)

    def _set_busy(self, busy: bool, message: str) -> None:
        self._busy = busy
        self.operation_var.set(message)
        if busy:
            self.progress.start(12)
        else:
            self.progress.stop()
        self._set_action_states(self._selected_model())

    def _use_selected(self) -> None:
        model = self._selected_model()
        if model is None or self._on_use is None:
            return
        self._on_use(model.id)
        self._close()

    def _open_model_card(self) -> None:
        model = self._selected_model()
        if model is not None:
            webbrowser.open(model.model_card_url)

    def _close(self) -> None:
        if self._busy:
            messagebox.showwarning(
                "Pobieranie trwa",
                "Poczekaj na zakończenie bieżącej operacji. Przerwane pobieranie można "
                "wznowić po ponownym uruchomieniu programu.",
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
