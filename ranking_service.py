from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent / "config.txt"
DEFAULT_ELO = 1000.0

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
class RankingConfig:
    k_factor: float
    d_factor: float


@dataclass
class Para:
    tancerz1: str
    tancerz2: str
    elo: float = DEFAULT_ELO

    def pobierz_id(self) -> tuple[str, str]:
        return self.tancerz1, self.tancerz2

    def __str__(self) -> str:
        return f"Para: {self.tancerz1} i {self.tancerz2} (Ranking: {self.elo})"


@dataclass(frozen=True)
class RankingBuildResult:
    category: str
    years: tuple[int, ...]
    ranking: tuple[Para, ...]
    processed_files: tuple[Path, ...]
    included_categories: tuple[str, ...]
    skipped_files: tuple[tuple[str, str], ...]


def _parse_config_number(raw_value: str, key: str, line_number: int) -> float:
    value = raw_value.split("#", 1)[0].strip().replace(",", ".")
    if not value:
        raise ValueError(
            f"Brak wartosci dla {key} w pliku config.txt (linia {line_number})."
        )

    try:
        return float(value)
    except ValueError as exc:
        raise ValueError(
            f"Nieprawidlowa wartosc dla {key} w pliku config.txt "
            f"(linia {line_number}): {raw_value.strip()}"
        ) from exc


def load_ranking_config(config_path: str | Path | None = None) -> RankingConfig:
    path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH

    if not path.is_file():
        raise FileNotFoundError(f"Nie znaleziono pliku konfiguracyjnego: {path}")

    values: dict[str, float] = {}

    for line_number, raw_line in enumerate(
        path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError(
                f"Nieprawidlowy wpis w pliku config.txt (linia {line_number}): {raw_line}"
            )

        key, value = line.split("=", 1)
        normalized_key = key.strip().lower()

        if normalized_key not in {"k", "d"}:
            continue

        values[normalized_key] = _parse_config_number(
            value,
            normalized_key.upper(),
            line_number,
        )

    missing = [key.upper() for key in ("k", "d") if key not in values]
    if missing:
        raise ValueError(
            "Brakuje wymaganych wartosci w config.txt: " + ", ".join(missing)
        )

    if values["k"] < 0:
        raise ValueError("Wartosc K w config.txt nie moze byc ujemna.")
    if values["d"] <= 0:
        raise ValueError("Wartosc D w config.txt musi byc dodatnia.")

    return RankingConfig(k_factor=values["k"], d_factor=values["d"])


def oblicz_oczekiwane_elo(ranking_a: float, ranking_b: float, wskaznik_d: float) -> float:
    return 1 / (1 + 10 ** ((ranking_b - ranking_a) / wskaznik_d))


def aktualizacja_rankingu(
    lista_par: list[dict[str, object]],
    wskaznik_k: float,
    wskaznik_d: float,
) -> None:
    if wskaznik_d == 0:
        raise ValueError("Wskaznik D nie moze byc rowny 0.")

    n = len(lista_par)
    if n < 2:
        return

    zmiany = [0.0] * n
    for i in range(n):
        for j in range(n):
            if i == j:
                continue

            expected = oblicz_oczekiwane_elo(
                float(lista_par[i]["elo"]),
                float(lista_par[j]["elo"]),
                wskaznik_d,
            )
            place_i = int(lista_par[i]["place"])
            place_j = int(lista_par[j]["place"])

            if place_i < place_j:
                actual = 1.0
            elif place_i > place_j:
                actual = 0.0
            else:
                actual = 0.5

            zmiany[i] += actual - expected

    efektywne_k = wskaznik_k / (n - 1)
    for i in range(n):
        lista_par[i]["elo"] = float(lista_par[i]["elo"]) + zmiany[i] * efektywne_k


def przetworz_turniej(
    sciezka_do_pliku: str | Path,
    baza_danych: dict[tuple[str, str], Para],
    wskaznik_k: float | None = None,
    wskaznik_d: float | None = None,
    config_path: str | Path | None = None,
) -> None:
    if wskaznik_k is None or wskaznik_d is None:
        config = load_ranking_config(config_path)
        if wskaznik_k is None:
            wskaznik_k = config.k_factor
        if wskaznik_d is None:
            wskaznik_d = config.d_factor

    lista_do_kalkulatora: list[dict[str, object]] = []

    with open(sciezka_do_pliku, "r", encoding="utf-8") as plik:
        czytnik = csv.DictReader(plik, delimiter=";")

        for wiersz in czytnik:
            lokata = int(wiersz["Lokata"])
            nazwiska = wiersz["Para"].split(", ")
            if len(nazwiska) != 2:
                continue

            tancerz1, tancerz2 = nazwiska
            id_pary = (tancerz1, tancerz2)
            para = baza_danych.setdefault(id_pary, Para(tancerz1, tancerz2))

            lista_do_kalkulatora.append(
                {
                    "id": id_pary,
                    "elo": para.elo,
                    "place": lokata,
                }
            )

    aktualizacja_rankingu(lista_do_kalkulatora, wskaznik_k, wskaznik_d)

    for wpis in lista_do_kalkulatora:
        pair_id = wpis["id"]
        if not isinstance(pair_id, tuple):
            continue
        baza_danych[pair_id].elo = float(wpis["elo"])


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
    rsc_dir: str | Path = "rsc",
    years: Iterable[int | str] | None = None,
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

    baza_par: dict[tuple[str, str], Para] = {}
    skipped_files: list[tuple[str, str]] = []

    for file_path in matching_files:
        try:
            przetworz_turniej(
                file_path,
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


def format_ranking_table(ranking: Iterable[Para]) -> str:
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
