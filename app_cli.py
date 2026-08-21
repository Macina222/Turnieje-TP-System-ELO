#!/usr/bin/env python3
"""
CLI handlers for App.py extended commands.

This module provides the CLI command implementations that App.py delegates to:
- run_import_sql: Import XLSX to SQLite
- run_migrate: Run/check SQLite migrations
- run_export_progress: Export progress history to CSV
- run_plot: Generate ELO charts for pairs
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add project root to path
_PROJECT_ROOT = Path(__file__).resolve().parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# Add SQL to path
_SQL_DIR = _PROJECT_ROOT / "SQL"
if str(_SQL_DIR) not in sys.path:
    sys.path.insert(0, str(_SQL_DIR))


def run_import_sql(
    xlsx_path: Path,
    db_path: Path,
    sheet: str | None = None,
    replace: bool = False,
) -> int:
    """
    Import official TTP XLSX data to SQLite database.

    Args:
        xlsx_path: Path to source XLSX file
        db_path: Path to target SQLite database
        sheet: Optional sheet name (default: active sheet)
        replace: If True, delete existing database before import

    Returns:
        Exit code (0 = success, 1 = error)
    """
    try:
        from import_official_ttp_to_sqlite import import_xlsx_to_sqlite
    except ImportError as exc:
        print(f"Błąd: Backend SQLite niedostępny: {exc}", file=sys.stderr)
        return 1

    if not xlsx_path.is_file():
        print(f"Błąd: Nie znaleziono pliku XLSX: {xlsx_path}", file=sys.stderr)
        return 1

    try:
        import_xlsx_to_sqlite(xlsx_path, db_path, sheet_name=sheet, replace=replace)
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"Błąd importu: {exc}", file=sys.stderr)
        return 1


def run_migrate(
    db_path: Path,
    target: int | None = None,
    status_only: bool = False,
) -> int:
    """
    Run or check SQLite migrations.

    Args:
        db_path: Path to SQLite database
        target: Target migration version (None = latest)
        status_only: If True, only show status without running

    Returns:
        Exit code (0 = success, 1 = error)
    """
    try:
        from migrations import (
            CURRENT_SCHEMA_VERSION,
            ensure_schema,
            get_applied_migrations,
            get_current_version,
            run_migrations,
        )
    except ImportError as exc:
        print(f"Błąd: Moduł migracji niedostępny: {exc}", file=sys.stderr)
        return 1

    if not db_path.is_file():
        if status_only:
            print(f"Baza nie istnieje: {db_path}")
            return 0
        # Create new database with schema
        try:
            ensure_schema(db_path, target)
            print(f"Utworzono nową bazę: {db_path}")
            return 0
        except Exception as exc:  # noqa: BLE001
            print(f"Błąd tworzenia bazy: {exc}", file=sys.stderr)
            return 1

    try:
        current = get_current_version(db_path)
        applied = get_applied_migrations(db_path)

        if status_only:
            print(f"Obecna wersja: v{current}")
            print(f"Najnowsza wersja: v{CURRENT_SCHEMA_VERSION}")
            print("Zastosowane migracje:")
            if applied:
                for version, name, applied_at in applied:
                    print(f"  v{version}: {name} ({applied_at})")
            else:
                print("  (brak)")
            if current < CURRENT_SCHEMA_VERSION:
                pending = CURRENT_SCHEMA_VERSION - current
                print(f"\nOczekujące migracje: {pending}")
            return 0

        if current >= (target or CURRENT_SCHEMA_VERSION):
            print("Baza jest aktualna (brak migracji do zastosowania).")
            return 0

        applied_versions = run_migrations(db_path, target)
        if applied_versions:
            print(f"Zastosowano migracje: {applied_versions}")
        else:
            print("Brak migracji do zastosowania.")
        return 0

    except Exception as exc:  # noqa: BLE001
        print(f"Błąd migracji: {exc}", file=sys.stderr)
        return 1


def run_export_progress(args: argparse.Namespace, project_dir: Path) -> int:
    """
    Export progress history to CSV.

    Args:
        args: Parsed command-line arguments
        project_dir: Project root directory

    Returns:
        Exit code (0 = success, 1 = error)
    """
    # Determine backend
    backend = args.backend or "xlsx"

    try:
        if backend == "sqlite":
            from sqlite_ranking_service import (
                build_ranking_from_sqlite,
                load_config,
                parse_years_arg,
            )
            from SQL.progress_export_sqlite import write_progress_csv
        else:
            from new_progress_export import (
                build_default_new_progress_filename,
                build_new_progress_export,
                save_new_progress_csv,
            )
            from new_ranking_service import (
                list_available_categories_for_years_xlsx,
                list_available_classes_for_category_and_years_xlsx,
                list_available_years_xlsx,
                load_xlsx_data,
            )

    except ImportError as exc:
        print(f"Błąd: Wymagany moduł niedostępny: {exc}", file=sys.stderr)
        return 1

    # Parse years
    try:
        from new_ranking_service import parse_year_arguments
        if backend == "sqlite":
            from sqlite_ranking_service import get_available_years
            available_years = get_available_years(args.db)
        else:
            xlsx_path = Path(args.input_excel) if args.input_excel else project_dir / "data_new.xlsx"
            df = load_xlsx_data(xlsx_path)
            available_years = list_available_years_xlsx(df)
    except Exception as exc:  # noqa: BLE001
        print(f"Błąd odczytu lat: {exc}", file=sys.stderr)
        return 1

    selected_years = parse_year_arguments(args.years, available_years) if args.years else list(available_years)

    if not selected_years:
        print("Błąd: Brak lat do przetworzenia.", file=sys.stderr)
        return 1

    if not args.category:
        print("Błąd: Wymagana kategoria (--category).", file=sys.stderr)
        return 1

    category = args.category.strip().upper()
    classes = args.classes if args.classes else None
    output_path = Path(args.export_output) if args.export_output else None
    delimiter = args.delimiter

    # Determine default output path
    if not output_path:
        csv_dir = project_dir / "csv"
        csv_dir.mkdir(parents=True, exist_ok=True)
        if backend == "xlsx":
            # We need to build the export first to get the filename
            # For now use a generic name
            output_path = csv_dir / f"progress_{category}_{'_'.join(map(str, selected_years))}.csv"
        else:
            output_path = csv_dir / f"progress_sqlite_{category}_{'_'.join(map(str, selected_years))}.csv"

    try:
        if backend == "xlsx":
            xlsx_path = Path(args.input_excel) if args.input_excel else project_dir / "data_new.xlsx"
            if not xlsx_path.is_file():
                print(f"Błąd: Nie znaleziono pliku: {xlsx_path}", file=sys.stderr)
                return 1

            # Validate category
            available_categories = list_available_categories_for_years_xlsx(df, selected_years)
            if category not in available_categories:
                print(f"Błąd: Kategoria {category} niedostępna. Dostępne: {available_categories}", file=sys.stderr)
                return 1

            # Validate classes
            if classes:
                available_classes = list_available_classes_for_category_and_years_xlsx(df, category, selected_years)
                invalid = [c for c in classes if c.upper() not in [ac.upper() for ac in available_classes]]
                if invalid:
                    print(f"Błąd: Nieznane klasy: {invalid}. Dostępne: {available_classes}", file=sys.stderr)
                    return 1

            result = build_new_progress_export(
                file_path=xlsx_path,
                category=category,
                years=selected_years,
                classes=classes,
            )
            saved_path = save_new_progress_csv(result, output_path, delimiter=delimiter)
            print(f"Zapisano CSV: {saved_path}")
            print(
                f"Wiersze: {len(result.rows)} | turnieje: {result.tournaments_processed} | "
                f"kategoria: {result.category} | klasy: {', '.join(result.included_classes) if result.included_classes else 'wszystkie'}"
            )

        else:
            # SQLite backend
            db_path = Path(args.db)
            if not db_path.is_file():
                print(f"Błąd: Nie znaleziono bazy: {db_path}", file=sys.stderr)
                return 1

            from migrations import ensure_schema
            ensure_schema(db_path)

            config = load_config(args.config) if args.config else load_config()

            # Validate category
            from sqlite_ranking_service import get_available_categories_sqlite
            available_categories = get_available_categories_sqlite(db_path, selected_years)
            if category not in available_categories:
                print(f"Błąd: Kategoria {category} niedostępna. Dostępne: {available_categories}", file=sys.stderr)
                return 1

            # Validate classes
            if classes:
                from sqlite_ranking_service import get_available_classes
                available_classes = get_available_classes(db_path, category, selected_years)
                invalid = [c for c in classes if c.upper() not in [ac.upper() for ac in available_classes]]
                if invalid:
                    print(f"Błąd: Nieznane klasy: {invalid}. Dostępne: {available_classes}", file=sys.stderr)
                    return 1

            run = build_ranking_from_sqlite(
                db_path=db_path,
                category=category,
                years=selected_years,
                classes=classes,
                config=config,
            )
            write_progress_csv(run, output_path, delimiter=delimiter)
            print(f"Zapisano CSV: {output_path}")
            print(f"Wiersze: {len(run.progress_rows)}")

        return 0

    except Exception as exc:  # noqa: BLE001
        print(f"Błąd eksportu: {exc}", file=sys.stderr)
        return 1


def run_plot(args: argparse.Namespace, project_dir: Path) -> int:
    """
    Generate ELO progress charts for pairs.

    Args:
        args: Parsed command-line arguments
        project_dir: Project root directory

    Returns:
        Exit code (0 = success, 1 = error)
    """
    # Determine backend
    backend = args.backend or "xlsx"

    try:
        if backend == "xlsx":
            from new_pair_progress_plot import (
                build_progress_rows,
                filter_pair_catalog,
                normalize_text,
                plot_pair_progress,
                resolve_pair_series,
                unique_pairs,
            )
            from new_ranking_service import (
                list_available_categories_for_years_xlsx,
                list_available_classes_for_category_and_years_xlsx,
                list_available_years_xlsx,
                load_xlsx_data,
            )
        else:
            from sqlite_ranking_service import (
                build_ranking_from_sqlite,
                get_available_categories_sqlite,
                get_available_classes,
                get_available_years,
                load_config,
            )
            from migrations import ensure_schema
            from new_pair_progress_plot import (
                filter_pair_catalog,
                normalize_text,
                plot_pair_progress,
                resolve_pair_series,
                unique_pairs,
            )
    except ImportError as exc:
        print(f"Błąd: Wymagany moduł niedostępny: {exc}", file=sys.stderr)
        return 1

    # Parse years
    try:
        if backend == "sqlite":
            available_years = get_available_years(args.db)
        else:
            xlsx_path = Path(args.input_excel) if args.input_excel else project_dir / "data_new.xlsx"
            df = load_xlsx_data(xlsx_path)
            available_years = list_available_years_xlsx(df)
    except Exception as exc:  # noqa: BLE001
        print(f"Błąd odczytu lat: {exc}", file=sys.stderr)
        return 1

    selected_years = available_years
    if args.years:
        from new_ranking_service import parse_year_arguments
        selected_years = parse_year_arguments(args.years, available_years)

    if not selected_years:
        print("Błąd: Brak lat do przetworzenia.", file=sys.stderr)
        return 1

    if not args.category and not args.list_pairs:
        print("Błąd: Wymagana kategoria (--category).", file=sys.stderr)
        return 1

    category = args.category.strip().upper() if args.category else None
    classes = args.classes if args.classes else None

    # Collect pair selection
    requested_pairs = list(args.pair) if args.pair else []
    requested_pair_ids = list(args.pair_id) if args.pair_id else []
    dancer_1 = args.tancerz1
    dancer_2 = args.tancerz2

    if (dancer_1 and not dancer_2) or (dancer_2 and not dancer_1):
        print("Błąd: --tancerz1 i --tancerz2 muszą być użyte razem.", file=sys.stderr)
        return 1

    try:
        if backend == "xlsx":
            xlsx_path = Path(args.input_excel) if args.input_excel else project_dir / "data_new.xlsx"
            if not xlsx_path.is_file():
                print(f"Błąd: Nie znaleziono pliku: {xlsx_path}", file=sys.stderr)
                return 1

            if not category:
                print("Błąd: Wymagana kategoria (--category).", file=sys.stderr)
                return 1

            # Validate category
            available_categories = list_available_categories_for_years_xlsx(df, selected_years)
            if category not in available_categories:
                print(f"Błąd: Kategoria {category} niedostępna. Dostępne: {available_categories}", file=sys.stderr)
                return 1

            # Validate classes
            if classes:
                available_classes = list_available_classes_for_category_and_years_xlsx(df, category, selected_years)
                invalid = [c for c in classes if c.upper() not in [ac.upper() for ac in available_classes]]
                if invalid:
                    print(f"Błąd: Nieznane klasy: {invalid}. Dostępne: {available_classes}", file=sys.stderr)
                    return 1

            rows = build_progress_rows(
                xlsx_path,
                selected_years,
                category,
                classes,
            )

        else:
            # SQLite backend
            db_path = Path(args.db)
            if not db_path.is_file():
                print(f"Błąd: Nie znaleziono bazy: {db_path}", file=sys.stderr)
                return 1

            ensure_schema(db_path)

            if not category:
                print("Błąd: Wymagana kategoria (--category).", file=sys.stderr)
                return 1

            # Validate category
            available_categories = get_available_categories_sqlite(db_path, selected_years)
            if category not in available_categories:
                print(f"Błąd: Kategoria {category} niedostępna. Dostępne: {available_categories}", file=sys.stderr)
                return 1

            # Validate classes
            if classes:
                available_classes = get_available_classes(db_path, category, selected_years)
                invalid = [c for c in classes if c.upper() not in [ac.upper() for ac in available_classes]]
                if invalid:
                    print(f"Błąd: Nieznane klasy: {invalid}. Dostępne: {available_classes}", file=sys.stderr)
                    return 1

            config = load_config(args.config) if args.config else load_config()
            run = build_ranking_from_sqlite(
                db_path=db_path,
                category=category,
                years=selected_years,
                classes=classes,
                config=config,
            )

            # Convert run.progress_rows to same format as build_progress_rows
            rows = []
            for row in run.progress_rows:
                dancer_1_name, dancer_2_name = row["pair"].split(",")[:2] if "," in row["pair"] else ("", "")
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
                    "tancerz_1": dancer_1_name.strip(),
                    "tancerz_2": dancer_2_name.strip(),
                    "punkty_przed": f"{row['punkty_przed']:.2f}",
                    "punkty_po": f"{row['punkty_po']:.2f}",
                    "roznica_punktow": f"{row['roznica_punktow']:.2f}",
                    "_row_order": str(len(rows) + 1),
                })

    except Exception as exc:  # noqa: BLE001
        print(f"Błąd budowania danych: {exc}", file=sys.stderr)
        return 1

    # List pairs mode
    if args.list_pairs:
        pairs = filter_pair_catalog(unique_pairs(rows), args.search)
        print(f"Plik: {xlsx_path if backend == 'xlsx' else db_path}")
        limit = max(args.limit, 1) if args.limit else 50
        for index, pair in enumerate(pairs, start=1):
            if index > limit:
                print(f"... pominięto kolejne pozycje; zwiększ --limit, aby zobaczyć więcej.")
                break
            print(
                f"{index:>3}. [{pair['pair_id']}] {pair['para']} "
                f"| występy: {pair['wystepy']} "
                f"| turnieje: {pair['pierwszy']} - {pair['ostatni']}"
            )
        return 0

    # Resolve pair selection
    try:
        pair_series = resolve_pair_series(
            rows=rows,
            pair_names=requested_pairs,
            pair_ids=requested_pair_ids,
            dancer_1=dancer_1,
            dancer_2=dancer_2,
        )
    except ValueError as exc:
        print(f"Błąd wyboru par: {exc}", file=sys.stderr)
        return 1

    if not pair_series:
        print("Błąd: Nie wybrano par do wykresu.", file=sys.stderr)
        return 1

    # Resolve output mode
    output_path = None
    show_plot = args.show
    if args.plot_output:
        output_path = Path(args.plot_output)
        if not output_path.is_absolute() and len(output_path.parts) == 1:
            img_dir = project_dir / "img"
            img_dir.mkdir(parents=True, exist_ok=True)
            output_path = img_dir / output_path
        # If --plot-output is given without --show, default to not showing
        if not args.show:
            show_plot = False

    # If neither output nor show specified, prompt (but in CLI non-interactive, default to show)
    if not args.plot_output and not args.show:
        show_plot = True

    source_path = xlsx_path if backend == "xlsx" else db_path

    try:
        plot_pair_progress(
            pair_series=pair_series,
            source_path=source_path,
            config_path=project_dir / "config.txt",
            output_path=output_path,
            show_plot=show_plot,
            title=args.title,
        )
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"Błąd rysowania wykresu: {exc}", file=sys.stderr)
        return 1