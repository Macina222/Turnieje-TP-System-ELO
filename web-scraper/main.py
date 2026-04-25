"""
Scraper zasilający kalkulator rankingu danymi z archiwum wyników.

Rola modułu w całym systemie:
1. wchodzi na stronę główną archiwum i pobiera listę lat,
2. dla każdego roku odczytuje listę turniejów,
3. dla każdego turnieju pobiera wszystkie tabele kategorii i ich wiersze,
4. normalizuje kolumny oraz zapis par do wspólnego formatu,
5. zapisuje wynik jako CSV albo bezpośrednio do struktury `rsc/`,
6. dzięki temu backend z `ranking_service.py` dostaje dane wejściowe w formacie,
   który może przeliczać na ranking ELO bez dodatkowych transformacji.

Domyślny wynik to `wyniki_par.csv` z kolumnami:
`rok`, `turniej`, `turniej_id`, `kategoria`, `miejsce`, `para`, `osrodek`,
`instruktor`.
"""

import argparse
import csv
import re
import sys
import time
from datetime import datetime
from pathlib import Path
import unicodedata

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
except ImportError:
    sys.exit("Zainstaluj: pip install playwright && playwright install chromium")

try:
    import pandas as pd
    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False

BASE_URL = "https://archiwum-tp.cioff.pl"
DEFAULT_OUTPUT = "wyniki_par.csv"
DEFAULT_RSC_DIR = "rsc"
TIMEOUT = 30_000


def log(msg: str, level: str = "INFO"):
    """Wypisuje komunikat diagnostyczny z poziomem logowania i godziną."""

    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] [{level}] {msg}", flush=True)


# ──────────────────────────────────────────────────────────────
# Czyszczenie danych
# ──────────────────────────────────────────────────────────────

def clean_tournament_name(raw: str) -> str:
    """
    Czyści nazwę turnieju pobraną z kafelka na stronie.

    Kafelek zawiera zwykle kilka linii: nazwę, datę, miasto i tekst linku.
    Scraper bierze tylko pierwszą niepustą linię, bo to ona stanowi stabilną
    nazwę turnieju używaną później w CSV i nazwach plików.
    """
    for line in raw.splitlines():
        line = line.strip()
        if line:
            return line
    return raw.strip()


def split_pair(raw: str) -> list[str]:
    """Rozbija zapis pary z wielu linii HTML na listę pojedynczych osób."""

    return [p.strip() for p in raw.splitlines() if p.strip()]


def clean_pair(raw: str, separator: str = "; ") -> str:
    """
    Scala wieloliniowy zapis pary do jednej linii.

    To ważne, bo w tabelach HTML partner i partnerka często stoją w osobnych
    liniach komórki, a backend rankingu oczekuje jednego pola tekstowego.
    """
    return separator.join(split_pair(raw))


def normalize_text_for_filename(text: str) -> str:
    """Normalizuje tekst do bezpiecznej, ASCII-owej postaci nazwy pliku."""

    normalized = unicodedata.normalize("NFKD", text)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    ascii_text = ascii_text.lower().strip()
    ascii_text = re.sub(r"\s+", "_", ascii_text)
    ascii_text = re.sub(r"[^a-z0-9_]+", "", ascii_text)
    ascii_text = re.sub(r"_+", "_", ascii_text).strip("_")
    return ascii_text or "nieznane"


def tournament_filename_part(name: str) -> str:
    """Buduje fragment nazwy pliku reprezentujący nazwę turnieju."""

    clean_name = re.sub(r"\s+\d{4}$", "", name.strip(), flags=re.IGNORECASE)
    return normalize_text_for_filename(clean_name)


def category_filename_part(category: str) -> str:
    """Buduje fragment nazwy pliku reprezentujący kategorię turniejową."""

    clean_category = re.sub(r"^\s*kategoria\s+", "", category.strip(), flags=re.IGNORECASE)
    clean_category = clean_category.replace("-", " ")
    return normalize_text_for_filename(clean_category).replace("_", "")


# ──────────────────────────────────────────────────────────────
# Krok 1: lata ze strony głównej
# ──────────────────────────────────────────────────────────────

def get_years(page) -> list:
    """
    Pobiera dostępne lata ze strony głównej archiwum.

    To pierwszy krok scrapera, od którego zaczyna się iteracja po całym serwisie.
    """

    log("Pobieram listę lat...")
    page.goto(BASE_URL, wait_until="networkidle", timeout=TIMEOUT)
    page.wait_for_timeout(2000)

    hrefs = page.evaluate("""
        () => Array.from(document.querySelectorAll('a[href]'))
                   .map(a => a.getAttribute('href'))
    """)
    years = []
    for href in hrefs:
        if not href:
            continue
        m = re.search(r"/(\d{4})/?$", href)
        if m:
            year = m.group(1)
            if year not in years:
                years.append(year)

    years.sort(reverse=True)
    log(f"Znalezione lata: {years}")
    return years


# ──────────────────────────────────────────────────────────────
# Krok 2: turnieje dla danego roku
# ──────────────────────────────────────────────────────────────

def get_tournaments(page, year: str) -> list:
    """
    Pobiera wszystkie turnieje widoczne dla wskazanego roku.

    Dla każdego linku wyciąga nazwę, identyfikator i pełny URL, z których potem
    korzysta etap pobierania tabel wynikowych.
    """

    url = f"{BASE_URL}/{year}/"
    log(f"  [{year}] Pobieram turnieje: {url}")
    page.goto(url, wait_until="networkidle", timeout=TIMEOUT)
    page.wait_for_timeout(1500)

    link_data = page.evaluate("""
        () => Array.from(document.querySelectorAll('a[href]'))
                   .map(a => ({
                       href: a.getAttribute('href'),
                       text: a.innerText.trim()
                   }))
    """)

    tournaments = []
    for item in link_data:
        href = item.get("href") or ""
        text = item.get("text") or ""
        m = re.search(rf"/{year}/(.+?-id-(\d+))/?$", href)
        if not m:
            continue
        slug = m.group(1)
        tid = int(m.group(2))
        if any(t["id"] == tid for t in tournaments):
            continue

        # Czyścimy nazwę – bierzemy tylko pierwszą linię tekstu kafelka
        name = clean_tournament_name(text) if text else \
               re.sub(r"-id-\d+$", "", slug).replace("-", " ").strip().upper()

        tournaments.append({
            "name": name,
            "id": tid,
            "url": f"{BASE_URL}/{year}/{slug}",
            "year": year,
        })

    log(f"    Znaleziono {len(tournaments)} turniejów: {[t['name'] for t in tournaments]}")
    return tournaments


# ──────────────────────────────────────────────────────────────
# Krok 3: wyniki z jednego turnieju
# ──────────────────────────────────────────────────────────────

def get_results(page, tournament: dict, debug: bool) -> list:
    """
    Pobiera i normalizuje wszystkie wyniki z pojedynczego turnieju.

    Funkcja:
    1. otwiera stronę turnieju,
    2. znajduje wszystkie tabele wyników,
    3. przypisuje każdej tabeli kategorię,
    4. normalizuje nazwy kolumn,
    5. scala dane w listę rekordów gotowych do zapisu.
    """

    url = tournament["url"]
    log(f"    [{tournament['year']}] {tournament['name']} (id={tournament['id']})")

    try:
        page.goto(url, wait_until="networkidle", timeout=TIMEOUT)
        page.wait_for_timeout(1500)
    except PWTimeout:
        log(f"    Timeout dla {url}", "WARN")
        return []

    if debug:
        path = f"debug_{tournament['id']}.png"
        page.screenshot(path=path)
        log(f"    Zrzut: {path}", "DEBUG")

    # Pobieramy wszystkie bloki kategorii przez JavaScript w jednym wywołaniu.
    #
    # Struktura DOM (zweryfikowana):
    #   <div class="mb-12">
    #       <h3 ...>Kategoria I</h3>
    #       <div>...<table>...</table></div>
    #   </div>
    #
    # Sama tabela jest opakowana dodatkowymi <div>, więc `closest('div')`
    # trafia w wewnętrzny wrapper bez nagłówka. Szukamy więc najpierw
    # sekcji `.mb-12`, a dopiero później stosujemy fallbacki.

    raw_data = page.evaluate("""
        () => {
            const blocks = [];
            const getCategoryForTable = (table) => {
                // Główny przypadek: sekcja wyników ma kontener `.mb-12`
                // z nagłówkiem h3 stojącym nad tabelą.
                const section = table.closest('div.mb-12');
                if (section) {
                    const heading = section.querySelector('h3');
                    if (heading && heading.innerText.trim()) {
                        return heading.innerText.trim();
                    }
                }

                // Fallback: najbliższy poprzedni nagłówek w drzewie DOM.
                let node = table;
                while (node) {
                    let prev = node.previousElementSibling;
                    while (prev) {
                        const heading = prev.matches?.('h1, h2, h3, h4, h5, h6')
                            ? prev
                            : prev.querySelector?.('h1, h2, h3, h4, h5, h6');
                        if (heading && heading.innerText.trim()) {
                            return heading.innerText.trim();
                        }
                        prev = prev.previousElementSibling;
                    }
                    node = node.parentElement;
                }

                // Ostateczny fallback: caption wewnątrz tabeli.
                const caption = table.querySelector('caption');
                return caption ? caption.innerText.trim() : '';
            };

            document.querySelectorAll('table').forEach(table => {
                const category = getCategoryForTable(table);

                // Nagłówki kolumn
                const headers = Array.from(
                    table.querySelectorAll('thead th, thead td')
                ).map(el => el.innerText.trim());

                // Wiersze danych
                let rows = Array.from(table.querySelectorAll('tbody tr'));
                if (!rows.length) {
                    const all = Array.from(table.querySelectorAll('tr'));
                    rows = all.slice(headers.length ? 1 : 0);
                }

                rows.forEach(tr => {
                    const cells = Array.from(tr.querySelectorAll('td, th'))
                                       .map(td => td.innerText.trim());
                    if (cells.length && cells.some(c => c !== ''))
                        blocks.push({ category, headers, cells });
                });
            });
            return blocks;
        }
    """)

    base = {
        "rok":        tournament["year"],
        "turniej":    tournament["name"],
        "turniej_id": tournament["id"],
    }

    records = []
    for row in raw_data:
        category = row.get("category") or "nieznana"
        headers  = row.get("headers") or []
        cells    = row.get("cells") or []

        if headers and len(cells) >= len(headers):
            mapped = {_normalize_col(h): cells[i] for i, h in enumerate(headers)}
        else:
            mapped = {f"kol_{i}": v for i, v in enumerate(cells)}

        # Wyczyść pole "para" – zamień \n na "; "
        if "para" in mapped:
            mapped["para"] = clean_pair(mapped["para"])

        records.append({**base, "kategoria": category, **mapped})

    if records:
        log(f"      Pobrano {len(records)} wyników w {len(set(r['kategoria'] for r in records))} kategoriach")
    else:
        log(f"      Brak wyników – uruchom z --debug", "WARN")

    return records


def _normalize_col(name: str) -> str:
    """Mapuje różne nagłówki tabel na wspólne klucze używane w eksporcie."""
    n = name.lower().strip()
    if re.match(r"^(lp\.?|nr\.?|#|lokata|miejsce|place|poz\.?|rank)$", n):
        return "miejsce"
    if any(x in n for x in ["para", "pair", "tancerz", "zawodnik", "nazwa"]):
        return "para"
    if any(x in n for x in ["ośrodek", "osrodek", "zesp", "group", "club", "klub", "org"]):
        return "osrodek"
    if any(x in n for x in ["instruktor", "trener", "coach"]):
        return "instruktor"
    if any(x in n for x in ["pkt", "point", "wynik", "score", "suma"]):
        return "punkty"
    return name.lower()


# ──────────────────────────────────────────────────────────────
# Zapis CSV
# ──────────────────────────────────────────────────────────────

PREFERRED_COLS = ["rok", "turniej", "turniej_id", "kategoria", "miejsce", "para", "osrodek", "instruktor", "punkty"]


def save_csv(records: list, output_path: str):
    """
    Zapisuje zebrane rekordy do jednego pliku CSV.

    Jeśli dostępny jest `pandas`, funkcja dodatkowo usuwa duplikaty i porządkuje
    kolumny według preferowanej kolejności.
    """

    if not records:
        log("Brak danych do zapisania.", "WARN")
        return

    if HAS_PANDAS:
        df = pd.DataFrame(records)
        cols = [c for c in PREFERRED_COLS if c in df.columns]
        extra = [c for c in df.columns if c not in cols]
        df = df[cols + extra]
        before = len(df)
        df = df.drop_duplicates()
        if before != len(df):
            log(f"Usunięto {before - len(df)} duplikatów.")
        df.to_csv(output_path, index=False, encoding="utf-8-sig")
        log(f"\nZapisano {len(df)} wierszy → {output_path}")
        log(f"Kolumny: {list(df.columns)}")
        print("\n--- Podgląd (pierwsze 10 wierszy) ---")
        print(df.head(10).to_string(index=False))
    else:
        all_keys: list = []
        for r in records:
            for k in r:
                if k not in all_keys:
                    all_keys.append(k)
        ordered = [k for k in PREFERRED_COLS if k in all_keys]
        ordered += [k for k in all_keys if k not in ordered]
        with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=ordered, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(records)
        log(f"Zapisano {len(records)} wierszy → {output_path}")


def save_organized_data(records: list, output_dir: str = DEFAULT_RSC_DIR):
    """
    Zapisuje rekordy bezpośrednio do struktury wymaganej przez kalkulator.

    To najważniejszy tryb integracyjny między scraperem a rankingiem:
    rekordy są grupowane do plików `rsc/{rok}/{turniej}-{kategoria}.txt`, dzięki
    czemu `ranking_service.py` może je od razu przeliczyć.
    """

    if not records:
        log("Brak danych do zapisania w strukturze rsc.", "WARN")
        return

    grouped: dict[tuple[str, str, str], list[dict]] = {}
    for record in records:
        year = str(record.get("rok", "")).strip()
        tournament = str(record.get("turniej", "")).strip()
        category = str(record.get("kategoria", "")).strip()
        key = (year, tournament, category)
        grouped.setdefault(key, []).append(record)

    output_root = Path(output_dir)
    files_written = 0

    for (year, tournament, category), rows in sorted(grouped.items()):
        year_dir = output_root / year
        year_dir.mkdir(parents=True, exist_ok=True)

        filename = f"{tournament_filename_part(tournament)}-{category_filename_part(category)}.txt"
        path = year_dir / filename

        lines = ["Lokata;Para;Ośrodek;Instruktor"]
        seen_lines = set()
        for row in rows:
            para_raw = str(row.get("para", "") or "")
            if "; " in para_raw and "\n" not in para_raw:
                para = ", ".join(part.strip() for part in para_raw.split(";") if part.strip())
            else:
                para = clean_pair(para_raw, separator=", ")

            lokata = str(row.get("miejsce", "") or "")
            osrodek = str(row.get("osrodek", "") or "")
            instruktor = str(row.get("instruktor", "") or "")
            line = f"{lokata};{para};{osrodek};{instruktor}"
            if line not in seen_lines:
                lines.append(line)
                seen_lines.add(line)

        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        files_written += 1

    log(f"Zapisano {files_written} plików TXT w strukturze → {output_root}")


# ──────────────────────────────────────────────────────────────
# Główna funkcja
# ──────────────────────────────────────────────────────────────

def scrape(output=DEFAULT_OUTPUT, headless=True, debug=False, only_years=None,
           organise_data=False, organised_output_dir=DEFAULT_RSC_DIR):
    """
    Wykonuje pełny przebieg scrapera od wejścia na stronę do zapisu danych.

    To główna funkcja modułu. Zarządza przeglądarką, iteruje po latach i
    turniejach, zbiera rekordy i na końcu przekazuje je do odpowiedniego
    mechanizmu zapisu.
    """

    log(
        f"Start | headless={headless} | debug={debug} | output={output} "
        f"| organise_data={organise_data}"
    )
    all_records = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=headless)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
            locale="pl-PL",
        )
        page = context.new_page()

        years = get_years(page)
        if only_years:
            years = [y for y in years if y in only_years]
            log(f"Filtrowanie lat: {years}")

        if not years:
            log("Nie znaleziono żadnych lat.", "ERROR")
            browser.close()
            return []

        for year in years:
            tournaments = get_tournaments(page, year)
            for t in tournaments:
                results = get_results(page, t, debug)
                all_records.extend(results)
                time.sleep(0.4)

        browser.close()

    if organise_data:
        save_organized_data(all_records, organised_output_dir)
    else:
        save_csv(all_records, output)
    return all_records


def build_argument_parser() -> argparse.ArgumentParser:
    """Buduje parser argumentów dla trybu uruchomienia z terminala."""

    parser = argparse.ArgumentParser(
        description="Scraper wyników par tanecznych z archiwum-tp.cioff.pl"
    )
    parser.add_argument("--output", "-o", default=DEFAULT_OUTPUT,
                        help=f"Plik wyjściowy CSV (domyślnie: {DEFAULT_OUTPUT})")
    parser.add_argument("--no-headless", dest="headless", action="store_false",
                        help="Pokaż okno przeglądarki")
    parser.add_argument("--debug", action="store_true",
                        help="Zrzuty ekranu dla każdego turnieju")
    parser.add_argument("--year", "-y", nargs="+", metavar="ROK",
                        help="Ogranicz do wybranych lat, np. --year 2022 2023")
    parser.add_argument("--organise-data", action="store_true",
                        help="Zapisz dane do folderu rsc/{rok}/turniej-kategoria.txt")
    return parser


def main() -> None:
    """Uruchamia scraper w trybie CLI z argumentami użytkownika."""

    parser = build_argument_parser()
    args = parser.parse_args()

    scrape(
        output=args.output,
        headless=args.headless,
        debug=args.debug,
        only_years=args.year,
        organise_data=args.organise_data,
    )


if __name__ == "__main__":
    main()
