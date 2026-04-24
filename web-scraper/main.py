"""
Scraper wyników par tanecznych z https://archiwum-tp.cioff.pl/

Struktura strony:
  /              → kafelki z latami
  /2022/         → kafelki z turniejami
  /2022/malbork-id-143  → wyniki par w kategoriach

Struktura HTML strony wynikowej (zweryfikowana):
  <div class="mb-12">
      <h3 class="text-2xl ...">Kategoria I</h3>
      <table>
          <thead><tr><th>Lokata</th><th>Para</th><th>Ośrodek</th><th>Instruktor</th></tr></thead>
          <tbody>
              <tr><td>1</td><td>Kowalski Jan\nNowak Anna</td><td>ZTP X</td><td>NOWAK JAN</td></tr>
          </tbody>
      </table>
  </div>

Wynik: wyniki_par.csv z kolumnami:
  rok, turniej, turniej_id, kategoria, miejsce, para, osrodek, instruktor

Użycie:
  pip install playwright pandas
  playwright install chromium
  python scraper_cioff.py [--output PLIK] [--no-headless] [--debug] [--year 2022 2023]
"""

import argparse
import csv
import re
import sys
import time
from datetime import datetime

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
TIMEOUT = 30_000


def log(msg: str, level: str = "INFO"):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] [{level}] {msg}", flush=True)


# ──────────────────────────────────────────────────────────────
# Czyszczenie danych
# ──────────────────────────────────────────────────────────────

def clean_tournament_name(raw: str) -> str:
    """
    Z kafelka turnieju bierze tylko pierwszą niepustą linię.
    Wejście:  "KATOWICE 2025\n\n2025-11-21\nKatowice\n\nPrzejdź do wyników turnieju"
    Wyjście:  "KATOWICE 2025"
    """
    for line in raw.splitlines():
        line = line.strip()
        if line:
            return line
    return raw.strip()


def clean_pair(raw: str) -> str:
    """
    Dwa nazwiska rozdzielone \\n zamienia na "Nazwisko1 Imię1; Nazwisko2 Imię2".
    Wejście:  "Klimkiewicz Bartosz\nIwańczak Zofia"
    Wyjście:  "Klimkiewicz Bartosz; Iwańczak Zofia"
    """
    parts = [p.strip() for p in raw.splitlines() if p.strip()]
    return "; ".join(parts)


# ──────────────────────────────────────────────────────────────
# Krok 1: lata ze strony głównej
# ──────────────────────────────────────────────────────────────

def get_years(page) -> list:
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
    #       <table>...</table>
    #   </div>
    #
    # Dla każdej tabeli szukamy h3 w tym samym kontenerze (closest div).
    # Jeśli h3 nie ma w bezpośrednim rodzicu, szukamy go w drzewie wyżej.

    raw_data = page.evaluate("""
        () => {
            const blocks = [];
            document.querySelectorAll('table').forEach(table => {

                // Znajdź nagłówek kategorii: szukaj h3 w tym samym bloku (div.mb-12)
                let category = '';
                const container = table.closest('div');
                if (container) {
                    const h3 = container.querySelector('h3');
                    if (h3) category = h3.innerText.trim();
                }
                // Fallback: poprzednie rodzeństwo tabeli
                if (!category) {
                    let prev = table.previousElementSibling;
                    while (prev) {
                        const t = prev.innerText.trim();
                        if (t.length > 0 && t.length < 100) { category = t; break; }
                        prev = prev.previousElementSibling;
                    }
                }
                // Fallback: caption wewnątrz tabeli
                if (!category) {
                    const cap = table.querySelector('caption');
                    if (cap) category = cap.innerText.trim();
                }

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
    """Mapuje nagłówki kolumn z polskiego na ustandaryzowane klucze."""
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


# ──────────────────────────────────────────────────────────────
# Główna funkcja
# ──────────────────────────────────────────────────────────────

def scrape(output=DEFAULT_OUTPUT, headless=True, debug=False, only_years=None):
    log(f"Start | headless={headless} | debug={debug} | output={output}")
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

    save_csv(all_records, output)
    return all_records


# ──────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
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
    args = parser.parse_args()

    scrape(
        output=args.output,
        headless=args.headless,
        debug=args.debug,
        only_years=args.year,
    )