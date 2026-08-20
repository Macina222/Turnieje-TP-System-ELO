"""
Punkt wejścia aplikacji rankingu ELO.

Ten moduł spina warstwę użytkownika z backendem obliczeniowym:
1. odczytuje dostępne lata, kategorie i klasy z `data_new.xlsx`,
2. pozwala wybrać filtry w GUI albo CLI,
3. przekazuje wybór do `new_ranking_service.build_new_ranking`,
4. odbiera gotowy raport i pokazuje go w oknie lub konsoli,
5. opcjonalnie zapisuje raport do pliku tekstowego.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from new_ranking_service import (
    build_default_new_output_filename,
    build_new_ranking,
    format_class_for_display,
    format_new_ranking_report,
    list_available_categories_for_years_xlsx,
    list_available_classes_for_category_and_years_xlsx,
    list_available_years_xlsx,
    load_xlsx_data,
    parse_classes_text,
    run_cli_from_args as run_new_cli_from_args,
    save_new_ranking_report,
)

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
except ModuleNotFoundError:
    tk = None
    filedialog = None
    messagebox = None
    ttk = None


def parse_years_text(value: str, available_years: list[int]) -> list[int]:
    """
    Zamienia tekst wpisany przez użytkownika na listę poprawnych lat.

    Obsługuje pojedyncze lata, listy rozdzielone przecinkami oraz zakresy typu
    `2021-2025`. Dodatkowo akceptuje skróty oznaczające wybór wszystkich lat.
    """

    text = value.strip()
    if not text:
        raise ValueError("Nie podano lat.")

    lowered = text.lower()
    if lowered in {"all", "wszystkie", "*"}:
        return list(available_years)

    available_set = set(available_years)
    selected: set[int] = set()

    for chunk in text.replace(";", ",").split(","):
        part = chunk.strip()
        if not part:
            continue

        if "-" in part:
            start_text, end_text = part.split("-", 1)
            start = int(start_text.strip())
            end = int(end_text.strip())
            if start > end:
                start, end = end, start
            for year in range(start, end + 1):
                selected.add(year)
            continue

        selected.add(int(part))

    invalid = sorted(year for year in selected if year not in available_set)
    if invalid:
        raise ValueError(
            "Niedostępne lata: " + ", ".join(str(year) for year in invalid)
        )

    return sorted(selected)


def parse_year_arguments(values: list[str] | None, available_years: list[int]) -> list[int]:
    """Parsuje lata przekazane przez argument `--years`."""

    if not values:
        return list(available_years)
    return parse_years_text(",".join(values), available_years)


def prompt_until_valid(prompt: str, parser) -> object:
    """Powtarza pytanie w CLI, dopóki parser nie zaakceptuje wartości."""

    while True:
        raw_value = input(prompt).strip()
        try:
            return parser(raw_value)
        except ValueError as exc:
            print(f"Błąd: {exc}")


def prompt_for_years(available_years: list[int]) -> list[int]:
    """Wyświetla użytkownikowi listę lat i zwraca poprawny wybór CLI."""

    print("Dostępne lata:")
    print(", ".join(str(year) for year in available_years))
    print("Wpisz np. 2024,2025 albo 2021-2025 albo all")
    return prompt_until_valid(
        "Lata do uwzględnienia: ",
        lambda value: parse_years_text(value, available_years),
    )


def prompt_for_category(categories: list[str]) -> str:
    """Pozwala wybrać kategorię przez numer pozycji albo symbol kategorii."""

    print("Dostępne kategorie:")
    for index, category in enumerate(categories, start=1):
        print(f"{index}. {category}")

    def parse_category(value: str) -> str:
        """Waliduje pojedynczą odpowiedź użytkownika dotyczącą kategorii."""

        text = value.strip().upper()
        if not text:
            raise ValueError("Nie podano kategorii.")
        if text.isdigit():
            index = int(text)
            if 1 <= index <= len(categories):
                return categories[index - 1]
            raise ValueError("Numer kategorii jest poza zakresem.")
        if text in categories:
            return text
        raise ValueError("Nieznana kategoria.")

    return prompt_until_valid("Kategoria (numer lub symbol): ", parse_category)


def prompt_for_classes(available_classes: list[str]) -> list[str] | None:
    """Pozwala opcjonalnie zawęzić ranking do wybranych klas."""

    if not available_classes:
        return None

    print("Dostępne klasy:")
    for index, klasa in enumerate(available_classes, start=1):
        print(f"{index}. {format_class_for_display(klasa)}")
    print("Wpisz np. B,A albo 1,2 albo all")
    return prompt_until_valid(
        "Klasy do uwzględnienia (Enter lub all = wszystkie): ",
        lambda value: parse_classes_text(value, available_classes),
    )


def prompt_yes_no(prompt: str, default: bool = True) -> bool:
    """Obsługuje pytanie typu tak/nie z domyślną odpowiedzią."""

    suffix = "[T/n]" if default else "[t/N]"
    answer = input(f"{prompt} {suffix}: ").strip().lower()
    if not answer:
        return default
    return answer in {"t", "tak", "y", "yes"}


def run_cli_interactive(project_dir: Path) -> int:
    """
    Uruchamia interaktywny tryb terminalowy.

    Przepływ jest prosty:
    1. wykryj dostępne lata,
    2. poproś o wybór lat i kategorii,
    3. wylicz ranking,
    4. pokaż raport,
    5. opcjonalnie zapisz wynik do pliku.
    """

    xlsx_path = project_dir / "data_new.xlsx"
    if not xlsx_path.is_file():
        raise FileNotFoundError(f"Nie znaleziono pliku: {xlsx_path}")

    print(f"Plik danych: {xlsx_path}")
    df = load_xlsx_data(xlsx_path)
    available_years = list_available_years_xlsx(df)

    if not available_years:
        print("Nie znaleziono żadnych sezonów w pliku.")
        return 1

    selected_years = prompt_for_years(available_years)
    categories = list_available_categories_for_years_xlsx(df, selected_years)
    if not categories:
        print("Brak kategorii dla wybranych lat.")
        return 1

    selected_category = prompt_for_category(categories)
    available_classes = list_available_classes_for_category_and_years_xlsx(
        df,
        selected_category,
        selected_years,
    )
    selected_classes = prompt_for_classes(available_classes)
    result = build_new_ranking(
        file_path=xlsx_path,
        category=selected_category,
        years=selected_years,
        classes=selected_classes,
    )
    report = format_new_ranking_report(result)

    print()
    print(report)
    print()

    if prompt_yes_no("Zapisać ranking do pliku?", default=True):
        default_name = build_default_new_output_filename(result)
        suggested_path = project_dir / "txt" / default_name
        target = input(
            f"Ścieżka zapisu [{suggested_path}]: "
        ).strip()
        output_path = Path(target) if target else suggested_path
        if not output_path.is_absolute() and len(output_path.parts) == 1:
            output_path = project_dir / "txt" / output_path
        saved_path = save_new_ranking_report(report, output_path)
        print(f"Zapisano do: {saved_path}")

    return 0


def run_cli_from_args(args: argparse.Namespace, project_dir: Path) -> int:
    """Obsługuje nieinteraktywny tryb CLI przez wybrany backend."""

    # SQLite backend
    if getattr(args, "backend", "xlsx") == "sqlite":
        from new_ranking_service import (
            build_new_ranking,
            format_new_ranking_report,
            save_new_ranking_report,
        )

        if not args.db:
            print("Błąd: dla backend='sqlite' wymagany jest argument --db.")
            return 1

        if not args.category:
            print("Błąd: dla backend='sqlite' wymagany jest argument --category.")
            return 1

        from new_ranking_service import normalize_years
        from sqlite_ranking_service import (
            get_available_years as get_available_years_sqlite,
            parse_years_arg,
        )

        years = parse_years_arg(args.years) if args.years else get_available_years_sqlite(args.db)
        result = build_new_ranking(
            category=args.category,
            years=years,
            classes=args.classes,
            db_path=args.db,
            backend="sqlite",
        )
        report = format_new_ranking_report(result)
        print(report)
        if args.output:
            saved_path = save_new_ranking_report(report, args.output)
            print(f"Zapisano do: {saved_path}")
        return 0

    return run_new_cli_from_args(args, project_dir)


def build_argument_parser() -> argparse.ArgumentParser:
    """Buduje parser argumentów współdzielony przez GUI i tryb terminalowy."""

    parser = argparse.ArgumentParser(
        description="Kalkulator rankingu ELO dla data_new.xlsx (XLSX backend) lub SQLite."
    )
    parser.add_argument(
        "--backend",
        choices=["xlsx", "sqlite"],
        default="xlsx",
        help="Backend danych: xlsx (domyślnie) lub sqlite.",
    )
    parser.add_argument(
        "--input-excel",
        help="Ścieżka pliku xlsx. Domyślnie: data_new.xlsx.",
    )
    parser.add_argument(
        "--db",
        help="Ścieżka do bazy SQLite (wymagane dla --backend sqlite).",
    )
    parser.add_argument(
        "--category",
        help="Kategoria bazowa rankingu, np. V albo III.",
    )
    parser.add_argument(
        "--years",
        nargs="+",
        help="Lata lub zakresy lat, np. 2024 2025 albo 2021-2025.",
    )
    parser.add_argument(
        "--classes",
        nargs="+",
        help="Klasy do uwzględnienia, np. B A albo S. Brak = wszystkie.",
    )
    parser.add_argument(
        "--output",
        help="Opcjonalna ścieżka pliku wyjściowego dla jednej kategorii.",
    )
    parser.add_argument(
        "--output-dir",
        default="txt",
        help="Katalog wyjściowy dla --all-categories. Domyślnie: txt.",
    )
    parser.add_argument(
        "--all-categories",
        action="store_true",
        help="Wygeneruj raporty dla wszystkich kategorii dostępnych w latach.",
    )
    parser.add_argument(
        "--cli",
        action="store_true",
        help="Wymuś tryb terminalowy nawet jeśli tkinter jest dostępny.",
    )
    return parser


if tk is not None:
    class RankingApp(tk.Tk):
        """
        Okno GUI do liczenia rankingu bez pracy w terminalu.

        Klasa utrzymuje aktualny stan filtrów, deleguje obliczenia do backendu
        i pokazuje raport tekstowy wraz ze statusem ostatniej operacji.
        """

        def __init__(self) -> None:
            """Inicjalizuje okno, dane wejściowe i bazowy stan interfejsu."""

            super().__init__()

            self.title("Kalkulator rankingu ELO")
            self.geometry("1280x820")
            self.minsize(980, 640)

            self.project_dir = Path(__file__).resolve().parent
            self.xlsx_path = self.project_dir / "data_new.xlsx"
            self.data_frame = load_xlsx_data(self.xlsx_path) if self.xlsx_path.is_file() else None
            self.available_years = (
                list_available_years_xlsx(self.data_frame)
                if self.data_frame is not None
                else []
            )
            self.current_result = None
            self.current_report = ""
            self.available_classes: list[str] = []

            self.category_var = tk.StringVar()
            self.source_var = tk.StringVar(value=str(self.xlsx_path))
            self.backend_var = tk.StringVar(value="xlsx")
            self.db_var = tk.StringVar()
            self.status_var = tk.StringVar(
                value="Wybierz kategorię i lata, a następnie kliknij \"Oblicz ranking\"."
            )
            self.summary_var = tk.StringVar(
                value="Ranking nie został jeszcze obliczony."
            )

            self._build_ui()
            self._select_all_years()
            self._refresh_category_choices()
            self.summary_var.set("Ranking nie został jeszcze obliczony dla bieżących filtrów.")
            self.status_var.set(
                "Wybierz kategorię i lata, a następnie kliknij \"Oblicz ranking\"."
            )

            if not self.available_years:
                self.calculate_button.state(["disabled"])
                self.status_var.set("Nie znaleziono sezonów w data_new.xlsx.")

        def _build_ui(self) -> None:
            """Buduje layout okna: filtry po lewej, raport i status po prawej."""

            try:
                ttk.Style(self).theme_use("clam")
            except tk.TclError:
                pass

            self.columnconfigure(0, weight=1)
            self.rowconfigure(0, weight=1)

            container = ttk.Frame(self, padding=16)
            container.grid(row=0, column=0, sticky="nsew")
            container.columnconfigure(1, weight=1)
            container.rowconfigure(0, weight=1)

            sidebar = ttk.Frame(container)
            sidebar.grid(row=0, column=0, sticky="nsw", padx=(0, 16))
            sidebar.columnconfigure(0, weight=1)

            filters_frame = ttk.LabelFrame(sidebar, text="Filtry", padding=12)
            filters_frame.grid(row=0, column=0, sticky="new")
            filters_frame.columnconfigure(0, weight=1)

            # Backend selection
            ttk.Label(filters_frame, text="Backend danych").grid(
                row=0, column=0, sticky="w"
            )
            backend_combo = ttk.Combobox(
                filters_frame,
                textvariable=self.backend_var,
                values=["xlsx", "sqlite"],
                state="readonly",
                width=20,
            )
            backend_combo.grid(row=1, column=0, sticky="ew", pady=(4, 4))
            backend_combo.bind("<<ComboboxSelected>>", self._on_backend_changed)

            # XLSX file selection (shown for xlsx backend)
            self.xlsx_source_label = ttk.Label(filters_frame, text="Plik danych (XLSX)")
            self.xlsx_source_label.grid(row=2, column=0, sticky="w")
            source_frame = ttk.Frame(filters_frame)
            source_frame.grid(row=3, column=0, sticky="ew", pady=(4, 12))
            source_frame.columnconfigure(0, weight=1)
            ttk.Entry(
                source_frame,
                textvariable=self.source_var,
                state="readonly",
                width=32,
            ).grid(row=0, column=0, sticky="ew", padx=(0, 6))
            ttk.Button(
                source_frame,
                text="Wybierz...",
                command=self._choose_xlsx_file,
            ).grid(row=0, column=1, sticky="e")

            # SQLite database selection (shown for sqlite backend)
            self.db_source_label = ttk.Label(filters_frame, text="Baza danych (SQLite)")
            self.db_source_label.grid(row=4, column=0, sticky="w")
            db_frame = ttk.Frame(filters_frame)
            db_frame.grid(row=5, column=0, sticky="ew", pady=(4, 12))
            db_frame.columnconfigure(0, weight=1)
            self.db_entry = ttk.Entry(
                db_frame,
                textvariable=self.db_var,
                width=32,
            )
            self.db_entry.grid(row=0, column=0, sticky="ew", padx=(0, 6))
            ttk.Button(
                db_frame,
                text="Wybierz...",
                command=self._choose_sqlite_db,
            ).grid(row=0, column=1, sticky="e")

            self._update_backend_ui()

            ttk.Label(filters_frame, text="Kategoria rankingu").grid(
                row=2, column=0, sticky="w"
            )
            self.category_combobox = ttk.Combobox(
                filters_frame,
                textvariable=self.category_var,
                state="readonly",
                width=20,
            )
            self.category_combobox.grid(row=3, column=0, sticky="ew", pady=(4, 12))
            self.category_combobox.bind("<<ComboboxSelected>>", self._on_category_changed)

            ttk.Label(filters_frame, text="Lata uwzględniane w kalkulacji").grid(
                row=4, column=0, sticky="w"
            )

            years_frame = ttk.Frame(filters_frame)
            years_frame.grid(row=5, column=0, sticky="nsew", pady=(4, 12))
            years_frame.columnconfigure(0, weight=1)
            years_frame.rowconfigure(0, weight=1)

            self.years_listbox = tk.Listbox(
                years_frame,
                selectmode=tk.EXTENDED,
                exportselection=False,
                height=10,
                width=18,
            )
            self.years_listbox.grid(row=0, column=0, sticky="nsew")
            self.years_listbox.bind("<<ListboxSelect>>", self._on_year_selection_change)

            years_scroll = ttk.Scrollbar(
                years_frame, orient="vertical", command=self.years_listbox.yview
            )
            years_scroll.grid(row=0, column=1, sticky="ns")
            self.years_listbox.configure(yscrollcommand=years_scroll.set)

            for year in self.available_years:
                self.years_listbox.insert(tk.END, year)

            years_buttons = ttk.Frame(filters_frame)
            years_buttons.grid(row=6, column=0, sticky="ew")
            years_buttons.columnconfigure(0, weight=1)
            years_buttons.columnconfigure(1, weight=1)

            ttk.Button(
                years_buttons, text="Zaznacz wszystkie", command=self._select_all_years
            ).grid(row=0, column=0, sticky="ew", padx=(0, 6))
            ttk.Button(
                years_buttons, text="Wyczyść wybór", command=self._clear_years_selection
            ).grid(row=0, column=1, sticky="ew")

            ttk.Label(filters_frame, text="Klasy").grid(
                row=7, column=0, sticky="w", pady=(12, 0)
            )
            classes_frame = ttk.Frame(filters_frame)
            classes_frame.grid(row=8, column=0, sticky="nsew", pady=(4, 12))
            classes_frame.columnconfigure(0, weight=1)
            classes_frame.rowconfigure(0, weight=1)

            self.classes_listbox = tk.Listbox(
                classes_frame,
                selectmode=tk.EXTENDED,
                exportselection=False,
                height=7,
                width=18,
            )
            self.classes_listbox.grid(row=0, column=0, sticky="nsew")
            self.classes_listbox.bind("<<ListboxSelect>>", self._on_filter_changed)

            classes_scroll = ttk.Scrollbar(
                classes_frame, orient="vertical", command=self.classes_listbox.yview
            )
            classes_scroll.grid(row=0, column=1, sticky="ns")
            self.classes_listbox.configure(yscrollcommand=classes_scroll.set)

            classes_buttons = ttk.Frame(filters_frame)
            classes_buttons.grid(row=9, column=0, sticky="ew")
            classes_buttons.columnconfigure(0, weight=1)
            classes_buttons.columnconfigure(1, weight=1)

            ttk.Button(
                classes_buttons,
                text="Zaznacz wszystkie",
                command=self._select_all_classes,
            ).grid(row=0, column=0, sticky="ew", padx=(0, 6))
            ttk.Button(
                classes_buttons,
                text="Wyczyść wybór",
                command=self._clear_classes_selection,
            ).grid(row=0, column=1, sticky="ew")

            actions_frame = ttk.Frame(sidebar)
            actions_frame.grid(row=1, column=0, sticky="ew", pady=(12, 0))
            actions_frame.columnconfigure(0, weight=1)

            self.calculate_button = ttk.Button(
                actions_frame,
                text="Oblicz ranking",
                command=self._calculate_ranking,
            )
            self.calculate_button.grid(row=0, column=0, sticky="ew")

            self.save_button = ttk.Button(
                actions_frame,
                text="Zapisz ranking",
                command=self._save_ranking,
            )
            self.save_button.grid(row=1, column=0, sticky="ew", pady=(8, 0))
            self.save_button.state(["disabled"])

            status_frame = ttk.LabelFrame(sidebar, text="Status", padding=12)
            status_frame.grid(row=2, column=0, sticky="ew", pady=(12, 0))
            status_frame.columnconfigure(0, weight=1)

            ttk.Label(
                status_frame,
                textvariable=self.status_var,
                wraplength=280,
                justify="left",
            ).grid(row=0, column=0, sticky="w")

            results_frame = ttk.Frame(container)
            results_frame.grid(row=0, column=1, sticky="nsew")
            results_frame.columnconfigure(0, weight=1)
            results_frame.rowconfigure(1, weight=1)

            ttk.Label(
                results_frame,
                textvariable=self.summary_var,
                wraplength=760,
                justify="left",
            ).grid(row=0, column=0, sticky="ew", pady=(0, 10))

            text_frame = ttk.Frame(results_frame)
            text_frame.grid(row=1, column=0, sticky="nsew")
            text_frame.columnconfigure(0, weight=1)
            text_frame.rowconfigure(0, weight=1)

            self.result_text = tk.Text(
                text_frame,
                wrap="none",
                font=("Courier New", 10),
                state="disabled",
            )
            self.result_text.grid(row=0, column=0, sticky="nsew")

            y_scroll = ttk.Scrollbar(
                text_frame, orient="vertical", command=self.result_text.yview
            )
            y_scroll.grid(row=0, column=1, sticky="ns")
            self.result_text.configure(yscrollcommand=y_scroll.set)

            x_scroll = ttk.Scrollbar(
                text_frame, orient="horizontal", command=self.result_text.xview
            )
            x_scroll.grid(row=1, column=0, sticky="ew")
            self.result_text.configure(xscrollcommand=x_scroll.set)

        def _get_selected_years(self) -> list[int]:
            """Odczytuje zaznaczone lata z listy w GUI."""

            return [
                int(self.years_listbox.get(index))
                for index in self.years_listbox.curselection()
            ]

        def _get_selected_classes(self) -> list[str] | None:
            """Odczytuje zaznaczone klasy; brak zaznaczenia oznacza wszystkie."""

            classes = [
                self.available_classes[index]
                for index in self.classes_listbox.curselection()
            ]
            return classes if classes else None

        def _reload_xlsx_data(self, xlsx_path: Path) -> None:
            """Wczytuje wybrany arkusz i odświeża filtry zależne od danych."""

            self.xlsx_path = xlsx_path
            self.data_frame = load_xlsx_data(self.xlsx_path)
            self.available_years = list_available_years_xlsx(self.data_frame)
            self.source_var.set(str(self.xlsx_path))

            self.years_listbox.delete(0, tk.END)
            for year in self.available_years:
                self.years_listbox.insert(tk.END, year)

            if self.available_years:
                self.calculate_button.state(["!disabled"])
                self._select_all_years()
                self.status_var.set("Wczytano plik danych. Kliknij \"Oblicz ranking\".")
            else:
                self.calculate_button.state(["disabled"])
                self._refresh_category_choices()
                self.status_var.set("Nie znaleziono sezonów w wybranym pliku.")
            self._mark_result_stale()

        def _choose_xlsx_file(self) -> None:
            """Pozwala wybrać inny plik XLSX jako źródło danych."""

            selected_path = filedialog.askopenfilename(
                title="Wybierz plik XLSX z danymi",
                initialdir=str(self.project_dir),
                filetypes=(("Arkusz Excel", "*.xlsx"), ("Wszystkie pliki", "*.*")),
            )
            if not selected_path:
                return

            try:
                self._reload_xlsx_data(Path(selected_path))
            except Exception as exc:
                messagebox.showerror("Błąd wczytywania danych", str(exc))

        def _on_backend_changed(self, _event: tk.Event | None = None) -> None:
            """Reaguje na zmianę backendu - odświeża UI i dane."""
            self._update_backend_ui()
            self._mark_result_stale()

        def _update_backend_ui(self) -> None:
            """Pokazuje/ukrywa odpowiednie pola w zależności od wybranego backendu."""
            backend = self.backend_var.get()
            if backend == "xlsx":
                self.xlsx_source_label.grid()
                self.source_var.master.grid()  # source_frame
                self.db_source_label.grid_remove()
                self.db_entry.master.grid_remove()  # db_frame
                self._load_xlsx_years()
            else:
                self.xlsx_source_label.grid_remove()
                self.source_var.master.grid_remove()  # source_frame
                self.db_source_label.grid()
                self.db_entry.master.grid()  # db_frame
                self._load_sqlite_years()

        def _load_xlsx_years(self) -> None:
            """Ładuje lata z XLSX."""
            self.data_frame = load_xlsx_data(self.xlsx_path) if self.xlsx_path.is_file() else None
            self.available_years = (
                list_available_years_xlsx(self.data_frame)
                if self.data_frame is not None
                else []
            )
            self.years_listbox.delete(0, tk.END)
            for year in self.available_years:
                self.years_listbox.insert(tk.END, year)
            self._refresh_category_choices()
            self._refresh_class_choices()

        def _load_sqlite_years(self) -> None:
            """Ładuje lata z bazy SQLite."""
            if not self.db_var.get():
                self.available_years = []
            else:
                try:
                    from sqlite_ranking_service import get_available_years as get_available_years_sqlite
                    self.available_years = get_available_years_sqlite(self.db_var.get())
                except Exception as exc:
                    self.status_var.set(f"Błąd wczytywania bazy: {exc}")
                    self.available_years = []
            self.years_listbox.delete(0, tk.END)
            for year in self.available_years:
                self.years_listbox.insert(tk.END, year)
            self._refresh_category_choices()
            self._refresh_class_choices()

        def _choose_sqlite_db(self) -> None:
            """Pozwala wybrać plik bazy SQLite."""
            selected_path = filedialog.askopenfilename(
                title="Wybierz plik bazy SQLite",
                initialdir=str(self.project_dir),
                filetypes=(("Baza SQLite", "*.sqlite"), ("Wszystkie pliki", "*.*")),
            )
            if not selected_path:
                return
            self.db_var.set(selected_path)
            self._load_sqlite_years()

        def _set_result_text(self, content: str) -> None:
            """Podmienia zawartość pola tekstowego z raportem."""

            self.result_text.configure(state="normal")
            self.result_text.delete("1.0", tk.END)
            self.result_text.insert("1.0", content)
            self.result_text.configure(state="disabled")

        def _select_all_years(self) -> None:
            """Zaznacza wszystkie dostępne lata i odświeża stan filtrów."""

            if self.available_years:
                self.years_listbox.selection_set(0, tk.END)
            self._refresh_category_choices()
            self._refresh_class_choices()
            self._mark_result_stale()

        def _clear_years_selection(self) -> None:
            """Czyści zaznaczenie lat i oznacza raport jako nieaktualny."""

            self.years_listbox.selection_clear(0, tk.END)
            self._refresh_category_choices()
            self._refresh_class_choices()
            self._mark_result_stale()

        def _on_year_selection_change(self, _event: tk.Event | None = None) -> None:
            """Reaguje na zmianę lat przez odświeżenie listy kategorii."""

            self._refresh_category_choices()
            self._refresh_class_choices()
            self._mark_result_stale()

        def _on_filter_changed(self, _event: tk.Event | None = None) -> None:
            """Oznacza poprzedni wynik jako nieaktualny po zmianie filtra."""

            self._mark_result_stale()

        def _on_category_changed(self, _event: tk.Event | None = None) -> None:
            """Odświeża klasy po zmianie kategorii."""

            self._refresh_class_choices()
            self._mark_result_stale()

        def _select_all_classes(self) -> None:
            """Zaznacza wszystkie dostępne klasy."""

            if self.classes_listbox.size():
                self.classes_listbox.selection_set(0, tk.END)
            self._mark_result_stale()

        def _clear_classes_selection(self) -> None:
            """Czyści filtr klas; backend potraktuje to jako wszystkie klasy."""

            self.classes_listbox.selection_clear(0, tk.END)
            self._mark_result_stale()

        def _refresh_category_choices(self) -> None:
            """
            Odświeża listę kategorii dostępnych dla aktualnie wybranych lat.

            Dzięki temu użytkownik może wybrać tylko te rodziny kategorii,
            dla których faktycznie istnieją pliki wejściowe.
            """

            years = self._get_selected_years()
            if self.backend_var.get() == "sqlite":
                categories = self._get_sqlite_categories(years)
            elif self.data_frame is None:
                categories = []
            else:
                categories = list_available_categories_for_years_xlsx(
                    self.data_frame, years if years else None
                )

            current_category = self.category_var.get()
            self.category_combobox.configure(values=categories)

            if current_category in categories:
                self.category_var.set(current_category)
            elif categories:
                self.category_var.set(categories[0])
            else:
                self.category_var.set("")

        def _get_sqlite_categories(self, years: list[int]) -> list[str]:
            """Pobiera dostępne kategorie z bazy SQLite."""
            db_path = self.db_var.get()
            if not db_path:
                return []
            try:
                from sqlite_ranking_service import get_available_categories_sqlite
                return get_available_categories_sqlite(db_path, years or None)
            except ImportError:
                return []
            except Exception as exc:
                self.status_var.set(f"Błąd odczytu kategorii z bazy: {exc}")
                return []

        def _refresh_class_choices(self) -> None:
            """Odświeża klasy dostępne dla aktualnych lat i kategorii."""

            years = self._get_selected_years()
            category = self.category_var.get().strip()
            previous_selection = set(self._get_selected_classes() or [])

            if self.backend_var.get() == "sqlite":
                classes = self._get_sqlite_classes(category, years)
            elif self.data_frame is None or not category:
                classes = []
            else:
                classes = list_available_classes_for_category_and_years_xlsx(
                    self.data_frame,
                    category,
                    years if years else None,
                )

            self.available_classes = classes
            self.classes_listbox.delete(0, tk.END)
            for klasa in classes:
                self.classes_listbox.insert(tk.END, format_class_for_display(klasa))
                if klasa in previous_selection:
                    self.classes_listbox.selection_set(tk.END)

            if classes and not previous_selection:
                self.classes_listbox.selection_set(0, tk.END)

        def _get_sqlite_classes(self, category: str, years: list[int]) -> list[str]:
            """Pobiera dostępne klasy z bazy SQLite."""
            db_path = self.db_var.get()
            if not db_path or not category:
                return []
            try:
                from sqlite_ranking_service import get_available_classes as get_available_classes_sqlite
                return get_available_classes_sqlite(db_path, category, years or None)
            except ImportError:
                return []
            except Exception as exc:
                self.status_var.set(f"Błąd odczytu klas z bazy: {exc}")
                return []

        def _mark_result_stale(self) -> None:
            """Resetuje wynik po zmianie filtrów i blokuje zapis starego raportu."""

            self.current_result = None
            self.current_report = ""
            self.save_button.state(["disabled"])
            self.summary_var.set("Ranking nie został jeszcze obliczony dla bieżących filtrów.")
            self.status_var.set("Filtry zostały zmienione. Kliknij \"Oblicz ranking\".")

        def _calculate_ranking(self) -> None:
            """
            Uruchamia pełny backend rankingu dla aktualnie ustawionych filtrów.

            Metoda waliduje wybór w GUI, wywołuje `build_new_ranking`, a potem
            aktualizuje podsumowanie, status i treść raportu w oknie.
            """

            category = self.category_var.get().strip()
            years = self._get_selected_years()
            classes = self._get_selected_classes()

            if not category:
                messagebox.showerror("Brak kategorii", "Wybierz kategorię rankingu.")
                return
            if not years:
                messagebox.showerror("Brak lat", "Wybierz przynajmniej jeden rok.")
                return

            backend = self.backend_var.get()

            try:
                if backend == "sqlite":
                    db_path = self.db_var.get()
                    if not db_path:
                        messagebox.showerror("Brak bazy", "Wybierz plik bazy SQLite.")
                        return
                    result = build_new_ranking(
                        category=category,
                        years=years,
                        classes=classes,
                        backend="sqlite",
                        db_path=db_path,
                    )
                else:
                    result = build_new_ranking(
                        file_path=self.xlsx_path,
                        category=category,
                        years=years,
                        classes=classes,
                    )
            except Exception as exc:
                messagebox.showerror("Błąd obliczania", str(exc))
                return

            report = format_new_ranking_report(result)
            included_categories = ", ".join(result.included_categories) or "brak"

            self.current_result = result
            self.current_report = report
            self._set_result_text(report)
            self.summary_var.set(
                f"Kategoria {result.category} | lata: {', '.join(str(year) for year in result.years)} | "
                f"turnieje: {result.tournaments_processed} | uwzględnione kategorie: {included_categories}"
            )
            self.status_var.set("Ranking został obliczony.")
            self.save_button.state(["!disabled"])

        def _save_ranking(self) -> None:
            """Zapisuje ostatnio obliczony raport do pliku wybranego w GUI."""

            if not self.current_result or not self.current_report:
                messagebox.showerror(
                    "Brak rankingu",
                    "Najpierw oblicz ranking, który ma zostać zapisany.",
                )
                return

            default_path = (
                self.project_dir
                / "txt"
                / build_default_new_output_filename(self.current_result)
            )
            output_path = filedialog.asksaveasfilename(
                title="Zapisz ranking",
                initialdir=str(default_path.parent),
                initialfile=default_path.name,
                defaultextension=".txt",
                filetypes=(("Plik tekstowy", "*.txt"), ("Wszystkie pliki", "*.*")),
            )

            if not output_path:
                return

            try:
                saved_path = save_new_ranking_report(self.current_report, output_path)
            except Exception as exc:
                messagebox.showerror("Błąd zapisu", str(exc))
                return

            self.status_var.set(f"Ranking zapisany do pliku: {saved_path}")


def main() -> None:
    """
    Wybiera tryb uruchomienia aplikacji.

    Kolejność decyzji jest następująca:
    1. jeśli podano argumenty obliczeń, uruchom tryb CLI z argumentów,
    2. jeśli wymuszono `--cli`, uruchom tryb interaktywny w terminalu,
    3. jeśli `tkinter` nie jest dostępny, przejdź do CLI,
    4. w przeciwnym razie uruchom GUI.
    """

    project_dir = Path(__file__).resolve().parent
    parser = build_argument_parser()
    args = parser.parse_args()

    has_cli_arguments = bool(
        args.input_excel
        or args.category
        or args.years
        or args.classes
        or args.output
        or args.all_categories
    )

    if args.cli and not has_cli_arguments:
        raise SystemExit(run_cli_interactive(project_dir))

    if has_cli_arguments:
        raise SystemExit(run_cli_from_args(args, project_dir))

    if tk is None:
        print("Moduł tkinter nie jest dostępny. Uruchamiam tryb terminalowy.")
        raise SystemExit(run_cli_interactive(project_dir))

    app = RankingApp()
    app.mainloop()


if __name__ == "__main__":
    main()
