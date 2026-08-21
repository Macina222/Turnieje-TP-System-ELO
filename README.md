# Turnieje TP - System rankingu ELO

Kalkulator rankingu ELO dla par tańca polskich. Głównym punktem wejścia jest
`App.py` — centralne centrum sterowania aplikacją, obsługujące zarówno GUI
(jako `tkinter` Notebook z 5 zakładkami), jak i rozszerzone CLI.

## Aktualny Stan

- `App.py` uruchamia GUI w `tkinter` (5 zakładki Notebook), a bez `tkinter` lub z flagą `--cli` przechodzi do trybu terminalowego.
- Domyślny backend to `new_ranking_service.py`, który czyta `data_new.xlsx`.
- Pełna obsługa backendu **SQLite** (`SQL/sqlite_ranking_service.py`) z importem danych i migracjami schematu.
- Aplikacja obsługuje filtry:
  - kategoria bazowa `I`-`VIII`,
  - jeden lub wiele sezonów,
  - jedna lub wiele klas, np. `B`, `A`, `S`, `OPEN`,
  - opcjonalny wybór innego pliku XLSX w GUI albo przez `--input-excel`.
- `new_progress_export.py` / `SQL/progress_export_sqlite.py` eksportują historie zmian punktów do CSV.
- `new_pair_progress_plot.py` rysuje historie ELO par bezpośrednio z XLSX lub SQLite.
- Stary przepływ `rsc/` + `ranking_service.py` jest zachowany tylko jako legacy w `legacy/`.

## Struktura

```
Turnieje-TP-System-ELO/
├── App.py                          # Główna aplikacja GUI/CLI — centrum sterowania
├── app_gui.py                      # Moduł GUI z 5 zakładkami Notebook
├── app_cli.py                      # Handlery CLI dla rozszerzonych komend App.py
├── ranking_config.py               # Ujednolicona konfiguracja (EloConfig dataclass)
├── new_ranking_service.py          # Backend XLSX: ranking, discovery, eksport, wykresy
├── new_progress_export.py          # Eksport CSV historii (XLSX backend)
├── new_pair_progress_plot.py       # Wykresy ELO par (XLSX + SQLite backend)
├── data_new.xlsx                   # Domyślny plik danych (format legacy)
├── config.txt                      # Parametry algorytmu ELO: K, D, defaultELO
├── legacy/                         # Poprzednia wersja (rsc/, ranking_service.py)
├── SQL/                            # Narzędzia SQLite
│   ├── migrations.py               # Framework migracji (v1, v2)
│   ├── import_official_ttp_to_sqlite.py  # Import XLSX → SQLite
│   ├── sqlite_ranking_service.py   # Backend SQLite (ranking, discovery, eksport)
│   ├── progress_export_sqlite.py   # Eksport CSV historii (SQLite backend)
│   └── App_sqlite.py               # Legacy CLI SQLite
└── tests/                          # Testy regresyjne
```

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

W pliku najnowsze turnieje mogą być na górze. Backend odwraca kolejność wierszy,
aby liczyć ranking chronologicznie od najstarszych wyników.

## Uruchamianie

### GUI (5 zakładek Notebook)

```bash
.venv/bin/python App.py
```

Zakładki:
1. **Ranking** — obliczanie rankingu ELO (backend XLSX/SQLite, filtry, zapis)
2. **Import SQL** — import oficjalnego XLSX do bazy SQLite z podglądem postępu
3. **Export CSV** — eksport historii zmian punktów do CSV (oba backendy, podgląd)
4. **Charts** — wykresy ELO par z listą par, filtrem, eksportem PNG
5. **Migrations** — status i uruchamianie migracji bazy SQLite

### CLI — Ranking (domyślny backend XLSX)

```bash
# Jedna kategoria
.venv/bin/python App.py --category V --years 2025 --classes B
.venv/bin/python App.py --category III --years 2022-2025 --classes A S --output ranking_iii.txt

# Wszystkie kategorie dostępne w latach
.venv/bin/python App.py --all-categories --years 2025 --output-dir txt

# Inny plik XLSX
.venv/bin/python App.py --input-excel path/to/dane.xlsx --category V --years 2025
```

### CLI — Ranking (backend SQLite)

```bash
.venv/bin/python App.py --backend sqlite --db ttp_official.sqlite --category V --years 2025 --classes B
.venv/bin/python App.py --backend sqlite --db ttp_official.sqlite --category III --years 2022-2025 --classes A S
```

### CLI — Import SQL (nowy)

```bash
# Import XLSX → SQLite
.venv/bin/python App.py --import-sql "_Oficjalne dane.xlsx" ttp_official.sqlite

# Import z nadpisaniem bazy
.venv/bin/python App.py --import-sql "_Oficjalne dane.xlsx" ttp_official.sqlite --replace-db

# Import konkretnego arkusza
.venv/bin/python App.py --import-sql "_Oficjalne dane.xlsx" ttp_official.sqlite --import-sheet "Arkusz1"
```

### CLI — Migracje (nowy)

```bash
# Status migracji
.venv/bin/python App.py --migrate ttp_official.sqlite --migrate-status

# Uruchom wszystkie oczekujące migracje
.venv/bin/python App.py --migrate ttp_official.sqlite

# Uruchom do konkretnej wersji
.venv/bin/python App.py --migrate ttp_official.sqlite --migrate-target 2
```

### CLI — Eksport CSV historii (nowy, ujednolicony dla obu backendów)

```bash
# Backend XLSX (domyślny)
.venv/bin/python App.py --export-progress --category V --years 2025 --classes B
.venv/bin/python App.py --export-progress --category V --years 2024-2025 --classes B A --export-output progress_v.csv --delimiter ","

# Backend SQLite
.venv/bin/python App.py --backend sqlite --db ttp_official.sqlite --export-progress --category V --years 2025 --classes B
```

### CLI — Wykresy (nowy, ujednolicony dla obu backendów)

```bash
# Lista par z filtrem (XLSX)
.venv/bin/python App.py --category V --years 2025 --list-pairs --search "Kowalski"

# Lista par (SQLite)
.venv/bin/python App.py --backend sqlite --db ttp_official.sqlite --category V --years 2025 --list-pairs

# Wykres dla pary (po ID) — zapis do PNG
.venv/bin/python App.py --backend sqlite --db ttp_official.sqlite --plot --category V --years 2025 --pair-id 12345 --plot-output img/elo_12345.png

# Wykres dla pary (po nazwie) — pokaż okno
.venv/bin/python App.py --backend xlsx --category V --years 2025 --plot --pair "JAN, ANNA" --show

# Wykres dla pary (po obu tancerzach)
.venv/bin/python App.py --backend sqlite --db ttp_official.sqlite --plot --category V --years 2025 --tancerz1 "JAN" --tancerz2 "ANNA" --show
```

### CLI — Eksploracja danych (SQLite)

```bash
# Dostępne lata
.venv/bin/python App.py --backend sqlite --db ttp_official.sqlite --list-years

# Dostępne kategorie dla lat
.venv/bin/python App.py --backend sqlite --db ttp_official.sqlite --years 2024 2025 --list-categories

# Dostępne klasy dla kategorii
.venv/bin/python App.py --backend sqlite --db ttp_official.sqlite --category V --years 2025 --list-classes
```

### Tryb interaktywny terminalowy (tylko XLSX, ranking)

```bash
.venv/bin/python App.py --cli
```

### Wybór backendu

| Argument | Wartości | Opis |
|----------|----------|------|
| `--backend` | `xlsx` (domyślnie), `sqlite` | Źródło danych: plik XLSX lub baza SQLite |
| `--input-excel` | ścieżka | Plik XLSX (dla backend xlsx) |
| `--db` | ścieżka | Plik bazy SQLite (wymagane dla `--backend sqlite`) |
| `--config` | ścieżka | Plik konfiguracyjny (domyślnie `config.txt`) |

W GUI dostępny jest rozwijany wybór backendu ("xlsx" / "sqlite") oraz odpowiednie pola wyboru pliku XLSX lub bazy SQLite.

## Eksport Historii

```bash
# XLSX backend
.venv/bin/python App.py --export-progress --category V --years 2025
.venv/bin/python App.py --export-progress --category V --years 2024-2025 --classes B A --output progress_v.csv

# SQLite backend (nowy ujednolicony interfejs)
.venv/bin/python App.py --backend sqlite --db ttp_official.sqlite --export-progress --category V --years 2025
```

CSV zawiera m.in. sezon, kolejność turnieju, kod i nazwę turnieju, kategorie,
klasę, lokatę, `pair_id`, nazwę pary oraz punkty przed i po turnieju.
Separator domyślny: `;` (konfigurowalny `--delimiter`).

## Wykresy

```bash
# Lista par
.venv/bin/python App.py --category V --years 2025 --list-pairs --search "Kowalski"
.venv/bin/python App.py --backend sqlite --db ttp_official.sqlite --category V --years 2025 --list-pairs

# Wykres do pliku / okno
.venv/bin/python App.py --plot --category V --years 2025 --pair-id 12345 --plot-output wykres.png
.venv/bin/python App.py --plot --category V --years 2025 --pair "JAN, ANNA" --show
```

## Algorytm

1. Para jest identyfikowana przez `pair id`.
2. Nowa para startuje z domyślnego ELO dla klasy z `config.txt`.
3. W obrębie jednego turnieju każda para jest porównywana z każdą inną parą.
4. Niższa lokata oznacza zwycięstwo, wyższą porażkę, taka sama lokata remis.
5. Zmiana punktów jest liczona klasycznym wzorem ELO z parametrami `K` i `D`.

Domyślne `config.txt`:

```text
K=50
D=250
defaulteloC=800
defaulteloB=900
defaulteloA=1000
defaulteloS=1100
defaulteloOPEN=950
```

## Testy

Testy aktualnego backendu używają standardowego `unittest`:

```bash
.venv/bin/python -m unittest tests.test_new_ranking_service
```

Szybki smoke test aplikacji CLI:

```bash
.venv/bin/python App.py --category V --years 2025 --classes B --output /tmp/ranking_smoke.txt
```

Testy CLI nowych komend:

```bash
# Import
.venv/bin/python App.py --import-sql "_Oficjalne dane.xlsx" /tmp/test_import.sqlite --replace-db

# Migracje
.venv/bin/python App.py --migrate /tmp/test_import.sqlite --migrate-status

# Eksport CSV
.venv/bin/python App.py --backend sqlite --db /tmp/test_import.sqlite --export-progress --category V --years 2025 --classes B

# Wykresy - lista par
.venv/bin/python App.py --backend sqlite --db /tmp/test_import.sqlite --plot --category V --years 2025 --list-pairs
```

## Legacy

Poprzedni backend oparty o katalog `rsc/` zostaje w repozytorium jako punkt
odniesienia i zgodność wsteczna w `legacy/`. Nowe zmiany powinny trafić do ścieżki
`data_new.xlsx`/`new_ranking_service.py` (XLSX) lub `SQL/` (SQLite), chyba że zadanie dotyczy wprost legacy.

## SQLite Backend i Migracje

Moduł `SQL/` zawiera produkcyjny backend oparty na SQLite:

- `migrations.py` — framework migracji z tabelą `schema_version`, migracje v1 (schemat początkowy) i v2 (kolumna `event_date` w `tournaments`).
- `import_official_ttp_to_sqlite.py` — import oficjalnego XLSX do SQLite (idempotentny, z ostrzeżeniami).
- `sqlite_ranking_service.py` — backend rankingu ELO (ten sam algorytm co XLSX) z obsługą `event_date` do sortowania chronologicznego.
- `App_sqlite.py` — legacy CLI do rankingu z SQLite.
- `progress_export_sqlite.py` — eksport postępu ELO do CSV.

Uruchamianie (nowy ujednolicony interfejs przez App.py):

```bash
# Import oficjalnych danych
.venv/bin/python App.py --import-sql "_Oficjalne dane.xlsx" ttp_official.sqlite

# Ranking z SQLite
.venv/bin/python App.py --backend sqlite --db ttp_official.sqlite --category V --years 2025 --classes B

# Eksport postępu do CSV
.venv/bin/python App.py --backend sqlite --db ttp_official.sqlite --export-progress --category V --years 2025 --classes B

# Migracje
.venv/bin/python App.py --migrate ttp_official.sqlite --migrate-status
.venv/bin/python App.py --migrate ttp_official.sqlite

# Wykresy
.venv/bin/python App.py --backend sqlite --db ttp_official.sqlite --plot --category V --years 2025 --list-pairs
```

Legacy CLI (wciąż działające):

```bash
# Import
python SQL/import_official_ttp_to_sqlite.py "_Oficjalne dane.xlsx" ttp_official.sqlite

# Ranking
python SQL/App_sqlite.py --db ttp_official.sqlite --category V --years 2025 --classes B

# Eksport postępu
python SQL/progress_export_sqlite.py --db ttp_official.sqlite --category V --years 2025

# Migracje
python SQL/migrations.py ttp_official.sqlite --status
```