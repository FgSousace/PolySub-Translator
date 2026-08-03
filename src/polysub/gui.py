from __future__ import annotations

import os
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

from .detector import detect_language
from .engines import DeepLEngine, M2M100Engine
from .languages import language_name, language_options, parse_language_option
from .models import TranslationMode
from .service import TranslationOptions, TranslationService
from .subtitles import SRTDocument, default_output_path

ENGINE_LABELS = {
    "Lokalny AI (M2M100)": "local",
    "DeepL API": "deepl",
}


class PolySubApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("PolySub Translator")
        self.geometry("920x700")
        self.minsize(780, 620)
        self.document: SRTDocument | None = None
        self.source_path: Path | None = None
        self._build_style()
        self._build_ui()

    def _build_style(self) -> None:
        style = ttk.Style(self)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure("Title.TLabel", font=("Segoe UI", 22, "bold"))
        style.configure("Heading.TLabel", font=("Segoe UI", 11, "bold"))
        style.configure("Primary.TButton", font=("Segoe UI", 11, "bold"), padding=(16, 10))
        style.configure("Mode.TRadiobutton", font=("Segoe UI", 11, "bold"), padding=8)

    def _build_ui(self) -> None:
        container = ttk.Frame(self, padding=24)
        container.pack(fill="both", expand=True)

        ttk.Label(container, text="PolySub Translator", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            container,
            text="Wykrywa język, tłumaczy napisy i nie zmienia timestampów.",
        ).pack(anchor="w", pady=(2, 20))

        file_frame = ttk.LabelFrame(container, text="1. Plik napisów", padding=14)
        file_frame.pack(fill="x")
        self.file_var = tk.StringVar(value="Nie wybrano pliku")
        ttk.Label(file_frame, textvariable=self.file_var).pack(side="left", fill="x", expand=True)
        ttk.Button(file_frame, text="Wybierz plik SRT", command=self._choose_file).pack(
            side="right"
        )

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

        context_frame = ttk.LabelFrame(
            container, text="5. Postacie i kontekst (opcjonalnie)", padding=12
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

        progress_frame = ttk.Frame(container)
        progress_frame.pack(fill="x")
        self.progress_var = tk.IntVar(value=0)
        self.progress_bar = ttk.Progressbar(
            progress_frame, variable=self.progress_var, maximum=1, mode="determinate"
        )
        self.progress_bar.pack(fill="x")
        self.progress_text = tk.StringVar(value="Przetłumaczono 0 z 0 słów")
        ttk.Label(progress_frame, textvariable=self.progress_text).pack(anchor="w", pady=(4, 0))
        self.status_var = tk.StringVar(value="Gotowy")
        ttk.Label(progress_frame, textvariable=self.status_var).pack(anchor="w")

        self.start_button = ttk.Button(
            container,
            text="Rozpocznij tłumaczenie",
            command=self._start_translation,
            style="Primary.TButton",
        )
        self.start_button.pack(anchor="e", pady=(12, 0))
        self._update_api_state()

    def _choose_file(self) -> None:
        selected = filedialog.askopenfilename(
            title="Wybierz napisy", filetypes=[("Napisy SubRip", "*.srt"), ("Wszystkie pliki", "*")]
        )
        if not selected:
            return
        try:
            document = SRTDocument.load(selected)
            detected = detect_language(document.combined_text)
        except Exception as exc:
            messagebox.showerror("Nie można wczytać pliku", str(exc), parent=self)
            return
        self.document = document
        self.source_path = Path(selected)
        self.file_var.set(str(self.source_path))
        self.source_var.set(f"{detected.name} ({detected.code})")
        self.detected_var.set(
            f"Wykryto: {detected.name} • pewność {detected.confidence:.0%} • "
            f"{document.total_words:,} słów".replace(",", " ")
        )
        self._set_progress(0, document.total_words)

    def _update_api_state(self) -> None:
        state = "normal" if ENGINE_LABELS[self.engine_var.get()] == "deepl" else "disabled"
        self.api_entry.configure(state=state)

    def _start_translation(self) -> None:
        if self.document is None or self.source_path is None:
            messagebox.showwarning("Brak pliku", "Najpierw wybierz plik SRT.", parent=self)
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

        self.start_button.configure(state="disabled")
        self.status_var.set("Przygotowywanie silnika...")
        self._set_progress(0, self.document.total_words)
        engine_kind = ENGINE_LABELS[self.engine_var.get()]
        api_key = self.api_key_var.get()
        mode = TranslationMode(self.mode_var.get())
        context_notes = self.context_text.get("1.0", "end").strip()
        thread = threading.Thread(
            target=self._translation_worker,
            args=(source, target, engine_kind, api_key, mode, context_notes),
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
    ) -> None:
        try:
            engine = DeepLEngine(api_key) if engine_kind == "deepl" else M2M100Engine()
            options = TranslationOptions(
                source_language=source,
                target_language=target,
                mode=mode,
                context_notes=context_notes,
            )
            service = TranslationService(engine)
            self.after(0, self.status_var.set, f"Tłumaczenie przez {engine.display_name}...")
            output = default_output_path(self.source_path, target)
            result = service.translate(
                self.document,
                options,
                progress=lambda done, total: self.after(0, self._set_progress, done, total),
                output_path=output if mode is TranslationMode.AUTOMATIC else None,
            )
            self.after(0, self._translation_finished, result, output, mode)
        except Exception as exc:
            self.after(0, self._translation_failed, str(exc))

    def _translation_finished(self, result, output: Path, mode: TranslationMode) -> None:
        self.start_button.configure(state="normal")
        if mode is TranslationMode.REVIEW:
            self.status_var.set(
                f"Tłumaczenie gotowe — {len(result.review_items)} kwestii oznaczono."
            )
            ReviewWindow(
                self,
                self.document,
                result.document,
                result.review_items,
                output,
                result.checkpoint_path,
            )
            return
        self.status_var.set(f"Gotowe: {output.name}")
        messagebox.showinfo("Tłumaczenie gotowe", f"Zapisano plik:\n{output}", parent=self)

    def _translation_failed(self, message: str) -> None:
        self.start_button.configure(state="normal")
        self.status_var.set("Wystąpił błąd")
        messagebox.showerror("Tłumaczenie nie powiodło się", message, parent=self)

    def _set_progress(self, processed: int, total: int) -> None:
        self.progress_bar.configure(maximum=max(total, 1))
        self.progress_var.set(processed)
        self.progress_text.set(f"Przetłumaczono {processed:,} z {total:,} słów".replace(",", " "))


class ReviewWindow(tk.Toplevel):
    def __init__(
        self,
        parent,
        original,
        translated,
        review_items,
        output_path: Path,
        checkpoint_path: Path | None,
    ) -> None:
        super().__init__(parent)
        self.title("Weryfikacja tłumaczenia — PolySub")
        self.geometry("1180x720")
        self.minsize(900, 600)
        self.original = original
        self.translated = translated
        self.output_path = output_path
        self.checkpoint_path = checkpoint_path
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
    app = PolySubApp()
    app.mainloop()


if __name__ == "__main__":
    main()
