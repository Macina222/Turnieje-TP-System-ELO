# Turnieje TP — System rankingu ELO

Kalkulator rankingu ELO dla par tanecznych na podstawie wyników turniejów tańców polskich. Projekt pracuje na plikach zapisanych w katalogu `rsc/`, potrafi liczyć ranking dla wybranej rodziny kategorii i wybranych lat, a także pomaga zorganizować dane pobrane z archiwum wyników.

## Aktualny stan projektu

- Głównym punktem wejścia jest `App.py`.
- `App.py` uruchamia GUI w `tkinter`, jeśli moduł jest dostępny.
- Jeśli `tkinter` nie jest zainstalowany, `App.py` automatycznie przechodzi do trybu terminalowego.
- Cały backend rankingu został scalony do jednego modułu `ranking_service.py`.
- Aplikacja pozwala wybrać:
  - kategorię bazową rankingu `I`-`VIII`,
  - jeden lub wiele lat,
  - zapis wyniku do wskazanego pliku.
- Dla kategorii bazowej zbierane są wszystkie pasujące podkategorie z plików `rsc/`.
- `main.py` nadal istnieje jako prosty, starszy skrypt liczący jeden globalny ranking ze wszystkich plików `rsc/`, ale korzysta już z tego samego backendu co `App.py`.

## Struktura repozytorium

- `App.py` — aplikacja użytkowa: GUI, tryb terminalowy interaktywny i tryb CLI z argumentami.
- `ranking_service.py` — scalony backend rankingu: model pary, wczytywanie `config.txt`, przetwarzanie pojedynczych turniejów, obliczanie zmian ELO, budowa rankingu, formatowanie raportu i zapis wyniku.
- `main.py` — legacy script przetwarzający całe `rsc/` i zapisujący wynik do `ranking.txt`.
- `rsc/` — dane wejściowe, zorganizowane w podkatalogach roczników.
- `web-scraper/` — narzędzia do pobierania i organizowania danych z archiwum wyników.

## Format danych wejściowych

Każdy plik w `rsc/` jest traktowany jako jeden zestaw wyników dla konkretnego turnieju i kategorii. Oczekiwany format:

```csv
Lokata;Para;Ośrodek;Instruktor
1;Nazwisko1 Imię1, Nazwisko2 Imię2;Nazwa ośrodka;Imię Nazwisko
2;Nazwisko3 Imię3, Nazwisko4 Imię4;Nazwa ośrodka;Imię Nazwisko
```

W obliczeniach wykorzystywane są tylko pola `Lokata` i `Para`.

Projekt zakłada układ plików:

```text
rsc/{rok}/{turniej}-{kategoria}.txt
```

Przykład:

```text
rsc/2025/krakow-vb.txt
rsc/2025/olsztyn-vs.txt
rsc/2024/wilanow-iiic.txt
```

## Agregacja kategorii

Aplikacja operuje na kategoriach bazowych `I`, `II`, `III`, `IV`, `V`, `VI`, `VII`, `VIII`.

Każda kategoria bazowa zbiera wszystkie pliki, których końcówka kategorii należy do tej samej rodziny. Przykłady:

- `V` obejmuje między innymi `V`, `VA`, `VB`, `VS`, `VOPEN`, `VAB`.
- `III` obejmuje między innymi `IIIA`, `IIIB`, `IIIC`, `IIIOPEN`.
- `IV` obejmuje między innymi `IVA`, `IVB`, `IVOPEN`.

Mapowanie działa po prefiksie kategorii z priorytetem dłuższych numerów rzymskich, więc `VI` nie wpada do `V`, a `VIII` nie wpada do `VII`.

## Jak liczony jest ranking

1. Para jest identyfikowana jako krotka `(tancerz1, tancerz2)`.
2. Nowa para startuje z ELO `1000.0`.
3. W obrębie jednego pliku każda para jest porównywana z każdą inną parą.
4. Niższa lokata oznacza zwycięstwo, wyższa porażkę, taka sama lokata remis.
5. Oczekiwany wynik liczony jest klasycznym wzorem ELO:

```text
expected = 1 / (1 + 10 ^ ((ranking_b - ranking_a) / D))
```

6. Aktualizacja odbywa się według:

```text
nowe_elo = stare_elo + suma(actual - expected) * efektywne_k
efektywne_k = K / (n - 1)
```

7. Wskaźniki `K` i `D` są wczytywane z pliku `config.txt` w katalogu projektu.
8. Domyślna zawartość `config.txt` to `K = 32` oraz `D = 250`.
9. Ranking jest budowany sekwencyjnie, rok po roku i plik po pliku w kolejności sortowanej alfabetycznie.
10. `main.py` i `App.py` korzystają z tej samej logiki backendowej, więc liczenie ELO i parsowanie danych pozostaje spójne między trybami uruchomienia.

### Konfiguracja

Plik `config.txt` w katalogu głównym projektu:

```text
K=32
D=250
```

## Uruchamianie

### 1. Zalecany sposób: `App.py`

Jeżeli `tkinter` jest dostępny:

```bash
python3 App.py
```

Uruchomi się okno z wyborem lat i kategorii.

Jeżeli `tkinter` nie jest dostępny:

```bash
python3 App.py
```

Uruchomi się tryb terminalowy z pytaniami o lata, kategorię i zapis wyniku.

### 2. Tryb CLI z argumentami

```bash
python3 App.py --category V --years 2025
python3 App.py --category III --years 2022 2023 2024
python3 App.py --category IV --years 2021-2025 --output ranking_iv_2021_2025.txt
python3 App.py --cli
```

Zasady:

- `--category` przyjmuje kategorię bazową, np. `V` albo `III`.
- `--years` przyjmuje pojedyncze lata i zakresy, np. `2024 2025` albo `2021-2025`.
- jeśli w trybie argumentowym nie podasz `--years`, zostaną użyte wszystkie dostępne lata z `rsc/`.
- `--output` zapisuje raport do pliku.
- `--cli` wymusza tryb terminalowy nawet wtedy, gdy `tkinter` jest dostępny.

### 3. Legacy script

```bash
python3 main.py
```

To polecenie:

- przetwarza całe `rsc/`,
- nie filtruje po latach ani kategoriach,
- zapisuje wynik do `ranking.txt`.

## Raport wynikowy

Raport generowany przez `App.py` zawiera:

- kategorię bazową,
- listę wybranych lat,
- liczbę przetworzonych plików,
- listę uwzględnionych podkategorii,
- tabelę rankingu,
- listę pominiętych plików, jeśli podczas wczytywania pojawił się błąd.

Domyślna nazwa pliku wyjściowego ma postać zbliżoną do:

```text
ranking_v_2025.txt
ranking_iii_2022_2023_2024.txt
```

## `tkinter`

GUI wymaga modułu `tkinter`.

Jeśli go nie masz, możesz:

- korzystać z trybu terminalowego w `App.py`, albo
- doinstalować `tkinter` dla systemowego Pythona.

Przykładowo:

- Fedora / RHEL:

```bash
sudo dnf install python3-tkinter
```

- Debian / Ubuntu:

```bash
sudo apt install python3-tk
```

## Web scraper

W katalogu `web-scraper/` znajduje się scraper dla `https://archiwum-tp.cioff.pl`.

Instalacja zależności:

```bash
pip install playwright pandas
playwright install chromium
```

Przykładowe użycie:

```bash
python3 web-scraper/main.py --year 2025 --output web-scraper/wyniki_par.csv
python3 web-scraper/main.py --organise-data --year 2025
```

Tryb `--organise-data` zapisuje dane bezpośrednio do struktury `rsc/{rok}/{turniej}-{kategoria}.txt`, czyli do formatu używanego przez kalkulator rankingu.

## Ograniczenia obecnej wersji

- identyfikacja par zależy od dokładnego zapisu nazwisk i imion,
- ta sama para ma jedno ELO w ramach aktualnie liczonego zestawu plików,
- system nie waży turniejów według rangi,
- liczą się wyłącznie lokaty, bez punktów sędziowskich,
- kolejność przetwarzania plików wpływa na końcowy ranking,
- błędne lub niespójne pliki mogą zostać pominięte.

## Autorzy projektu

- Maciej Zych — kod, logika kalkulatora
- Krzysztof Mrozik — kod, logika web-scrapera
- Mateusz Zych — PR, nagłaśnianie projektu, rozmowy z osobami decyzyjnymi
