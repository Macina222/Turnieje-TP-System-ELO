"""
Wykres historii rankingu ELO par bezpośrednio z data_new.xlsx.

To odpowiednik legacy/pair_progress_plot.py dla nowego formatu danych.
Skrypt nie wymaga pośredniego CSV z new_progress_export.py: historię punktów
buduje w pamięci przez new_ranking_service.build_new_progress_export.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import tempfile
import webbrowser
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


def build_all_pair_series(rows: list[dict[str, str]]) -> list[tuple[str, list[dict[str, str]]]]:
    """Buduje serie dla wszystkich wykrytych par z aktualnych filtrów."""
    selections: list[tuple[str, list[dict[str, str]]]] = []
    for pair in unique_pairs(rows):
        pair_rows = pair_rows_by_id(rows, pair["pair_id"]) if pair["pair_id"] else pair_rows_by_name(rows, pair["para"])
        if not pair_rows:
            continue
        ordered_rows = sorted_pair_rows(pair_rows)
        selections.append((ordered_rows[0]["para"], ordered_rows))
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


def build_default_interactive_plot_filename(
    scope: str,
    pair_series: list[tuple[str, list[dict[str, str]]]],
) -> str:
    """Buduje domyślną nazwę pliku HTML dla interaktywnego wykresu."""
    if scope == "all":
        return "wykres_elo_new_interaktywny_all_pairs.html"
    if len(pair_series) == 1:
        return (
            "wykres_elo_new_interaktywny_"
            f"{slugify_filename_part(pair_series[0][0])}.html"
        )
    return f"wykres_elo_new_interaktywny_{len(pair_series)}_par.html"


def prompt_interactive_scope() -> str:
    """Pyta, czy interaktywny wykres ma startować od wszystkich czy wybranych par."""
    print()
    print("Tryb interaktywny:")
    print("  1. Wszystkie wykryte pary")
    print("  2. Ręczny wybór par na start")

    while True:
        choice = input("Wybór [1/2, Enter = 1]: ").strip()
        if not choice or choice == "1":
            return "all"
        if choice == "2":
            return "selected"
        print("Wpisz 1 albo 2.")


def prompt_chart_mode() -> str:
    """Pyta o rodzaj wykresu w terminalowym trybie interaktywnym."""
    print()
    print("Rodzaj wykresu:")
    print("  1. Statyczny PNG/okno matplotlib")
    print("  2. Interaktywny HTML w przeglądarce")

    while True:
        choice = input("Wybór [1/2, Enter = 2]: ").strip()
        if not choice or choice == "2":
            return "interactive"
        if choice == "1":
            return "static"
        print("Wpisz 1 albo 2.")


def prompt_interactive_output_action(
    project_dir: Path,
    scope: str,
    pair_series: list[tuple[str, list[dict[str, str]]]],
) -> tuple[Path, bool]:
    """Pyta o zapis i otwarcie interaktywnego wykresu HTML."""
    print()
    print("Co zrobić z interaktywnym wykresem?")
    print("  1. Zapisz HTML i otwórz w przeglądarce")
    print("  2. Tylko zapisz HTML")

    img_dir = project_dir / "img"
    img_dir.mkdir(parents=True, exist_ok=True)
    default_path = img_dir / build_default_interactive_plot_filename(scope, pair_series)

    while True:
        choice = input("Wybór [1/2, Enter = 1]: ").strip()
        if choice not in {"", "1", "2"}:
            print("Wpisz 1 albo 2.")
            continue

        raw_path = input(f"Ścieżka zapisu [{default_path}]: ").strip()
        output_path = Path(raw_path) if raw_path else default_path
        if not output_path.is_absolute() and len(output_path.parts) == 1:
            output_path = img_dir / output_path
        if output_path.suffix.lower() != ".html":
            output_path = output_path.with_suffix(".html")
        return output_path, choice != "2"


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
    elif initial_scope == "all":
        chart_title = "Historia rankingu ELO wszystkich par"
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


def build_interactive_plot_data(
    pair_series: list[tuple[str, list[dict[str, str]]]],
    x_by_key: dict[str, int],
    labels: list[str],
) -> tuple[list[dict[str, object]], list[float]]:
    """Przygotowuje serie danych dla HTML/Plotly."""
    series_data: list[dict[str, object]] = []
    all_y: list[float] = []

    for pair_name, ordered_rows in pair_series:
        x_values: list[int] = []
        y_values: list[float] = []
        custom_data: list[list[str]] = []
        for row in ordered_rows:
            x_value = x_by_key[tournament_key(row)]
            y_value = parse_number(row["punkty_po"])
            delta_value = parse_number(row["roznica_punktow"])
            x_values.append(x_value)
            y_values.append(y_value)
            all_y.append(y_value)
            custom_data.append([
                row["para"],
                row["turniej"],
                row["rok"],
                row["podkategoria"],
                row["lokata"],
                f"{delta_value:+.2f}",
                f"{parse_number(row['punkty_przed']):.2f}",
                f"{y_value:.2f}",
                row["kod_turnieju"],
            ])

        series_data.append({
            "name": pair_name,
            "x": x_values,
            "y": y_values,
            "customdata": custom_data,
        })

    return series_data, all_y


def write_interactive_plot_html(
    pair_series: list[tuple[str, list[dict[str, str]]]],
    source_path: Path,
    config_path: Path,
    output_path: Path,
    title: str | None,
    initial_scope: str,
) -> Path:
    """Tworzy plik HTML z interaktywnym wykresem Plotly i panelem wyboru par."""
    if not pair_series:
        raise ValueError("Nie wybrano żadnej pary do wykresu.")

    x_by_key, labels = build_tournament_axis(pair_series)
    series_data, all_y = build_interactive_plot_data(pair_series, x_by_key, labels)
    thresholds = load_class_thresholds(config_path)
    threshold_values = [value for _, value in thresholds]
    visible_values = all_y + threshold_values

    if title:
        chart_title = title
    elif initial_scope == "all":
        chart_title = "Historia rankingu ELO wszystkich par"
    elif len(pair_series) == 1:
        chart_title = f"Historia rankingu ELO: {pair_series[0][0]}"
    else:
        chart_title = "Historia rankingu ELO wybranych par"

    if visible_values:
        min_value = min(visible_values)
        max_value = max(visible_values)
        margin = max(35.0, (max_value - min_value) * 0.06)
        y_range = [round(min_value - margin, 2), round(max_value + margin, 2)]
    else:
        y_range = None

    layout_shapes = []
    layout_annotations = []
    for class_name, value in thresholds:
        layout_shapes.append({
            "type": "line",
            "xref": "paper",
            "x0": 0,
            "x1": 1,
            "y0": value,
            "y1": value,
            "line": {
                "color": "#9aa4ad",
                "width": 1,
                "dash": "dash",
            },
            "opacity": 0.75,
        })
        layout_annotations.append({
            "xref": "paper",
            "x": 0.01,
            "y": value,
            "text": f"Klasa {class_name}: {value:.0f}",
            "showarrow": False,
            "font": {"size": 11, "color": "#4b5563"},
            "xanchor": "left",
            "yanchor": "bottom",
            "bgcolor": "rgba(255,255,255,0.78)",
        })

    hover_template = (
        "<b>%{customdata[0]}</b><br>"
        "Turniej: %{customdata[1]}<br>"
        "Rok: %{customdata[2]}<br>"
        "Podkategoria: %{customdata[3]}<br>"
        "Miejsce: %{customdata[4]}<br>"
        "Zmiana ELO: %{customdata[5]}<br>"
        "ELO przed: %{customdata[6]}<br>"
        "ELO po: %{customdata[7]}<br>"
        "<extra></extra>"
    )

    html_payload = {
        "series": series_data,
        "labels": labels,
        "thresholds": thresholds,
        "title": chart_title,
        "sourceName": source_path.name,
        "yRange": y_range,
        "initialScope": initial_scope,
        "hoverTemplate": hover_template,
        "layoutShapes": layout_shapes,
        "layoutAnnotations": layout_annotations,
    }

    document = f"""<!DOCTYPE html>
<html lang="pl">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(chart_title)}</title>
  <script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f4f1ea;
      --panel: #fffdf8;
      --line: #d8d1c4;
      --ink: #1f2933;
      --muted: #5b6470;
      --accent: #0f766e;
      --accent-soft: rgba(15, 118, 110, 0.12);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Segoe UI", "Helvetica Neue", sans-serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, rgba(15, 118, 110, 0.10), transparent 28%),
        linear-gradient(180deg, #faf7f2 0%, var(--bg) 100%);
    }}
    .app {{
      display: grid;
      grid-template-columns: minmax(280px, 360px) 1fr;
      gap: 18px;
      min-height: 100vh;
      padding: 18px;
    }}
    .panel, .chart-shell {{
      background: rgba(255, 253, 248, 0.92);
      border: 1px solid var(--line);
      border-radius: 18px;
      box-shadow: 0 12px 36px rgba(31, 41, 51, 0.08);
      backdrop-filter: blur(10px);
    }}
    .panel {{
      padding: 18px;
      display: flex;
      flex-direction: column;
      gap: 14px;
    }}
    h1 {{
      margin: 0;
      font-size: 1.15rem;
      line-height: 1.3;
    }}
    .meta {{
      color: var(--muted);
      font-size: 0.92rem;
      line-height: 1.5;
    }}
    .controls {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }}
    button {{
      border: 1px solid var(--line);
      background: white;
      color: var(--ink);
      border-radius: 999px;
      padding: 9px 12px;
      cursor: pointer;
      font: inherit;
    }}
    button:hover {{
      border-color: var(--accent);
      background: var(--accent-soft);
    }}
    input[type="search"] {{
      width: 100%;
      padding: 10px 12px;
      border: 1px solid var(--line);
      border-radius: 12px;
      font: inherit;
      background: white;
    }}
    .pair-list {{
      overflow: auto;
      min-height: 260px;
      max-height: 56vh;
      display: flex;
      flex-direction: column;
      gap: 6px;
      padding-right: 6px;
    }}
    .pair-item {{
      display: flex;
      align-items: flex-start;
      gap: 10px;
      padding: 10px 11px;
      border: 1px solid transparent;
      border-radius: 12px;
      background: rgba(255,255,255,0.76);
    }}
    .pair-item:hover {{
      border-color: var(--line);
    }}
    .pair-item span {{
      font-size: 0.93rem;
      line-height: 1.35;
    }}
    .pair-count {{
      display: inline-block;
      margin-top: 3px;
      color: var(--muted);
      font-size: 0.82rem;
    }}
    .chart-shell {{
      padding: 10px 10px 2px 10px;
      min-width: 0;
    }}
    #chart {{
      width: 100%;
      height: calc(100vh - 48px);
      min-height: 620px;
    }}
    .hint {{
      color: var(--muted);
      font-size: 0.87rem;
      line-height: 1.5;
    }}
    @media (max-width: 980px) {{
      .app {{
        grid-template-columns: 1fr;
      }}
      .pair-list {{
        max-height: 34vh;
      }}
      #chart {{
        height: 72vh;
        min-height: 520px;
      }}
    }}
  </style>
</head>
<body>
  <div class="app">
    <aside class="panel">
      <div>
        <h1>{html.escape(chart_title)}</h1>
        <div class="meta">
          Źródło: {html.escape(source_path.name)}<br>
          Pary: <span id="visible-count">0</span> / <span id="total-count">0</span>
        </div>
      </div>
      <div class="controls">
        <button type="button" id="show-all">Pokaż wszystkie</button>
        <button type="button" id="hide-all">Ukryj wszystkie</button>
        <button type="button" id="reset-view">Reset widoku</button>
      </div>
      <input id="search" type="search" placeholder="Filtruj pary po nazwie...">
      <div id="pair-list" class="pair-list"></div>
      <div class="hint">
        Zoom: kółko myszy lub zaznaczenie obszaru. Przesuwanie: przeciągnij wykres.
        Kliknięcie legendy także ukrywa/pokazuje linię.
      </div>
    </aside>
    <main class="chart-shell">
      <div id="chart"></div>
    </main>
  </div>
  <script>
    const payload = {json.dumps(html_payload, ensure_ascii=False)};
    const chartEl = document.getElementById("chart");
    const pairListEl = document.getElementById("pair-list");
    const searchEl = document.getElementById("search");
    const visibleCountEl = document.getElementById("visible-count");
    const totalCountEl = document.getElementById("total-count");
    const traces = payload.series.map((serie, index) => ({{
      type: "scatter",
      mode: "lines+markers",
      name: serie.name,
      x: serie.x,
      y: serie.y,
      customdata: serie.customdata,
      hovertemplate: payload.hoverTemplate,
      line: {{ width: 2.4 }},
      marker: {{ size: 8 }},
      visible: true,
    }}));

    const layout = {{
      title: {{ text: payload.title, x: 0.02 }},
      paper_bgcolor: "rgba(0,0,0,0)",
      plot_bgcolor: "rgba(255,255,255,0.84)",
      hovermode: "closest",
      margin: {{ l: 70, r: 30, t: 70, b: 130 }},
      xaxis: {{
        title: "Turnieje chronologicznie",
        tickmode: "array",
        tickvals: payload.labels.map((_, index) => index + 1),
        ticktext: payload.labels,
        tickangle: -35,
        showgrid: true,
        gridcolor: "rgba(148, 163, 184, 0.16)",
      }},
      yaxis: {{
        title: "Ranking ELO",
        range: payload.yRange,
        zeroline: false,
        showgrid: true,
        gridcolor: "rgba(148, 163, 184, 0.18)",
      }},
      shapes: payload.layoutShapes,
      annotations: payload.layoutAnnotations,
      legend: {{
        orientation: "h",
        yanchor: "bottom",
        y: 1.02,
        xanchor: "left",
        x: 0,
      }},
    }};

    const config = {{
      responsive: true,
      displaylogo: false,
      toImageButtonOptions: {{
        format: "png",
        filename: "wykres_elo_interaktywny",
        scale: 2,
      }},
    }};

    const checkboxByIndex = new Map();

    function syncCounts() {{
      let visible = 0;
      traces.forEach((trace) => {{
        if (trace.visible !== "legendonly") {{
          visible += 1;
        }}
      }});
      visibleCountEl.textContent = String(visible);
      totalCountEl.textContent = String(traces.length);
    }}

    function renderPairList(filterText = "") {{
      const normalizedFilter = filterText.trim().toLocaleLowerCase();
      pairListEl.innerHTML = "";
      traces.forEach((trace, index) => {{
        if (normalizedFilter && !trace.name.toLocaleLowerCase().includes(normalizedFilter)) {{
          return;
        }}

        const row = document.createElement("label");
        row.className = "pair-item";

        const checkbox = document.createElement("input");
        checkbox.type = "checkbox";
        checkbox.checked = trace.visible !== "legendonly";
        checkbox.addEventListener("change", () => setTraceVisibility(index, checkbox.checked));
        checkboxByIndex.set(index, checkbox);

        const content = document.createElement("span");
        content.innerHTML = `${{escapeHtml(trace.name)}}<span class="pair-count">Występy: ${{trace.x.length}}</span>`;

        row.appendChild(checkbox);
        row.appendChild(content);
        pairListEl.appendChild(row);
      }});
      syncCounts();
    }}

    function escapeHtml(text) {{
      return text
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;");
    }}

    function setTraceVisibility(index, visible) {{
      traces[index].visible = visible ? true : "legendonly";
      Plotly.restyle(chartEl, {{ visible: traces[index].visible }}, [index]);
      const checkbox = checkboxByIndex.get(index);
      if (checkbox) {{
        checkbox.checked = visible;
      }}
      syncCounts();
    }}

    function setAllVisibility(visible) {{
      traces.forEach((trace, index) => {{
        trace.visible = visible ? true : "legendonly";
        const checkbox = checkboxByIndex.get(index);
        if (checkbox) {{
          checkbox.checked = visible;
        }}
      }});
      Plotly.restyle(chartEl, {{ visible: visible ? true : "legendonly" }});
      syncCounts();
    }}

    Plotly.newPlot(chartEl, traces, layout, config).then(() => {{
      totalCountEl.textContent = String(traces.length);
      renderPairList();
    }});

    chartEl.on("plotly_restyle", () => {{
      traces.forEach((trace, index) => {{
        const fullTrace = chartEl.data[index];
        trace.visible = fullTrace.visible === undefined ? true : fullTrace.visible;
        const checkbox = checkboxByIndex.get(index);
        if (checkbox) {{
          checkbox.checked = trace.visible !== "legendonly";
        }}
      }});
      syncCounts();
    }});

    document.getElementById("show-all").addEventListener("click", () => setAllVisibility(true));
    document.getElementById("hide-all").addEventListener("click", () => setAllVisibility(false));
    document.getElementById("reset-view").addEventListener("click", () => Plotly.relayout(chartEl, {{
      "xaxis.autorange": true,
      "yaxis.autorange": true,
    }}));
    searchEl.addEventListener("input", (event) => renderPairList(event.target.value));
  </script>
</body>
</html>
"""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(document, encoding="utf-8")
    return output_path


def open_interactive_plot_in_browser(output_path: Path) -> None:
    """Otwiera wygenerowany plik HTML w domyślnej przeglądarce."""
    opened = webbrowser.open(output_path.resolve().as_uri())
    if not opened:
        print(f"Nie udało się automatycznie otworzyć przeglądarki. Otwórz ręcznie: {output_path}")


def render_interactive_plot(
    pair_series: list[tuple[str, list[dict[str, str]]]],
    source_path: Path,
    config_path: Path,
    output_path: Path,
    open_in_browser: bool,
    title: str | None,
    initial_scope: str,
) -> None:
    """Zapisuje interaktywny wykres HTML i opcjonalnie otwiera go w przeglądarce."""
    saved_path = write_interactive_plot_html(
        pair_series=pair_series,
        source_path=source_path,
        config_path=config_path,
        output_path=output_path,
        title=title,
        initial_scope=initial_scope,
    )
    print(f"Zapisano interaktywny wykres: {saved_path}")
    if open_in_browser:
        open_interactive_plot_in_browser(saved_path)


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


def resolve_interactive_output_mode(
    args: argparse.Namespace,
    project_dir: Path,
    pair_series: list[tuple[str, list[dict[str, str]]]],
    scope: str,
) -> tuple[Path, bool]:
    """Ustala zapis i otwieranie dla interaktywnego wykresu HTML."""
    if args.output or args.show:
        output_path = Path(args.output) if args.output else (
            project_dir / "img" / build_default_interactive_plot_filename(scope, pair_series)
        )
        if not output_path.is_absolute() and len(output_path.parts) == 1:
            output_path = project_dir / "img" / output_path
        if output_path.suffix.lower() != ".html":
            output_path = output_path.with_suffix(".html")
        return output_path, args.show or not args.output

    return prompt_interactive_output_action(project_dir, scope, pair_series)


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

    chart_mode = prompt_chart_mode()
    if chart_mode == "interactive":
        interactive_scope = prompt_interactive_scope()
        if interactive_scope == "all":
            pair_series = build_all_pair_series(rows)
        else:
            selected_pairs = choose_pairs_interactively(rows)
            pair_series = resolve_pair_series(
                rows=rows,
                pair_names=selected_pairs,
                pair_ids=[],
                dancer_1=None,
                dancer_2=None,
            )
        output_path, open_in_browser = prompt_interactive_output_action(
            project_dir,
            interactive_scope,
            pair_series,
        )
        render_interactive_plot(
            pair_series=pair_series,
            source_path=xlsx_path,
            config_path=project_dir / "config.txt",
            output_path=output_path,
            open_in_browser=open_in_browser,
            title=None,
            initial_scope=interactive_scope,
        )
        return 0

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

    if args.interactive and args.interactive_scope == "all":
        pair_series = build_all_pair_series(rows)
    else:
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

    if args.interactive:
        output_path, open_in_browser = resolve_interactive_output_mode(
            args,
            project_dir,
            pair_series,
            args.interactive_scope,
        )
        render_interactive_plot(
            pair_series=pair_series,
            source_path=xlsx_path,
            config_path=project_dir / "config.txt",
            output_path=output_path,
            open_in_browser=open_in_browser,
            title=args.title,
            initial_scope=args.interactive_scope,
        )
    else:
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
        help="Pokaż wynik po wygenerowaniu: okno matplotlib albo otwarcie HTML w przeglądarce.",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Wygeneruj interaktywny wykres HTML z zoomem, hoverem i wyborem par.",
    )
    parser.add_argument(
        "--interactive-scope",
        choices=("selected", "all"),
        default="selected",
        help="Dla --interactive: start od wybranych par albo od wszystkich wykrytych. Domyślnie selected.",
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
        or args.interactive
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
