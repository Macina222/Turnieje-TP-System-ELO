"""
Skrypt diagnostyczny – zrzuca strukturę HTML strony wynikowej
aby zobaczyć jak są zbudowane kategorie i wyniki.

Uruchomienie:
    python diagnoza.py

Wynik: diagnoza_dom.html + wydruk w konsoli
"""

from playwright.sync_api import sync_playwright

URL = "https://archiwum-tp.cioff.pl/2022/malbork-id-143"

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    page = browser.new_page(locale="pl-PL")
    page.goto(URL, wait_until="networkidle", timeout=30000)
    page.wait_for_timeout(2000)

    # Zrzuć cały innerHTML głównej sekcji
    html = page.evaluate("""
        () => {
            const main = document.querySelector('main') ||
                         document.querySelector('#app') ||
                         document.querySelector('#root') ||
                         document.body;
            return main.innerHTML;
        }
    """)

    with open("diagnoza_dom.html", "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Zapisano HTML ({len(html)} znaków) → diagnoza_dom.html")

    # Wydrukuj tekst strony z podziałem na linie
    text = page.evaluate("() => document.body.innerText")
    print("\n=== TEKST STRONY (pierwsze 3000 znaków) ===")
    print(text[:3000])

    # Sprawdź jakie tagi/klasy zawierają słowo "kategoria"
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
    import json
    print(json.dumps(info, ensure_ascii=False, indent=2))

    # Sprawdź strukturę tabel
    print("\n=== TABELE NA STRONIE ===")
    tables_info = page.evaluate("""
        () => {
            return Array.from(document.querySelectorAll('table')).map((t, i) => {
                const prev = [];
                let el = t.previousElementSibling;
                let steps = 0;
                while (el && steps < 5) {
                    prev.push({ tag: el.tagName, class: el.className, text: el.innerText.trim().slice(0,80) });
                    el = el.previousElementSibling;
                    steps++;
                }
                const headers = Array.from(t.querySelectorAll('thead th,thead td')).map(h => h.innerText.trim());
                const firstRow = t.querySelector('tbody tr');
                const firstCells = firstRow ? Array.from(firstRow.querySelectorAll('td,th')).map(c => c.innerText.trim()) : [];
                return { tableIndex: i, previousSiblings: prev, headers, firstRow: firstCells };
            });
        }
    """)
    print(json.dumps(tables_info, ensure_ascii=False, indent=2))

    browser.close()