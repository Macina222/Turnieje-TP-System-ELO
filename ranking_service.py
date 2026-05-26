"""
Backend rankingu ELO dla par tańców polskich.

Przepływ systemu w tym module wygląda następująco:

1. `load_ranking_config` odczytuje parametry K, D oraz domyślne ELO per klasa z `config.txt`.
2. `collect_category_files` wybiera pliki `rsc/{rok}/{dd-mm-turniej}-{kategoria}.txt`
   pasujące do wybranych lat, rodziny kategorii i (opcjonalnie) klas.
   Pliki sortowane są chronologicznie: najpierw po roku, potem po (miesiąc, dzień).
3. `przetworz_turniej` wczytuje jeden plik z wynikami; nowe pary inicjalizowane są
   z domyślnym ELO odpowiadającym ich klasie (wyciągniętej z nazwy pliku).
4. `aktualizacja_rankingu` porównuje każdą parę z każdą inną w obrębie turnieju.
5. `build_ranking` powtarza ten proces dla wszystkich dopasowanych plików.
6. Funkcje formatujące zamieniają wynik obliczeń na raport tekstowy.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent / "config.txt"
DEFAULT_ELO = 1000.0

# Kolejność klas od najwyższej do najniższej (do sortowania wyświetlania)
CLASS_ORDER = ["S", "OPEN", "A", "B", "C"]

# Prefiksy kategorii bazowych — dłuższe muszą być sprawdzane pierwsze,
# żeby np. "VIII" nie wpadło do "VII" albo "V".
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


# ---------------------------------------------------------------------------
# Modele danych
# ---------------------------------------------------------------------------

@dataclass
class RankingConfig:
    """Przenosi parametry ELO odczytane z konfiguracji projektu."""
    k_factor: float
    d_factor: float
    # Domyślne ELO per klasa, np. {"C": 1000, "B": 1100, "A": 1200, "S": 1300}
    class_default_elos: dict[str, float]


@dataclass
class Para:
    """
    Reprezentuje jedną parę taneczną w trakcie budowania rankingu.

    `klasa` jest przypisywana przy pierwszym wystąpieniu pary i odpowiada
    sufiksowi kategorii z pliku, w którym para pojawiła się po raz pierwszy
    (np. "B" dla pliku z kategorią "VB", "OPEN" dla "VOPEN").
    """
    tancerz1: str
    tancerz2: str
    elo: float = DEFAULT_ELO
    klasa: str = ""

    def __post_init__(self) -> None:
        self.tancerz1 = normalize_dancer_name(self.tancerz1)
        self.tancerz2 = normalize_dancer_name(self.tancerz2)

    def pobierz_id(self) -> tuple[str, str]:
        """Zwraca stabilny identyfikator pary używany jako klucz słownika."""
        return self.tancerz1, self.tancerz2

    def __str__(self) -> str:
        klasa_label = self.klasa if self.klasa else "brak"
        return (
            f"Para: {self.tancerz1} i {self.tancerz2} "
            f"(ELO: {self.elo:.2f}, Klasa: {klasa_label})"
        )


@dataclass(frozen=True)
class TournamentEntry:
    """Jeden poprawny wpis pary odczytany z pliku wyników turnieju."""
    place: int
    tancerz1: str
    tancerz2: str
    osrodek: str = ""
    instruktor: str = ""

    def pobierz_id(self) -> tuple[str, str]:
        return self.tancerz1, self.tancerz2


@dataclass(frozen=True)
class RankingBuildResult:
    """
    Zbiera pełny rezultat pojedynczego przebiegu budowy rankingu.

    Zawiera zarówno ranking końcowy, jak i metadane potrzebne do raportu.
    """
    category: str
    years: tuple[int, ...]
    ranking: tuple[Para, ...]
    processed_files: tuple[Path, ...]
    included_categories: tuple[str, ...]
    included_classes: tuple[str, ...]   # klasy uwzględnione w tym przebiegu
    skipped_files: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class TournamentProgressRow:
    """Zmiana punktów jednej pary po jednym turnieju."""
    year: int
    tournament_date: str
    tournament_name: str
    source_file: str
    category: str
    exact_category: str
    klasa: str
    place: int
    tancerz1: str
    tancerz2: str
    pair_name: str
    points_before: float
    points_after: float
    points_delta: float


@dataclass(frozen=True)
class ProgressExportResult:
    """Pełny rezultat budowania historii zmian punktów pod eksport CSV."""
    category: str
    years: tuple[int, ...]
    rows: tuple[TournamentProgressRow, ...]
    processed_files: tuple[Path, ...]
    included_categories: tuple[str, ...]
    included_classes: tuple[str, ...]
    skipped_files: tuple[tuple[str, str], ...]


# ---------------------------------------------------------------------------
# Narzędzia pomocnicze — nazwy, kategorie, klasy
# ---------------------------------------------------------------------------

def normalize_dancer_name(raw_name: str) -> str:
    """Usuwa zbędne spacje i końcowe kropki z nazwy tancerza."""
    return raw_name.strip().rstrip(".").strip()


def parse_pair_names(raw_pair: str) -> tuple[str, str] | None:
    """
    Rozbija pole `Para` na dokładnie dwa nazwiska zapisane po przecinku.

    Zwraca `None`, jeśli rekord nie daje się jednoznacznie zinterpretować
    jako jedna para taneczna.
    """
    names = [normalize_dancer_name(name) for name in raw_pair.split(",")]
    if len(names) != 2 or any(not name for name in names):
        return None
    return names[0], names[1]


def extract_base_and_class(category_slug: str) -> tuple[str | None, str]:
    """
    Rozkłada slug kategorii na (kategoria_bazowa, klasa).

    Przykłady:
      'vb'     -> ('V', 'B')
      'iiic'   -> ('III', 'C')
      'vopen'  -> ('V', 'OPEN')
      'v'      -> ('V', '')
      'xiv'    -> (None, '')
    """
    if not category_slug:
        return None, ""
    normalized = category_slug.strip().lower()
    for label, prefix in BASE_CATEGORY_MATCHERS:
        if normalized.startswith(prefix):
            suffix = normalized[len(prefix):]
            return label, suffix.upper()
    return None, ""


def detect_base_category(category_slug: str | None) -> str | None:
    """Zwraca tylko kategorię bazową (I–VIII) z danego slugu."""
    if not category_slug:
        return None
    base, _ = extract_base_and_class(category_slug)
    return base


def extract_category_slug(file_path: str | Path) -> str | None:
    """
    Wyciąga końcówkę kategorii z nazwy pliku po ostatnim myślniku.

    Format pliku: {dd}-{mm}-{turniej}-{kategoria}.txt
    Przykład: '05-11-dobczyce-vb' -> 'vb'
    """
    path = Path(file_path)
    if "-" not in path.stem:
        return None
    return path.stem.rsplit("-", 1)[1].lower()


def sort_key_for_file(file_path: Path) -> tuple:
    """
    Klucz sortowania chronologicznego dla pliku turnieju.

    Oczekiwany format nazwy: {dd}-{mm}-{turniej}-{kategoria}.txt
    Zwraca (miesiąc, dzień, stem) — dzięki temu pliki z tego samego roku
    są przetwarzane w kolejności chronologicznej.
    """
    parts = file_path.stem.split("-")
    try:
        day = int(parts[0])
        month = int(parts[1])
        return (month, day, file_path.stem)
    except (ValueError, IndexError):
        # Jeśli nazwa nie pasuje do formatu, trafia na koniec
        return (99, 99, file_path.stem)


def _class_sort_key(klasa: str) -> tuple:
    """Klucz sortowania klas według CLASS_ORDER, nieznane klasy na końcu."""
    try:
        return (0, CLASS_ORDER.index(klasa), klasa)
    except ValueError:
        return (1, 0, klasa)


def format_class_for_display(klasa: str) -> str:
    """Zwraca czytelną etykietę klasy do raportów i komunikatów."""
    return klasa if klasa else "(brak sufiksu)"


def format_classes_for_display(classes: Iterable[str]) -> str:
    """Formatuje listę klas do wyświetlenia użytkownikowi."""
    class_list = list(classes)
    if not class_list:
        return "wszystkie"
    return ", ".join(format_class_for_display(klasa) for klasa in class_list)


def _class_for_filename(klasa: str) -> str:
    """Zwraca bezpieczny fragment nazwy pliku dla klasy."""
    return klasa if klasa else "bez_sufiksu"


def describe_tournament_file(
    file_path: str | Path,
    rsc_dir: str | Path = "rsc",
) -> dict[str, object]:
    """
    Wyciąga metadane turnieju z nazwy pliku `rsc/{rok}/{dd-mm-turniej}-{kat}.txt`.

    Zwraca słownik z rokiem, datą ISO, nazwą turnieju, relatywną ścieżką pliku,
    podkategorią i klasą. Przy nietypowej nazwie zostawia puste wartości tam,
    gdzie nie da się ich wiarygodnie odczytać.
    """
    path = Path(file_path)
    root = Path(rsc_dir)
    year = int(path.parent.name) if path.parent.name.isdigit() else 0
    category_slug = extract_category_slug(path) or ""
    base_category, klasa = extract_base_and_class(category_slug)

    try:
        source_file = str(path.relative_to(root))
    except ValueError:
        source_file = str(path)

    tournament_date = ""
    tournament_name = path.stem
    parts = path.stem.split("-")
    if len(parts) >= 4:
        try:
            day = int(parts[0])
            month = int(parts[1])
            tournament_date = (
                f"{year:04d}-{month:02d}-{day:02d}"
                if year
                else f"{day:02d}-{month:02d}"
            )
            tournament_name = "-".join(parts[2:-1]) or path.stem
        except ValueError:
            pass

    return {
        "year": year,
        "tournament_date": tournament_date,
        "tournament_name": tournament_name,
        "source_file": source_file,
        "category": base_category or "",
        "exact_category": category_slug.upper(),
        "klasa": klasa,
    }


# ---------------------------------------------------------------------------
# Konfiguracja
# ---------------------------------------------------------------------------

def _parse_config_number(raw_value: str, key: str, line_number: int) -> float:
    """Parsuje pojedynczą wartość liczbową z `config.txt` wraz z walidacją."""
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
    """
    Wczytuje parametry ELO z pliku konfiguracyjnego projektu.

    Obsługuje klucze:
      K=<liczba>          — współczynnik K
      D=<liczba>          — współczynnik D
      defaulteloC=<liczba> — domyślne ELO dla klasy C
      defaulteloB=<liczba> — domyślne ELO dla klasy B
      defaulteloA=<liczba> — domyślne ELO dla klasy A
      defaulteloS=<liczba> — domyślne ELO dla klasy S
    """
    path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
    if not path.is_file():
        raise FileNotFoundError(f"Nie znaleziono pliku konfiguracyjnego: {path}")

    values: dict[str, float] = {}
    class_elos: dict[str, float] = {}

    for line_number, raw_line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
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

        if normalized_key in {"k", "d"}:
            values[normalized_key] = _parse_config_number(
                value, normalized_key.upper(), line_number
            )
        elif normalized_key.startswith("defaultelo"):
            klasa = normalized_key[len("defaultelo"):].upper()
            class_elos[klasa] = _parse_config_number(value, normalized_key, line_number)

    missing = [key.upper() for key in ("k", "d") if key not in values]
    if missing:
        raise ValueError(
            "Brakuje wymaganych wartosci w config.txt: " + ", ".join(missing)
        )
    if values["k"] < 0:
        raise ValueError("Wartosc K w config.txt nie moze byc ujemna.")
    if values["d"] <= 0:
        raise ValueError("Wartosc D w config.txt musi byc dodatnia.")

    return RankingConfig(
        k_factor=values["k"],
        d_factor=values["d"],
        class_default_elos=class_elos,
    )


def get_default_elo_for_class(klasa: str, class_default_elos: dict[str, float]) -> float:
    """
    Zwraca domyślne ELO dla danej klasy.

    Jeśli klasa nie jest skonfigurowana (np. "AB", ""), zwraca najniższe
    z dostępnych domyślnych ELO — zgodnie z założeniem, że nieznana klasa
    traktowana jest jako najniższa.
    """
    if klasa in class_default_elos:
        return class_default_elos[klasa]
    if class_default_elos:
        return min(class_default_elos.values())
    return DEFAULT_ELO


# ---------------------------------------------------------------------------
# Algorytm ELO
# ---------------------------------------------------------------------------

def oblicz_oczekiwane_elo(ranking_a: float, ranking_b: float, wskaznik_d: float) -> float:
    """Liczy oczekiwany wynik pary A przeciwko parze B według wzoru ELO."""
    return 1 / (1 + 10 ** ((ranking_b - ranking_a) / wskaznik_d))


def aktualizacja_rankingu(
    lista_par: list[dict[str, object]],
    wskaznik_k: float,
    wskaznik_d: float,
) -> None:
    """
    Aktualizuje ELO wszystkich par biorących udział w jednym turnieju.

    Algorytm:
    1. Każda para porównywana jest z każdą inną.
    2. Wyznaczany jest wynik oczekiwany na podstawie aktualnego ELO.
    3. Lokaty zamieniają się na wynik: wygrana (1), porażka (0), remis (0.5).
    4. Sumowane są różnice actual - expected.
    5. Zmiana ELO skalowana jest przez efektywne K = K / (n-1).
    """
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


# ---------------------------------------------------------------------------
# Przetwarzanie plików
# ---------------------------------------------------------------------------

def read_tournament_entries(sciezka_do_pliku: str | Path) -> list[TournamentEntry]:
    """
    Wczytuje poprawne wpisy par z pojedynczego pliku wynikowego.

    Rekordy z niejednoznacznym polem `Para` są pomijane tak samo jak w
    dotychczasowym przetwarzaniu rankingu. Brak wymaganych kolumn albo
    niepoprawna lokata przerywają przetwarzanie pliku.
    """
    entries: list[TournamentEntry] = []

    with open(sciezka_do_pliku, "r", encoding="utf-8") as plik:
        czytnik = csv.DictReader(plik, delimiter=";")
        for line_number, wiersz in enumerate(czytnik, start=2):
            try:
                lokata = int(str(wiersz["Lokata"]).strip())
                raw_pair = wiersz["Para"]
            except KeyError as exc:
                raise KeyError(f"Brak wymaganej kolumny w pliku: {exc}") from exc
            except ValueError as exc:
                raise ValueError(
                    f"Nieprawidlowa lokata w linii {line_number}: {wiersz.get('Lokata')!r}"
                ) from exc

            para_nazwy = parse_pair_names(raw_pair)
            if para_nazwy is None:
                continue

            entries.append(
                TournamentEntry(
                    place=lokata,
                    tancerz1=para_nazwy[0],
                    tancerz2=para_nazwy[1],
                    osrodek=str(wiersz.get("Ośrodek", "") or "").strip(),
                    instruktor=str(wiersz.get("Instruktor", "") or "").strip(),
                )
            )

    return entries


def _ensure_pair_in_database(
    baza_danych: dict[tuple[str, str], Para],
    entry: TournamentEntry,
    file_class: str,
    class_default_elos: dict[str, float],
) -> Para:
    """Dodaje nową parę do bazy z domyślnym ELO, jeśli jeszcze jej nie ma."""
    id_pary = entry.pobierz_id()
    if id_pary not in baza_danych:
        default_elo = get_default_elo_for_class(file_class, class_default_elos)
        baza_danych[id_pary] = Para(
            entry.tancerz1,
            entry.tancerz2,
            elo=default_elo,
            klasa=file_class,
        )
    return baza_danych[id_pary]


def przetworz_turniej(
    sciezka_do_pliku: str | Path,
    baza_danych: dict[tuple[str, str], Para],
    wskaznik_k: float | None = None,
    wskaznik_d: float | None = None,
    config_path: str | Path | None = None,
    file_class: str = "",
    class_default_elos: dict[str, float] | None = None,
) -> None:
    """
    Przetwarza jeden plik z wynikami i zapisuje zmiany w wspólnej bazie par.

    Nowe pary (niewidziane wcześniej) inicjalizowane są z domyślnym ELO
    odpowiadającym `file_class`. Klasa pary jest przypisywana raz na zawsze
    przy pierwszym wystąpieniu.
    """
    if wskaznik_k is None or wskaznik_d is None:
        config = load_ranking_config(config_path)
        if wskaznik_k is None:
            wskaznik_k = config.k_factor
        if wskaznik_d is None:
            wskaznik_d = config.d_factor
        if class_default_elos is None:
            class_default_elos = config.class_default_elos

    if class_default_elos is None:
        class_default_elos = {}

    lista_do_kalkulatora: list[dict[str, object]] = []
    entries = read_tournament_entries(sciezka_do_pliku)

    for entry in entries:
        para = _ensure_pair_in_database(
            baza_danych,
            entry,
            file_class=file_class,
            class_default_elos=class_default_elos,
        )
        lista_do_kalkulatora.append({
            "id": entry.pobierz_id(),
            "elo": para.elo,
            "place": entry.place,
        })

    aktualizacja_rankingu(lista_do_kalkulatora, wskaznik_k, wskaznik_d)

    for wpis in lista_do_kalkulatora:
        pair_id = wpis["id"]
        if not isinstance(pair_id, tuple):
            continue
        baza_danych[pair_id].elo = float(wpis["elo"])


# ---------------------------------------------------------------------------
# Odkrywanie dostępnych danych
# ---------------------------------------------------------------------------

def list_available_years(rsc_dir: str | Path = "rsc") -> list[int]:
    """Zwraca posortowaną listę lat dostępnych jako katalogi w `rsc/`."""
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
    """
    Wykrywa bazowe kategorie (I–VIII) dostępne dla wskazanych lat.
    """
    root = Path(rsc_dir)
    selected_years = normalize_years(years) if years else tuple(list_available_years(root))
    found_categories: set[str] = set()
    for year in selected_years:
        year_dir = root / str(year)
        if not year_dir.is_dir():
            continue
        for file_path in year_dir.glob("*.txt"):
            category_slug = extract_category_slug(file_path)
            base_category = detect_base_category(category_slug)
            if base_category:
                found_categories.add(base_category)
    return [category for category in BASE_CATEGORIES if category in found_categories]


def list_available_classes_for_category_and_years(
    rsc_dir: str | Path,
    base_category: str,
    years: Iterable[int | str] | None = None,
) -> list[str]:
    """
    Wykrywa klasy (B, A, S, OPEN, …) dostępne dla danej kategorii bazowej i lat.

    Klasy sortowane są według CLASS_ORDER (S, OPEN, A, B, C), nieznane na końcu.
    """
    root = Path(rsc_dir)
    selected_years = normalize_years(years) if years else tuple(list_available_years(root))
    found_classes: set[str] = set()
    for year in selected_years:
        year_dir = root / str(year)
        if not year_dir.is_dir():
            continue
        for file_path in year_dir.glob("*.txt"):
            category_slug = extract_category_slug(file_path)
            if not category_slug:
                continue
            base, klasa = extract_base_and_class(category_slug)
            if base == base_category:
                found_classes.add(klasa)
    return sorted(found_classes, key=_class_sort_key)


def normalize_years(years: Iterable[int | str] | None) -> tuple[int, ...]:
    """Normalizuje listę lat do unikalnej, posortowanej krotki liczb całkowitych."""
    if years is None:
        return tuple()
    normalized = {
        int(str(year).strip())
        for year in years
        if str(year).strip()
    }
    return tuple(sorted(normalized))


# ---------------------------------------------------------------------------
# Zbieranie i budowanie rankingu
# ---------------------------------------------------------------------------

def collect_category_files(
    category: str,
    years: Iterable[int | str],
    rsc_dir: str | Path = "rsc",
    classes: Iterable[str] | None = None,
) -> tuple[list[Path], list[str], list[str]]:
    """
    Zbiera pliki pasujące do kategorii, lat i (opcjonalnie) klas.

    Pliki sortowane są chronologicznie: rok rosnąco, a w obrębie roku
    po (miesiąc, dzień) wyciągniętych z nazwy {dd}-{mm}-{turniej}-{kat}.txt.

    Zwraca:
      (lista_plików, uwzględnione_podkategorie, uwzględnione_klasy)
    """
    root = Path(rsc_dir)
    normalized_category = detect_base_category(category)
    selected_years = normalize_years(years)
    selected_classes = (
        {c.upper() for c in classes} if classes is not None else None
    )

    if not normalized_category:
        raise ValueError(f"Nieznana kategoria rankingu: {category}")
    if not selected_years:
        raise ValueError("Wybierz przynajmniej jeden rok.")

    matching_files: list[Path] = []
    exact_categories: set[str] = set()
    found_classes: set[str] = set()

    for year in selected_years:
        year_dir = root / str(year)
        if not year_dir.is_dir():
            continue
        # Sortowanie chronologiczne wewnątrz roku
        year_files = sorted(year_dir.glob("*.txt"), key=sort_key_for_file)
        for file_path in year_files:
            category_slug = extract_category_slug(file_path)
            if not category_slug:
                continue
            base, klasa = extract_base_and_class(category_slug)
            if base != normalized_category:
                continue
            if selected_classes is not None and klasa not in selected_classes:
                continue
            matching_files.append(file_path)
            exact_categories.add(category_slug.upper())
            found_classes.add(klasa)

    return (
        matching_files,
        sorted(exact_categories),
        sorted(found_classes, key=_class_sort_key),
    )


def build_ranking(
    category: str,
    years: Iterable[int | str],
    rsc_dir: str | Path = "rsc",
    k_factor: float | None = None,
    d_factor: float | None = None,
    config_path: str | Path | None = None,
    classes: Iterable[str] | None = None,
) -> RankingBuildResult:
    """
    Buduje pełny ranking dla wybranej kategorii, lat i (opcjonalnie) klas.

    Główna funkcja backendu:
    1. Normalizuje filtry wejściowe.
    2. Dobiera konfigurację ELO (K, D, domyślne ELO per klasa).
    3. Zbiera pasujące pliki w kolejności chronologicznej.
    4. Przetwarza każdy turniej, przekazując klasę pliku do inicjalizacji nowych par.
    5. Sortuje pary malejąco po ELO.
    """
    normalized_category = detect_base_category(category)
    selected_years = normalize_years(years)

    config = load_ranking_config(config_path)
    if k_factor is None:
        k_factor = config.k_factor
    if d_factor is None:
        d_factor = config.d_factor
    class_default_elos = config.class_default_elos

    matching_files, included_categories, included_classes = collect_category_files(
        category=category,
        years=selected_years,
        rsc_dir=rsc_dir,
        classes=classes,
    )

    if not matching_files:
        years_label = ", ".join(str(year) for year in selected_years)
        raise ValueError(
            f"Brak plików dla kategorii {normalized_category} w latach: {years_label}."
        )

    baza_par: dict[tuple[str, str], Para] = {}
    skipped_files: list[tuple[str, str]] = []

    for file_path in matching_files:
        category_slug = extract_category_slug(file_path)
        _, file_class = extract_base_and_class(category_slug or "")
        try:
            przetworz_turniej(
                file_path,
                baza_par,
                k_factor,
                d_factor,
                config_path=config_path,
                file_class=file_class,
                class_default_elos=class_default_elos,
            )
        except Exception as exc:
            skipped_files.append((str(file_path), str(exc)))

    ranking = tuple(
        sorted(baza_par.values(), key=lambda para: para.elo, reverse=True)
    )

    return RankingBuildResult(
        category=normalized_category or category.upper(),
        years=selected_years,
        ranking=ranking,
        processed_files=tuple(matching_files),
        included_categories=tuple(included_categories),
        included_classes=tuple(included_classes),
        skipped_files=tuple(skipped_files),
    )


def build_progress_export(
    category: str,
    years: Iterable[int | str],
    rsc_dir: str | Path = "rsc",
    k_factor: float | None = None,
    d_factor: float | None = None,
    config_path: str | Path | None = None,
    classes: Iterable[str] | None = None,
) -> ProgressExportResult:
    """
    Buduje historię zmian punktów par po każdym turnieju.

    Zwracane wiersze odpowiadają występom par w kolejnych plikach turniejowych.
    Dla każdego występu zapisane są punkty przed turniejem, punkty po turnieju,
    różnica oraz lokata pary w tym turnieju.
    """
    normalized_category = detect_base_category(category)
    selected_years = normalize_years(years)

    config = load_ranking_config(config_path)
    if k_factor is None:
        k_factor = config.k_factor
    if d_factor is None:
        d_factor = config.d_factor
    class_default_elos = config.class_default_elos

    matching_files, included_categories, included_classes = collect_category_files(
        category=category,
        years=selected_years,
        rsc_dir=rsc_dir,
        classes=classes,
    )

    if not matching_files:
        years_label = ", ".join(str(year) for year in selected_years)
        raise ValueError(
            f"Brak plików dla kategorii {normalized_category} w latach: {years_label}."
        )

    root = Path(rsc_dir)
    baza_par: dict[tuple[str, str], Para] = {}
    rows: list[TournamentProgressRow] = []
    skipped_files: list[tuple[str, str]] = []

    for file_path in matching_files:
        category_slug = extract_category_slug(file_path)
        _, file_class = extract_base_and_class(category_slug or "")

        try:
            entries = read_tournament_entries(file_path)
            lista_do_kalkulatora: list[dict[str, object]] = []
            points_before: list[float] = []

            for entry in entries:
                para = _ensure_pair_in_database(
                    baza_par,
                    entry,
                    file_class=file_class,
                    class_default_elos=class_default_elos,
                )
                points_before.append(para.elo)
                lista_do_kalkulatora.append({
                    "id": entry.pobierz_id(),
                    "elo": para.elo,
                    "place": entry.place,
                })

            aktualizacja_rankingu(lista_do_kalkulatora, k_factor, d_factor)

            points_after = [float(wpis["elo"]) for wpis in lista_do_kalkulatora]
            for wpis in lista_do_kalkulatora:
                pair_id = wpis["id"]
                if not isinstance(pair_id, tuple):
                    continue
                baza_par[pair_id].elo = float(wpis["elo"])

            file_info = describe_tournament_file(file_path, root)
            for entry, before, after in zip(entries, points_before, points_after):
                rows.append(
                    TournamentProgressRow(
                        year=int(file_info["year"]),
                        tournament_date=str(file_info["tournament_date"]),
                        tournament_name=str(file_info["tournament_name"]),
                        source_file=str(file_info["source_file"]),
                        category=str(file_info["category"]),
                        exact_category=str(file_info["exact_category"]),
                        klasa=str(file_info["klasa"]),
                        place=entry.place,
                        tancerz1=entry.tancerz1,
                        tancerz2=entry.tancerz2,
                        pair_name=f"{entry.tancerz1}, {entry.tancerz2}",
                        points_before=before,
                        points_after=after,
                        points_delta=after - before,
                    )
                )
        except Exception as exc:
            skipped_files.append((str(file_path), str(exc)))

    return ProgressExportResult(
        category=normalized_category or category.upper(),
        years=selected_years,
        rows=tuple(rows),
        processed_files=tuple(matching_files),
        included_categories=tuple(included_categories),
        included_classes=tuple(included_classes),
        skipped_files=tuple(skipped_files),
    )


# ---------------------------------------------------------------------------
# Formatowanie raportu
# ---------------------------------------------------------------------------

def format_ranking_table(ranking: Iterable[Para]) -> str:
    """Formatuje samą tabelę rankingową do postaci tekstowej."""
    header = f"{'Miejsce':<8} | {'Para':<50} | {'ELO':<10} | Klasa"
    separator = "-" * 82
    lines = [header, separator]
    has_rows = False
    for place, para in enumerate(ranking, start=1):
        has_rows = True
        pair_name = f"{para.tancerz1}, {para.tancerz2}"
        klasa_display = para.klasa if para.klasa else "-"
        lines.append(
            f"{place:<8} | {pair_name:<50} | {para.elo:<10.2f} | {klasa_display}"
        )
    if not has_rows:
        lines.append("Brak wyników dla wybranych filtrów.")
    return "\n".join(lines)


def format_ranking_report(result: RankingBuildResult) -> str:
    """
    Buduje pełny raport tekstowy na podstawie wyniku obliczeń.

    Zawiera filtry wejściowe, liczbę plików, listę podkategorii i klas,
    tabelę rankingową oraz ewentualne pliki pominięte z błędami.
    """
    classes_label = format_classes_for_display(result.included_classes)
    lines = [
        f"Kategoria bazowa: {result.category}",
        f"Klasy: {classes_label}",
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
    """Tworzy domyślną nazwę pliku raportu z kategorii, klas i zakresu lat."""
    if result.included_classes:
        classes_part = "_".join(
            _class_for_filename(klasa) for klasa in result.included_classes
        )
    else:
        classes_part = "wszystkie"

    if len(result.years) == 1:
        years_part = str(result.years[0])
    elif len(result.years) <= 4:
        years_part = "_".join(str(year) for year in result.years)
    else:
        years_part = f"{result.years[0]}-{result.years[-1]}_{len(result.years)}lat"

    return f"ranking_{result.category.lower()}_{classes_part}_{years_part}.txt"


def build_default_progress_filename(result: ProgressExportResult) -> str:
    """Tworzy domyślną nazwę pliku CSV z historią zmian punktów."""
    if result.included_classes:
        classes_part = "_".join(
            _class_for_filename(klasa) for klasa in result.included_classes
        )
    else:
        classes_part = "wszystkie"

    if len(result.years) == 1:
        years_part = str(result.years[0])
    elif len(result.years) <= 4:
        years_part = "_".join(str(year) for year in result.years)
    else:
        years_part = f"{result.years[0]}-{result.years[-1]}_{len(result.years)}lat"

    return f"progress_{result.category.lower()}_{classes_part}_{years_part}.csv"


def save_ranking_report(report_text: str, output_path: str | Path) -> Path:
    """Zapisuje gotowy raport tekstowy do wskazanego pliku."""
    path = Path(output_path)
    path.write_text(report_text, encoding="utf-8")
    return path


def save_progress_csv(
    result: ProgressExportResult,
    output_path: str | Path,
    delimiter: str = ";",
    encoding: str = "utf-8-sig",
) -> Path:
    """Zapisuje historię zmian punktów do pliku CSV."""
    path = Path(output_path)
    fieldnames = [
        "rok",
        "data_turnieju",
        "turniej",
        "plik",
        "kategoria_bazowa",
        "podkategoria",
        "klasa",
        "lokata",
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
            writer.writerow({
                "rok": row.year,
                "data_turnieju": row.tournament_date,
                "turniej": row.tournament_name,
                "plik": row.source_file,
                "kategoria_bazowa": row.category,
                "podkategoria": row.exact_category,
                "klasa": row.klasa if row.klasa else "-",
                "lokata": row.place,
                "para": row.pair_name,
                "tancerz_1": row.tancerz1,
                "tancerz_2": row.tancerz2,
                "punkty_przed": f"{row.points_before:.2f}",
                "punkty_po": f"{row.points_after:.2f}",
                "roznica_punktow": f"{row.points_delta:.2f}",
            })

    return path
