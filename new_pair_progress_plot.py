"""
Wykres historii rankingu ELO par bezpośrednio z data_new.xlsx.

To odpowiednik legacy/pair_progress_plot.py dla nowego formatu danych.
Skrypt nie wymaga pośredniego CSV z new_progress_export.py: historię punktów
buduje w pamięci przez new_ranking_service.build_new_progress_export.
"""

from __future__ import annotations

import argparse
import os
import re
import tempfile
from pathlib import Path
from typing import Iterable

from new_ranking_service import (
    build_new_progress_export,
    format_classes_for_display,
    list_available_categories_for_years_xlsx,
    list_available_classes_for_category_and_years_xlsx,
    list_available_years_xlsx,
    load_xlsx_data,
    parse_class_arguments,
    parse_year_arguments,
    prompt_for_category,
    prompt_for_classes,
    prompt_for_years,
)


def normalize_text(value: str) -> str:
    """Normalizuje tekst do porównań odpornych na wielokrotne spacje."""
    return re.sub(r"\s+", " ", value.strip()).casefold()


def slugify_filename_part(value: str, fallback: str = "wykres") -> str:
    """Zamienia tekst na bezpieczny fragment nazwy pliku."""
    slug = re.sub(r"[^\w]+", "_", normalize_text(value), flags=re.UNICODE)
    slug = slug.strip("_")
    return slug or fallback


def parse_number(value: str) -> float:
    """Parsuje liczbę z kropką albo przecinkiem dziesiętnym."""
    return float(value.strip().replace(",", "."))


def split_pair_name(pair_name: str) -> tuple[str, str]:
    """Rozbija nazwę pary na dwóch tancerzy, jeśli separator jest jednoznaczny."""
    parts = [part.strip() for part in pair_name.split(",")]
    if len(parts) != 2:
        return "", ""
    return parts[0], parts[1]


def prepare_matplotlib_config_dir() -> None:
    """Ustawia zapisywalny katalog cache Matplotlib, jeśli użytkownik go nie wskazał."""
    if "MPLCONFIGDIR" in os.environ:
        return
    cache_dir = Path(tempfile.gettempdir()) / "turnieje_tp_matplotlib"
    cache_dir.mkdir(parents=True, exist_ok=True)
    os.environ["MPLCONFIGDIR"] = str(cache_dir)


def load_class_thresholds(config_path: Path) -> list[tuple[str, float]]:
    """Wczytuje progi defaultelo... z config.txt, pomijając defaulteloOPEN."""
    thresholds: dict[str, float] = {}
    if not config_path.is_file():
        return []

    for raw_line in config_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line or "=" not in line:
            continue
        key, value = line.split("=", 1)
        normalized_key = key.strip().lower()
        if not normalized_key.startswith("defaultelo"):
            continue

        class_name = normalized_key[len("defaultelo"):].upper()
        if not class_name or class_name == "OPEN":
            continue

        try:
            thresholds[class_name] = parse_number(value)
        except ValueError:
            continue

    return sorted(thresholds.items(), key=lambda item: (item[1], item[0]))


def build_progress_rows(
    xlsx_path: Path,
    years: list[int],
    category: str | None,
    classes: list[str] | None,
) -> list[dict[str, str]]:
    """Buduje słownikowe wiersze historii punktów z arkusza xlsx."""
    result = build_new_progress_export(
        file_path=xlsx_path,
        years=years,
        category=category,
        classes=classes,
    )
    rows: list[dict[str, str]] = []
    for row_order, row in enumerate(result.rows, start=1):
        dancer_1, dancer_2 = split_pair_name(row.pair_name)
        rows.append({
            "rok": str(row.year),
            "kolejnosc_turnieju": str(row.tournament_order),
            "kod_turnieju": row.tournament_code,
            "turniej": row.tournament_name,
            "kategoria_bazowa": row.category,
            "podkategoria": row.exact_category,
            "klasa": row.klasa,
            "lokata": str(row.place),
            "pair_id": row.pair_id,
            "para": row.pair_name,
            "tancerz_1": dancer_1,
            "tancerz_2": dancer_2,
            "punkty_przed": f"{row.points_before:.2f}",
            "punkty_po": f"{row.points_after:.2f}",
            "roznica_punktow": f"{row.points_delta:.2f}",
            "_row_order": str(row_order),
        })

    if not rows:
        raise ValueError("Brak wierszy historii dla wybranych filtrów.")
    return rows


def unique_pairs(rows: Iterable[dict[str, str]]) -> list[dict[str, str]]:
    """Zwraca unikalne pary wraz z liczbą występów."""
    pairs: dict[str, dict[str, str]] = {}
    for row in rows:
        key = row["pair_id"] or normalize_text(row["para"])
        if key not in pairs:
            pairs[key] = {
                "pair_id": row["pair_id"],
                "para": row["para"],
                "wystepy": "0",
                "pierwszy": row["kolejnosc_turnieju"],
                "ostatni": row["kolejnosc_turnieju"],
            }
        pair_info = pairs[key]
        pair_info["wystepy"] = str(int(pair_info["wystepy"]) + 1)
        if int(row["kolejnosc_turnieju"]) < int(pair_info["pierwszy"]):
            pair_info["pierwszy"] = row["kolejnosc_turnieju"]
        if int(row["kolejnosc_turnieju"]) > int(pair_info["ostatni"]):
            pair_info["ostatni"] = row["kolejnosc_turnieju"]

    return sorted(
        pairs.values(),
        key=lambda item: (
            item["para"].split(",")[-1].strip(),
            item["para"],
            item["pair_id"],
        ),
    )


def filter_pair_catalog(
    pairs: Iterable[dict[str, str]],
    search_text: str | None,
) -> list[dict[str, str]]:
    """Filtruje katalog par po fragmencie nazwy albo pair_id."""
    if not search_text:
        return list(pairs)
    normalized_search = normalize_text(search_text)
    return [
        pair
        for pair in pairs
        if normalized_search in normalize_text(pair["para"])
        or normalized_search in normalize_text(pair["pair_id"])
    ]


def print_pairs(pairs: Iterable[dict[str, str]], limit: int) -> None:
    """Wypisuje dostępne pary w formacie przydatnym do argumentów CLI."""
    for index, pair in enumerate(pairs, start=1):
        if index > limit:
            print(f"... pominięto kolejne pozycje; zwiększ --limit, aby zobaczyć więcej.")
            break
        print(
            f"{index:>3}. [{pair['pair_id']}] {pair['para']} "
            f"| występy: {pair['wystepy']} "
            f"| turnieje: {pair['pierwszy']} - {pair['ostatni']}"
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


def pair_rows_by_id(
    rows: Iterable[dict[str, str]],
    pair_id: str,
) -> list[dict[str, str]]:
    """Wyszukuje parę po pair_id z arkusza."""
    normalized_pair_id = pair_id.strip()
    return [row for row in rows if row["pair_id"] == normalized_pair_id]


def pair_rows_by_dancers(
    rows: Iterable[dict[str, str]],
    dancer_1: str,
    dancer_2: str,
) -> list[dict[str, str]]:
    """Wyszukuje parę po dwóch tancerzach, niezależnie od kolejności."""
    requested = {normalize_text(dancer_1), normalize_text(dancer_2)}
    return [
        row
        for row in rows
        if {normalize_text(row["tancerz_1"]), normalize_text(row["tancerz_2"])}
        == requested
    ]


def sorted_pair_rows(rows: Iterable[dict[str, str]]) -> list[dict[str, str]]:
    """Sortuje występy zgodnie z kolejnością wyliczeń ELO."""
    return sorted(rows, key=lambda row: int(row.get("_row_order", "0") or 0))


def choose_pairs_interactively(rows: list[dict[str, str]]) -> list[str]:
    """Prosty wybór jednej lub wielu par w terminalu przez fragment nazwy."""
    pairs = unique_pairs(rows)
    selected_pairs: list[str] = []
    print(f"W danych znaleziono pary: {len(pairs)}")

    while True:
        if selected_pairs:
            prompt = "Wpisz fragment kolejnej pary (Enter = rysuj wybrane pary): "
        else:
            prompt = "Wpisz fragment nazwy pary albo pair_id: "
        search_text = input(prompt).strip()
        if not search_text:
            if selected_pairs:
                return selected_pairs
            print("Podaj przynajmniej fragment nazwiska, imienia albo pair_id.")
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
            matches = [
                pair
                for pair in filter_pair_catalog(pairs, choice)
                if pair["para"] not in selected_pairs
            ]
            if len(matches) == 1:
                selected = matches[0]["para"]
                selected_pairs.append(selected)
                print(f"Dodano: {selected}")
                continue
        print("Nie wybrano poprawnej pozycji.")


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
    pair_key = ordered_rows[0]["pair_id"] or normalize_text(pair_name)
    if pair_key in selected_keys:
        return

    selected_keys.add(pair_key)
    selections.append((pair_name, ordered_rows))


def resolve_pair_series(
    rows: list[dict[str, str]],
    pair_names: Iterable[str],
    pair_ids: Iterable[str],
    dancer_1: str | None,
    dancer_2: str | None,
) -> list[tuple[str, list[dict[str, str]]]]:
    """Zamienia wybór z CLI na serie danych gotowe do wykresu."""
    selections: list[tuple[str, list[dict[str, str]]]] = []
    selected_keys: set[str] = set()

    for pair_id in pair_ids:
        add_pair_selection(
            selections,
            selected_keys,
            pair_rows_by_id(rows, pair_id),
            pair_id,
        )

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


def tournament_key(row: dict[str, str]) -> str:
    """Zwraca stabilny klucz turnieju/kategorii dla wspólnej osi X."""
    return "|".join([
        row["kolejnosc_turnieju"],
        row["rok"],
        row["kod_turnieju"],
        row["podkategoria"],
    ])


def format_tournament_label(row: dict[str, str]) -> str:
    """Buduje etykietę osi X dla pojedynczego występu."""
    return f"{row['rok']}\n{row['turniej']} ({row['podkategoria']})"


def build_tournament_axis(
    pair_series: list[tuple[str, list[dict[str, str]]]],
) -> tuple[dict[str, int], list[str]]:
    """Buduje wspólną oś X z sumy występów wybranych par."""
    tournaments: dict[str, dict[str, str]] = {}
    for _, rows in pair_series:
        for row in sorted_pair_rows(rows):
            key = tournament_key(row)
            if key not in tournaments:
                tournaments[key] = row

    ordered_keys = sorted(
        tournaments,
        key=lambda key: int(tournaments[key].get("_row_order", "0") or 0),
    )
    x_by_key = {key: index for index, key in enumerate(ordered_keys, start=1)}
    labels = [format_tournament_label(tournaments[key]) for key in ordered_keys]
    return x_by_key, labels


def build_default_plot_filename(
    pair_series: list[tuple[str, list[dict[str, str]]]],
) -> str:
    """Buduje domyślną nazwę pliku PNG dla wykresu."""
    if len(pair_series) == 1:
        return f"wykres_elo_new_{slugify_filename_part(pair_series[0][0])}.png"
    return f"wykres_elo_new_porownanie_{len(pair_series)}_par.png"


def prompt_plot_output_action(
    pair_series: list[tuple[str, list[dict[str, str]]]],
    project_dir: Path,
) -> tuple[Path | None, bool]:
    """Pyta, czy wykres pokazać, zapisać, czy zrobić obie rzeczy."""
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

        img_dir = project_dir / "img"
        img_dir.mkdir(parents=True, exist_ok=True)
        default_path = img_dir / build_default_plot_filename(pair_series)
        raw_path = input(f"Ścieżka zapisu [{default_path}]: ").strip()
        output_path = Path(raw_path) if raw_path else default_path
        if not output_path.is_absolute() and len(output_path.parts) == 1:
            output_path = img_dir / output_path
        return output_path, choice == "3"


def plot_pair_progress(
    pair_series: list[tuple[str, list[dict[str, str]]]],
    source_path: Path,
    config_path: Path,
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

    all_y: list[float] = []
    for _, ordered_rows in pair_series:
        all_y.extend([parse_number(row["punkty_po"]) for row in ordered_rows])

    if all_y:
        thresholds = load_class_thresholds(config_path)
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
        f"Źródło: {source_path.name} | punkty po występie",
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


def resolve_output_mode(
    args: argparse.Namespace,
    project_dir: Path,
    pair_series: list[tuple[str, list[dict[str, str]]]],
) -> tuple[Path | None, bool]:
    """Ustala ścieżkę zapisu i tryb pokazywania wykresu."""
    if args.output or args.show:
        output_path = Path(args.output) if args.output else None
        show_plot = args.show or output_path is None
        if output_path and not output_path.is_absolute() and len(output_path.parts) == 1:
            output_path = project_dir / "img" / output_path
        return output_path, show_plot

    return prompt_plot_output_action(pair_series, project_dir)


def resolve_filters_from_args(
    args: argparse.Namespace,
    project_dir: Path,
    require_category: bool,
) -> tuple[Path, list[int], str | None, list[str] | None]:
    """Parsuje filtry wejściowe dla trybu argumentowego."""
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

    if args.classes and not args.category:
        raise ValueError("--classes wymaga podania --category.")
    if require_category and not args.category:
        raise ValueError("Do rysowania wykresu podaj --category.")

    selected_category = args.category.strip().upper() if args.category else None
    selected_classes = None
    if selected_category:
        available_classes = list_available_classes_for_category_and_years_xlsx(
            df,
            selected_category,
            selected_years,
        )
        selected_classes = parse_class_arguments(args.classes, available_classes)

    return xlsx_path, selected_years, selected_category, selected_classes


def run_interactive(project_dir: Path, xlsx_path: Path) -> int:
    """Uruchamia pełny tryb interaktywny: filtry, wybór par i zapis/pokazanie."""
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

    print("Budowanie historii zmian punktów...")
    rows = build_progress_rows(
        xlsx_path,
        selected_years,
        selected_category,
        selected_classes,
    )
    print(
        f"Wiersze: {len(rows)} | kategoria: {selected_category} | "
        f"klasy: {format_classes_for_display(selected_classes or [])}"
    )

    selected_pairs = choose_pairs_interactively(rows)
    pair_series = resolve_pair_series(
        rows=rows,
        pair_names=selected_pairs,
        pair_ids=[],
        dancer_1=None,
        dancer_2=None,
    )
    output_path, show_plot = prompt_plot_output_action(pair_series, project_dir)
    plot_pair_progress(
        pair_series=pair_series,
        source_path=xlsx_path,
        config_path=project_dir / "config.txt",
        output_path=output_path,
        show_plot=show_plot,
        title=None,
    )
    return 0


def run_from_args(args: argparse.Namespace, project_dir: Path) -> int:
    """Uruchamia listowanie par albo rysowanie wykresu z argumentów CLI."""
    requested_pairs: list[str] = []
    if args.pair:
        requested_pairs.extend(args.pair)
    if args.pairs:
        requested_pairs.extend(args.pairs)
    requested_pair_ids = args.pair_id or []

    require_category = bool(
        requested_pairs
        or requested_pair_ids
        or args.tancerz1
        or args.tancerz2
        or args.output
        or args.show
        or not args.list_pairs
    )
    xlsx_path, selected_years, selected_category, selected_classes = (
        resolve_filters_from_args(args, project_dir, require_category)
    )

    rows = build_progress_rows(
        xlsx_path,
        selected_years,
        selected_category,
        selected_classes,
    )

    if args.list_pairs:
        pairs = filter_pair_catalog(unique_pairs(rows), args.search)
        print(f"Plik: {xlsx_path}")
        print_pairs(pairs, limit=max(args.limit, 1))
        return 0

    pair_series = resolve_pair_series(
        rows=rows,
        pair_names=requested_pairs,
        pair_ids=requested_pair_ids,
        dancer_1=args.tancerz1,
        dancer_2=args.tancerz2,
    )
    if not pair_series:
        selected_pairs = choose_pairs_interactively(rows)
        pair_series = resolve_pair_series(
            rows=rows,
            pair_names=selected_pairs,
            pair_ids=[],
            dancer_1=None,
            dancer_2=None,
        )

    output_path, show_plot = resolve_output_mode(args, project_dir, pair_series)
    plot_pair_progress(
        pair_series=pair_series,
        source_path=xlsx_path,
        config_path=project_dir / "config.txt",
        output_path=output_path,
        show_plot=show_plot,
        title=args.title,
    )
    return 0


def build_argument_parser() -> argparse.ArgumentParser:
    """Buduje parser argumentów CLI."""
    parser = argparse.ArgumentParser(
        description="Rysuje wykres historii ELO par bezpośrednio z data_new.xlsx."
    )
    parser.add_argument(
        "--input-excel",
        help="Ścieżka pliku xlsx. Domyślnie: data_new.xlsx.",
    )
    parser.add_argument(
        "--category",
        help="Kategoria bazowa, np. V albo III. Wymagana do rysowania wykresu.",
    )
    parser.add_argument(
        "--years",
        nargs="+",
        help="Lata lub zakresy lat, np. 2024 2025 albo 2021-2025. Brak = wszystkie.",
    )
    parser.add_argument(
        "--classes",
        nargs="+",
        help="Klasy do uwzględnienia, np. B A albo S. Brak = wszystkie.",
    )
    parser.add_argument(
        "--pair",
        action="append",
        help="Nazwa pary. Można podać wiele razy.",
    )
    parser.add_argument(
        "--pairs",
        nargs="+",
        help="Kilka nazw par jako osobne argumenty.",
    )
    parser.add_argument(
        "--pair-id",
        action="append",
        help="Id pary z kolumny `pair id`. Można podać wiele razy.",
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
        help="Wypisz pary dostępne dla filtrów zamiast rysować wykres.",
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
    return parser


def main() -> None:
    """Punkt wejścia skryptu."""
    project_dir = Path(__file__).resolve().parent
    parser = build_argument_parser()
    args = parser.parse_args()
    xlsx_path = (
        Path(args.input_excel) if args.input_excel
        else project_dir / "data_new.xlsx"
    )
    has_cli_arguments = bool(
        args.category
        or args.years
        or args.classes
        or args.pair
        or args.pairs
        or args.pair_id
        or args.tancerz1
        or args.tancerz2
        or args.list_pairs
        or args.output
        or args.show
        or args.search
    )

    try:
        if has_cli_arguments:
            raise SystemExit(run_from_args(args, project_dir))
        raise SystemExit(run_interactive(project_dir, xlsx_path))
    except (FileNotFoundError, ValueError) as exc:
        raise SystemExit(f"Błąd: {exc}") from exc


if __name__ == "__main__":
    main()
