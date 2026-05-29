"""
Wykres historii rankingu ELO wybranych par na podstawie CSV z progress_export.py.

Skrypt czyta wiersze eksportu postępu, filtruje występy jednej albo kilku par
i rysuje wykres `punkty_po` po kolejnych turniejach z użyciem Seaborn.
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import tempfile
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


def slugify_filename_part(value: str, fallback: str = "wykres") -> str:
    """Zamienia tekst na bezpieczny fragment nazwy pliku."""
    slug = re.sub(r"[^\w]+", "_", normalize_text(value), flags=re.UNICODE)
    slug = slug.strip("_")
    return slug or fallback


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


def choose_pairs_interactively(rows: list[dict[str, str]]) -> list[str]:
    """Prosty wybór jednej lub wielu par w terminalu przez fragment nazwy."""
    pairs = unique_pairs(rows)
    selected_pairs: list[str] = []
    print(f"W CSV znaleziono pary: {len(pairs)}")

    while True:
        if selected_pairs:
            prompt = (
                "Wpisz fragment kolejnej pary "
                "(Enter = rysuj wybrane pary): "
            )
        else:
            prompt = "Wpisz fragment nazwy pary: "
        search_text = input(prompt).strip()
        if not search_text:
            if selected_pairs:
                return selected_pairs
            print("Podaj przynajmniej fragment nazwiska lub imienia.")
            continue

        matches = [
            pair
            for pair in filter_pair_catalog(pairs, search_text)
            if pair["para"] not in selected_pairs
        ]
        if not matches:
            print("Brak nowych pasujących par.")
            continue
        if len(matches) == 1:
            selected = matches[0]["para"]
            selected_pairs.append(selected)
            print(f"Dodano: {selected}")
            continue

        print_pairs(matches, limit=20)
        choice = input("Wybierz numer z listy albo wpisz nowy fragment: ").strip()
        if choice.isdigit():
            index = int(choice)
            if 1 <= index <= min(len(matches), 20):
                selected = matches[index - 1]["para"]
                selected_pairs.append(selected)
                print(f"Dodano: {selected}")
                continue
        if choice:
            search_text = choice
            matches = [
                pair
                for pair in filter_pair_catalog(pairs, search_text)
                if pair["para"] not in selected_pairs
            ]
            if len(matches) == 1:
                selected = matches[0]["para"]
                selected_pairs.append(selected)
                print(f"Dodano: {selected}")
                continue
        print("Nie wybrano poprawnej pozycji.")


def format_tournament_label(row: dict[str, str]) -> str:
    """Buduje etykietę osi X dla pojedynczego występu."""
    category = row["podkategoria"]
    return f"{row['data_turnieju']}\n{row['turniej']} ({category})"


def tournament_key(row: dict[str, str]) -> str:
    """Zwraca stabilny klucz turnieju/kategorii dla wspólnej osi X."""
    source_file = row.get("plik", "")
    if source_file:
        return source_file
    return "|".join([row["data_turnieju"], row["turniej"], row["podkategoria"]])


def row_order(row: dict[str, str]) -> int:
    """Zwraca kolejność wiersza w CSV jako liczbę."""
    return int(row.get("_row_order", "0") or 0)


def build_tournament_axis(
    pair_series: list[tuple[str, list[dict[str, str]]]],
) -> tuple[dict[str, int], list[str]]:
    """Buduje wspólną chronologiczną oś X z sumy występów wybranych par."""
    tournaments: dict[str, dict[str, str]] = {}
    for _, rows in pair_series:
        for row in sorted_pair_rows(rows):
            key = tournament_key(row)
            if key not in tournaments:
                tournaments[key] = row

    ordered_keys = sorted(
        tournaments,
        key=lambda key: (
            tournaments[key]["data_turnieju"],
            row_order(tournaments[key]),
        ),
    )
    x_by_key = {key: index for index, key in enumerate(ordered_keys, start=1)}
    labels = [format_tournament_label(tournaments[key]) for key in ordered_keys]
    return x_by_key, labels


def add_pair_selection(
    selections: list[tuple[str, list[dict[str, str]]]],
    selected_keys: set[str],
    pair_rows: list[dict[str, str]],
    selector_label: str,
) -> None:
    """Dodaje parę do listy serii, walidując brak wyników i duplikaty."""
    if not pair_rows:
        raise ValueError(f"Nie znaleziono występów pary: {selector_label}")

    ordered_rows = sorted_pair_rows(pair_rows)
    pair_name = ordered_rows[0]["para"]
    pair_key = normalize_text(pair_name)
    if pair_key in selected_keys:
        return

    selected_keys.add(pair_key)
    selections.append((pair_name, ordered_rows))


def resolve_pair_series(
    rows: list[dict[str, str]],
    pair_names: Iterable[str],
    dancer_1: str | None,
    dancer_2: str | None,
) -> list[tuple[str, list[dict[str, str]]]]:
    """Zamienia wybór z CLI na serie danych gotowe do wykresu."""
    selections: list[tuple[str, list[dict[str, str]]]] = []
    selected_keys: set[str] = set()

    for pair_name in pair_names:
        add_pair_selection(
            selections,
            selected_keys,
            pair_rows_by_name(rows, pair_name),
            pair_name,
        )

    if dancer_1 and dancer_2:
        add_pair_selection(
            selections,
            selected_keys,
            pair_rows_by_dancers(rows, dancer_1, dancer_2),
            f"{dancer_1}, {dancer_2}",
        )
    elif dancer_1 or dancer_2:
        raise ValueError("Argumenty --tancerz1 i --tancerz2 muszą być podane razem.")

    return selections


def prepare_matplotlib_config_dir() -> None:
    """Ustawia zapisywalny katalog cache Matplotlib, jeśli użytkownik go nie wskazał."""
    if "MPLCONFIGDIR" in os.environ:
        return
    cache_dir = Path(tempfile.gettempdir()) / "turnieje_tp_matplotlib"
    cache_dir.mkdir(parents=True, exist_ok=True)
    os.environ["MPLCONFIGDIR"] = str(cache_dir)


def build_default_plot_filename(
    pair_series: list[tuple[str, list[dict[str, str]]]],
) -> str:
    """Buduje domyślną nazwę pliku PNG dla wykresu."""
    if len(pair_series) == 1:
        return f"wykres_elo_{slugify_filename_part(pair_series[0][0])}.png"
    return f"wykres_elo_porownanie_{len(pair_series)}_par.png"


def prompt_plot_output_action(
    pair_series: list[tuple[str, list[dict[str, str]]]],
    project_dir: Path,
) -> tuple[Path | None, bool]:
    """
    Pyta użytkownika, czy wykres pokazać, zapisać, czy zrobić obie rzeczy.

    Zwraca: (ścieżka zapisu lub None, czy pokazać okno wykresu).
    """
    print()
    print("Co zrobić z wykresem?")
    print("  1. Pokaż wykres")
    print("  2. Zapisz wykres do pliku")
    print("  3. Zapisz do pliku i pokaż wykres")

    while True:
        choice = input("Wybór [1/2/3, Enter = 1]: ").strip()
        if not choice:
            return None, True
        if choice not in {"1", "2", "3"}:
            print("Wpisz 1, 2 albo 3.")
            continue
        if choice == "1":
            return None, True

        default_path = project_dir / build_default_plot_filename(pair_series)
        raw_path = input(f"Ścieżka zapisu [{default_path}]: ").strip()
        output_path = Path(raw_path) if raw_path else default_path
        return output_path, choice == "3"


def plot_pair_progress(
    pair_series: list[tuple[str, list[dict[str, str]]]],
    csv_path: Path,
    output_path: Path | None,
    show_plot: bool,
    title: str | None,
) -> None:
    """Rysuje i opcjonalnie zapisuje wykres ELO jednej albo wielu par."""
    try:
        prepare_matplotlib_config_dir()

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

    if not pair_series:
        raise ValueError("Nie wybrano żadnej pary do wykresu.")

    x_by_key, labels = build_tournament_axis(pair_series)

    sns.set_theme(style="whitegrid", context="notebook")
    width = min(max(10.0, len(labels) * 1.05), 28.0)
    fig, ax = plt.subplots(figsize=(width, 6.5))

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

    if title:
        chart_title = title
    elif len(pair_series) == 1:
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
        f"Źródło: {csv_path.name} | punkty po występie",
        fontsize=8,
        color="dimgray",
    )
    right_margin = 0.78 if len(pair_series) > 1 else 1
    fig.tight_layout(rect=(0, 0.03, right_margin, 1))

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
            "Rysuje wykres historii ELO jednej albo wielu par "
            "na podstawie CSV z progress_export.py."
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
        action="append",
        help=(
            "Nazwa pary z kolumny `para`. Można podać wiele razy, "
            'np. --pair "Pasiut Paweł, Ziółek Weronika" --pair "Teperek Kajetan, Drzas Joanna".'
        ),
    )
    parser.add_argument(
        "--pairs",
        nargs="+",
        help=(
            "Kilka nazw par jako osobne argumenty, np. "
            '--pairs "Pasiut Paweł, Ziółek Weronika" "Teperek Kajetan, Drzas Joanna".'
        ),
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

    requested_pairs: list[str] = []
    if args.pair:
        requested_pairs.extend(args.pair)
    if args.pairs:
        requested_pairs.extend(args.pairs)

    pair_series = resolve_pair_series(
        rows=rows,
        pair_names=requested_pairs,
        dancer_1=args.tancerz1,
        dancer_2=args.tancerz2,
    )
    if not pair_series:
        selected_pairs = choose_pairs_interactively(rows)
        pair_series = resolve_pair_series(
            rows=rows,
            pair_names=selected_pairs,
            dancer_1=None,
            dancer_2=None,
        )

    if args.output or args.show:
        output_path = Path(args.output) if args.output else None
        show_plot = args.show or output_path is None
    else:
        output_path, show_plot = prompt_plot_output_action(pair_series, project_dir)

    plot_pair_progress(
        pair_series=pair_series,
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
