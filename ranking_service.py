from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from Processer import przetworz_turniej
from app_config import load_ranking_config


BASE_CATEGORY_MATCHERS = (
    ("VIII", "viii"),
    ("VII", "vii"),
    ("VI", "vi"),
    ("V", "v"),
    ("IV", "iv"),
    ("III", "iii"),
    ("II", "ii"),
    ("I", "i"),
)
BASE_CATEGORIES = tuple(label for label, _ in BASE_CATEGORY_MATCHERS)


@dataclass(frozen=True)
class RankingBuildResult:
    category: str
    years: tuple[int, ...]
    ranking: tuple[object, ...]
    processed_files: tuple[Path, ...]
    included_categories: tuple[str, ...]
    skipped_files: tuple[tuple[str, str], ...]


def list_available_years(rsc_dir: str | Path = "rsc") -> list[int]:
    root = Path(rsc_dir)
    years: list[int] = []

    if not root.exists():
        return years

    for path in root.iterdir():
        if path.is_dir() and path.name.isdigit():
            years.append(int(path.name))

    return sorted(years)


def list_available_categories_for_years(
    rsc_dir: str | Path = "rsc", years: Iterable[int | str] | None = None
) -> list[str]:
    root = Path(rsc_dir)
    selected_years = normalize_years(years) if years else tuple(list_available_years(root))
    found_categories: set[str] = set()

    for year in selected_years:
        year_dir = root / str(year)
        if not year_dir.is_dir():
            continue

        for file_path in sorted(year_dir.glob("*.txt")):
            category_slug = extract_category_slug(file_path)
            base_category = detect_base_category(category_slug)
            if base_category:
                found_categories.add(base_category)

    return [category for category in BASE_CATEGORIES if category in found_categories]


def normalize_years(years: Iterable[int | str] | None) -> tuple[int, ...]:
    if years is None:
        return tuple()

    normalized = {
        int(str(year).strip())
        for year in years
        if str(year).strip()
    }
    return tuple(sorted(normalized))


def detect_base_category(category_slug: str | None) -> str | None:
    if not category_slug:
        return None

    normalized = category_slug.strip().lower()
    for label, prefix in BASE_CATEGORY_MATCHERS:
        if normalized.startswith(prefix):
            return label

    return None


def extract_category_slug(file_path: str | Path) -> str | None:
    path = Path(file_path)
    if "-" not in path.stem:
        return None

    return path.stem.rsplit("-", 1)[1].lower()


def collect_category_files(
    category: str,
    years: Iterable[int | str],
    rsc_dir: str | Path = "rsc",
) -> tuple[list[Path], list[str]]:
    root = Path(rsc_dir)
    normalized_category = detect_base_category(category)
    selected_years = normalize_years(years)

    if not normalized_category:
        raise ValueError(f"Nieznana kategoria rankingu: {category}")
    if not selected_years:
        raise ValueError("Wybierz przynajmniej jeden rok.")

    matching_files: list[Path] = []
    exact_categories: set[str] = set()

    for year in selected_years:
        year_dir = root / str(year)
        if not year_dir.is_dir():
            continue

        for file_path in sorted(year_dir.glob("*.txt")):
            category_slug = extract_category_slug(file_path)
            if detect_base_category(category_slug) != normalized_category:
                continue

            matching_files.append(file_path)
            if category_slug:
                exact_categories.add(category_slug.upper())

    return matching_files, sorted(exact_categories)


def build_ranking(
    category: str,
    years: Iterable[int | str],
    rsc_dir: str | Path = "rsc",
    k_factor: float | None = None,
    d_factor: float | None = None,
    config_path: str | Path | None = None,
) -> RankingBuildResult:
    normalized_category = detect_base_category(category)
    selected_years = normalize_years(years)
    if k_factor is None or d_factor is None:
        config = load_ranking_config(config_path)
        if k_factor is None:
            k_factor = config.k_factor
        if d_factor is None:
            d_factor = config.d_factor

    matching_files, included_categories = collect_category_files(
        category=category,
        years=selected_years,
        rsc_dir=rsc_dir,
    )

    if not matching_files:
        years_label = ", ".join(str(year) for year in selected_years)
        raise ValueError(
            f"Brak plików dla kategorii {normalized_category} w latach: {years_label}."
        )

    baza_par: dict[tuple[str, str], object] = {}
    skipped_files: list[tuple[str, str]] = []

    for file_path in matching_files:
        try:
            przetworz_turniej(
                str(file_path),
                baza_par,
                k_factor,
                d_factor,
                config_path=config_path,
            )
        except Exception as exc:
            skipped_files.append((str(file_path), str(exc)))

    ranking = tuple(sorted(baza_par.values(), key=lambda para: para.elo, reverse=True))

    return RankingBuildResult(
        category=normalized_category or category.upper(),
        years=selected_years,
        ranking=ranking,
        processed_files=tuple(matching_files),
        included_categories=tuple(included_categories),
        skipped_files=tuple(skipped_files),
    )


def format_ranking_table(ranking: Iterable[object]) -> str:
    header = f"{'Miejsce':<8} | {'Para':<50} | {'ELO':<10}"
    separator = "-" * 75
    lines = [header, separator]

    has_rows = False
    for place, para in enumerate(ranking, start=1):
        has_rows = True
        pair_name = f"{para.tancerz1}, {para.tancerz2}"
        lines.append(f"{place:<8} | {pair_name:<50} | {para.elo:<10.2f}")

    if not has_rows:
        lines.append("Brak wyników dla wybranych filtrów.")

    return "\n".join(lines)


def format_ranking_report(result: RankingBuildResult) -> str:
    lines = [
        f"Kategoria bazowa: {result.category}",
        f"Lata: {', '.join(str(year) for year in result.years)}",
        f"Przetworzone pliki: {len(result.processed_files)}",
        "Uwzględnione kategorie: "
        + (", ".join(result.included_categories) if result.included_categories else "brak"),
        "",
        format_ranking_table(result.ranking),
    ]

    if result.skipped_files:
        lines.append("")
        lines.append("Pominięte pliki:")
        for file_path, error in result.skipped_files:
            lines.append(f"- {file_path}: {error}")

    return "\n".join(lines)


def build_default_output_filename(result: RankingBuildResult) -> str:
    if len(result.years) == 1:
        years_part = str(result.years[0])
    elif len(result.years) <= 4:
        years_part = "_".join(str(year) for year in result.years)
    else:
        years_part = f"{result.years[0]}-{result.years[-1]}_{len(result.years)}lat"

    return f"ranking_{result.category.lower()}_{years_part}.txt"


def save_ranking_report(report_text: str, output_path: str | Path) -> Path:
    path = Path(output_path)
    path.write_text(report_text, encoding="utf-8")
    return path
