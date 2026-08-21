#!/usr/bin/env python3
"""
Interfejs graficzny aplikacji Turnieje TP - System ELO.

Główne okno z 5 zakładkami Notebook:
1. Ranking      — obliczanie rankingu ELO (backend XLSX lub SQLite)
2. Import SQL   — import oficjalnych danych XLSX -> baza SQLite
3. Export CSV   — eksport historii zmian punktów do CSV
4. Charts       — wykresy ELO par (obydwa backendy)
5. Migrations   — zarządzanie migracjami schematu bazy SQLite

Wszystkie funkcje delegują do istniejących modułów:
- new_ranking_service.py (backend XLSX)
- SQL/sqlite_ranking_service.py (backend SQLite)
- SQL/import_official_ttp_to_sqlite.py (import danych)
- SQL/migrations.py (migracje)
- new_pair_progress_plot.py (wykresy)
- new_progress_export.py (eksport CSV)
"""

from __future__ import annotations

import os
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

# Add project root to sys.path
_PROJECT_ROOT = Path(__file__).resolve().parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# Add SQL dir to sys.path for SQLite backend
_SQL_DIR = _PROJECT_ROOT / "SQL"
if str(_SQL_DIR) not in sys.path:
    sys.path.insert(0, str(_SQL_DIR))

from new_ranking_service import (
    build_default_new_output_filename,
    build_new_ranking,
    format_new_ranking_report,
    list_available_categories_for_years_xlsx,
    list_available_classes_for_category_and_years_xlsx,
    list_available_years_xlsx,
    load_xlsx_data,
    save_new_ranking_report,
)

# Try to import SQLite backend
try:
    from sqlite_ranking_service import (
        build_ranking_from_sqlite,
        fetch_events,
        format_ranking_report,
        get_available_categories_sqlite,
        get_available_classes,
        get_available_years,
        load_config,
    )
    from migrations import (
        CURRENT_SCHEMA_VERSION,
        ensure_schema,
        get_applied_migrations,
        get_current_version,
        run_migrations,
    )
    from import_official_ttp_to_sqlite import import_xlsx_to_sqlite
    SQLITE_AVAILABLE = True
except ImportError as exc:
    SQLITE_AVAILABLE = False
    print(f"Ostrzeżenie: Backend SQLite niedostępny: {exc}", file=sys.stderr)

# Check for plotting
try:
    import matplotlib
    # Use TkAgg backend for embedding in tkinter
    matplotlib.use("TkAgg")
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
    import seaborn as sns
    PLOT_AVAILABLE = True
except ImportError as exc:
    PLOT_AVAILABLE = False
    print(f"Ostrzeżenie: Wykresy niedostępne: {exc}", file=sys.stderr)

# Try to import plotting
try:
    from new_pair_progress_plot import (
        build_progress_rows,
        filter_pair_catalog,
        normalize_text,
        plot_pair_progress,
        resolve_pair_series,
        unique_pairs,
    )
    PLOT_AVAILABLE = True
except ImportError as exc:
    PLOT_AVAILABLE = False
    print(f"Ostrzeżenie: Moduł wykresów niedostępny: {exc}", file=sys.stderr)

# Try to import progress export
try:
    from new_progress_export import (
        build_default_new_progress_filename,
        build_new_progress_export,
        save_new_progress_csv,
    )
    from SQL.progress_export_sqlite import write_progress_csv
    EXPORT_AVAILABLE = True
except ImportError as exc:
    EXPORT_AVAILABLE = False
    print(f"Ostrzeżenie: Moduł eksportu CSV niedostępny: {exc}", file=sys.stderr)


class ToolTip:
    """Prosty tooltip dla widgetów Tkinter."""

    def __init__(self, widget: tk.Widget, text: str) -> None:
        self.widget = widget
        self.text = text
        self.tip_window = None
        widget.bind("<Enter>", self._on_enter)
        widget.bind("<Leave>", self._on_leave)

    def _on_enter(self, _event=None) -> None:
        self._show_tip()

    def _on_leave(self, _event=None) -> None:
        self._hide_tip()

    def _show_tip(self) -> None:
        if self.tip_window or not self.text:
            return
        x, y, _, cy = self.widget.bbox("insert")
        x += self.widget.winfo_rootx() + 25
        y += self.widget.winfo_rooty() + cy + 25
        self.tip_window = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        label = tk.Label(
            tw,
            text=self.text,
            justify=tk.LEFT,
            background="#ffffe0",
            relief=tk.SOLID,
            borderwidth=1,
            font=("tahoma", 8, "normal"),
        )
        label.pack(ipadx=1)

    def _hide_tip(self) -> None:
        if self.tip_window:
            self.tip_window.destroy()
            self.tip_window = None


class BaseTab(ttk.Frame):
    """Bazowa klasa dla zakładek z pomocniczymi metodami UI."""

    def __init__(self, parent: tk.Widget, project_dir: Path) -> None:
        super().__init__(parent)
        self.project_dir = Path(project_dir).resolve()

    def make_labeled_entry(
        self,
        parent: tk.Widget,
        label_text: str,
        default_value: str = "",
        tooltip: str | None = None,
        width: int = 40,
    ) -> tuple[ttk.Label, ttk.Entry]:
        """Tworzy etykietę i pole tekstowe w jednym wierszu."""
        row = ttk.Frame(parent)
        row.pack(fill=tk.X, pady=2)
        label = ttk.Label(row, text=label_text, width=18)
        label.pack(side=tk.LEFT)
        var = tk.StringVar(value=default_value)
        entry = ttk.Entry(row, textvariable=var, width=width)
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        if tooltip:
            ToolTip(entry, tooltip)
        # Store var on entry to prevent garbage collection
        entry._string_var = var
        return label, entry

    def make_button(
        self,
        parent: tk.Widget,
        text: str,
        command,
        tooltip: str | None = None,
    ) -> ttk.Button:
        btn = ttk.Button(parent, text=text, command=command)
        btn.pack(side=tk.LEFT, padx=4)
        if tooltip:
            ToolTip(btn, tooltip)
        return btn

    def make_status_label(self, parent: tk.Widget) -> ttk.Label:
        status = ttk.Label(parent, text="", foreground="gray")
        status.pack(side=tk.LEFT, padx=4)
        return status

    def show_error(self, message: str) -> None:
        messagebox.showerror("Błąd", message)

    def show_info(self, message: str) -> None:
        messagebox.showinfo("Info", message)

    def run_in_thread(self, target, on_complete=None) -> None:
        """Uruchamia funkcję w wątku, by nie blokować GUI."""
        def wrapper() -> None:
            try:
                result = target()
                if on_complete:
                    self.after(0, lambda: on_complete(result))
            except Exception as exc:  # noqa: BLE001
                self.after(0, lambda: self.show_error(str(exc)))
        thread = threading.Thread(target=wrapper, daemon=True)
        thread.start()


class RankingTab(BaseTab):
    """Zakładka 1: Obliczanie rankingu ELO."""

    def __init__(self, parent: tk.Widget, project_dir: Path) -> None:
        super().__init__(parent, project_dir)
        self.available_years: list[int] = []
        self.available_categories: list[str] = []
        self.available_classes: list[str] = []
        self._build_widgets()

    def _build_widgets(self) -> None:
        # Backend selection
        backend_frame = ttk.LabelFrame(self, text="Backend danych", padding=10)
        backend_frame.pack(fill=tk.X, padx=10, pady=5)

        self.backend_var = tk.StringVar(value="xlsx")
        ttk.Radiobutton(
            backend_frame,
            text="XLSX (data_new.xlsx)",
            variable=self.backend_var,
            value="xlsx",
            command=self._on_backend_change,
        ).pack(side=tk.LEFT, padx=10)
        ttk.Radiobutton(
            backend_frame,
            text="SQLite (baza danych)",
            variable=self.backend_var,
            value="sqlite",
            command=self._on_backend_change,
        ).pack(side=tk.LEFT, padx=10)

        # XLSX path
        self.source_frame = ttk.Frame(self)
        self.source_frame.pack(fill=tk.X, padx=10, pady=2)
        self.xlsx_entry = self.make_labeled_entry(
            self.source_frame,
            "Plik XLSX:",
            str(self.project_dir / "data_new.xlsx"),
            tooltip="Ścieżka do pliku z danymi (data_new.xlsx)",
        )[1]
        ttk.Button(
            self.source_frame,
            text="Przeglądaj...",
            command=lambda: self._pick_file(
                self.xlsx_entry,
                [("Excel files", "*.xlsx"), ("All files", "*.*")],
            ),
        ).pack(side=tk.LEFT, padx=4)

        # SQLite path
        self.db_frame = ttk.Frame(self)
        self.db_frame.pack(fill=tk.X, padx=10, pady=2)
        self.db_entry = self.make_labeled_entry(
            self.db_frame,
            "Baza SQLite:",
            str(self.project_dir / "ttp_official.sqlite") if (self.project_dir / "ttp_official.sqlite").is_file() else str(self.project_dir / "ttp_official.sqlite"),
            tooltip="Ścieżka do bazy SQLite z zaimportowanymi danymi",
        )[1]
        ttk.Button(
            self.db_frame,
            text="Przeglądaj...",
            command=lambda: self._pick_file(
                self.db_entry,
                [("SQLite files", "*.sqlite"), ("All files", "*.*")],
            ),
        ).pack(side=tk.LEFT, padx=4)

        # Filters
        filters_frame = ttk.LabelFrame(self, text="Filtry", padding=10)
        filters_frame.pack(fill=tk.X, padx=10, pady=5)

        # Years
        years_row = ttk.Frame(filters_frame)
        years_row.pack(fill=tk.X, pady=2)
        ttk.Label(years_row, text="Lata:", width=18).pack(side=tk.LEFT)
        self.years_var = tk.StringVar()
        self.years_entry = ttk.Entry(years_row, textvariable=self.years_var, width=40)
        self.years_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ToolTip(self.years_entry, "Np. 2024,2025 albo 2021-2025 albo 'all'")
        ttk.Button(years_row, text="Wszystkie", command=self._select_all_years).pack(side=tk.LEFT, padx=4)

        # Category
        cat_row = ttk.Frame(filters_frame)
        cat_row.pack(fill=tk.X, pady=2)
        ttk.Label(cat_row, text="Kategoria:", width=18).pack(side=tk.LEFT)
        self.category_var = tk.StringVar()
        self.category_combo = ttk.Combobox(cat_row, textvariable=self.category_var, width=20)
        self.category_combo.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.category_combo.bind("<<ComboboxSelected>>", self._on_category_change)

        # Classes
        class_row = ttk.Frame(filters_frame)
        class_row.pack(fill=tk.X, pady=2)
        ttk.Label(class_row, text="Klasy:", width=18).pack(side=tk.LEFT)
        self.classes_var = tk.StringVar()
        self.classes_entry = ttk.Entry(class_row, textvariable=self.classes_var, width=40)
        self.classes_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ToolTip(self.classes_entry, "Np. B,A,S albo 'all' (puste = wszystkie)")

        # Buttons
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill=tk.X, padx=10, pady=10)
        self.make_button(
            btn_frame, "Odśwież dane", self._refresh_discovery,
            tooltip="Wykryj dostępne lata, kategorie i klasy",
        )
        self.make_button(
            btn_frame, "Oblicz ranking", self._calculate_ranking,
            tooltip="Wygeneruj ranking ELO dla wybranych filtrów",
        )
        self.make_button(
            btn_frame, "Zapisz raport", self._save_report,
            tooltip="Zapisz raport rankingu do pliku .txt",
        )
        self.status_label = self.make_status_label(btn_frame)

        # Results
        result_frame = ttk.LabelFrame(self, text="Wynik", padding=10)
        result_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        self.result_text = tk.Text(result_frame, wrap=tk.WORD, font=("consolas", 10))
        scrollbar = ttk.Scrollbar(result_frame, command=self.result_text.yview)
        self.result_text.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.result_text.pack(fill=tk.BOTH, expand=True)

        # State
        self.last_result = None
        self._update_backend_ui()
        self._refresh_discovery()

    def _pick_file(self, entry: ttk.Entry, filetypes: list[tuple[str, str]]) -> None:
        path = filedialog.askopenfilename(filetypes=filetypes)
        if path:
            entry.delete(0, tk.END)
            entry.insert(0, path)

    def _update_backend_ui(self) -> None:
        backend = self.backend_var.get()
        if backend == "xlsx":
            self.source_frame.pack(fill=tk.X, padx=10, pady=2, after=self.children.get("!labelframe"))
            self.db_frame.pack_forget()
        else:
            self.source_frame.pack_forget()
            self.db_frame.pack(fill=tk.X, padx=10, pady=2, after=self.children.get("!labelframe"))

    def _on_backend_change(self) -> None:
        self._update_backend_ui()
        self._refresh_discovery()

    def _select_all_years(self) -> None:
        self.years_var.set("all")

    def _refresh_discovery(self) -> None:
        backend = self.backend_var.get()
        try:
            if backend == "xlsx":
                xlsx_path = Path(self.xlsx_entry.get())
                if not xlsx_path.is_file():
                    self.show_error(f"Nie znaleziono pliku: {xlsx_path}")
                    return
                df = load_xlsx_data(xlsx_path)
                self.available_years = list_available_years_xlsx(df)
                self.available_categories = []
                self.available_classes = []
            else:
                if not SQLITE_AVAILABLE:
                    self.show_error("Backend SQLite niedostępny.")
                    return
                db_path = Path(self.db_entry.get())
                if not db_path.is_file():
                    self.show_error(f"Nie znaleziono bazy: {db_path}")
                    return
                ensure_schema(db_path)
                self.available_years = get_available_years(db_path)
                self.available_categories = get_available_categories_sqlite(db_path)
                self.available_classes = []

            self.status_label.config(
                text=f"Dostępne lata: {', '.join(map(str, self.available_years))}"
            )
            if self.available_years:
                self.years_var.set(str(self.available_years[0]))
            else:
                self.years_var.set("all")

            if backend == "sqlite" and self.available_categories:
                self.category_combo["values"] = self.available_categories
                self.category_combo.current(0)

        except Exception as exc:  # noqa: BLE001
            self.show_error(str(exc))

    def _parse_years(self) -> list[int]:
        text = self.years_var.get().strip().lower()
        if text in {"", "all", "wszystkie", "*"}:
            return list(self.available_years)
        years: list[int] = []
        for chunk in text.replace(";", ",").split(","):
            part = chunk.strip()
            if not part:
                continue
            if "-" in part:
                start, end = part.split("-", 1)
                years.extend(range(int(start), int(end) + 1))
            else:
                years.append(int(part))
        return sorted(set(years))

    def _on_category_change(self, _event=None) -> None:
        backend = self.backend_var.get()
        category = self.category_var.get().strip().upper()
        if not category or not self.available_years:
            return
        try:
            if backend == "xlsx":
                df = load_xlsx_data(Path(self.xlsx_entry.get()))
                years = self._parse_years()
                self.available_classes = list_available_classes_for_category_and_years_xlsx(
                    df, category, years
                )
            else:
                if not SQLITE_AVAILABLE:
                    self.show_error("Backend SQLite niedostępny.")
                    return
                db_path = Path(self.db_entry.get())
                ensure_schema(db_path)
                years = self._parse_years()
                self.available_classes = get_available_classes(db_path, category, years)
            self.classes_var.set("")
        except Exception as exc:  # noqa: BLE001
            self.show_error(str(exc))

    def _get_xlsx_categories(self) -> list[str]:
        df = load_xlsx_data(Path(self.xlsx_entry.get()))
        years = self._parse_years()
        return list_available_categories_for_years_xlsx(df, years)

    def _calculate_ranking(self) -> None:
        backend = self.backend_var.get()
        years = self._parse_years()
        category = self.category_var.get().strip().upper() or None
        classes_text = self.classes_var.get().strip().lower()
        classes = None
        if classes_text and classes_text not in {"all", "wszystkie", "*"}:
            classes = [c.strip().upper() for c in classes_text.replace(";", ",").split(",") if c.strip()]

        try:
            if backend == "xlsx":
                if not category:
                    self.show_error("Wybierz kategorię dla backendu XLSX.")
                    return
                result = build_new_ranking(
                    file_path=Path(self.xlsx_entry.get()),
                    years=years,
                    category=category,
                    classes=classes,
                )
                report = format_new_ranking_report(result)
                self.last_result = result
            else:
                if not SQLITE_AVAILABLE:
                    self.show_error("Backend SQLite niedostępny.")
                    return
                if not category:
                    self.show_error("Wybierz kategorię dla backendu SQLite.")
                    return
                db_path = Path(self.db_entry.get())
                ensure_schema(db_path)
                result = build_new_ranking(
                    file_path=None,
                    backend="sqlite",
                    db_path=db_path,
                    years=years,
                    category=category,
                    classes=classes,
                    config_path=self.project_dir / "config.txt",
                )
                report = format_new_ranking_report(result)
                self.last_result = result

            self.result_text.delete("1.0", tk.END)
            self.result_text.insert("1.0", report)
            self.status_label.config(text="Ranking obliczony.")
        except Exception as exc:  # noqa: BLE001
            self.show_error(str(exc))

    def _save_report(self) -> None:
        if self.last_result is None:
            self.show_error("Najpierw oblicz ranking.")
            return
        try:
            default_name = build_default_new_output_filename(self.last_result)
            path = filedialog.asksaveasfilename(
                defaultextension=".txt",
                initialfile=default_name,
                filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
            )
            if not path:
                return
            save_new_ranking_report(
                format_new_ranking_report(self.last_result), Path(path)
            )
            self.show_info(f"Zapisano: {path}")
        except Exception as exc:  # noqa: BLE001
            self.show_error(str(exc))


class ImportSQLTab(BaseTab):
    """Zakładka 2: Import danych XLSX do bazy SQLite."""

    def __init__(self, parent: tk.Widget, project_dir: Path) -> None:
        super().__init__(parent, project_dir)
        self._build_widgets()

    def _build_widgets(self) -> None:
        if not SQLITE_AVAILABLE:
            ttk.Label(self, text="Backend SQLite niedostępny.").pack(padx=20, pady=20)
            return

        # XLSX source
        src_frame = ttk.LabelFrame(self, text="Źródło danych (XLSX)", padding=10)
        src_frame.pack(fill=tk.X, padx=10, pady=5)

        self.xlsx_entry = self.make_labeled_entry(
            src_frame,
            "Plik XLSX:",
            str(self.project_dir / "_Oficjalne dane.xlsx"),
            tooltip="Plik z oficjalnymi danymi TTP (np. _Oficjalne dane.xlsx)",
        )[1]
        ttk.Button(
            src_frame,
            text="Przeglądaj...",
            command=lambda: self._pick_file(
                self.xlsx_entry,
                [("Excel files", "*.xlsx"), ("All files", "*.*")],
            ),
        ).pack(side=tk.LEFT, padx=4)

        # Sheet name (optional)
        self.sheet_entry = self.make_labeled_entry(
            src_frame,
            "Arkusz:",
            "",
            tooltip="Opcjonalnie: nazwa arkusza (puste = aktywny)",
        )[1]

        # SQLite target
        db_frame = ttk.LabelFrame(self, text="Docelowa baza SQLite", padding=10)
        db_frame.pack(fill=tk.X, padx=10, pady=5)

        self.db_entry = self.make_labeled_entry(
            db_frame,
            "Baza SQLite:",
            str(self.project_dir / "ttp_official.sqlite"),
            tooltip="Docelowa baza SQLite (zostanie utworzona/migrowana)",
        )[1]
        ttk.Button(
            db_frame,
            text="Przeglądaj...",
            command=lambda: self._pick_file(
                self.db_entry,
                [("SQLite files", "*.sqlite"), ("All files", "*.*")],
            ),
        ).pack(side=tk.LEFT, padx=4)

        # Options
        opt_frame = ttk.LabelFrame(self, text="Opcje", padding=10)
        opt_frame.pack(fill=tk.X, padx=10, pady=5)

        self.replace_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            opt_frame,
            text="Usuń istniejącą bazę przed importem (replace)",
            variable=self.replace_var,
        ).pack(side=tk.LEFT, padx=4)

        # Buttons
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill=tk.X, padx=10, pady=10)
        self.make_button(
            btn_frame, "Importuj", self._run_import,
            tooltip="Rozpocznij import danych do bazy",
        )
        self.status_label = self.make_status_label(btn_frame)

        # Progress
        prog_frame = ttk.LabelFrame(self, text="Postęp", padding=10)
        prog_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        self.progress_text = tk.Text(prog_frame, wrap=tk.WORD, font=("consolas", 9), height=10)
        scrollbar = ttk.Scrollbar(prog_frame, command=self.progress_text.yview)
        self.progress_text.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.progress_text.pack(fill=tk.BOTH, expand=True)

    def _pick_file(self, entry: ttk.Entry, filetypes: list[tuple[str, str]]) -> None:
        path = filedialog.askopenfilename(filetypes=filetypes)
        if path:
            entry.delete(0, tk.END)
            entry.insert(0, path)

    def _run_import(self) -> None:
        xlsx_path = Path(self.xlsx_entry.get())
        db_path = Path(self.db_entry.get())
        sheet = self.sheet_entry.get().strip() or None
        replace = self.replace_var.get()

        if not xlsx_path.is_file():
            self.show_error(f"Nie znaleziono pliku XLSX: {xlsx_path}")
            return

        self.status_label.config(text="Importowanie...")
        self.progress_text.delete("1.0", tk.END)

        def import_task() -> None:
            import_xlsx_to_sqlite(
                xlsx_path,
                db_path,
                sheet_name=sheet,
                replace=replace,
            )

        def on_done(_result) -> None:
            self.progress_text.insert(
                tk.END, f"Import zakończony: {db_path}\n"
            )
            self.status_label.config(text="Import zakończony.")

        self.run_in_thread(import_task, on_done)


class ExportCSVTab(BaseTab):
    """Zakładka 3: Eksport historii zmian punktów do CSV."""

    def __init__(self, parent: tk.Widget, project_dir: Path) -> None:
        super().__init__(parent, project_dir)
        self.available_years: list[int] = []
        self.available_categories: list[str] = []
        self.available_classes: list[str] = []
        if not EXPORT_AVAILABLE:
            ttk.Label(self, text="Moduł eksportu CSV niedostępny.").pack(padx=20, pady=20)
            return
        self._build_widgets()

    def _build_widgets(self) -> None:
        # Backend selection
        backend_frame = ttk.LabelFrame(self, text="Backend danych", padding=10)
        backend_frame.pack(fill=tk.X, padx=10, pady=5)

        self.backend_var = tk.StringVar(value="xlsx")
        ttk.Radiobutton(
            backend_frame,
            text="XLSX (data_new.xlsx)",
            variable=self.backend_var,
            value="xlsx",
            command=self._on_backend_change,
        ).pack(side=tk.LEFT, padx=10)
        if SQLITE_AVAILABLE:
            ttk.Radiobutton(
                backend_frame,
                text="SQLite (baza danych)",
                variable=self.backend_var,
                value="sqlite",
                command=self._on_backend_change,
            ).pack(side=tk.LEFT, padx=10)

        # XLSX path
        self.source_frame = ttk.Frame(self)
        self.source_frame.pack(fill=tk.X, padx=10, pady=2)
        self.xlsx_entry = self.make_labeled_entry(
            self.source_frame,
            "Plik XLSX:",
            str(self.project_dir / "data_new.xlsx"),
        )[1]
        ttk.Button(
            self.source_frame,
            text="Przeglądaj...",
            command=lambda: self._pick_file(
                self.xlsx_entry,
                [("Excel files", "*.xlsx"), ("All files", "*.*")],
            ),
        ).pack(side=tk.LEFT, padx=4)

        # SQLite path
        self.db_frame = ttk.Frame(self)
        self.db_frame.pack(fill=tk.X, padx=10, pady=2)
        self.db_entry = self.make_labeled_entry(
            self.db_frame,
            "Baza SQLite:",
            str(self.project_dir / "ttp_official.sqlite"),
        )[1]
        ttk.Button(
            self.db_frame,
            text="Przeglądaj...",
            command=lambda: self._pick_file(
                self.db_entry,
                [("SQLite files", "*.sqlite"), ("All files", "*.*")],
            ),
        ).pack(side=tk.LEFT, padx=4)

        # Filters
        filters_frame = ttk.LabelFrame(self, text="Filtry", padding=10)
        filters_frame.pack(fill=tk.X, padx=10, pady=5)

        # Years
        years_row = ttk.Frame(filters_frame)
        years_row.pack(fill=tk.X, pady=2)
        ttk.Label(years_row, text="Lata:", width=18).pack(side=tk.LEFT)
        self.years_var = tk.StringVar()
        self.years_entry = ttk.Entry(years_row, textvariable=self.years_var, width=40)
        self.years_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ToolTip(self.years_entry, "Np. 2024,2025 albo 2021-2025 albo 'all'")

        # Category
        cat_row = ttk.Frame(filters_frame)
        cat_row.pack(fill=tk.X, pady=2)
        ttk.Label(cat_row, text="Kategoria:", width=18).pack(side=tk.LEFT)
        self.category_var = tk.StringVar()
        self.category_combo = ttk.Combobox(cat_row, textvariable=self.category_var, width=20)
        self.category_combo.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.category_combo.bind("<<ComboboxSelected>>", self._on_category_change)

        # Classes
        class_row = ttk.Frame(filters_frame)
        class_row.pack(fill=tk.X, pady=2)
        ttk.Label(class_row, text="Klasy:", width=18).pack(side=tk.LEFT)
        self.classes_var = tk.StringVar()
        self.classes_entry = ttk.Entry(class_row, textvariable=self.classes_var, width=40)
        self.classes_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ToolTip(self.classes_entry, "Np. B,A,S albo 'all' (puste = wszystkie)")

        # Output
        out_frame = ttk.LabelFrame(self, text="Wyjście", padding=10)
        out_frame.pack(fill=tk.X, padx=10, pady=5)

        self.output_entry = self.make_labeled_entry(
            out_frame,
            "Plik CSV:",
            str(self.project_dir / "csv" / "progress.csv"),
            tooltip="Ścieżka pliku wyjściowego CSV",
        )[1]
        ttk.Button(
            out_frame,
            text="Przeglądaj...",
            command=lambda: self._pick_output(),
        ).pack(side=tk.LEFT, padx=4)

        # Delimiter
        del_row = ttk.Frame(out_frame)
        del_row.pack(fill=tk.X, pady=2)
        ttk.Label(del_row, text="Separator:", width=18).pack(side=tk.LEFT)
        self.delimiter_var = tk.StringVar(value=";")
        ttk.Combobox(
            del_row,
            textvariable=self.delimiter_var,
            values=[";", ",", "\t"],
            width=10,
        ).pack(side=tk.LEFT)

        # Buttons
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill=tk.X, padx=10, pady=10)
        self.make_button(btn_frame, "Odśwież", self._refresh_discovery)
        self.make_button(btn_frame, "Eksportuj CSV", self._export_csv)
        self.status_label = self.make_status_label(btn_frame)

        # Preview
        preview_frame = ttk.LabelFrame(self, text="Podgląd", padding=10)
        preview_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        self.preview_text = tk.Text(preview_frame, wrap=tk.WORD, font=("consolas", 9))
        scrollbar = ttk.Scrollbar(preview_frame, command=self.preview_text.yview)
        self.preview_text.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.preview_text.pack(fill=tk.BOTH, expand=True)

        self._update_backend_ui()
        self._refresh_discovery()

    def _pick_file(self, entry: ttk.Entry, filetypes: list[tuple[str, str]]) -> None:
        path = filedialog.askopenfilename(filetypes=filetypes)
        if path:
            entry.delete(0, tk.END)
            entry.insert(0, path)

    def _pick_output(self) -> None:
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            initialfile="progress.csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if path:
            self.output_entry.delete(0, tk.END)
            self.output_entry.insert(0, path)

    def _update_backend_ui(self) -> None:
        backend = self.backend_var.get()
        if backend == "xlsx":
            self.source_frame.pack(fill=tk.X, padx=10, pady=2, after=self.children.get("!labelframe"))
            self.db_frame.pack_forget()
        else:
            self.source_frame.pack_forget()
            self.db_frame.pack(fill=tk.X, padx=10, pady=2, after=self.children.get("!labelframe"))

    def _on_backend_change(self) -> None:
        self._update_backend_ui()
        self._refresh_discovery()

    def _refresh_discovery(self) -> None:
        backend = self.backend_var.get()
        try:
            if backend == "xlsx":
                xlsx_path = Path(self.xlsx_entry.get())
                if not xlsx_path.is_file():
                    self.show_error(f"Nie znaleziono pliku: {xlsx_path}")
                    return
                df = load_xlsx_data(xlsx_path)
                self.available_years = list_available_years_xlsx(df)
                self.available_categories = []
            else:
                if not SQLITE_AVAILABLE:
                    self.show_error("Backend SQLite niedostępny.")
                    return
                db_path = Path(self.db_entry.get())
                if not db_path.is_file():
                    self.show_error(f"Nie znaleziono bazy: {db_path}")
                    return
                ensure_schema(db_path)
                self.available_years = get_available_years(db_path)
                self.available_categories = get_available_categories_sqlite(db_path)

            self.status_label.config(
                text=f"Dostępne lata: {', '.join(map(str, self.available_years))}"
            )
            if self.available_years:
                self.years_var.set(str(self.available_years[0]))
            else:
                self.years_var.set("all")

            if backend == "sqlite":
                self.category_combo["values"] = self.available_categories
                if self.available_categories:
                    self.category_combo.current(0)
        except Exception as exc:  # noqa: BLE001
            self.show_error(str(exc))

    def _parse_years(self) -> list[int]:
        text = self.years_var.get().strip().lower()
        if text in {"", "all", "wszystkie", "*"}:
            return list(self.available_years)
        years: list[int] = []
        for chunk in text.replace(";", ",").split(","):
            part = chunk.strip()
            if not part:
                continue
            if "-" in part:
                start, end = part.split("-", 1)
                years.extend(range(int(start), int(end) + 1))
            else:
                years.append(int(part))
        return sorted(set(years))

    def _on_category_change(self, _event=None) -> None:
        backend = self.backend_var.get()
        if backend != "sqlite" or not SQLITE_AVAILABLE:
            return
        category = self.category_var.get().strip().upper()
        if not category or not self.available_years:
            return
        try:
            db_path = Path(self.db_entry.get())
            years = self._parse_years()
            self.available_classes = get_available_classes(db_path, category, years)
            self.classes_var.set("")
        except Exception as exc:  # noqa: BLE001
            self.show_error(str(exc))

    def _export_csv(self) -> None:
        backend = self.backend_var.get()
        years = self._parse_years()
        category = self.category_var.get().strip().upper() or None
        classes_text = self.classes_var.get().strip().lower()
        classes = None
        if classes_text and classes_text not in {"all", "wszystkie", "*"}:
            classes = [c.strip().upper() for c in classes_text.replace(";", ",").split(",") if c.strip()]

        output_path = Path(self.output_entry.get())
        delimiter = self.delimiter_var.get()

        if not output_path.parent.exists():
            output_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            if backend == "xlsx":
                if not category:
                    self.show_error("Wybierz kategorię dla backendu XLSX.")
                    return
                result = build_new_progress_export(
                    file_path=Path(self.xlsx_entry.get()),
                    years=years,
                    category=category,
                    classes=classes,
                )
                saved_path = save_new_progress_csv(result, output_path, delimiter=delimiter)
                self.status_label.config(text=f"Zapisano: {saved_path}")
                self._preview_csv(saved_path)
            else:
                if not SQLITE_AVAILABLE:
                    self.show_error("Backend SQLite niedostępny.")
                    return
                if not category:
                    self.show_error("Wybierz kategorię dla backendu SQLite.")
                    return
                db_path = Path(self.db_entry.get())
                ensure_schema(db_path)
                config = load_config()
                run = build_ranking_from_sqlite(
                    db_path=db_path,
                    category=category,
                    years=years,
                    classes=classes,
                    config=config,
                )
                write_progress_csv(run, output_path, delimiter=delimiter)
                self.status_label.config(text=f"Zapisano: {output_path}")
                self._preview_csv(output_path)
        except Exception as exc:  # noqa: BLE001
            self.show_error(str(exc))

    def _preview_csv(self, path: Path) -> None:
        try:
            with path.open(encoding="utf-8") as handle:
                lines = handle.readlines()[:50]
            self.preview_text.delete("1.0", tk.END)
            self.preview_text.insert("1.0", "".join(lines))
        except Exception:  # noqa: BLE001
            pass


class ChartsTab(BaseTab):
    """Zakładka 4: Wykresy ELO par."""

    def __init__(self, parent: tk.Widget, project_dir: Path) -> None:
        super().__init__(parent, project_dir)
        self.available_years: list[int] = []
        self.available_categories: list[str] = []
        self.available_classes: list[str] = []
        self.progress_rows: list[dict[str, str]] = []
        if not PLOT_AVAILABLE:
            ttk.Label(self, text="Moduł wykresów niedostępny.").pack(padx=20, pady=20)
            return
        self._build_widgets()

    def _build_widgets(self) -> None:
        # Backend selection
        backend_frame = ttk.LabelFrame(self, text="Backend danych", padding=10)
        backend_frame.pack(fill=tk.X, padx=10, pady=5)

        self.backend_var = tk.StringVar(value="xlsx")
        ttk.Radiobutton(
            backend_frame,
            text="XLSX (data_new.xlsx)",
            variable=self.backend_var,
            value="xlsx",
            command=self._on_backend_change,
        ).pack(side=tk.LEFT, padx=10)
        if SQLITE_AVAILABLE:
            ttk.Radiobutton(
                backend_frame,
                text="SQLite (baza danych)",
                variable=self.backend_var,
                value="sqlite",
                command=self._on_backend_change,
            ).pack(side=tk.LEFT, padx=10)

        # XLSX path
        self.source_frame = ttk.Frame(self)
        self.source_frame.pack(fill=tk.X, padx=10, pady=2)
        self.xlsx_entry = self.make_labeled_entry(
            self.source_frame,
            "Plik XLSX:",
            str(self.project_dir / "data_new.xlsx"),
        )[1]
        ttk.Button(
            self.source_frame,
            text="Przeglądaj...",
            command=lambda: self._pick_file(
                self.xlsx_entry,
                [("Excel files", "*.xlsx"), ("All files", "*.*")],
            ),
        ).pack(side=tk.LEFT, padx=4)

        # SQLite path
        self.db_frame = ttk.Frame(self)
        self.db_frame.pack(fill=tk.X, padx=10, pady=2)
        self.db_entry = self.make_labeled_entry(
            self.db_frame,
            "Baza SQLite:",
            str(self.project_dir / "ttp_official.sqlite"),
        )[1]
        ttk.Button(
            self.db_frame,
            text="Przeglądaj...",
            command=lambda: self._pick_file(
                self.db_entry,
                [("SQLite files", "*.sqlite"), ("All files", "*.*")],
            ),
        ).pack(side=tk.LEFT, padx=4)

        # Filters
        filters_frame = ttk.LabelFrame(self, text="Filtry", padding=10)
        filters_frame.pack(fill=tk.X, padx=10, pady=5)

        # Years
        years_row = ttk.Frame(filters_frame)
        years_row.pack(fill=tk.X, pady=2)
        ttk.Label(years_row, text="Lata:", width=18).pack(side=tk.LEFT)
        self.years_var = tk.StringVar()
        self.years_entry = ttk.Entry(years_row, textvariable=self.years_var, width=40)
        self.years_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ToolTip(self.years_entry, "Np. 2024,2025 albo 2021-2025 albo 'all'")

        # Category
        cat_row = ttk.Frame(filters_frame)
        cat_row.pack(fill=tk.X, pady=2)
        ttk.Label(cat_row, text="Kategoria:", width=18).pack(side=tk.LEFT)
        self.category_var = tk.StringVar()
        self.category_combo = ttk.Combobox(cat_row, textvariable=self.category_var, width=20)
        self.category_combo.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.category_combo.bind("<<ComboboxSelected>>", self._on_category_change)

        # Classes
        class_row = ttk.Frame(filters_frame)
        class_row.pack(fill=tk.X, pady=2)
        ttk.Label(class_row, text="Klasy:", width=18).pack(side=tk.LEFT)
        self.classes_var = tk.StringVar()
        self.classes_entry = ttk.Entry(class_row, textvariable=self.classes_var, width=40)
        self.classes_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ToolTip(self.classes_entry, "Np. B,A,S albo 'all' (puste = wszystkie)")

        # Buttons
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill=tk.X, padx=10, pady=5)
        self.make_button(btn_frame, "Odśwież dane", self._refresh_discovery)
        self.make_button(btn_frame, "Załaduj pary", self._load_pairs, tooltip="Załaduj listę par dla filtrów")
        self.status_label = self.make_status_label(btn_frame)

        # Pair selection
        pair_frame = ttk.LabelFrame(self, text="Wybór par", padding=10)
        pair_frame.pack(fill=tk.X, padx=10, pady=5)

        pair_list_frame = ttk.Frame(pair_frame)
        pair_list_frame.pack(fill=tk.BOTH, expand=True)

        self.pair_listbox = tk.Listbox(pair_list_frame, selectmode=tk.EXTENDED, height=8)
        pair_scroll = ttk.Scrollbar(pair_list_frame, command=self.pair_listbox.yview)
        self.pair_listbox.configure(yscrollcommand=pair_scroll.set)
        pair_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.pair_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        search_row = ttk.Frame(pair_frame)
        search_row.pack(fill=tk.X, pady=2)
        ttk.Label(search_row, text="Szukaj:", width=10).pack(side=tk.LEFT)
        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(search_row, textvariable=self.search_var, width=30)
        self.search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.search_entry.bind("<KeyRelease>", self._filter_pairs)

        # Plot options
        opt_frame = ttk.LabelFrame(self, text="Opcje wykresu", padding=10)
        opt_frame.pack(fill=tk.X, padx=10, pady=5)

        self.show_plot_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(opt_frame, text="Pokaż wykres", variable=self.show_plot_var).pack(side=tk.LEFT, padx=4)

        self.save_plot_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(opt_frame, text="Zapisz do pliku", variable=self.save_plot_var).pack(side=tk.LEFT, padx=4)

        self.output_entry = self.make_labeled_entry(
            opt_frame,
            "Plik PNG:",
            str(self.project_dir / "img" / "wykres.png"),
            tooltip="Ścieżka zapisu wykresu PNG",
        )[1]
        ttk.Button(
            opt_frame,
            text="Przeglądaj...",
            command=self._pick_output,
        ).pack(side=tk.LEFT, padx=4)

        # Plot button
        plot_btn_frame = ttk.Frame(self)
        plot_btn_frame.pack(fill=tk.X, padx=10, pady=10)
        self.make_button(
            plot_btn_frame, "Rysuj wykres", self._draw_plot,
            tooltip="Narysuj wykres dla wybranych par",
        )

        self._update_backend_ui()
        self._refresh_discovery()

    def _pick_file(self, entry: ttk.Entry, filetypes: list[tuple[str, str]]) -> None:
        path = filedialog.askopenfilename(filetypes=filetypes)
        if path:
            entry.delete(0, tk.END)
            entry.insert(0, path)

    def _pick_output(self) -> None:
        path = filedialog.asksaveasfilename(
            defaultextension=".png",
            initialfile="wykres.png",
            filetypes=[("PNG files", "*.png"), ("All files", "*.*")],
        )
        if path:
            self.output_entry.delete(0, tk.END)
            self.output_entry.insert(0, path)

    def _update_backend_ui(self) -> None:
        backend = self.backend_var.get()
        if backend == "xlsx":
            self.source_frame.pack(fill=tk.X, padx=10, pady=2, after=self.children.get("!labelframe"))
            self.db_frame.pack_forget()
        else:
            self.source_frame.pack_forget()
            self.db_frame.pack(fill=tk.X, padx=10, pady=2, after=self.children.get("!labelframe"))

    def _on_backend_change(self) -> None:
        self._update_backend_ui()
        self._refresh_discovery()

    def _refresh_discovery(self) -> None:
        backend = self.backend_var.get()
        try:
            if backend == "xlsx":
                xlsx_path = Path(self.xlsx_entry.get())
                if not xlsx_path.is_file():
                    self.show_error(f"Nie znaleziono pliku: {xlsx_path}")
                    return
                df = load_xlsx_data(xlsx_path)
                self.available_years = list_available_years_xlsx(df)
                self.available_categories = []
            else:
                if not SQLITE_AVAILABLE:
                    self.show_error("Backend SQLite niedostępny.")
                    return
                db_path = Path(self.db_entry.get())
                if not db_path.is_file():
                    self.show_error(f"Nie znaleziono bazy: {db_path}")
                    return
                ensure_schema(db_path)
                self.available_years = get_available_years(db_path)
                self.available_categories = get_available_categories_sqlite(db_path)

            self.status_label.config(
                text=f"Dostępne lata: {', '.join(map(str, self.available_years))}"
            )
            if self.available_years:
                self.years_var.set(str(self.available_years[0]))
            else:
                self.years_var.set("all")

            if backend == "sqlite":
                self.category_combo["values"] = self.available_categories
                if self.available_categories:
                    self.category_combo.current(0)
        except Exception as exc:  # noqa: BLE001
            self.show_error(str(exc))

    def _parse_years(self) -> list[int]:
        text = self.years_var.get().strip().lower()
        if text in {"", "all", "wszystkie", "*"}:
            return list(self.available_years)
        years: list[int] = []
        for chunk in text.replace(";", ",").split(","):
            part = chunk.strip()
            if not part:
                continue
            if "-" in part:
                start, end = part.split("-", 1)
                years.extend(range(int(start), int(end) + 1))
            else:
                years.append(int(part))
        return sorted(set(years))

    def _on_category_change(self, _event=None) -> None:
        backend = self.backend_var.get()
        if backend != "sqlite" or not SQLITE_AVAILABLE:
            return
        category = self.category_var.get().strip().upper()
        if not category or not self.available_years:
            return
        try:
            db_path = Path(self.db_entry.get())
            years = self._parse_years()
            self.available_classes = get_available_classes(db_path, category, years)
            self.classes_var.set("")
        except Exception as exc:  # noqa: BLE001
            self.show_error(str(exc))

    def _load_pairs(self) -> None:
        backend = self.backend_var.get()
        years = self._parse_years()
        category = self.category_var.get().strip().upper() or None
        classes_text = self.classes_var.get().strip().lower()
        classes = None
        if classes_text and classes_text not in {"all", "wszystkie", "*"}:
            classes = [c.strip().upper() for c in classes_text.replace(";", ",").split(",") if c.strip()]

        try:
            if backend == "xlsx":
                if not category:
                    self.show_error("Wybierz kategorię dla backendu XLSX.")
                    return
                rows = build_progress_rows(
                    Path(self.xlsx_entry.get()),
                    years,
                    category,
                    classes,
                )
            else:
                if not SQLITE_AVAILABLE:
                    self.show_error("Backend SQLite niedostępny.")
                    return
                if not category:
                    self.show_error("Wybierz kategorię dla backendu SQLite.")
                    return
                db_path = Path(self.db_entry.get())
                ensure_schema(db_path)
                config = load_config()
                run = build_ranking_from_sqlite(
                    db_path=db_path,
                    category=category,
                    years=years,
                    classes=classes,
                    config=config,
                )
                rows = []
                for row in run.progress_rows:
                    dancer_1, dancer_2 = row["pair"].split(",")[:2] if "," in row["pair"] else ("", "")
                    rows.append({
                        "rok": str(row["season"]),
                        "kolejnosc_turnieju": str(row["event_id"]),
                        "kod_turnieju": row["tournament_code"],
                        "turniej": row["tournament_name"],
                        "kategoria_bazowa": row["base_category"],
                        "podkategoria": row["cat_code"],
                        "klasa": row["class_code"] or "",
                        "lokata": str(row["rank"]),
                        "pair_id": str(row["pair_id"]),
                        "para": row["pair"],
                        "tancerz_1": dancer_1.strip(),
                        "tancerz_2": dancer_2.strip(),
                        "punkty_przed": f"{row['punkty_przed']:.2f}",
                        "punkty_po": f"{row['punkty_po']:.2f}",
                        "roznica_punktow": f"{row['roznica_punktow']:.2f}",
                        "_row_order": str(len(rows) + 1),
                    })

            self.progress_rows = rows
            self._populate_pair_list(rows)
            self.status_label.config(text=f"Załadowano {len(rows)} wierszy historii.")
        except Exception as exc:  # noqa: BLE001
            self.show_error(str(exc))

    def _populate_pair_list(self, rows: list[dict[str, str]]) -> None:
        pairs = unique_pairs(rows)
        self.pair_catalog = pairs
        self.pair_listbox.delete(0, tk.END)
        for pair in pairs:
            self.pair_listbox.insert(
                tk.END,
                f"{pair['para']} | występy: {pair['wystepy']}"
            )

    def _filter_pairs(self, _event=None) -> None:
        if not hasattr(self, "pair_catalog"):
            return
        search_text = self.search_var.get().strip()
        filtered = filter_pair_catalog(self.pair_catalog, search_text)
        self.pair_listbox.delete(0, tk.END)
        for pair in filtered:
            self.pair_listbox.insert(
                tk.END,
                f"{pair['para']} | występy: {pair['wystepy']}"
            )

    def _draw_plot(self) -> None:
        if not self.progress_rows:
            self.show_error("Najpierw załaduj pary.")
            return

        selected_indices = self.pair_listbox.curselection()
        if not selected_indices:
            self.show_error("Wybierz przynajmniej jedną parę z listy.")
            return

        selected_pairs = []
        for idx in selected_indices:
            item_text = self.pair_listbox.get(idx)
            pair_name = item_text.split(" | ")[0]
            selected_pairs.append(pair_name)

        save_plot = self.save_plot_var.get()
        output_path = None
        if save_plot:
            output_path = Path(self.output_entry.get())
            if not output_path.parent.exists():
                output_path.parent.mkdir(parents=True, exist_ok=True)

        backend = self.backend_var.get()
        source_path = (
            Path(self.xlsx_entry.get()) if backend == "xlsx"
            else Path(self.db_entry.get())
        )

        def plot_task() -> None:
            pair_series = resolve_pair_series(
                rows=self.progress_rows,
                pair_names=selected_pairs,
                pair_ids=[],
                dancer_1=None,
                dancer_2=None,
            )
            # Create the figure data
            from new_pair_progress_plot import (
                build_tournament_axis,
                format_tournament_label,
                tournament_key,
                load_class_thresholds,
                parse_number,
                sorted_pair_rows,
            )
            from pathlib import Path

            x_by_key, labels = build_tournament_axis(pair_series)

            sns.set_theme(style="whitegrid", context="notebook")
            width = min(max(10.0, len(labels) * 1.05), 28.0)
            fig, ax = plt.subplots(figsize=(width, 6.5))

            all_y: list[float] = []
            for _, ordered_rows in pair_series:
                all_y.extend([parse_number(row["punkty_po"]) for row in ordered_rows])

            if all_y:
                thresholds = load_class_thresholds(self.project_dir / "config.txt")
                threshold_values = [value for _, value in thresholds]
                visible_values = all_y + threshold_values
                min_value = min(visible_values)
                max_value = max(visible_values)
                margin = max(35.0, (max_value - min_value) * 0.06)
                ax.set_ylim(min_value - margin, max_value + margin)

                for class_name, value in thresholds:
                    ax.axhline(
                        y=value,
                        color="#9aa4ad",
                        linestyle="--",
                        linewidth=1.1,
                        alpha=0.75,
                        zorder=1,
                    )
                    ax.text(
                        x=0.01,
                        y=value,
                        s=f"Klasa {class_name}: {value:.0f}",
                        color="#4b5563",
                        fontsize=8.5,
                        fontweight="semibold",
                        va="bottom",
                        ha="left",
                        transform=ax.get_yaxis_transform(),
                        zorder=2,
                    )

            palette = sns.color_palette(
                "tab10" if len(pair_series) <= 10 else "husl",
                n_colors=len(pair_series),
            )

            for series_index, (pair_name, ordered_rows) in enumerate(pair_series):
                x_values = [x_by_key[tournament_key(row)] for row in ordered_rows]
                y_values = [parse_number(row["punkty_po"]) for row in ordered_rows]

                sns.lineplot(
                    x=x_values,
                    y=y_values,
                    marker="o",
                    linewidth=2.4,
                    markersize=7,
                    label=pair_name,
                    color=palette[series_index],
                    ax=ax,
                )

                if len(pair_series) == 1:
                    for x_value, y_value, row in zip(x_values, y_values, ordered_rows):
                        ax.annotate(
                            f"{y_value:.0f}",
                            (x_value, y_value),
                            textcoords="offset points",
                            xytext=(0, 8),
                            ha="center",
                            fontsize=8,
                        )
                        ax.annotate(
                            f"#{row['lokata']}",
                            (x_value, y_value),
                            textcoords="offset points",
                            xytext=(0, -14),
                            ha="center",
                            fontsize=8,
                            color="dimgray",
                        )
                else:
                    last_x = x_values[-1]
                    last_y = y_values[-1]
                    ax.annotate(
                        f"{last_y:.0f}",
                        (last_x, last_y),
                        textcoords="offset points",
                        xytext=(7, 0),
                        ha="left",
                        va="center",
                        fontsize=8,
                        color=palette[series_index],
                    )

            if len(pair_series) == 1:
                chart_title = f"Historia rankingu ELO: {pair_series[0][0]}"
            else:
                chart_title = "Historia rankingu ELO wybranych par"

            ax.set_title(chart_title, pad=18)
            ax.set_xlabel("Turnieje chronologicznie")
            ax.set_ylabel("Ranking ELO")
            ax.set_xticks(list(range(1, len(labels) + 1)))
            ax.set_xticklabels(labels, rotation=45, ha="right")
            ax.margins(x=0.03)

            if len(pair_series) > 1:
                ax.legend(title="Pary", loc="upper left", bbox_to_anchor=(1.01, 1))
            else:
                legend = ax.get_legend()
                if legend:
                    legend.remove()

            fig.text(
                0.01,
                0.01,
                f"Źródło: {source_path.name} | punkty po występie",
                fontsize=8,
                color="dimgray",
            )
            right_margin = 0.78 if len(pair_series) > 1 else 1
            fig.tight_layout(rect=(0, 0.03, right_margin, 1))

            # Save if requested
            if output_path:
                output_path.parent.mkdir(parents=True, exist_ok=True)
                fig.savefig(output_path, dpi=160, bbox_inches="tight")

            return fig

        def on_done(fig) -> None:
            self._show_chart_window(fig, selected_pairs)
            self.status_label.config(text="Wykres wygenerowany.")

        self.run_in_thread(plot_task, on_done)

    def _show_chart_window(self, fig, pair_names: list[str]) -> None:
        """Display the matplotlib figure in a new tkinter window."""
        chart_window = tk.Toplevel(self)
        chart_window.title(f"Wykres ELO: {', '.join(pair_names[:2])}{'...' if len(pair_names) > 2 else ''}")
        chart_window.geometry("1000x700")

        canvas = FigureCanvasTkAgg(fig, master=chart_window)
        canvas.draw()
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        # Add toolbar
        toolbar = NavigationToolbar2Tk(canvas, chart_window)
        toolbar.update()
        toolbar.pack(side=tk.BOTTOM, fill=tk.X)

        # Handle window close
        def on_close():
            plt.close(fig)
            chart_window.destroy()

        chart_window.protocol("WM_DELETE_WINDOW", on_close)


class MigrationsTab(BaseTab):
    """Zakładka 5: Zarządzanie migracjami bazy SQLite."""

    def __init__(self, parent: tk.Widget, project_dir: Path) -> None:
        super().__init__(parent, project_dir)
        if not SQLITE_AVAILABLE:
            ttk.Label(self, text="Backend SQLite niedostępny.").pack(padx=20, pady=20)
            return
        self._build_widgets()

    def _build_widgets(self) -> None:
        # Database selection
        db_frame = ttk.LabelFrame(self, text="Baza danych", padding=10)
        db_frame.pack(fill=tk.X, padx=10, pady=5)

        self.db_entry = self.make_labeled_entry(
            db_frame,
            "Baza SQLite:",
            str(self.project_dir / "ttp_official.sqlite"),
            tooltip="Baza do zarządzania migracjami",
        )[1]
        ttk.Button(
            db_frame,
            text="Przeglądaj...",
            command=lambda: self._pick_file(),
        ).pack(side=tk.LEFT, padx=4)

        # Target version
        target_frame = ttk.Frame(self)
        target_frame.pack(fill=tk.X, padx=10, pady=2)
        ttk.Label(target_frame, text="Wersja docelowa:", width=18).pack(side=tk.LEFT)
        self.target_var = tk.StringVar(value="najnowsza")
        ttk.Combobox(
            target_frame,
            textvariable=self.target_var,
            values=["najnowsza", "1", "2"],
            width=15,
        ).pack(side=tk.LEFT)
        ttk.Label(target_frame, text=f"(obecna najnowsza: v{CURRENT_SCHEMA_VERSION})").pack(side=tk.LEFT, padx=4)

        # Buttons
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill=tk.X, padx=10, pady=10)
        self.make_button(btn_frame, "Sprawdź status", self._check_status)
        self.make_button(btn_frame, "Uruchom migracje", self._run_migrations)
        self.status_label = self.make_status_label(btn_frame)

        # Output
        out_frame = ttk.LabelFrame(self, text="Status migracji", padding=10)
        out_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        self.status_text = tk.Text(out_frame, wrap=tk.WORD, font=("consolas", 10))
        scrollbar = ttk.Scrollbar(out_frame, command=self.status_text.yview)
        self.status_text.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.status_text.pack(fill=tk.BOTH, expand=True)

        self._check_status()

    def _pick_file(self) -> None:
        path = filedialog.askopenfilename(
            filetypes=[("SQLite files", "*.sqlite"), ("All files", "*.*")]
        )
        if path:
            self.db_entry.delete(0, tk.END)
            self.db_entry.insert(0, path)

    def _check_status(self) -> None:
        db_path = Path(self.db_entry.get())
        if not db_path.is_file():
            self.status_text.delete("1.0", tk.END)
            self.status_text.insert("1.0", f"Baza nie istnieje: {db_path}\nZostanie utworzona przy migracji.")
            return

        try:
            current = get_current_version(db_path)
            applied = get_applied_migrations(db_path)

            lines = [f"Obecna wersja: v{current}"]
            lines.append(f"Najnowsza wersja: v{CURRENT_SCHEMA_VERSION}")
            lines.append("")
            lines.append("Zastosowane migracje:")
            if applied:
                for version, name, applied_at in applied:
                    lines.append(f"  v{version}: {name} ({applied_at})")
            else:
                lines.append("  (brak)")

            if current < CURRENT_SCHEMA_VERSION:
                pending = CURRENT_SCHEMA_VERSION - current
                lines.append("")
                lines.append(f"Oczekujące migracje: {pending}")

            self.status_text.delete("1.0", tk.END)
            self.status_text.insert("1.0", "\n".join(lines))
            self.status_label.config(text=f"Status: v{current}")
        except Exception as exc:  # noqa: BLE001
            self.show_error(str(exc))

    def _run_migrations(self) -> None:
        db_path = Path(self.db_entry.get())
        target_text = self.target_var.get().strip().lower()
        target_version = None
        if target_text and target_text != "najnowsza":
            target_version = int(target_text)

        self.status_label.config(text="Uruchamianie migracji...")

        def migrate_task() -> None:
            if not db_path.is_file():
                ensure_schema(db_path, target_version)
            else:
                run_migrations(db_path, target_version)

        def on_done(_result) -> None:
            self._check_status()
            self.status_label.config(text="Migracje zakończone.")

        self.run_in_thread(migrate_task, on_done)


class TournamentDateTab(BaseTab):
    """Zakładka 6: Edycja dat turniejów w bazie SQLite."""

    def __init__(self, parent: tk.Widget, project_dir: Path) -> None:
        super().__init__(parent, project_dir)
        if not SQLITE_AVAILABLE:
            ttk.Label(self, text="Backend SQLite niedostępny.").pack(padx=20, pady=20)
            return
        self._build_widgets()

    def _build_widgets(self) -> None:
        # Database selection
        db_frame = ttk.LabelFrame(self, text="Baza danych", padding=10)
        db_frame.pack(fill=tk.X, padx=10, pady=5)

        self.db_entry = self.make_labeled_entry(
            db_frame,
            "Baza SQLite:",
            str(self.project_dir / "ttp_official.sqlite"),
            tooltip="Baza do edycji dat turniejów",
        )[1]
        ttk.Button(
            db_frame,
            text="Przeglądaj...",
            command=lambda: self._pick_file(),
        ).pack(side=tk.LEFT, padx=4)

        # Filters
        filters_frame = ttk.LabelFrame(self, text="Filtry", padding=10)
        filters_frame.pack(fill=tk.X, padx=10, pady=5)

        # Year filter
        year_row = ttk.Frame(filters_frame)
        year_row.pack(fill=tk.X, pady=2)
        ttk.Label(year_row, text="Rok:", width=18).pack(side=tk.LEFT)
        self.year_var = tk.StringVar(value="")
        self.year_combo = ttk.Combobox(year_row, textvariable=self.year_var, width=20)
        self.year_combo.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.year_combo.bind("<<ComboboxSelected>>", self._on_year_change)

        # Buttons
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill=tk.X, padx=10, pady=10)
        self.make_button(
            btn_frame, "Odśwież", self._refresh_tournaments,
            tooltip="Załaduj turnieje z bazy",
        )
        self.make_button(
            btn_frame, "Zapisz zmiany", self._save_changes,
            tooltip="Zapisz wszystkie zmiany dat",
        )
        self.status_label = self.make_status_label(btn_frame)

        # Tournament list with dates
        list_frame = ttk.LabelFrame(self, text="Turnieje (edytuj daty)", padding=10)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # Scrollable frame for tournament rows
        canvas = tk.Canvas(list_frame)
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.canvas = canvas
        self.scrollable_frame = scrollable_frame
        self.tournament_entries: list[tuple[int, tk.StringVar]] = []

        # Initial refresh
        self._refresh_tournaments()

    def _pick_file(self) -> None:
        path = filedialog.askopenfilename(
            filetypes=[("SQLite files", "*.sqlite"), ("All files", "*.*")]
        )
        if path:
            self.db_entry.delete(0, tk.END)
            self.db_entry.insert(0, path)
            self._refresh_tournaments()

    def _refresh_tournaments(self) -> None:
        """Load tournaments from DB and display in editable list."""
        db_path = Path(self.db_entry.get())
        if not db_path.is_file():
            self.show_error(f"Nie znaleziono bazy: {db_path}")
            return

        try:
            ensure_schema(db_path)

            # Clear existing entries
            for widget in self.scrollable_frame.winfo_children():
                widget.destroy()
            self.tournament_entries.clear()

            # Get tournaments ordered by date (nulls last)
            import sqlite3
            with sqlite3.connect(str(db_path)) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute("""
                    SELECT tournament_id, season, tournament_code, tournament_name, event_date
                    FROM tournaments
                    ORDER BY
                        CASE WHEN event_date IS NOT NULL THEN 0 ELSE 1 END,
                        event_date ASC,
                        season ASC,
                        tournament_code ASC
                """).fetchall()

            if not rows:
                ttk.Label(
                    self.scrollable_frame,
                    text="Brak turniejów w bazie.",
                    padding=10,
                ).pack()
                return

            # Update year combobox
            years = sorted({row["season"] for row in rows})
            self.year_combo["values"] = [""] + [str(y) for y in years]

            # Header
            header = ttk.Frame(self.scrollable_frame)
            header.pack(fill=tk.X, pady=2)
            ttk.Label(header, text="Sezon", width=8).pack(side=tk.LEFT, padx=2)
            ttk.Label(header, text="Kod", width=10).pack(side=tk.LEFT, padx=2)
            ttk.Label(header, text="Nazwa turnieju", width=40).pack(side=tk.LEFT, padx=2)
            ttk.Label(header, text="Data (RRRR-MM-DD)", width=20).pack(side=tk.LEFT, padx=2)

            # Tournament rows
            for row in rows:
                tournament_id = row["tournament_id"]
                frame = ttk.Frame(self.scrollable_frame)
                frame.pack(fill=tk.X, pady=1)

                ttk.Label(frame, text=str(row["season"]), width=8).pack(side=tk.LEFT, padx=2)
                ttk.Label(frame, text=row["tournament_code"], width=10).pack(side=tk.LEFT, padx=2)
                ttk.Label(frame, text=row["tournament_name"], width=40).pack(side=tk.LEFT, padx=2)

                date_var = tk.StringVar(value=row["event_date"] or "")
                date_entry = ttk.Entry(frame, textvariable=date_var, width=20)
                date_entry.pack(side=tk.LEFT, padx=2)

                self.tournament_entries.append((tournament_id, date_var))

            self.status_label.config(text=f"Załadowano {len(rows)} turniejów.")

        except Exception as exc:  # noqa: BLE001
            self.show_error(str(exc))

    def _on_year_change(self, _event=None) -> None:
        """Filter tournaments by selected year."""
        self._refresh_tournaments()

    def _save_changes(self) -> None:
        """Save all edited dates back to database."""
        db_path = Path(self.db_entry.get())
        if not db_path.is_file():
            self.show_error(f"Nie znaleziono bazy: {db_path}")
            return

        try:
            import sqlite3
            from datetime import datetime

            with sqlite3.connect(str(db_path)) as conn:
                saved_count = 0
                for tournament_id, date_var in self.tournament_entries:
                    date_str = date_var.get().strip()

                    # Validate date format if not empty
                    if date_str:
                        try:
                            datetime.strptime(date_str, "%Y-%m-%d")
                        except ValueError:
                            self.show_error(f"Nieprawidłowy format daty: {date_str}. Użyj RRRR-MM-DD.")
                            return

                    conn.execute(
                        "UPDATE tournaments SET event_date = ? WHERE tournament_id = ?",
                        (date_str or None, tournament_id),
                    )
                    saved_count += 1

                conn.commit()

            self.status_label.config(text=f"Zapisano {saved_count} dat turniejów.")
            self.show_info(f"Zapisano {saved_count} dat turniejów.")

        except Exception as exc:  # noqa: BLE001
            self.show_error(str(exc))


class RankingApp:
    """Główne okno aplikacji z Notebookiem zakładek."""

    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("Turnieje TP - System ELO")
        self.root.geometry("900x750")

        # Style
        style = ttk.Style()
        style.theme_use("clam")

        self.project_dir = Path(__file__).resolve().parent

        # Notebook
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Tabs
        self.ranking_tab = RankingTab(self.notebook, self.project_dir)
        self.import_tab = ImportSQLTab(self.notebook, self.project_dir)
        self.export_tab = ExportCSVTab(self.notebook, self.project_dir)
        self.charts_tab = ChartsTab(self.notebook, self.project_dir)
        self.migrations_tab = None  # lazy init
        self.tournament_date_tab = None  # lazy init

        self.notebook.add(self.ranking_tab, text="1. Ranking")
        self.notebook.add(self.import_tab, text="2. Import SQL")
        self.notebook.add(self.export_tab, text="3. Export CSV")
        self.notebook.add(self.charts_tab, text="4. Charts")
        self.notebook.add(self._get_migrations_tab(), text="5. Migrations")
        self.notebook.add(self._get_tournament_date_tab(), text="6. Tournament Dates")

        # Status bar
        self.status_bar = ttk.Label(
            self.root, text="Gotowy", relief=tk.SUNKEN, anchor=tk.W
        )
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)

    def _get_migrations_tab(self) -> MigrationsTab:
        if self.migrations_tab is None:
            self.migrations_tab = MigrationsTab(self.notebook, self.project_dir)
        return self.migrations_tab

    def _get_tournament_date_tab(self) -> TournamentDateTab:
        if self.tournament_date_tab is None:
            self.tournament_date_tab = TournamentDateTab(self.notebook, self.project_dir)
        return self.tournament_date_tab

    def mainloop(self) -> None:
        self.root.mainloop()

    def quit(self) -> None:
        self.root.quit()


def main() -> None:
    """Punkt wejścia GUI."""
    app = RankingApp()
    app.mainloop()


if __name__ == "__main__":
    main()
