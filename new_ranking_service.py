"""
Backend rankingu ELO dla par tańców polskich — wersja na nowy format danych.

Czyta dane z pliku ``data_new.xlsx`` (format kolumn po ``header=3``):
  season, turnament code, turnament name, cat code, pair id, pair, group, rank, …

Moduł udostępnia:
* Funkcje discovery — wykrywanie dostępnych lat, kategorii i klas z xlsx.
* ``build_new_ranking``   — pełny ranking ELO z filtrami lat / kategorii / klas.
* ``build_new_progress_export`` — historia zmian punktów (turniej po turnieju).
* ``save_new_progress_csv``   — zapis historii do CSV.
* ``run_new_ranking``         — prosta funkcja CLI do generowania raportów .txt.
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd

# Dodajemy katalog nadrzędny do ścieżki, żeby móc zaimportować legacy
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from legacy.ranking_service import (
    BASE_CATEGORIES,
    RankingConfig,
    _class_for_filename,
    _class_sort_key,
    aktualizacja_rankingu,
    detect_base_category,
    extract_base_and_class,
    format_class_for_display,
    format_classes_for_display,
    get_default_elo_for_class,
    load_ranking_config,
    normalize_years,
)

# Optional SQLite backend - may not be available if SQL/ is not on path
try:
    import sys
    from pathlib import Path
    sys.path.append(str(Path(__file__).resolve().parent / "SQL"))
    from sqlite_ranking_service import (
        build_ranking_from_sqlite,
        format_ranking_report,
        get_available_years as get_available_years_sqlite,
        get_available_classes as get_available_classes_sqlite,
        fetch_events as fetch_events_sqlite,
        load_config as load_config_sqlite,
        normalize_classes as normalize_classes_sqlite,
    )
    SQLITE_AVAILABLE = True
except ImportError:
    SQLITE_AVAILABLE = False


# ---------------------------------------------------------------------------
# Stałe
# ---------------------------------------------------------------------------

DEFAULT_XLSX_PATH = Path(__file__).resolve().parent / "data_new.xlsx"
DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent / "config.txt"
REQUIRED_XLSX_COLUMNS = {
    "season",
    "turnament code",
    "turnament name",
    "cat code",
    "pair id",
    "pair",
    "rank",
}


# ---------------------------------------------------------------------------
# Narzędzia pomocnicze
# ---------------------------------------------------------------------------

def _validate_xlsx_columns(df: pd.DataFrame) -> None:
    """Sprawdza, czy arkusz ma kolumny wymagane przez nowy backend."""
    missing = sorted(REQUIRED_XLSX_COLUMNS - set(df.columns))
    if missing:
        raise ValueError(
            "Plik xlsx nie ma wymaganych kolumn: " + ", ".join(missing)
        )


def _filter_by_years(
    df: pd.DataFrame,
    years: Iterable[int | str] | None,
) -> pd.DataFrame:
    """Zwraca dane zawężone do wskazanych sezonów."""
    if years is None:
        return df
    year_set = set(normalize_years(years))
    if not year_set:
        return df.iloc[0:0]
    return df[df["season"].isin(year_set)]


def _normalize_base_category(category: str | None) -> str | None:
    """Normalizuje kategorię wejściową do bazowej kategorii I–VIII."""
    if category is None or not str(category).strip():
        return None
    base_category = detect_base_category(str(category).strip())
    if not base_category:
        raise ValueError(f"Nieznana kategoria rankingu: {category}")
    return base_category


def _normalize_class_filter(classes: Iterable[str] | None) -> set[str] | None:
    """Normalizuje filtr klas; None oznacza wszystkie klasy."""
    if classes is None:
        return None
    return {str(klasa).strip().upper() for klasa in classes if str(klasa).strip()}


def _sort_classes(classes: Iterable[str]) -> tuple[str, ...]:
    """Sortuje klasy dokładnie tak jak legacy."""
    return tuple(sorted(classes, key=_class_sort_key))


def _split_pair_name(pair_name: str) -> tuple[str, str]:
    """Rozbija pole pary na dwóch tancerzy, jeśli separator jest jednoznaczny."""
    parts = [part.strip() for part in str(pair_name).split(",")]
    if len(parts) != 2:
        return "", ""
    return parts[0], parts[1]


def _format_years_for_filename(years: Iterable[int]) -> str:
    """Buduje fragment nazwy pliku z listy lat."""
    year_tuple = tuple(years)
    if len(year_tuple) == 1:
        return str(year_tuple[0])
    if len(year_tuple) <= 4:
        return "_".join(str(year) for year in year_tuple)
    return f"{year_tuple[0]}-{year_tuple[-1]}_{len(year_tuple)}lat"


# ---------------------------------------------------------------------------
# Modele danych (wynikowe)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class NewRankingEntry:
    """Jeden wiersz finalnego rankingu."""
    pair_id: str
    pair_name: str
    elo: float
    klasa: str
    base_category: str


@dataclass(frozen=True)
class NewRankingBuildResult:
    """Wynik budowania rankingu dla jednej kategorii bazowej."""
    category: str
    years: tuple[int, ...]
    ranking: tuple[NewRankingEntry, ...]
    included_categories: tuple[str, ...]
    included_classes: tuple[str, ...]
    tournaments_processed: int
    source: str = "xlsx"


@dataclass(frozen=True)
class NewTournamentProgressRow:
    """Zmiana punktów jednej pary po jednym turnieju."""
    year: int
    tournament_order: int
    tournament_code: str
    tournament_name: str
    category: str
    exact_category: str
    klasa: str
    place: int
    pair_id: str
    pair_name: str
    points_before: float
    points_after: float
    points_delta: float


@dataclass(frozen=True)
class NewProgressExportResult:
    """Pełny rezultat budowania historii zmian punktów."""
    category: str
    years: tuple[int, ...]
    rows: tuple[NewTournamentProgressRow, ...]
    included_categories: tuple[str, ...]
    included_classes: tuple[str, ...]
    tournaments_processed: int


# ---------------------------------------------------------------------------
# Ładowanie danych
# ---------------------------------------------------------------------------

def load_xlsx_data(file_path: str | Path | None = None) -> pd.DataFrame:
    """
    Wczytuje ``data_new.xlsx`` i zwraca DataFrame posortowany chronologicznie.

    W pliku xlsx najnowsze turnieje są na górze — odwracamy kolejność,
    żeby przetwarzać od najstarszych.
    """
    path = Path(file_path) if file_path else DEFAULT_XLSX_PATH
    df = pd.read_excel(path, header=3)
    _validate_xlsx_columns(df)
    # Odwracamy — najstarsze na początek
    df = df.iloc[::-1].reset_index(drop=True)
    return df


# ---------------------------------------------------------------------------
# Funkcje discovery
# ---------------------------------------------------------------------------

def list_available_years_xlsx(
    df: pd.DataFrame | None = None,
    file_path: str | Path | None = None,
) -> list[int]:
    """Zwraca posortowaną listę lat (sezonów) dostępnych w danych."""
    if df is None:
        df = load_xlsx_data(file_path)
    return sorted(int(s) for s in df["season"].dropna().unique())


def list_available_categories_for_years_xlsx(
    df: pd.DataFrame | None = None,
    years: Iterable[int] | None = None,
    file_path: str | Path | None = None,
) -> list[str]:
    """
    Wykrywa bazowe kategorie (I–VIII) dostępne dla wskazanych lat.

    Zwraca je w kolejności zdefiniowanej przez ``BASE_CATEGORIES``.
    """
    if df is None:
        df = load_xlsx_data(file_path)
    filtered = _filter_by_years(df, years)

    found: set[str] = set()
    for cat_code in filtered["cat code"].dropna().unique():
        base, _ = extract_base_and_class(str(cat_code))
        if base:
            found.add(base)
    return [cat for cat in BASE_CATEGORIES if cat in found]


def list_available_classes_for_category_and_years_xlsx(
    df: pd.DataFrame | None = None,
    base_category: str = "",
    years: Iterable[int] | None = None,
    file_path: str | Path | None = None,
) -> list[str]:
    """
    Wykrywa klasy (B, A, S, OPEN, …) dostępne dla kategorii bazowej i lat.

    Klasy sortowane są według CLASS_ORDER.
    """
    if df is None:
        df = load_xlsx_data(file_path)
    filtered = _filter_by_years(df, years)
    normalized_category = _normalize_base_category(base_category)

    found: set[str] = set()
    for cat_code in filtered["cat code"].dropna().unique():
        base, klasa = extract_base_and_class(str(cat_code))
        if base == normalized_category:
            found.add(klasa)
    return list(_sort_classes(found))


# ---------------------------------------------------------------------------
# Wewnętrzna funkcja przetwarzania turniejów
# ---------------------------------------------------------------------------

def _process_tournaments(
    df: pd.DataFrame,
    config: RankingConfig,
    *,
    years: Iterable[int | str] | None = None,
    category: str | None = None,
    classes: Iterable[str] | None = None,
    track_progress: bool = False,
) -> tuple[
    dict[tuple[str, str], float],   # (pair_id, base_cat) -> elo
    dict[tuple[str, str], str],     # (pair_id, base_cat) -> klasa
    dict[str, str],                 # pair_id -> pair_name
    list[NewTournamentProgressRow], # progress rows
    set[str],                       # included exact categories
    set[str],                       # included classes
    int,                            # tournaments processed
]:
    """
    Iteruje po grupach (sezon, turniej, kategoria) i oblicza ELO.

    Zwraca surowe dane potrzebne do budowy rankingu albo eksportu postępu.
    """
    df = _filter_by_years(df, years)
    target_base = _normalize_base_category(category)
    selected_classes = _normalize_class_filter(classes)

    # Stan ELO
    elos: dict[tuple[str, str], float] = {}
    pair_classes: dict[tuple[str, str], str] = {}
    pair_names: dict[str, str] = {}

    progress_rows: list[NewTournamentProgressRow] = []
    included_categories: set[str] = set()
    included_classes: set[str] = set()
    tournaments_processed = 0

    groups = df.groupby(["season", "turnament code", "cat code"], sort=False)

    for (season, t_code, cat_code), group in groups:
        cat_code_str = str(cat_code)
        base_cat, klasa = extract_base_and_class(cat_code_str)
        if not base_cat:
            continue

        if target_base and base_cat != target_base:
            continue

        if selected_classes is not None and klasa not in selected_classes:
            continue

        lista_do_kalkulatora: list[dict] = []
        entry_data: list[tuple[str, str, int]] = []  # (pair_id, pair_name, rank)
        points_before_list: list[float] = []

        for _, row in group.sort_values("rank", kind="stable").iterrows():
            if pd.isna(row["pair id"]):
                continue

            try:
                pair_id = str(int(float(row["pair id"])))
            except (ValueError, TypeError):
                pair_id = str(row["pair id"]).strip()

            try:
                rank = int(row["rank"])
            except (ValueError, TypeError) as exc:
                raise ValueError(
                    "Nieprawidłowa lokata w arkuszu dla "
                    f"{season}/{t_code}/{cat_code_str}: {row['rank']!r}"
                ) from exc
            pair_name = str(row["pair"]).strip()
            if not pair_id or not pair_name:
                continue

            pair_names[pair_id] = pair_name

            key = (pair_id, base_cat)

            if key not in elos:
                elos[key] = get_default_elo_for_class(
                    klasa, config.class_default_elos
                )
                pair_classes[key] = klasa

            points_before_list.append(elos[key])
            lista_do_kalkulatora.append({
                "id": pair_id,
                "elo": elos[key],
                "place": rank,
            })
            entry_data.append((pair_id, pair_name, rank))

        if not lista_do_kalkulatora:
            continue

        included_categories.add(cat_code_str.upper())
        included_classes.add(klasa)
        current_tournament_order = tournaments_processed + 1

        aktualizacja_rankingu(
            lista_do_kalkulatora, config.k_factor, config.d_factor
        )

        t_name = str(group.iloc[0].get("turnament name", t_code))

        for i, wpis in enumerate(lista_do_kalkulatora):
            pid = wpis["id"]
            new_elo = float(wpis["elo"])
            elos[(pid, base_cat)] = new_elo

            if track_progress:
                p_id, p_name, p_rank = entry_data[i]
                progress_rows.append(
                    NewTournamentProgressRow(
                        year=int(season),
                        tournament_order=current_tournament_order,
                        tournament_code=str(t_code),
                        tournament_name=t_name,
                        category=base_cat,
                        exact_category=cat_code_str.upper(),
                        klasa=klasa,
                        place=p_rank,
                        pair_id=p_id,
                        pair_name=p_name,
                        points_before=points_before_list[i],
                        points_after=new_elo,
                        points_delta=new_elo - points_before_list[i],
                    )
                )

        tournaments_processed += 1

    return (
        elos,
        pair_classes,
        pair_names,
        progress_rows,
        included_categories,
        included_classes,
        tournaments_processed,
    )


# ---------------------------------------------------------------------------
# Budowanie rankingu
# ---------------------------------------------------------------------------

def build_new_ranking(
    file_path: str | Path | None = None,
    years: Iterable[int | str] | None = None,
    category: str | None = None,
    classes: Iterable[str] | None = None,
    config_path: str | Path | None = None,
    backend: str = "xlsx",
    db_path: str | Path | None = None,
) -> NewRankingBuildResult:
    """
    Buduje ranking ELO dla wybranej kategorii, lat i klas.

    Parametry:
    - file_path: ścieżka do pliku XLSX (dla backend="xlsx")
    - years: lista lat/sezonów
    - category: kategoria bazowa (I-VIII)
    - classes: lista klas do uwzględnienia
    - config_path: ścieżka do pliku config.txt
    - backend: "xlsx" (domyślnie) lub "sqlite"
    - db_path: ścieżka do bazy SQLite (wymagane dla backend="sqlite")
    """
    if backend == "sqlite":
        return _build_ranking_sqlite(
            db_path=db_path,
            years=years,
            category=category,
            classes=classes,
            config_path=config_path,
        )

    # XLSX backend (default)
    df = load_xlsx_data(file_path)
    config = load_ranking_config(config_path or DEFAULT_CONFIG_PATH)

    selected_years = (
        normalize_years(years)
        if years is not None
        else tuple(list_available_years_xlsx(df))
    )
    if not selected_years:
        raise ValueError("Wybierz przynajmniej jeden rok.")
    base_cat = _normalize_base_category(category)

    elos, pair_classes, pair_names, _, inc_cats, inc_classes, t_count = (
        _process_tournaments(
            df, config,
            years=selected_years,
            category=category,
            classes=classes,
            track_progress=False,
        )
    )

    ranking_entries: list[NewRankingEntry] = []
    for (pid, bcat), elo in elos.items():
        if base_cat and bcat != base_cat:
            continue
        ranking_entries.append(
            NewRankingEntry(
                pair_id=pid,
                pair_name=pair_names.get(pid, "?"),
                elo=elo,
                klasa=pair_classes.get((pid, bcat), ""),
                base_category=bcat,
            )
        )

    ranking_entries.sort(key=lambda e: e.elo, reverse=True)

    if category and not inc_cats:
        years_label = ", ".join(str(year) for year in selected_years)
        raise ValueError(
            f"Brak danych dla kategorii {base_cat} w latach: {years_label}."
        )

    return NewRankingBuildResult(
        category=base_cat or "WSZYSTKIE",
        years=selected_years,
        ranking=tuple(ranking_entries),
        included_categories=tuple(sorted(inc_cats)),
        included_classes=_sort_classes(inc_classes),
        tournaments_processed=t_count,
    )


def _build_ranking_sqlite(
    db_path: str | Path | None = None,
    years: Iterable[int | str] | None = None,
    category: str | None = None,
    classes: Iterable[str] | None = None,
    config_path: str | Path | None = None,
) -> NewRankingBuildResult:
    """Buduje ranking używając backendu SQLite."""
    if not SQLITE_AVAILABLE:
        raise RuntimeError(
            "Backend SQLite niedostępny. Upewnij się, że moduł SQL/sqlite_ranking_service.py jest dostępny."
        )
    if db_path is None:
        raise ValueError("Dla backend='sqlite' wymagany jest parametr db_path.")

    config = load_config_sqlite(config_path or DEFAULT_CONFIG_PATH)

    selected_years = normalize_years(years) if years is not None else get_available_years_sqlite(db_path)
    if not selected_years:
        raise ValueError("Wybierz przynajmniej jeden rok.")

    base_cat = _normalize_base_category(category)
    if not base_cat:
        raise ValueError("Dla backend='sqlite' wymagany jest parametr category.")

    # Get available classes for validation
    selected_classes = normalize_classes_sqlite(classes) if classes is not None else get_available_classes_sqlite(db_path, base_cat, selected_years)

    run = build_ranking_from_sqlite(
        db_path=db_path,
        category=base_cat,
        years=selected_years,
        classes=selected_classes,
        config=config,
    )

    # Convert SQLite results to NewRankingBuildResult format
    ranking_entries: list[NewRankingEntry] = []
    for rating in run.ratings.values():
        ranking_entries.append(
            NewRankingEntry(
                pair_id=str(rating.pair_id),
                pair_name=rating.display_name,
                elo=rating.rating,
                klasa=rating.last_class or "",
                base_category=rating.last_category or base_cat,
            )
        )

    ranking_entries.sort(key=lambda e: e.elo, reverse=True)

    included_categories = sorted({event.cat_code for event in run.processed_events})
    included_classes = _sort_classes(run.classes) if run.classes else tuple()

    return NewRankingBuildResult(
        category=base_cat,
        years=tuple(selected_years),
        ranking=tuple(ranking_entries),
        included_categories=tuple(included_categories),
        included_classes=included_classes,
        tournaments_processed=len(run.processed_events),
        source="sqlite",
    )


# ---------------------------------------------------------------------------
# Eksport historii zmian (progress)
# ---------------------------------------------------------------------------

def build_new_progress_export(
    file_path: str | Path | None = None,
    years: Iterable[int | str] | None = None,
    category: str | None = None,
    classes: Iterable[str] | None = None,
    config_path: str | Path | None = None,
) -> NewProgressExportResult:
    """
    Buduje historię zmian punktów par po każdym turnieju.

    Odpowiednik ``build_progress_export`` z legacy, ale czyta z xlsx.
    """
    df = load_xlsx_data(file_path)
    config = load_ranking_config(config_path or DEFAULT_CONFIG_PATH)

    selected_years = (
        normalize_years(years)
        if years is not None
        else tuple(list_available_years_xlsx(df))
    )
    if not selected_years:
        raise ValueError("Wybierz przynajmniej jeden rok.")
    base_cat = _normalize_base_category(category)

    _, _, _, rows, inc_cats, inc_classes, t_count = _process_tournaments(
        df, config,
        years=selected_years,
        category=category,
        classes=classes,
        track_progress=True,
    )

    if category and not inc_cats:
        years_label = ", ".join(str(year) for year in selected_years)
        raise ValueError(
            f"Brak danych dla kategorii {base_cat} w latach: {years_label}."
        )

    return NewProgressExportResult(
        category=base_cat or "WSZYSTKIE",
        years=selected_years,
        rows=tuple(rows),
        included_categories=tuple(sorted(inc_cats)),
        included_classes=_sort_classes(inc_classes),
        tournaments_processed=t_count,
    )


# ---------------------------------------------------------------------------
# Zapis do CSV
# ---------------------------------------------------------------------------

def build_default_new_progress_filename(result: NewProgressExportResult) -> str:
    """Tworzy domyślną nazwę pliku CSV z kategorii, klas i zakresu lat."""
    if result.included_classes:
        classes_part = "_".join(
            _class_for_filename(klasa) for klasa in result.included_classes
        )
    else:
        classes_part = "wszystkie"

    years_part = _format_years_for_filename(result.years)

    return f"progress_new_{result.category.lower()}_{classes_part}_{years_part}.csv"


def build_default_new_output_filename(result: NewRankingBuildResult) -> str:
    """Tworzy domyślną nazwę pliku raportu rankingu."""
    if result.included_classes:
        classes_part = "_".join(
            _class_for_filename(klasa) for klasa in result.included_classes
        )
    else:
        classes_part = "wszystkie"

    years_part = _format_years_for_filename(result.years)
    return f"ranking_new_{result.category.lower()}_{classes_part}_{years_part}.txt"


def save_new_progress_csv(
    result: NewProgressExportResult,
    output_path: str | Path,
    delimiter: str = ";",
    encoding: str = "utf-8-sig",
) -> Path:
    """Zapisuje historię zmian punktów do pliku CSV."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "rok",
        "kolejnosc_turnieju",
        "kod_turnieju",
        "turniej",
        "kategoria_bazowa",
        "podkategoria",
        "klasa",
        "lokata",
        "pair_id",
        "para",
        "tancerz_1",
        "tancerz_2",
        "punkty_przed",
        "punkty_po",
        "roznica_punktow",
    ]

    with path.open("w", encoding=encoding, newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames, delimiter=delimiter)
        writer.writeheader()
        for row in result.rows:
            dancer_1, dancer_2 = _split_pair_name(row.pair_name)
            writer.writerow({
                "rok": row.year,
                "kolejnosc_turnieju": row.tournament_order,
                "kod_turnieju": row.tournament_code,
                "turniej": row.tournament_name,
                "kategoria_bazowa": row.category,
                "podkategoria": row.exact_category,
                "klasa": row.klasa if row.klasa else "-",
                "lokata": row.place,
                "pair_id": row.pair_id,
                "para": row.pair_name,
                "tancerz_1": dancer_1,
                "tancerz_2": dancer_2,
                "punkty_przed": f"{row.points_before:.2f}",
                "punkty_po": f"{row.points_after:.2f}",
                "roznica_punktow": f"{row.points_delta:.2f}",
            })

    return path


def save_new_ranking_report(
    report_text: str,
    output_path: str | Path,
    encoding: str = "utf-8",
) -> Path:
    """Zapisuje raport tekstowy rankingu do pliku."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report_text, encoding=encoding)
    return path


# ---------------------------------------------------------------------------
# Formatowanie raportów tekstowych
# ---------------------------------------------------------------------------

def format_new_ranking_report(result: NewRankingBuildResult) -> str:
    """Buduje pełny raport tekstowy na podstawie wyniku rankingu."""
    classes_label = format_classes_for_display(result.included_classes)
    header = f"{'Miejsce':<8} | {'Para':<50} | {'ELO':<10} | Klasa"
    separator = "-" * 82
    lines = [
        f"Kategoria bazowa: {result.category}",
        f"Klasy: {classes_label}",
        f"Lata: {', '.join(str(y) for y in result.years)}",
        f"Przetworzone turnieje: {result.tournaments_processed}",
        f"Uwzględnione kategorie: "
        + (", ".join(result.included_categories) if result.included_categories else "brak"),
        "",
        f"Raport wygenerowany z: {'SQLite' if result.source == 'sqlite' else 'data_new.xlsx'}",
        "",
        header,
        separator,
    ]

    if not result.ranking:
        lines.append("Brak wyników dla wybranych filtrów.")
    else:
        for place, entry in enumerate(result.ranking, start=1):
            klasa_display = format_class_for_display(entry.klasa)
            lines.append(
                f"{place:<8} | {entry.pair_name:<50} | {entry.elo:<10.2f} | {klasa_display}"
            )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Funkcja CLI — generowanie raportów .txt
# ---------------------------------------------------------------------------

def run_new_ranking(
    file_path: str | Path | None = None,
    output_dir: str = "txt",
    years: Iterable[int | str] | None = None,
    category: str | None = None,
    classes: Iterable[str] | None = None,
) -> None:
    """
    Generuje raporty ranking .txt dla wybranej kategorii / lat / klas.

    Jeśli ``category`` nie jest podane, generuje ranking dla każdej
    znalezionej kategorii bazowej (zachowanie domyślne).
    """
    xlsx_path = file_path or DEFAULT_XLSX_PATH
    print(f"Wczytywanie danych z {xlsx_path}...")
    df = load_xlsx_data(xlsx_path)

    config_path = DEFAULT_CONFIG_PATH
    selected_years = (
        normalize_years(years)
        if years is not None
        else tuple(list_available_years_xlsx(df))
    )

    generate_all_categories = category is None
    if category:
        categories_to_process = [category]
    else:
        categories_to_process = list_available_categories_for_years_xlsx(
            df, selected_years
        )

    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    print(f"Lata: {', '.join(str(y) for y in selected_years)}")
    print(f"Kategorie: {', '.join(categories_to_process)}")
    print("Przetwarzanie turniejów...")

    for cat in categories_to_process:
        try:
            result = build_new_ranking(
                file_path=xlsx_path,
                years=selected_years,
                category=cat,
                classes=classes,
                config_path=config_path,
            )
        except ValueError as exc:
            if generate_all_categories and classes is not None:
                print(f"Pominięto kategorię {cat}: {exc}")
                continue
            raise
        report_text = format_new_ranking_report(result)
        out_file = out_path / build_default_new_output_filename(result)
        save_new_ranking_report(report_text, out_file)
        print(f"Utworzono: {out_file} ({len(result.ranking)} par)")


def parse_years_text(value: str, available_years: list[int]) -> list[int]:
    """
    Zamienia tekst z latami na listę sezonów.

    Obsługuje pojedyncze lata, listy po przecinku i zakresy typu ``2021-2025``.
    """
    text = value.strip()
    if not text:
        raise ValueError("Nie podano lat.")
    if text.lower() in {"all", "wszystkie", "*"}:
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
    """Parsuje argument ``--years``; brak argumentu oznacza wszystkie lata."""
    if not values:
        return list(available_years)
    return parse_years_text(",".join(values), available_years)


def parse_classes_text(value: str, available_classes: list[str]) -> list[str] | None:
    """Parsuje klasy z tekstu użytkownika; None oznacza wszystkie klasy."""
    text = value.strip()
    if not text:
        return None
    if text.lower() in {"all", "wszystkie", "*"}:
        return None

    available_upper = [klasa.upper() for klasa in available_classes]
    selected: list[str] = []
    for chunk in text.replace(";", ",").split(","):
        part = chunk.strip()
        if not part:
            continue
        if part.isdigit():
            index = int(part)
            if 1 <= index <= len(available_classes):
                klasa = available_classes[index - 1]
            else:
                raise ValueError(f"Numer klasy {index} jest poza zakresem.")
        else:
            upper = part.upper()
            if upper not in available_upper:
                raise ValueError(f"Nieznana klasa: {part}")
            klasa = available_classes[available_upper.index(upper)]

        if klasa not in selected:
            selected.append(klasa)

    return selected if selected else None


def parse_class_arguments(
    values: list[str] | None,
    available_classes: list[str],
) -> list[str] | None:
    """Parsuje argument ``--classes``; brak argumentu oznacza wszystkie klasy."""
    if not values:
        return None
    return parse_classes_text(",".join(values), available_classes)


def prompt_until_valid(prompt: str, parser) -> object:
    """Powtarza pytanie, dopóki parser nie zaakceptuje wartości."""
    while True:
        raw_value = input(prompt).strip()
        try:
            return parser(raw_value)
        except ValueError as exc:
            print(f"Błąd: {exc}")


def prompt_for_years(available_years: list[int]) -> list[int]:
    """Pyta użytkownika o sezony do rankingu."""
    print("Dostępne lata:")
    print(", ".join(str(year) for year in available_years))
    print("Wpisz np. 2024,2025 albo 2021-2025 albo all")
    return prompt_until_valid(
        "Lata do uwzględnienia: ",
        lambda value: parse_years_text(value, available_years),
    )


def prompt_for_category(categories: list[str]) -> str:
    """Pyta użytkownika o kategorię bazową."""
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
        normalized = _normalize_base_category(text)
        if normalized in categories:
            return normalized
        raise ValueError("Nieznana kategoria.")

    return prompt_until_valid("Kategoria (numer lub symbol): ", parse_category)


def prompt_for_classes(available_classes: list[str]) -> list[str] | None:
    """Pyta użytkownika o opcjonalny filtr klas."""
    if not available_classes:
        return None
    print("Dostępne klasy:")
    for index, klasa in enumerate(available_classes, start=1):
        print(f"  {index}. {format_class_for_display(klasa)}")
    print(
        "Wpisz numery lub symbole klas rozdzielone przecinkami, "
        "np. B,A lub all"
    )
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


def run_cli_interactive(project_dir: Path, xlsx_path: Path) -> int:
    """Uruchamia interaktywny tryb terminalowy bez GUI."""
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
        years=selected_years,
        category=selected_category,
        classes=selected_classes,
    )
    report = format_new_ranking_report(result)

    print()
    print(report)
    print()

    if prompt_yes_no("Zapisać ranking do pliku?", default=True):
        default_path = project_dir / "txt" / build_default_new_output_filename(result)
        default_path.parent.mkdir(parents=True, exist_ok=True)
        target = input(f"Ścieżka zapisu [{default_path}]: ").strip()
        output_path = Path(target) if target else default_path
        if not output_path.is_absolute() and len(output_path.parts) == 1:
            output_path = project_dir / "txt" / output_path
        saved_path = save_new_ranking_report(report, output_path)
        print(f"Zapisano do: {saved_path}")

    return 0


def _all_classes_for_years(df: pd.DataFrame, years: Iterable[int]) -> list[str]:
    """Zwraca klasy dostępne w wybranych latach, niezależnie od kategorii."""
    found: set[str] = set()
    for cat_code in _filter_by_years(df, years)["cat code"].dropna().unique():
        _, klasa = extract_base_and_class(str(cat_code))
        found.add(klasa)
    return list(_sort_classes(found))


def run_cli_from_args(args: argparse.Namespace, project_dir: Path) -> int:
    """Uruchamia ranking na podstawie argumentów CLI."""
    xlsx_path = (
        Path(args.input_excel) if args.input_excel
        else project_dir / "data_new.xlsx"
    )
    if not xlsx_path.is_file():
        raise FileNotFoundError(f"Nie znaleziono pliku: {xlsx_path}")

    df = load_xlsx_data(xlsx_path)
    available_years = list_available_years_xlsx(df)
    if not available_years:
        raise ValueError("Nie znaleziono żadnych sezonów w pliku.")

    selected_years = parse_year_arguments(args.years, available_years)

    if args.all_categories:
        if args.output:
            raise ValueError("--output jest dostępne tylko dla jednej kategorii.")
        available_classes = _all_classes_for_years(df, selected_years)
        selected_classes = parse_class_arguments(args.classes, available_classes)
        output_dir = Path(args.output_dir)
        if not output_dir.is_absolute():
            output_dir = project_dir / output_dir
        run_new_ranking(
            file_path=xlsx_path,
            output_dir=str(output_dir),
            years=selected_years,
            category=None,
            classes=selected_classes,
        )
        return 0

    if not args.category:
        raise ValueError(
            "Podaj kategorię przez --category albo użyj --all-categories."
        )

    selected_category = _normalize_base_category(args.category)
    available_classes = list_available_classes_for_category_and_years_xlsx(
        df,
        selected_category,
        selected_years,
    )
    selected_classes = parse_class_arguments(args.classes, available_classes)

    result = build_new_ranking(
        file_path=xlsx_path,
        years=selected_years,
        category=selected_category,
        classes=selected_classes,
    )
    report = format_new_ranking_report(result)
    print(report)

    if args.output:
        output_path = Path(args.output)
        if not output_path.is_absolute() and len(output_path.parts) == 1:
            output_path = project_dir / "txt" / output_path
        saved_path = save_new_ranking_report(report, output_path)
        print()
        print(f"Zapisano do: {saved_path}")

    return 0


def build_argument_parser() -> argparse.ArgumentParser:
    """Buduje parser argumentów dla terminalowego rankingu nowego formatu."""
    parser = argparse.ArgumentParser(
        description="Kalkulator rankingu ELO dla data_new.xlsx."
    )
    parser.add_argument(
        "--input-excel",
        help="Ścieżka pliku xlsx. Domyślnie: data_new.xlsx.",
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
    return parser


def main() -> None:
    """Punkt wejścia CLI bez GUI."""
    project_dir = Path(__file__).resolve().parent
    parser = build_argument_parser()
    args = parser.parse_args()
    xlsx_path = (
        Path(args.input_excel) if args.input_excel
        else project_dir / "data_new.xlsx"
    )

    has_cli_arguments = bool(
        args.category or args.years or args.classes or args.output or args.all_categories
    )

    try:
        if has_cli_arguments:
            raise SystemExit(run_cli_from_args(args, project_dir))
        raise SystemExit(run_cli_interactive(project_dir, xlsx_path))
    except (FileNotFoundError, ImportError, ValueError) as exc:
        raise SystemExit(f"Błąd: {exc}") from exc


if __name__ == "__main__":
    main()
