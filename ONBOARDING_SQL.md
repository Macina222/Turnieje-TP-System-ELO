# Przewodnik startowy — Turnieje TP (edycja SQL)

Ten dokument opisuje krok po kroku, jak uruchomić system rankingu ELO
z bazą danych SQLite. Przewodnik jest przeznaczony dla nowych użytkowników
i administratorów, którzy chcą importować oficjalne dane TTP i liczyć rankingi.

---

## 1. Wymagania wstępne

| Wymaganie | Wersja / uwagi |
|-----------|----------------|
| Python | 3.10+ (testowano 3.14) |
| openpyxl | ≥3.1 (import XLSX) |
| pandas | ≥2.0 (obsługa XLSX) |
| sqlite3 | Dołączony do Pythona |
| tkinter | Dołączony do Pythona (GUI) |
| matplotlib | ≥3.5 (wykresy) |
| Plik danych | Oficjalny arkusz XLSX z danymi TTP |
| config.txt | Parametry algorytmu ELO (w katalogu głównym) |

Zainstaluj zależności:

```bash
python -m venv .venv
.venv/bin/pip install openpyxl pandas matplotlib
```

---

## 2. Struktura katalogów

```
Turnieje-TP-System-ELO/
├── App.py                          # Główna aplikacja (GUI + CLI) — centrum sterowania
├── app_gui.py                      # Moduł GUI z 5 zakładkami Notebook
├── app_cli.py                      # Handlery CLI dla App.py
├── config.txt                      # Parametry ELO (K, D, defaultELO)
├── data_new.xlsx                   # Dane turniejowe (format legacy XLSX)
├── ranking_config.py               # Ujednolicona konfiguracja (EloConfig)
├── new_ranking_service.py          # Backend XLSX (ranking, eksport, wykresy)
├── new_progress_export.py          # Eksport CSV historii (XLSX)
├── new_pair_progress_plot.py       # Wykresy ELO par (XLSX)
├── SQL/
│   ├── migrations.py               # Framework migracji (v1, v2)
│   ├── import_official_ttp_to_sqlite.py  # Import XLSX → SQLite
│   ├── sqlite_ranking_service.py   # Backend SQLite (ranking, eksport)
│   ├── progress_export_sqlite.py   # Eksport CSV historii (SQLite)
│   └── App_sqlite.py               # Legacy CLI SQLite
├── legacy/                         # Stary backend (rsc/, ranking_service.py)
├── tests/                          # Testy regresyjne
├── .venv/                          # Środowisko wirtualne
├── txt/                            # Katalog wyjściowy raportów rankingowych
├── csv/                            # Katalog wyjściowy eksportów CSV
├── img/                            # Katalog wyjściowy wykresów PNG
└── ttp_official.sqlite             # Baza SQLite (po imporcie)
```

---

## 3. Pierwszy start — import danych

### 3.1 Przygotuj oficjalny plik XLSX

Oficjalny arkusz danych TTP (np. `_Oficjalne dane.xlsx`) powinien zawierać
nagłówek w pierwszym niepustym wierszu z kolumnami:

| Kolumna | Opis | Przykład |
|---------|------|----------|
| dancers id | ID tancerzy (format: `591-1411`) | `591-1411` |
| pair id | Numer identyfikacyjny pary | `911` |
| season | Sezon (rok) | `2025` |
| turnament code | Kod turnieju | `POZNAN` |
| turnament name | Nazwa turnieju | `POZNAN` |
| cat code | Kod kategorii (bazowa + klasa) | `VB` |
| pair | Nazwa pary (imię, imię) | `PIOTR, WERONIKA` |
| group | Grupa (opcjonalnie) | `A` |
| rank | Lokata | `1` |
| points before | Punkty przed turniejem | `1000.5` |
| points | Przyznane punkty | `15.5` |
| medals | Medale (opcjonalnie) | `0` |
| points after | Punkty po turnieju | `1016.0` |
| medals after | Medale po turnieju | `0` |

### 3.2 Importuj do bazy SQLite

**Opcja A: CLI (App.py — nowy centralny punkt wejścia)**

```bash
# Import z domyślną nazwą bazy
.venv/bin/python App.py --import-sql "_Oficjalne dane.xlsx" ttp_official.sqlite

# Import zastępujący istniejącą bazę (usuwając ją najpierw)
.venv/bin/python App.py --import-sql "_Oficjalne dane.xlsx" ttp_official.sqlite --replace-db

# Import konkretnego arkusza
.venv/bin/python App.py --import-sql "_Oficjalne dane.xlsx" ttp_official.sqlite --import-sheet "Arkusz1"
```

**Opcja B: Legacy CLI (SQL/import_official_ttp_to_sqlite.py)**

```bash
# Import z domyślną nazwą bazy
.venv/bin/python SQL/import_official_ttp_to_sqlite.py "_Oficjalne dane.xlsx" ttp_official.sqlite

# Import zastępujący istniejącą bazę
.venv/bin/python SQL/import_official_ttp_to_sqlite.py "_Oficjalne dane.xlsx" ttp_official.sqlite --replace

# Import konkretnego arkusza
.venv/bin/python SQL/import_official_ttp_to_sqlite.py "_Oficjalne dane.xlsx" ttp_official.sqlite --sheet "Arkusz1"
```

**Opcja C: GUI (zakładka "2. Import SQL")**

1. Uruchom GUI: `.venv/bin/python App.py`
2. Przejdź do zakładki **2. Import SQL**
3. Wybierz plik XLSX źródłowy (przycisk "Przeglądaj...")
4. Wybierz lub wpisz ścieżę do bazy SQLite (domyślnie `ttp_official.sqlite`)
5. Opcjonalnie: wpisz nazwę arkusza
6. Zaznacz "Zastąp istniejącą bazę" jeśli chcesz nadpisać
7. Kliknij **Importuj do SQLite**

Po importie zobaczysz podsumowanie:
```
Zaimportowano rekordów z arkusza: 5049
SQLite zapisano w: ttp_official.sqlite
Podsumowanie bazy: tancerze=1069, pary=695, turnieje=55, eventy=571, wyniki=5049, ostrzeżenia=0
```

### 3.3 Sprawdź status migracji

**CLI (App.py):**
```bash
# Status migracji
.venv/bin/python App.py --migrate ttp_official.sqlite --migrate-status

# Uruchom migracje
.venv/bin/python App.py --migrate ttp_official.sqlite
```

**Legacy CLI (SQL/migrations.py):**
```bash
.venv/bin/python SQL/migrations.py ttp_official.sqlite --status
```

Przykładowy wynik:
```
Current version: 2
Target version: 2
Applied migrations:
  v1: initial_schema (2026-08-19 20:55:55)
  v2: add_event_date_to_tournaments (2026-08-19 20:55:55)
```

**GUI (zakładka "5. Migrations"):**
1. Przejdź do zakładki **5. Migrations**
2. Wpisz ścieżkę do bazy SQLite
3. Kliknij **Odśwież status** — zobaczysz listę zastosowanych migracji
4. Kliknij **Uruchom migracje** aby zastosować oczekujące

---

## 4. Liczenie rankingu

### 4.1 Podstawowe użycie (CLI App.py — backend SQLite)

```bash
# Ranking kategorii V, klasa B, sezon 2025
.venv/bin/python App.py --backend sqlite --db ttp_official.sqlite --category V --years 2025 --classes B

# Ranking kategorii III, klasy A i S, lata 2022-2025
.venv/bin/python App.py --backend sqlite --db ttp_official.sqlite --category III --years 2022-2025 --classes A S

# Ranking wszystkich klas w kategorii V
.venv/bin/python App.py --backend sqlite --db ttp_official.sqlite --category V --years 2025
```

### 4.2 Podstawowe użycie (CLI App.py — backend XLSX)

```bash
# Ranking z backendem XLSX (domyślny)
.venv/bin/python App.py --backend xlsx --category V --years 2025 --classes B

# Ranking z innym plikiem XLSX
.venv/bin/python App.py --backend xlsx --input-excel inny_plik.xlsx --category V --years 2025
```

### 4.3 Użycie z legacy CLI (SQL/App_sqlite.py)

```bash
# Ranking z backendem SQLite
.venv/bin/python SQL/App_sqlite.py --db ttp_official.sqlite --category V --years 2025 --classes B
```

### 4.4 GUI (zakładka "1. Ranking")

1. Uruchom GUI: `.venv/bin/python App.py`
2. W zakładce **1. Ranking** wybierz backend: **XLSX** lub **SQLite**
3. **Backend XLSX:**
   - Wybierz plik XLSX (domyślnie `data_new.xlsx`)
   - Kliknij **Odśwież lata** — zobaczysz dostępne sezony
   - Zaznacz lata (Ctrl+klik lub Shift+klik dla zakresu)
4. **Backend SQLite:**
   - Wybierz plik bazy SQLite (domyślnie `ttp_official.sqlite`)
   - Kliknij **Odśwież lata** — zobaczysz dostępne sezony
   - Zaznacz lata
5. Wybierz kategorię z listy (automatycznie aktualizowana po wyborze lat)
6. Opcjonalnie: zaznacz klasy (domyślnie wszystkie)
7. Opcjonalnie: wpisz ścieżkę wyjściową dla raportu
8. Kliknij **Oblicz ranking** — wynik pojawi się w polu tekstowym
9. Kliknij **Zapisz ranking** aby zapisać do pliku

### 4.5 Zapis raportu do pliku

```bash
.venv/bin/python App.py --backend sqlite --db ttp_official.sqlite \
  --category V --years 2025 --classes B \
  --output txt/ranking_v_2025_b.txt
```

### 4.6 Raporty dla wszystkich kategorii

```bash
# Wszystkie kategorie dostępne w latach 2025
.venv/bin/python App.py --backend sqlite --db ttp_official.sqlite \
  --all-categories --years 2025 --output-dir txt
```

### 4.7 Eksploracja danych (CLI)

```bash
# Dostępne lata w bazie SQLite
.venv/bin/python App.py --backend sqlite --db ttp_official.sqlite --list-years

# Dostępne kategorie dla lat 2024-2025
.venv/bin/python App.py --backend sqlite --db ttp_official.sqlite \
  --years 2024 2025 --list-categories

# Dostępne klasy dla kategorii V
.venv/bin/python App.py --backend sqlite --db ttp_official.sqlite \
  --category V --years 2025 --list-classes
```

---

## 5. Eksport historii zmian (progress)

Historia zmian punktów pozwala śledzić, jak ELO pary zmieniało się
od turnieju do turnieju.

### 5.1 CLI (App.py — nowy ujednolicony interfejs)

```bash
# Eksport historii kategorii V, klasa B (backend XLSX — domyślny)
.venv/bin/python App.py --export-progress --category V --years 2025 --classes B

# Eksport z backendem SQLite
.venv/bin/python App.py --backend sqlite --db ttp_official.sqlite \
  --export-progress --category V --years 2025 --classes B

# Własna ścieżka wyjściowa i separator
.venv/bin/python App.py --export-progress --category V --years 2025 \
  --export-output csv/progress_v_2025_b.csv --delimiter ","
```

### 5.2 Legacy CLI (SQL/progress_export_sqlite.py)

```bash
.venv/bin/python SQL/progress_export_sqlite.py \
  --db ttp_official.sqlite \
  --category V \
  --years 2025 \
  --classes B \
  --output progress_v_2025_b.csv
```

### 5.3 GUI (zakładka "3. Export CSV")

1. Przejdź do zakładki **3. Export CSV**
2. Wybierz backend: **XLSX** lub **SQLite**
3. Wskaż plik źródłowy (XLSX lub baza SQLite)
4. Kliknij **Odśwież lata** i zaznacz sezony
5. Wybierz kategorię z listy
6. Opcjonalnie: zaznacz klasy
7. Opcjonalnie: wpisz ścieżkę wyjściową CSV
8. Kliknij **Podgląd (pierwsze 20 wierszy)** — zobaczysz podgląd w polu tekstowym
9. Kliknij **Eksportuj do CSV** — plik zostanie zapisany

### 5.4 Format CSV

Plik CSV zawiera kolumny:
- `season`, `tournament_code`, `tournament_name`, `event_date`
- `event_id`, `cat_code`, `base_category`, `class_code`
- `rank`, `pair_id`, `pair`, `group`
- `punkty_przed`, `punkty_po`, `roznica_punktow`

Separator: `;` (średnik, konfigurowalny `--delimiter`), kodowanie: UTF-8-BOM.

---

## 6. Wykresy ELO par

Generowanie wykresów historii ELO dla wybranych par.

### 6.1 CLI (App.py — nowy ujednolicony interfejs)

```bash
# Lista par z filtrem (backend XLSX)
.venv/bin/python App.py --backend xlsx --category V --years 2025 --list-pairs --search "Kowalski"

# Lista par (backend SQLite)
.venv/bin/python App.py --backend sqlite --db ttp_official.sqlite --category V --years 2025 --list-pairs

# Wykres dla konkretnej pary (po ID) — zapis do PNG
.venv/bin/python App.py --backend sqlite --db ttp_official.sqlite \
  --plot --category V --years 2025 --pair-id 12345 \
  --plot-output img/elo_12345.png

# Wykres dla pary (po nazwie) — pokaż okno
.venv/bin/python App.py --backend xlsx --category V --years 2025 \
  --plot --pair "JAN, ANNA" --show

# Wykres dla obu tancerzy (musi być obydwa)
.venv/bin/python App.py --backend sqlite --db ttp_official.sqlite \
  --plot --category V --years 2025 \
  --tancerz1 "JAN" --tancerz2 "ANNA" --show
```

### 6.2 Legacy CLI (new_pair_progress_plot.py)

```bash
# Lista par z filtrem
.venv/bin/python new_pair_progress_plot.py --category V --years 2025 --list-pairs --search "Kowalski"

# Wykres do pliku
.venv/bin/python new_pair_progress_plot.py --category V --years 2025 --pair-id 12345 --output wykres.png
```

### 6.3 GUI (zakładka "4. Charts")

1. Przejdź do zakładki **4. Charts**
2. Wybierz backend: **XLSX** lub **SQLite**
3. Wskaż plik źródłowy
4. Kliknij **Odśwież lata** i zaznacz sezony
5. Wybierz kategorię
6. Opcjonalnie: zaznacz klasy
7. Kliknij **Odśwież listę par** — zobaczysz listę par z liczbą występów
8. Użyj pola **Szukaj** aby przefiltrować listę (np. nazwisko)
9. Zaznacz jedną lub więcej par na liście (Ctrl+klik)
10. Opcjonalnie: wpisz ścieżkę wyjściową PNG
11. Zaznacz **Pokaż wykres** jeśli chcesz zobaczyć okno interaktywne
12. Kliknij **Generuj wykres(y)**

---

## 7. Zarządzanie migracjami

### 7.1 Co to jest migracja?

Migracja to sekwencja instrukcji SQL, które modyfikują schemat bazy danych.
Framework migracji (`SQL/migrations.py`) śledzi, które migracje zostały już
zastosowane, i umożliwia bezpieczną ewolucję schematu.

### 7.2 Dostępne migracje

| Wersja | Nazwa | Opis |
|--------|-------|------|
| v1 | `initial_schema` | Schemat początkowy: tabele source_files, tournaments, events, results, pairs, dancers, pair_members, groups, import_warnings, schema_version |
| v2 | `add_event_date_to_tournaments` | Dodaje kolumnę `event_date` do tabeli `tournaments` dla lepszego sortowania chronologicznego |

### 7.3 Dodawanie nowej migracji

1. Otwórz `SQL/migrations.py`
2. Zwiększ `CURRENT_SCHEMA_VERSION` o 1
3. Dodaj nowy obiekt `Migration` do listy `MIGRATIONS`:

```python
Migration(
    version=3,  # numer wersji
    name="add_new_column",
    up_sql="""
    ALTER TABLE tournaments ADD COLUMN new_column TEXT;
    CREATE INDEX IF NOT EXISTS idx_tournaments_new ON tournaments(new_column);
    INSERT OR IGNORE INTO schema_version (version, name) VALUES (3, 'add_new_column');
    """,
    down_sql="""
    DELETE FROM schema_version WHERE version = 3;
    """,
)
```

### 7.4 Ręczne uruchomienie migracji

**CLI (App.py):**
```bash
# Status
.venv/bin/python App.py --migrate ttp_official.sqlite --migrate-status

# Uruchom wszystkie oczekujące
.venv/bin/python App.py --migrate ttp_official.sqlite

# Uruchom do konkretnej wersji
.venv/bin/python App.py --migrate ttp_official.sqlite --migrate-target 3
```

**Legacy CLI (SQL/migrations.py):**
```bash
# Uruchom wszystkie oczekujące migracje
.venv/bin/python SQL/migrations.py ttp_official.sqlite

# Uruchom migracje do konkretnej wersji
.venv/bin/python SQL/migrations.py ttp_official.sqlite --target 3
```

### 7.5 Automatyczne migracje

Migracje uruchamiają się automatycznie przy:
- pierwszym imporcie danych (`import_official_ttp_to_sqlite.py` lub `App.py --import-sql`)
- każdym uruchomieniu `sqlite_ranking_service.py` (jeśli wywoływane przez App.py)

### 7.6 GUI (zakładka "5. Migrations")

1. Przejdź do zakładki **5. Migrations**
2. Wpisz ścieżkę do bazy SQLite
3. Kliknij **Odśwież status** — zobaczysz:
   - Obecną wersję schematu
   - Docelową wersję
   - Listę zastosowanych migracji z datami
   - Liczbę oczekujących migracji
4. Kliknij **Uruchom migracje** aby zastosować wszystkie oczekujące
5. Opcjonalnie: wpisz **Wersja docelowa** i kliknij **Uruchom migracje** aby zatrzymać się na konkretnej wersji

---

## 8. Konfiguracja algorytmu ELO

Plik `config.txt` w katalogu głównym projektu:

```
K=50                          # Współczynnik K (tempo zmian)
D=250                         # Współczynnik D (skala różnic)
defaulteloC=800               # Domyślne ELO dla klasy C
defaulteloB=900               # Domyślne ELO dla klasy B
defaulteloA=1000              # Domyślne ELO dla klasy A
defaulteloS=1100              # Domyślne ELO dla klasy S
defaulteloOPEN=950            # Domyślne ELO dla OPEN i innych
```

Nowe pary zaczynają z domyślnego ELO odpowiadającemu ich klasie.

**Wskazówka:** Możesz użyć innego pliku konfiguracyjnego:
```bash
.venv/bin/python App.py --config moj_config.txt --backend sqlite --db ttp_official.sqlite --category V --years 2025
```

---

## 9. Algorytm ELO — jak działa

### 9.1 Para startowa
Każda nowa para (nie widziana wcześniej) otrzymuje domyślne ELO
z `config.txt` (np. 900 dla klasy B).

### 9.2 Porównanie w turnieju
W obrębie jednego turnieju (tego samego `tournament_code` + `cat_code`)
każda para jest porównywana z każdą inną.

### 9.3 Wynik meczu
- Niższa lokata = wygrana (`actual = 1.0`)
- Wyższa lokata = porażka (`actual = 0.0`)
- Ta sama lokata = remis (`actual = 0.5`)

### 9.4 Aktualizacja ELO
```
nowe_ELO = stare_ELO + (actual - expected) * K / (n-1)
```
Gdzie:
- `expected = 1 / (1 + 10^((rating_B - rating_A) / D))`
- `n` = liczba par w turnieju
- `K` = współczynnik z config.txt

---

## 10. Schemat bazy danych

```
source_files ─────────────────────────────────────────┐
    │                                                   │
    └─── tournaments ──── events ──── results ◄─────────┘
                              │         │
                              │         └─── pairs ◄──── pair_members
                              │              │             │
                              │              └─── dancers ◄┘
                              │
                              └─── groups
                              
import_warnings (logi importu)
schema_version (wersja schematu)
```

### Kluczowe tabele:

| Tabela | Opis |
|--------|------|
| `tournaments` | Turnieje (sezon, kod, nazwa, data) |
| `events` | Wydarzenia w turniejach (kategoria, klasa) |
| `results` | Wyniki par (lokata, punkty przed/po) |
| `pairs` | Pary taneczne (ID, nazwa) |
| `dancers` | Tancerze (ID, imię i nazwisko) |
| `pair_members` | Powiązania par z tancerzami (wiele-do-wielu) |
| `groups` | Grupy turniejowe (opcjonalnie) |
| `schema_version` | Wersja schematu (migracje) |
| `import_warnings` | Ostrzeżenia z procesu importu |

---

## 11. Rozwiązywanie problemów

### Problem: "Nie znaleziono wiersza nagłówka z wymaganymi kolumnami"
**Przyczyna:** Plik XLSX nie ma wszystkich wymaganych kolumn.
**Rozwiązanie:** Sprawdź, czy plik ma nagłówek z kolumnami wymienionymi w sekcji 3.1.

### Problem: "Brak danych dla kategorii X w latach Y"
**Przyczyna:** Brak wyników dla wybranych filtrów.
**Rozwiązanie:** Sprawdź dostępne lata (`--list-years`) i klasy (`--list-classes`).

### Problem: Import wstawia duplikaty
**Przyczyna:** Import jest idempotentny — duplikaty nie powinny wystąpić.
Jeśli się pojawiają, użyj `--replace-db` (App.py) lub `--replace` (legacy) lub sprawdź, czy plik nie został już wcześniej zaimportowany.

### Problem: Zły wynik rankingu (pary mają dziwne ELO)
**Przyczyna:** Zła kolejność turniejów w bazie.
**Rozwiązanie:** Sprawdź `event_date` w tabeli `tournaments` —
jeśli jest NULL, sortowanie odbywa się wg kolejności importu.
Uruchom migrację v2 (`add_event_date_to_tournaments`) i zaktualizuj daty turniejów.

### Problem: GUI nie pokazuje lat / kategorii
**Przyczyna:** Nie kliknięto "Odśwież lata" po wyborze pliku/bazy.
**Rozwiązanie:** Zawsze klikaj **Odśwież lata** po zmianie źródła danych.

### Problem: StringVar AttributeError w GUI
**Przyczyna:** Zmienne Tkinter zostały wyrzucone przez garbage collector.
**Rozwiązanie:** Zaktualizuj do najnowszej wersji `app_gui.py` (naprawiono w wersji z 5 zakładkami).

---

## 12. Szybki start (TL;DR)

```bash
# 1. Aktywuj środowisko
.venv/bin/activate

# 2. Importuj dane (nowy centralny CLI)
.venv/bin/python App.py --import-sql "_Oficjalne dane.xlsx" ttp_official.sqlite

# 3. Sprawdź migracje
.venv/bin/python App.py --migrate ttp_official.sqlite --migrate-status

# 4. Licz ranking (backend SQLite)
.venv/bin/python App.py --backend sqlite --db ttp_official.sqlite --category V --years 2025 --classes B

# 5. Eksportuj historię
.venv/bin/python App.py --backend sqlite --db ttp_official.sqlite --export-progress --category V --years 2025 --classes B

# 6. Wykresy
.venv/bin/python App.py --backend sqlite --db ttp_official.sqlite --plot --category V --years 2025 --list-pairs
.venv/bin/python App.py --backend sqlite --db ttp_official.sqlite --plot --category V --years 2025 --pair-id 12345 --plot-output img/wykres.png

# 7. Lub uruchom GUI ze wszystkimi funkcjami
.venv/bin/python App.py
```

---

## 13. Pełny przegląd CLI (App.py)

### Tryb GUI (domyślny)
```bash
.venv/bin/python App.py
```

### Tryb interaktywny terminalowy (tylko ranking XLSX)
```bash
.venv/bin/python App.py --cli
```

### Backend XLSX (domyślny)
```bash
# Ranking
.venv/bin/python App.py --category V --years 2025 --classes B
.venv/bin/python App.py --category III --years 2022-2025 --classes A S --output ranking.txt
.venv/bin/python App.py --all-categories --years 2025 --output-dir txt

# Eksport CSV
.venv/bin/python App.py --export-progress --category V --years 2025 --classes B
.venv/bin/python App.py --export-progress --category V --years 2024-2025 --classes B A --export-output progress.csv --delimiter ","

# Wykresy
.venv/bin/python App.py --category V --years 2025 --list-pairs --search "Kowalski"
.venv/bin/python App.py --plot --category V --years 2025 --pair "JAN, ANNA" --show
.venv/bin/python App.py --plot --category V --years 2025 --pair-id 12345 --plot-output wykres.png
```

### Backend SQLite
```bash
# Ranking
.venv/bin/python App.py --backend sqlite --db ttp_official.sqlite --category V --years 2025 --classes B

# Import
.venv/bin/python App.py --import-sql "_Oficjalne dane.xlsx" ttp_official.sqlite --replace-db

# Migracje
.venv/bin/python App.py --migrate ttp_official.sqlite --migrate-status
.venv/bin/python App.py --migrate ttp_official.sqlite

# Eksport CSV
.venv/bin/python App.py --backend sqlite --db ttp_official.sqlite --export-progress --category V --years 2025 --classes B

# Wykresy
.venv/bin/python App.py --backend sqlite --db ttp_official.sqlite --plot --category V --years 2025 --list-pairs
.venv/bin/python App.py --backend sqlite --db ttp_official.sqlite --plot --category V --years 2025 --pair-id 12345 --plot-output img/wykres.png
```

### Wspólne opcje
| Argument | Wartości | Opis |
|----------|----------|------|
| `--backend` | `xlsx` (domyślnie), `sqlite` | Źródło danych |
| `--input-excel` | ścieżka | Plik XLSX (dla backend xlsx) |
| `--db` | ścieżka | Plik bazy SQLite (wymagane dla `--backend sqlite`) |
| `--config` | ścieżka | Plik konfiguracyjny (domyślnie `config.txt`) |
| `--category` | np. `V`, `III` | Kategoria bazowa |
| `--years` | np. `2025`, `2022-2025` | Lata/sezony |
| `--classes` | np. `B A S` | Klasy (brak = wszystkie) |
| `--output` | ścieżka | Plik wyjściowy rankingu |
| `--output-dir` | katalog | Katalog dla `--all-categories` (domyślnie `txt`) |
| `--export-progress` | flaga | Eksport historii do CSV |
| `--export-output` | ścieżka | Plik CSV wyjściowy |
| `--delimiter` | znak | Separator CSV (domyślnie `;`) |
| `--plot` | flaga | Generuj wykres |
| `--pair` | nazwa | Nazwa pary (można wielokrotnie) |
| `--pair-id` | ID | ID pary (można wielokrotnie) |
| `--tancerz1` / `--tancerz2` | imię | Wybór pary po tancerzach (oba wymagane) |
| `--list-pairs` | flaga | Lista par zamiast wykresu |
| `--search` | tekst | Filtr dla `--list-pairs` |
| `--limit` | liczba | Limit na liście par (domyślnie 50) |
| `--plot-output` | ścieżka | Plik PNG wyjściowy |
| `--show` | flaga | Pokaż okno wykresu |
| `--title` | tekst | Własny tytuł wykresu |
| `--migrate` | ścieżka | Uruchom migracje bazy |
| `--migrate-target` | wersja | Docelowa wersja migracji |
| `--migrate-status` | flaga | Tylko status migracji |
| `--import-sql` | XLSX SQLite | Import XLSX → SQLite |
| `--import-sheet` | nazwa | Arkusz do importu |
| `--replace-db` | flaga | Usuń bazę przed importem |
| `--cli` | flaga | Wymuś tryb terminalowy |
| `--list-years` | flaga | Lista lat (SQLite) |
| `--list-categories` | flaga | Lista kategorii (SQLite) |
| `--list-classes` | flaga | Lista klas (SQLite) |

---

## 14. Kontakt i wsparcie

- Autor: Macina222
- Repozytorium: https://github.com/Macina222/Turnieje-TP-System-ELO
- Problemy: https://github.com/Macina222/Turnieje-TP-System-ELO/issues