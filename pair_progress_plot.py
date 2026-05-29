"""
Wykres historii rankingu ELO wybranej pary na podstawie CSV z progress_export.py.

Skrypt czyta wiersze eksportu postępu, filtruje występy jednej pary i rysuje
wykres `punkty_po` po kolejnych turniejach z użyciem Seaborn.
"""

from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path
from typing import Iterable


REQUIRED_COLUMNS = {
    "data_turnieju",
    "turniej",
    "podkategoria",
    "lokata",
    "para",
    "tancerz_1",
    "tancerz_2",
    "punkty_po",
}


def normalize_text(value: str) -> str:
    """Normalizuje tekst do porównań odpornych na wielokrotne spacje."""
    return re.sub(r"\s+", " ", value.strip()).casefold()


def parse_number(value: str) -> float:
    """Parsuje liczbę z CSV, akceptując kropkę i przecinek dziesiętny."""
    return float(value.strip().replace(",", "."))


def find_default_csv(project_dir: Path) -> Path:
    """Zwraca najnowszy plik `progress*.csv` w katalogu projektu."""
    candidates = [
        path
        for path in project_dir.glob("progress*.csv")
        if path.is_file() and not path.name.startswith(".~lock.")
    ]
    if not candidates:
        raise FileNotFoundError(
            "Nie podano pliku CSV i nie znaleziono `progress*.csv` w katalogu projektu."
        )
    return max(candidates, key=lambda path: path.stat().st_mtime)


def read_progress_csv(csv_path: Path, delimiter: str) -> list[dict[str, str]]:
    """Wczytuje CSV z progress_export.py i waliduje wymagane kolumny."""
    with csv_path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file, delimiter=delimiter)
        fieldnames = set(reader.fieldnames or [])
        missing = sorted(REQUIRED_COLUMNS - fieldnames)
        if missing:
            raise ValueError(
                "CSV nie wygląda na eksport z progress_export.py. "
                "Brakujące kolumny: " + ", ".join(missing)
            )

        rows: list[dict[str, str]] = []
        for row_number, row in enumerate(reader, start=1):
            cleaned = {key: str(value or "").strip() for key, value in row.items()}
            cleaned["_row_order"] = str(row_number)
            rows.append(cleaned)

    if not rows:
        raise ValueError("CSV nie zawiera żadnych wierszy danych.")
    return rows


def unique_pairs(rows: Iterable[dict[str, str]]) -> list[dict[str, str]]:
    """Zwraca unikalne pary wraz z liczbą występów i zakresem dat."""
    pairs: dict[str, dict[str, str]] = {}
    for row in rows:
        pair_name = row["para"]
        key = normalize_text(pair_name)
        if key not in pairs:
            pairs[key] = {
                "para": pair_name,
                "wystepy": "0",
                "pierwszy": row["data_turnieju"],
                "ostatni": row["data_turnieju"],
            }
        pair_info = pairs[key]
        pair_info["wystepy"] = str(int(pair_info["wystepy"]) + 1)
        if row["data_turnieju"] < pair_info["pierwszy"]:
            pair_info["pierwszy"] = row["data_turnieju"]
        if row["data_turnieju"] > pair_info["ostatni"]:
            pair_info["ostatni"] = row["data_turnieju"]

    return sorted(
        pairs.values(),
        key=lambda item: (item["para"].split(",")[-1].strip(), item["para"]),
    )


def filter_pair_catalog(
    pairs: Iterable[dict[str, str]],
    search_text: str | None,
) -> list[dict[str, str]]:
    """Filtruje katalog par po fragmencie nazwy."""
    if not search_text:
        return list(pairs)
    normalized_search = normalize_text(search_text)
    return [
        pair
        for pair in pairs
        if normalized_search in normalize_text(pair["para"])
    ]


def print_pairs(pairs: Iterable[dict[str, str]], limit: int) -> None:
    """Wypisuje dostępne pary w formacie przydatnym do skopiowania do --pair."""
    for index, pair in enumerate(pairs, start=1):
        if index > limit:
            print(f"... pominięto kolejne pozycje; zwiększ --limit, aby zobaczyć więcej.")
            break
        print(
            f"{index:>3}. {pair['para']} "
            f"| występy: {pair['wystepy']} "
            f"| {pair['pierwszy']} - {pair['ostatni']}"
        )


def pair_rows_by_name(
    rows: Iterable[dict[str, str]],
    pair_name: str,
) -> list[dict[str, str]]:
    """Wyszukuje parę po pełnej nazwie; przy braku wyniku dopuszcza fragment."""
    normalized_pair = normalize_text(pair_name)
    exact_matches = [
        row for row in rows if normalize_text(row["para"]) == normalized_pair
    ]
    if exact_matches:
        return exact_matches

    partial_matches = [
        row for row in rows if normalized_pair in normalize_text(row["para"])
    ]
    matched_pairs = sorted({row["para"] for row in partial_matches})
    if len(matched_pairs) > 1:
        candidates = "\n".join(f"- {pair}" for pair in matched_pairs[:20])
        raise ValueError(
            "Podany fragment pasuje do wielu par. Doprecyzuj --pair.\n" + candidates
        )
    return partial_matches


def pair_rows_by_dancers(
    rows: Iterable[dict[str, str]],
    dancer_1: str,
    dancer_2: str,
) -> list[dict[str, str]]:
    """Wyszukuje parę po dwóch nazwiskach, niezależnie od kolejności."""
    requested = {normalize_text(dancer_1), normalize_text(dancer_2)}
    return [
        row
        for row in rows
        if {normalize_text(row["tancerz_1"]), normalize_text(row["tancerz_2"])}
        == requested
    ]


def sorted_pair_rows(rows: Iterable[dict[str, str]]) -> list[dict[str, str]]:
    """Sortuje występy chronologicznie, zachowując kolejność z CSV dla tej samej daty."""
    return sorted(
        rows,
        key=lambda row: (
            row["data_turnieju"],
            int(row.get("_row_order", "0") or 0),
        ),
    )


def choose_pair_interactively(rows: list[dict[str, str]]) -> str:
    """Prosty wybór pary w terminalu przez wpisanie fragmentu nazwy."""
    pairs = unique_pairs(rows)
    print(f"W CSV znaleziono pary: {len(pairs)}")

    while True:
        search_text = input("Wpisz fragment nazwy pary: ").strip()
        if not search_text:
            print("Podaj przynajmniej fragment nazwiska lub imienia.")
            continue

        matches = filter_pair_catalog(pairs, search_text)
        if not matches:
            print("Brak pasujących par.")
            continue
        if len(matches) == 1:
            selected = matches[0]["para"]
            print(f"Wybrano: {selected}")
            return selected

        print_pairs(matches, limit=20)
        choice = input("Wybierz numer z listy albo wpisz nowy fragment: ").strip()
        if choice.isdigit():
            index = int(choice)
            if 1 <= index <= min(len(matches), 20):
                return matches[index - 1]["para"]
        if choice:
            search_text = choice
            matches = filter_pair_catalog(pairs, search_text)
            if len(matches) == 1:
                selected = matches[0]["para"]
                print(f"Wybrano: {selected}")
                return selected
        print("Nie wybrano poprawnej pozycji.")


def format_tournament_label(row: dict[str, str]) -> str:
    """Buduje etykietę osi X dla pojedynczego występu."""
    category = row["podkategoria"]
    return f"{row['data_turnieju']}\n{row['turniej']} ({category})"


def plot_pair_progress(
    rows: list[dict[str, str]],
    csv_path: Path,
    output_path: Path | None,
    show_plot: bool,
    title: str | None,
) -> None:
    """Rysuje i opcjonalnie zapisuje wykres ELO pary."""
    try:
        import matplotlib

        if output_path and not show_plot:
            matplotlib.use("Agg")

        import matplotlib.pyplot as plt
        import seaborn as sns
    except ModuleNotFoundError as exc:
        missing = exc.name or "seaborn"
        raise SystemExit(
            f"Brak wymaganej paczki `{missing}`. "
            "Zainstaluj zależności poleceniem: "
            "python3 -m pip install seaborn matplotlib"
        ) from exc

    ordered_rows = sorted_pair_rows(rows)
    x_values = list(range(1, len(ordered_rows) + 1))
    y_values = [parse_number(row["punkty_po"]) for row in ordered_rows]
    labels = [format_tournament_label(row) for row in ordered_rows]
    pair_name = ordered_rows[0]["para"]

    sns.set_theme(style="whitegrid", context="notebook")
    width = min(max(10.0, len(ordered_rows) * 1.05), 26.0)
    fig, ax = plt.subplots(figsize=(width, 6.5))

    sns.lineplot(
        x=x_values,
        y=y_values,
        marker="o",
        linewidth=2.4,
        markersize=7,
        ax=ax,
    )

    ax.set_title(title or f"Historia rankingu ELO: {pair_name}", pad=18)
    ax.set_xlabel("Turnieje chronologicznie")
    ax.set_ylabel("Ranking ELO")
    ax.set_xticks(x_values)
    ax.set_xticklabels(labels, rotation=45, ha="right")
    ax.margins(x=0.03)

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

    fig.text(
        0.01,
        0.01,
        f"Źródło: {csv_path.name} | punkty po występie",
        fontsize=8,
        color="dimgray",
    )
    fig.tight_layout(rect=(0, 0.03, 1, 1))

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(output_path, dpi=160, bbox_inches="tight")
        print(f"Zapisano wykres: {output_path}")

    if show_plot:
        plt.show()
    else:
        plt.close(fig)


def resolve_input_path(args: argparse.Namespace, project_dir: Path) -> Path:
    """Ustala plik wejściowy z argumentów albo wybiera najnowszy progress*.csv."""
    raw_path = args.input_path or args.csv_path
    if raw_path:
        return Path(raw_path)
    return find_default_csv(project_dir)


def build_argument_parser() -> argparse.ArgumentParser:
    """Buduje parser argumentów CLI."""
    parser = argparse.ArgumentParser(
        description=(
            "Rysuje wykres historii ELO pary na podstawie CSV z progress_export.py."
        )
    )
    parser.add_argument(
        "csv_path",
        nargs="?",
        help="Ścieżka CSV z progress_export.py. Brak = najnowszy progress*.csv.",
    )
    parser.add_argument(
        "--input",
        dest="input_path",
        help="Ścieżka CSV z progress_export.py.",
    )
    parser.add_argument(
        "--pair",
        help='Nazwa pary z kolumny `para`, np. "Pasiut Paweł, Ziółek Weronika".',
    )
    parser.add_argument(
        "--tancerz1",
        help="Pierwszy tancerz pary; używaj razem z --tancerz2.",
    )
    parser.add_argument(
        "--tancerz2",
        help="Drugi tancerz pary; używaj razem z --tancerz1.",
    )
    parser.add_argument(
        "--list-pairs",
        action="store_true",
        help="Wypisz pary dostępne w CSV zamiast rysować wykres.",
    )
    parser.add_argument(
        "--search",
        help="Filtr tekstowy dla --list-pairs.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Limit pozycji wypisywanych przez --list-pairs. Domyślnie 50.",
    )
    parser.add_argument(
        "--output",
        help="Opcjonalna ścieżka zapisu wykresu, np. wykres.png.",
    )
    parser.add_argument(
        "--show",
        action="store_true",
        help="Pokaż okno wykresu także wtedy, gdy użyto --output.",
    )
    parser.add_argument(
        "--title",
        help="Opcjonalny własny tytuł wykresu.",
    )
    parser.add_argument(
        "--delimiter",
        default=";",
        help='Separator CSV. Domyślnie średnik: ";".',
    )
    return parser


def run_from_args(args: argparse.Namespace, project_dir: Path) -> int:
    """Uruchamia wypisanie par albo rysowanie wykresu."""
    csv_path = resolve_input_path(args, project_dir)
    rows = read_progress_csv(csv_path, args.delimiter)

    if args.list_pairs:
        pairs = filter_pair_catalog(unique_pairs(rows), args.search)
        print(f"Plik: {csv_path}")
        print_pairs(pairs, limit=max(args.limit, 1))
        return 0

    if args.pair:
        pair_rows = pair_rows_by_name(rows, args.pair)
    elif args.tancerz1 and args.tancerz2:
        pair_rows = pair_rows_by_dancers(rows, args.tancerz1, args.tancerz2)
    elif args.tancerz1 or args.tancerz2:
        raise ValueError("Argumenty --tancerz1 i --tancerz2 muszą być podane razem.")
    else:
        selected_pair = choose_pair_interactively(rows)
        pair_rows = pair_rows_by_name(rows, selected_pair)

    if not pair_rows:
        raise ValueError("Nie znaleziono występów wybranej pary w podanym CSV.")

    output_path = Path(args.output) if args.output else None
    show_plot = args.show or output_path is None
    plot_pair_progress(
        rows=pair_rows,
        csv_path=csv_path,
        output_path=output_path,
        show_plot=show_plot,
        title=args.title,
    )
    return 0


def main() -> None:
    """Punkt wejścia skryptu."""
    project_dir = Path(__file__).resolve().parent
    parser = build_argument_parser()
    args = parser.parse_args()

    try:
        raise SystemExit(run_from_args(args, project_dir))
    except (FileNotFoundError, ValueError) as exc:
        raise SystemExit(f"Błąd: {exc}") from exc


if __name__ == "__main__":
    main()
