"""
Skrypt diagnostyczny pomagający utrzymać scraper zgodnie ze strukturą strony.

Nie bierze udziału w liczeniu rankingu bezpośrednio, ale wspiera system wtedy,
gdy serwis źródłowy zmienia HTML. Przebieg działania:
1. otwiera przykładową stronę turnieju,
2. zapisuje HTML głównej sekcji do pliku,
3. drukuje tekst strony do szybkiej kontroli,
4. wypisuje elementy zawierające słowo "kategoria",
5. pokazuje strukturę znalezionych tabel.
"""

import json
from pathlib import Path

from playwright.sync_api import sync_playwright

URL = "https://archiwum-tp.cioff.pl/2022/malbork-id-143"
OUTPUT_HTML = Path("diagnoza_dom.html")


def main() -> None:
    """Uruchamia zrzut diagnostyczny HTML i metadanych przykładowej strony wyników."""

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(locale="pl-PL")
        page.goto(URL, wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(2000)

        html = page.evaluate("""
            () => {
                const main = document.querySelector('main') ||
                             document.querySelector('#app') ||
                             document.querySelector('#root') ||
                             document.body;
                return main.innerHTML;
            }
        """)

        OUTPUT_HTML.write_text(html, encoding="utf-8")
        print(f"Zapisano HTML ({len(html)} znaków) → {OUTPUT_HTML}")

        text = page.evaluate("() => document.body.innerText")
        print("\n=== TEKST STRONY (pierwsze 3000 znaków) ===")
        print(text[:3000])

        print("\n=== ELEMENTY Z 'kategoria' W TEKŚCIE ===")
        info = page.evaluate("""
            () => {
                const all = Array.from(document.querySelectorAll('*'));
                return all
                    .filter(el => el.children.length === 0 &&
                                  el.innerText &&
                                  el.innerText.toLowerCase().includes('kategoria'))
                    .slice(0, 20)
                    .map(el => ({
                        tag: el.tagName,
                        class: el.className,
                        id: el.id,
                        text: el.innerText.trim().slice(0, 80),
                        parentTag: el.parentElement?.tagName,
                        parentClass: el.parentElement?.className,
                    }));
            }
        """)
        print(json.dumps(info, ensure_ascii=False, indent=2))

        print("\n=== TABELE NA STRONIE ===")
        tables_info = page.evaluate("""
            () => {
                return Array.from(document.querySelectorAll('table')).map((t, i) => {
                    const prev = [];
                    let el = t.previousElementSibling;
                    let steps = 0;
                    while (el && steps < 5) {
                        prev.push({
                            tag: el.tagName,
                            class: el.className,
                            text: el.innerText.trim().slice(0, 80),
                        });
                        el = el.previousElementSibling;
                        steps++;
                    }
                    const headers = Array.from(
                        t.querySelectorAll('thead th,thead td')
                    ).map(h => h.innerText.trim());
                    const firstRow = t.querySelector('tbody tr');
                    const firstCells = firstRow
                        ? Array.from(firstRow.querySelectorAll('td,th'))
                            .map(c => c.innerText.trim())
                        : [];
                    return {
                        tableIndex: i,
                        previousSiblings: prev,
                        headers,
                        firstRow: firstCells,
                    };
                });
            }
        """)
        print(json.dumps(tables_info, ensure_ascii=False, indent=2))

        browser.close()


if __name__ == "__main__":
    main()
