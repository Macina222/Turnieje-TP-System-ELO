"""
Punkt wejścia aplikacji rankingu ELO — centralne centrum sterowania.

Ten moduł spina warstwę użytkownika z backendem obliczeniowym i udostępnia
wszystkie funkcje aplikacji z jednego miejsca:
1. Ranking ELO (backend XLSX lub SQLite)
2. Import oficjalnych danych do bazy SQLite + migracje schematu
3. Eksport historii zmian punktów (CSV) dla obu backendów
4. Rysowanie wykresów historii ELO par (dla obu backendów)
5. Zarządzanie migracjami bazy SQLite

Uruchamiaj z GUI (domyślnie) lub CLI (--cli / argumenty obliczeń).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add SQL/ to path so its modules can be imported
_SQL_DIR = Path(__file__).resolve().parent / "SQL"
if str(_SQL_DIR) not in sys.path:
    sys.path.insert(0, str(_SQL_DIR))

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
    categories = [c for c in categories if c]
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
    Uruchamia interaktywny tryb terminalowy (tylko ranking).

    Przepływ jest prosty: wykryj lata, poproś o wybór, wylicz, pokaż, zapisz.
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
        df, selected_category, selected_years
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
        target = input(f"Ścieżka zapisu [{suggested_path}]: ").strip()
        output_path = Path(target) if target else suggested_path
        if not output_path.is_absolute() and len(output_path.parts) == 1:
            output_path = project_dir / "txt" / output_path
        saved_path = save_new_ranking_report(report, output_path)
        print(f"Zapisano do: {saved_path}")

    return 0


def build_argument_parser() -> argparse.ArgumentParser:
    """Buduje parser argumentów współdzielony przez GUI i tryb terminalowy."""

    parser = argparse.ArgumentParser(
        description="Kalkulator rankingu ELO dla data_new.xlsx (XLSX backend) lub SQLite."
    )
    # Backend & data source
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
    # Ranking filters
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
        help="Opcjonalna ścieżka pliku wyjściowego dla jednej kategorii (ranking).",
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
        "--list-categories",
        action="store_true",
        help="Wypisz dostępne kategorie dla wybranych lat i wyjdź (tylko SQLite).",
    )
    parser.add_argument(
        "--list-classes",
        action="store_true",
        help="Wypisz dostępne klasy dla wybranej kategorii/lat i wyjdź (tylko SQLite).",
    )
    parser.add_argument(
        "--list-years",
        action="store_true",
        help="Wypisz dostępne lata w bazie i wyjdź (tylko SQLite).",
    )
    # Import SQL
    parser.add_argument(
        "--import-sql",
        nargs=2,
        metavar=("XLSX", "SQLITE"),
        help="Importuj oficjalne dane XLSX do bazy SQLite: --import-sql <plik.xlsx> <baza.db>.",
    )
    parser.add_argument(
        "--import-sheet",
        help="Nazwa arkusza przy imporcie (opcjonalne).",
    )
    parser.add_argument(
        "--replace-db",
        action="store_true",
        help="Usuń istniejącą bazę przed importem.",
    )
    # Migrations
    parser.add_argument(
        "--migrate",
        metavar="DB",
        help="Uruchom migracje bazy SQLite: --migrate <baza.db>.",
    )
    parser.add_argument(
        "--migrate-target",
        type=int,
        help="Docelowa wersja migracji (domyślnie: najnowsza).",
    )
    parser.add_argument(
        "--migrate-status",
        action="store_true",
        help="Pokaż status migracji bazy zamiast ich uruchamiać.",
    )
    # Export progress CSV
    parser.add_argument(
        "--export-progress",
        action="store_true",
        help="Eksportuj historię zmian punktów do CSV (wymaga --category, --years).",
    )
    parser.add_argument(
        "--export-output",
        help="Ścieżka pliku CSV dla --export-progress.",
    )
    parser.add_argument(
        "--delimiter",
        default=";",
        help="Separator CSV (domyślnie średnik).",
    )
    parser.add_argument(
        "--config",
        default="config.txt",
        help="Ścieżka do pliku konfiguracyjnego (domyślnie: config.txt).",
    )
    # Plot
    parser.add_argument(
        "--plot",
        action="store_true",
        help="Rysuj wykres ELO par (wymaga --category, --years).",
    )
    parser.add_argument(
        "--pair",
        action="append",
        help="Nazwa pary do wykresu (można wielokrotnie).",
    )
    parser.add_argument(
        "--pair-id",
        action="append",
        help="ID pary do wykresu (można wielokrotnie).",
    )
    parser.add_argument(
        "--tancerz1",
        help="Pierwszy tancerz pary (używaj z --tancerz2).",
    )
    parser.add_argument(
        "--tancerz2",
        help="Drugi tancerz pary (używaj z --tancerz1).",
    )
    parser.add_argument(
        "--list-pairs",
        action="store_true",
        help="Wypisz dostępne pary zamiast rysować wykres.",
    )
    parser.add_argument(
        "--search",
        help="Filtr tekstowy dla --list-pairs.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Limit pozycji w --list-pairs (domyślnie 50).",
    )
    parser.add_argument(
        "--plot-output",
        help="Ścieżka zapisu wykresu PNG (dla --plot).",
    )
    parser.add_argument(
        "--show",
        action="store_true",
        help="Pokaż okno wykresu także przy --plot-output.",
    )
    parser.add_argument(
        "--title",
        help="Własny tytuł wykresu (dla --plot).",
    )
    # Mode
    parser.add_argument(
        "--cli",
        action="store_true",
        help="Wymuś tryb terminalowy nawet jeśli tkinter jest dostępny.",
    )
    return parser


if tk is not None:
    from app_gui import RankingApp


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

    # --- CLI: import SQL ---
    if args.import_sql:
        from app_cli import run_import_sql
        xlsx_arg, db_arg = args.import_sql
        return run_import_sql(
            Path(xlsx_arg), Path(db_arg),
            sheet=args.import_sheet, replace=args.replace_db,
        )

    # --- CLI: migrations ---
    if args.migrate:
        from app_cli import run_migrate
        return run_migrate(
            Path(args.migrate),
            target=args.migrate_target,
            status_only=args.migrate_status,
        )

    # --- CLI: export progress ---
    if args.export_progress:
        from app_cli import run_export_progress
        return run_export_progress(args, project_dir)

    # --- CLI: list categories (SQLite only) ---
    if args.list_categories:
        if not args.db:
            print("Błąd: --list-categories wymaga --db.", file=sys.stderr)
            return 1
        if not args.years:
            print("Błąd: --list-categories wymaga --years.", file=sys.stderr)
            return 1
        try:
            from sqlite_ranking_service import get_available_categories_sqlite, get_available_years, parse_years_arg
        except ImportError as exc:
            print(f"Błąd: Backend SQLite niedostępny: {exc}", file=sys.stderr)
            return 1
        db_path = Path(args.db)
        if not db_path.is_file():
            print(f"Błąd: Nie znaleziono bazy: {db_path}", file=sys.stderr)
            return 1
        years = parse_years_arg(args.years)
        categories = get_available_categories_sqlite(db_path, years)
        print("Dostępne kategorie:", ", ".join(categories))
        return 0

    # --- CLI: list classes (SQLite only) ---
    if args.list_classes:
        if not args.db:
            print("Błąd: --list-classes wymaga --db.", file=sys.stderr)
            return 1
        if not args.years:
            print("Błąd: --list-classes wymaga --years.", file=sys.stderr)
            return 1
        if not args.category:
            print("Błąd: --list-classes wymaga --category.", file=sys.stderr)
            return 1
        try:
            from sqlite_ranking_service import get_available_classes, parse_years_arg
        except ImportError as exc:
            print(f"Błąd: Backend SQLite niedostępny: {exc}", file=sys.stderr)
            return 1
        db_path = Path(args.db)
        if not db_path.is_file():
            print(f"Błąd: Nie znaleziono bazy: {db_path}", file=sys.stderr)
            return 1
        years = parse_years_arg(args.years)
        classes = get_available_classes(db_path, args.category, years)
        print("Dostępne klasy:", ", ".join(classes))
        return 0

    # --- CLI: list years (SQLite only) ---
    if args.list_years:
        if not args.db:
            print("Błąd: --list-years wymaga --db.", file=sys.stderr)
            return 1
        try:
            from sqlite_ranking_service import get_available_years
        except ImportError as exc:
            print(f"Błąd: Backend SQLite niedostępny: {exc}", file=sys.stderr)
            return 1
        db_path = Path(args.db)
        if not db_path.is_file():
            print(f"Błąd: Nie znaleziono bazy: {db_path}", file=sys.stderr)
            return 1
        years = get_available_years(db_path)
        print("Dostępne lata:", ", ".join(map(str, years)))
        return 0

    # --- CLI: plot ---
    if args.plot or args.list_pairs:
        from app_cli import run_plot
        return run_plot(args, project_dir)

    # --- CLI: ranking (existing logic) ---
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
        raise SystemExit(run_new_cli_from_args(args, project_dir))

    if tk is None:
        print("Moduł tkinter nie jest dostępny. Uruchamiam tryb terminalowy.")
        raise SystemExit(run_cli_interactive(project_dir))

    app = RankingApp()
    app.mainloop()


if __name__ == "__main__":
    main()
