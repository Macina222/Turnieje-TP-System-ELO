# Turnieje TP - System rankingu ELO

Kalkulator rankingu ELO dla par tancow polskich. Aktualnym domyslnym zrodlem
danych jest oficjalny arkusz `data_new.xlsx`, a glownym punktem wejscia jest
`App.py`.

## Aktualny Stan

- `App.py` uruchamia GUI w `tkinter`, a bez `tkinter` przechodzi do trybu CLI.
- Domyslny backend to `new_ranking_service.py`, ktory czyta `data_new.xlsx`.
- Aplikacja obsluguje filtry:
  - kategoria bazowa `I`-`VIII`,
  - jeden lub wiele sezonow,
  - jedna lub wiele klas, np. `B`, `A`, `S`, `OPEN`,
  - opcjonalny wybor innego pliku XLSX w GUI albo przez `--input-excel`.
- `new_progress_export.py` eksportuje historie zmian punktow do CSV.
- `new_pair_progress_plot.py` rysuje historie ELO par bezposrednio z XLSX.
- Stary przeplyw `rsc/` + `ranking_service.py` jest zachowany tylko jako legacy.

## Struktura

- `App.py` - glowna aplikacja GUI/CLI dla `data_new.xlsx`.
- `new_ranking_service.py` - aktualny backend: ladowanie XLSX, discovery filtrow,
  budowa rankingu, eksport historii i formatowanie raportow.
- `new_progress_export.py` - eksport CSV historii punktow turniej po turnieju.
- `new_pair_progress_plot.py` - wykresy ELO par z danych XLSX.
- `data_new.xlsx` - domyslny plik danych.
- `config.txt` - parametry algorytmu ELO: `K`, `D` i domyslne ELO klas.
- `legacy/` - poprzednia wersja oparta o pliki `rsc/`.
- `ranking_service.py` i `rsc/` - kompatybilnosc ze starym przeplywem; nie sa juz
  domyslna sciezka rozwoju.
- `SQL/` - eksperymentalne narzedzia SQLite/importu oficjalnych danych.
- `tests/` - testy regresyjne aktualnego backendu.

## Format `data_new.xlsx`

Arkusz jest czytany przez `pandas.read_excel(..., header=3)`. Wymagane kolumny:

```text
season
turnament code
turnament name
cat code
pair id
pair
rank
```

W pliku najnowsze turnieje moga byc na gorze. Backend odwraca kolejnosc wierszy,
aby liczyc ranking chronologicznie od najstarszych wynikow.

## Uruchamianie

GUI:

```bash
.venv/bin/python App.py
```

CLI dla jednej kategorii:

```bash
.venv/bin/python App.py --category V --years 2025 --classes B
.venv/bin/python App.py --category III --years 2022-2025 --classes A S --output ranking_iii.txt
```

Raporty dla wszystkich kategorii:

```bash
.venv/bin/python App.py --all-categories --years 2025 --output-dir txt
```

Inny plik XLSX:

```bash
.venv/bin/python App.py --input-excel path/to/dane.xlsx --category V --years 2025
```

Interaktywny tryb terminalowy:

```bash
.venv/bin/python App.py --cli
```

## Eksport Historii

```bash
.venv/bin/python new_progress_export.py --category V --years 2025
.venv/bin/python new_progress_export.py --category V --years 2024-2025 --classes B A --output progress_v.csv
```

CSV zawiera m.in. sezon, kolejnosc turnieju, kod i nazwe turnieju, kategorie,
klase, lokate, `pair_id`, nazwe pary oraz punkty przed i po turnieju.

## Wykresy

```bash
.venv/bin/python new_pair_progress_plot.py --category V --years 2025 --list-pairs --search "Kowalski"
.venv/bin/python new_pair_progress_plot.py --category V --years 2025 --pair-id 12345 --output wykres.png
```

## Algorytm

1. Para jest identyfikowana przez `pair id`.
2. Nowa para startuje z domyslnego ELO dla klasy z `config.txt`.
3. W obrebie jednego turnieju kazda para jest porownywana z kazda inna para.
4. Nizsza lokata oznacza zwyciestwo, wyzsza porazke, taka sama lokata remis.
5. Zmiana punktow jest liczona klasycznym wzorem ELO z parametrami `K` i `D`.

Domyslne `config.txt`:

```text
K=50
D=250
defaulteloC=1100
defaulteloB=1100
defaulteloA=1200
defaulteloS=1300
defaulteloOPEN=1000
```

## Testy

Testy aktualnego backendu uzywaja standardowego `unittest`:

```bash
.venv/bin/python -m unittest tests.test_new_ranking_service
```

Szybki smoke test aplikacji CLI:

```bash
.venv/bin/python App.py --category V --years 2025 --classes B --output /tmp/ranking_smoke.txt
```

## Legacy

Poprzedni backend oparty o katalog `rsc/` zostaje w repozytorium jako punkt
odniesienia i zgodnosc wsteczna. Nowe zmiany powinny trafiac do sciezki
`data_new.xlsx`/`new_ranking_service.py`, chyba ze zadanie dotyczy wprost legacy.
