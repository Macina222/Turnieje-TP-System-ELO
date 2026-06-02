"""
Eksport historii zmian punktów ELO par po kolejnych turniejach do CSV.

Wersja dla nowego formatu danych (data_new.xlsx).
Korzysta z ``new_ranking_service.py`` — te same filtry lat, kategorii, klas
oraz ta sama kolejność przetwarzania co ``new_ranking_service.run_new_ranking``.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from new_ranking_service import (
    build_default_new_progress_filename,
    build_new_progress_export,
    format_classes_for_display,
    list_available_categories_for_years_xlsx,
    list_available_classes_for_category_and_years_xlsx,
    list_available_years_xlsx,
    load_xlsx_data,
    save_new_progress_csv,
)


# ---------------------------------------------------------------------------
# Parsery tekstu (lata, klasy) — analogiczne do legacy/progress_export.py
# ---------------------------------------------------------------------------

def parse_years_text(value: str, available_years: list[int]) -> list[int]:
    """
    Zamienia tekst z latami na listę lat.

    Obsługuje pojedyncze lata, listy po przecinku i zakresy typu ``2021-2025``.
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
            selected.update(range(start, end + 1))
        else:
            selected.add(int(part))

    invalid = sorted(year for year in selected if year not in available_set)
    if invalid:
        raise ValueError(
            "Niedostępne lata: " + ", ".join(str(year) for year in invalid)
        )
    return sorted(selected)


def parse_year_arguments(
    values: list[str] | None,
    available_years: list[int],
) -> list[int]:
    """Parsuje lata z argumentu ``--years``; brak argumentu oznacza wszystkie lata."""
    if not values:
        return list(available_years)
    return parse_years_text(",".join(values), available_years)


def parse_classes_text(value: str, available_classes: list[str]) -> list[str] | None:
    """
    Parsuje klasy z tekstu użytkownika.

    Zwraca None, jeśli wybrano wszystkie klasy.
    """
    text = value.strip()
    if not text:
        return None
    lowered = text.lower()
    if lowered in {"all", "wszystkie", "*"}:
        return None

    available_upper = [c.upper() for c in available_classes]
    selected: list[str] = []
    for chunk in text.replace(";", ",").split(","):
        part = chunk.strip()
        if not part:
            continue
        if part.isdigit():
            index = int(part)
            if 1 <= index <= len(available_classes):
                cls = available_classes[index - 1]
            else:
                raise ValueError(f"Numer klasy {index} jest poza zakresem.")
        else:
            upper = part.upper()
            if upper not in available_upper:
                raise ValueError(f"Nieznana klasa: {part}")
            cls = available_classes[available_upper.index(upper)]

        if cls not in selected:
            selected.append(cls)

    return selected if selected else None


def parse_class_arguments(
    values: list[str] | None,
    available_classes: list[str],
) -> list[str] | None:
    """Parsuje klasy z argumentu ``--classes``; brak argumentu oznacza wszystkie."""
    if not values:
        return None
    return parse_classes_text(",".join(values), available_classes)


# ---------------------------------------------------------------------------
# Tryb interaktywny
# ---------------------------------------------------------------------------

def prompt_until_valid(prompt: str, parser) -> object:
    """Powtarza pytanie, dopóki parser nie zaakceptuje wartości."""
    while True:
        raw_value = input(prompt).strip()
        try:
            return parser(raw_value)
        except ValueError as exc:
            print(f"Błąd: {exc}")


def prompt_for_years(available_years: list[int]) -> list[int]:
    """Pyta o zakres lat do eksportu."""
    print("Dostępne lata:")
    print(", ".join(str(year) for year in available_years))
    print("Wpisz np. 2024,2025 albo 2021-2025 albo all")
    return prompt_until_valid(
        "Lata do uwzględnienia: ",
        lambda value: parse_years_text(value, available_years),
    )


def prompt_for_category(categories: list[str]) -> str:
    """Pyta o kategorię bazową."""
    print("Dostępne kategorie:")
    for index, category in enumerate(categories, start=1):
        print(f"  {index}. {category}")

    def parse_category(value: str) -> str:
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
    """Pyta o opcjonalny filtr klas."""
    if not available_classes:
        return None

    print("Dostępne klasy:")
    for index, klasa in enumerate(available_classes, start=1):
        label = klasa if klasa else "(brak sufiksu)"
        print(f"  {index}. {label}")
    print(
        "Wpisz numery lub symbole klas rozdzielone przecinkami, "
        "np. B,A lub all"
    )
    return prompt_until_valid(
        "Klasy do uwzględnienia (Enter lub all = wszystkie): ",
        lambda value: parse_classes_text(value, available_classes),
    )


# ---------------------------------------------------------------------------
# Eksport
# ---------------------------------------------------------------------------

def run_export(
    xlsx_path: Path,
    category: str,
    years: list[int],
    classes: list[str] | None,
    output_path: Path | None,
    delimiter: str,
    project_dir: Path,
) -> int:
    """Buduje historię zmian punktów i zapisuje ją do CSV."""
    result = build_new_progress_export(
        file_path=xlsx_path,
        category=category,
        years=years,
        classes=classes,
    )
    csv_dir = project_dir / "csv"
    if output_path:
        target_path = output_path
        if not target_path.is_absolute() and len(target_path.parts) == 1:
            target_path = csv_dir / target_path
    else:
        target_path = csv_dir / build_default_new_progress_filename(result)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    saved_path = save_new_progress_csv(result, target_path, delimiter=delimiter)

    classes_label = format_classes_for_display(result.included_classes)
    print(f"Zapisano CSV: {saved_path}")
    print(
        f"Wiersze: {len(result.rows)} | turnieje: {result.tournaments_processed} | "
        f"kategoria: {result.category} | klasy: {classes_label}"
    )

    return 0


def run_interactive(project_dir: Path, xlsx_path: Path, delimiter: str) -> int:
    """Uruchamia prosty tryb interaktywny w terminalu."""
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

    print("Budowanie historii zmian punktów...")
    result = build_new_progress_export(
        file_path=xlsx_path,
        category=selected_category,
        years=selected_years,
        classes=selected_classes,
    )
    csv_dir = project_dir / "csv"
    csv_dir.mkdir(parents=True, exist_ok=True)
    default_path = csv_dir / build_default_new_progress_filename(result)
    target = input(f"Ścieżka zapisu CSV [{default_path}]: ").strip()
    output_path = Path(target) if target else default_path
    if not output_path.is_absolute() and len(output_path.parts) == 1:
        output_path = csv_dir / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)

    saved_path = save_new_progress_csv(result, output_path, delimiter=delimiter)
    classes_label = format_classes_for_display(result.included_classes)
    print(f"Zapisano CSV: {saved_path}")
    print(
        f"Wiersze: {len(result.rows)} | "
        f"turnieje: {result.tournaments_processed} | "
        f"kategoria: {result.category} | klasy: {classes_label}"
    )
    return 0


def run_from_args(args: argparse.Namespace, project_dir: Path) -> int:
    """Uruchamia eksport na podstawie argumentów CLI."""
    xlsx_path = Path(args.input_excel) if args.input_excel else project_dir / "data_new.xlsx"
    if not xlsx_path.is_file():
        raise SystemExit(f"Nie znaleziono pliku: {xlsx_path}")

    df = load_xlsx_data(xlsx_path)
    available_years = list_available_years_xlsx(df)
    if not available_years:
        raise SystemExit("Nie znaleziono żadnych sezonów w pliku.")
    if not args.category:
        raise SystemExit(
            "Podaj kategorię przez --category albo uruchom skrypt bez argumentów."
        )

    selected_years = parse_year_arguments(args.years, available_years)
    selected_category = args.category.strip().upper()
    available_classes = list_available_classes_for_category_and_years_xlsx(
        df,
        selected_category,
        selected_years,
    )
    selected_classes = parse_class_arguments(args.classes, available_classes)
    output_path = Path(args.output) if args.output else None

    return run_export(
        xlsx_path=xlsx_path,
        category=selected_category,
        years=selected_years,
        classes=selected_classes,
        output_path=output_path,
        delimiter=args.delimiter,
        project_dir=project_dir,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_argument_parser() -> argparse.ArgumentParser:
    """Buduje parser argumentów skryptu eksportu."""
    parser = argparse.ArgumentParser(
        description="Eksport postępu par turniej po turnieju do CSV (nowy format xlsx)."
    )
    parser.add_argument(
        "--input-excel",
        help="Ścieżka pliku xlsx. Domyślnie: data_new.xlsx.",
    )
    parser.add_argument(
        "--category",
        help="Kategoria bazowa, np. V albo III.",
    )
    parser.add_argument(
        "--years",
        nargs="+",
        help=(
            "Lata lub zakresy lat, np. 2024 2025 albo 2021-2025. "
            "Brak = wszystkie."
        ),
    )
    parser.add_argument(
        "--classes",
        nargs="+",
        help="Klasy do uwzględnienia, np. B A albo S OPEN. Brak = wszystkie.",
    )
    parser.add_argument(
        "--output",
        help="Ścieżka pliku CSV. Brak = nazwa wygenerowana automatycznie.",
    )
    parser.add_argument(
        "--delimiter",
        default=";",
        help='Separator CSV. Domyślnie średnik: ";".',
    )
    return parser


def main() -> None:
    """Punkt wejścia skryptu eksportu CSV."""
    project_dir = Path(__file__).resolve().parent
    parser = build_argument_parser()
    args = parser.parse_args()

    xlsx_path = (
        Path(args.input_excel) if args.input_excel
        else project_dir / "data_new.xlsx"
    )

    has_cli_arguments = bool(
        args.category or args.years or args.classes or args.output
    )
    if has_cli_arguments:
        raise SystemExit(run_from_args(args, project_dir))

    raise SystemExit(run_interactive(project_dir, xlsx_path, args.delimiter))


if __name__ == "__main__":
    main()
