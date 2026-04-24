"""
Scraper wyników par tanecznych z https://archiwum-tp.cioff.pl/

Struktura strony:
  /              → kafelki z latami (np. 2022, 2021, ...)
  /2022/         → kafelki z turniejami danego roku
  /2022/katowice-id-144  → wyniki par w kategoriach

Wynik: wyniki_par.csv z kolumnami:
  rok, turniej, turniej_id, turniej_url, kategoria, miejsce, para, zespol

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
TIMEOUT = 30_000  # ms


def log(msg: str, level: str = "INFO"):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] [{level}] {msg}", flush=True)


# ──────────────────────────────────────────────────────────────
# Krok 1: lata ze strony głównej
# ──────────────────────────────────────────────────────────────

def get_years(page) -> list:
    log("Pobieram listę lat...")
    page.goto(BASE_URL, wait_until="networkidle", timeout=TIMEOUT)
    page.wait_for_timeout(2000)

    years = []
    # Pobierz wszystkie href-y przez JavaScript – unikamy stale element handles
    hrefs = page.evaluate("""
        () => Array.from(document.querySelectorAll('a[href]'))
                   .map(a => a.getAttribute('href'))
    """)
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
    log(f"  Pobieram turnieje dla roku {year}: {url}")
    page.goto(url, wait_until="networkidle", timeout=TIMEOUT)
    page.wait_for_timeout(1500)

    # Pobierz href + text przez JS – brak ryzyka stale handle po nawigacji
    link_data = page.evaluate("""
        () => Array.from(document.querySelectorAll('a[href]'))
                   .map(a => ({ href: a.getAttribute('href'), text: a.innerText.trim() }))
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
        full_url = f"{BASE_URL}/{year}/{slug}"
        # Nazwa: preferuj tekst linku, fallback ze sluga
        name = text if text else re.sub(r"-id-\d+$", "", slug).replace("-", " ").strip()
        tournaments.append({
            "name": name,
            "id": tid,
            "url": full_url,
            "year": year,
        })

    log(f"    Znaleziono {len(tournaments)} turniejów: {[t['name'] for t in tournaments]}")
    return tournaments


# ──────────────────────────────────────────────────────────────
# Krok 3: wyniki z jednego turnieju
# ──────────────────────────────────────────────────────────────

def get_results(page, tournament: dict, debug: bool) -> list:
    url = tournament["url"]
    log(f"    Pobieram wyniki: {url}")

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

    records = []
    base = {
        "rok": tournament["year"],
        "turniej": tournament["name"],
        "turniej_id": tournament["id"],
        "turniej_url": url,
    }

    # ── Strategia A: tabele HTML ──
    # Pobieramy całą strukturę tabel przez JS – jeden call, zero stale handles
    tables_data = page.evaluate("""
        () => {
            const results = [];
            const tables = document.querySelectorAll('table');
            tables.forEach(table => {
                // Nagłówek kategorii – szukaj przed tabelą
                let category = '';
                let prev = table.previousElementSibling;
                while (prev) {
                    const tag = prev.tagName.toLowerCase();
                    if (['h1','h2','h3','h4','h5','h6','p'].includes(tag)) {
                        const t = prev.innerText.trim();
                        if (t.length > 0 && t.length < 120) { category = t; break; }
                    }
                    prev = prev.previousElementSibling;
                }
                const caption = table.querySelector('caption');
                if (!category && caption) category = caption.innerText.trim();

                // Nagłówki
                const headers = Array.from(
                    table.querySelectorAll('thead th, thead td')
                ).map(el => el.innerText.trim().toLowerCase());

                // Wiersze
                let rows = Array.from(table.querySelectorAll('tbody tr'));
                if (!rows.length) {
                    rows = Array.from(table.querySelectorAll('tr')).slice(headers.length ? 1 : 0);
                }
                rows.forEach(tr => {
                    const cells = Array.from(tr.querySelectorAll('td,th')).map(td => td.innerText.trim());
                    if (cells.length && cells.some(c => c !== '')) {
                        results.push({ category, headers, cells });
                    }
                });
            });
            return results;
        }
    """)

    for row in tables_data:
        category = row.get("category") or "nieznana"
        headers = row.get("headers") or []
        cells = row.get("cells") or []
        if headers and len(cells) >= len(headers):
            mapped = {_normalize_col(h): cells[i] for i, h in enumerate(headers) if h}
        else:
            mapped = {f"kol_{i}": v for i, v in enumerate(cells)}
        records.append({**base, "kategoria": category, **mapped})

    # ── Strategia B: divs/listy z wynikami ──
    if not records:
        records = _parse_result_divs(page, base)

    # ── Strategia C: tekst linia po linii (fallback) ──
    if not records:
        records = _parse_text_fallback(page, base)

    if records:
        log(f"      Pobrano {len(records)} wyników")
    else:
        log(f"      Brak wyników – uruchom z --debug aby zobaczyć zrzut ekranu", "WARN")

    return records


def _normalize_col(name: str) -> str:
    n = name.lower().strip()
    if any(x in n for x in ["miejsc", "place", "poz", "rank", "lokata"]):
        return "miejsce"
    if re.match(r"^(lp\.?|nr\.?|#)$", n):
        return "miejsce"
    if any(x in n for x in ["para", "pair", "nazwa", "name", "tancerz", "zawodnik"]):
        return "para"
    if any(x in n for x in ["zesp", "group", "club", "klub", "org", "ośrodek", "osrodek"]):
        return "zespol"
    if any(x in n for x in ["pkt", "point", "wynik", "score", "suma"]):
        return "punkty"
    return name


def _parse_result_divs(page, base: dict) -> list:
    """Szuka elementów z klasami sugerującymi listę rankingową."""
    records = []
    selectors = [
        "[class*='result'] [class*='row']",
        "[class*='result'] [class*='item']",
        "[class*='ranking'] li",
        "[class*='ranking'] [class*='row']",
        "li[class*='place']",
        "li[class*='result']",
    ]
    for sel in selectors:
        items = page.evaluate(f"""
            () => Array.from(document.querySelectorAll('{sel}'))
                       .map(el => el.innerText.trim())
                       .filter(t => t.length > 0)
        """)
        if not items:
            continue
        for text in items:
            rec = _extract_from_text(text)
            if rec:
                records.append({**base, "kategoria": "nieznana", **rec})
        if records:
            break
    return records


def _parse_text_fallback(page, base: dict) -> list:
    """Parsuje całą treść tekstową strony linia po linii."""
    records = []
    try:
        text = page.evaluate("""
            () => {
                const main = document.querySelector('main') ||
                             document.querySelector('article') ||
                             document.querySelector('#content') ||
                             document.body;
                return main ? main.innerText : '';
            }
        """)
    except Exception:
        return []

    current_category = "nieznana"
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        rec = _extract_from_text(line)
        if rec:
            records.append({**base, "kategoria": current_category, **rec})
        elif _looks_like_category(line):
            current_category = line

    return records


def _extract_from_text(text: str):
    """Wydobywa {miejsce, para, zespol} z linii tekstu."""
    text = text.strip()
    if not text:
        return None
    m = re.match(r"^(\d{1,3})[\s.\-:)]+(.+)$", text)
    if not m:
        return None
    miejsce = m.group(1)
    reszta = m.group(2).strip()
    parts = re.split(r"\s{2,}|\t", reszta)
    para = parts[0].strip() if parts else reszta
    zespol = parts[-1].strip() if len(parts) > 1 else ""
    return {"miejsce": miejsce, "para": para, "zespol": zespol}


def _looks_like_category(text: str) -> bool:
    if len(text) < 3 or len(text) > 80 or text[0].isdigit():
        return False
    keywords = ["solo", "para", "mała", "junior", "senior", "młodszy",
                "starszy", "dziecięcy", "open", "klasa", "kategoria"]
    lower = text.lower()
    return any(kw in lower for kw in keywords) or text.isupper()


# ──────────────────────────────────────────────────────────────
# Zapis
# ──────────────────────────────────────────────────────────────

def save_csv(records: list, output_path: str):
    if not records:
        log("Brak danych do zapisania.", "WARN")
        return

    preferred = ["rok", "turniej", "turniej_id", "kategoria", "miejsce", "para", "zespol", "punkty", "turniej_url"]

    if HAS_PANDAS:
        df = pd.DataFrame(records)
        cols = [c for c in preferred if c in df.columns]
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
        all_keys = []
        for r in records:
            for k in r:
                if k not in all_keys:
                    all_keys.append(k)
        ordered = [k for k in preferred if k in all_keys]
        ordered += [k for k in all_keys if k not in ordered]
        with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=ordered, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(records)
        log(f"Zapisano {len(records)} wierszy → {output_path}")


# ──────────────────────────────────────────────────────────────
# Główna funkcja + CLI
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