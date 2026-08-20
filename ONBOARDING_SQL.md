# Przewodnik startowy — Turnieje TP (edytja SQL)

Ten dokument opisuje krok po kroku, jak uruchomić system rankingu ELO
z bazą danych SQLite. Przewodnik jest przeznaczony dla nowych użytkowników
i administratorów, którzy chcą importować oficjalne dane TTP i liczyć rankingi.

---

## 1. Wymagania wstępne

| Wymaganie | Wersja / uwagi |
|-----------|----------------|
| Python | 3.10+ (testowano 3.14) |
| openpyxl | ≥3.1 (import XLSX) |
| sqlite3 | Dołączony do Pythona |
| Plik danych | Oficjalny arkusz XLSX z danymi TTP |
| config.txt | Parametry algorytmu ELO (w katalogu głównym) |

Zainstaluj zależności:

```bash
python -m venv .venv
.venv/bin/pip install openpyxl pandas
```

---

## 2. Struktura katalogów

```
Turnieje-TP-System-ELO/
├── config.txt                    # Parametry ELO (K, D, defaultELO)
├── data_new.xlsx                 # Dane turniejowe (format legacy)
├── SQL/
│   ├── migrations.py             # Framework migracji
│   ├── import_official_ttp_to_sqlite.py
│   ├── sqlite_ranking_service.py
│   ├── progress_export_sqlite.py
│   └── App_sqlite.py
├── .venv/                        # Środowisko wirtualne
└── txt/                          # Katalog wyjściowy raportów
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

```bash
# Import z domyślną nazwą bazy
.venv/bin/python SQL/import_official_ttp_to_sqlite.py "_Oficjalne dane.xlsx" ttp_official.sqlite

# Import zastępujący istniejącą bazę (usuwając ją najpierw)
.venv/bin/python SQL/import_official_ttp_to_sqlite.py "_Oficjalne dane.xlsx" ttp_official.sqlite --replace

# Import konkretnego arkusza
.venv/bin/python SQL/import_official_ttp_to_sqlite.py "_Oficjalne dane.xlsx" ttp_official.sqlite --sheet "Arkusz1"
```

Po importie zobaczysz podsumowanie:
```
Zaimportowano rekordów z arkusza: 5049
SQLite zapisano w: ttp_official.sqlite
Podsumowanie bazy: tancerze=1069, pary=695, turnieje=55, eventy=571, wyniki=5049, ostrzeżenia=0
```

### 3.3 Sprawdź status migracji

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

---

## 4. Liczenie rankingu

### 4.1 Podstawowe użycie (CLI App_sqlite.py)

```bash
# Ranking kategorii V, klasa B, sezon 2025
.venv/bin/python SQL/App_sqlite.py --db ttp_official.sqlite --category V --years 2025 --classes B

# Ranking kategorii III, klasy A i S, lata 2022-2025
.venv/bin/python SQL/App_sqlite.py --db ttp_official.sqlite --category III --years 2022-2025 --classes A S

# Ranking wszystkich klas w kategorii V
.venv/bin/python SQL/App_sqlite.py --db ttp_official.sqlite --category V --years 2025
```

### 4.2 Użycie z główną aplikacją App.py (backend SQLite)

Główna aplikacja `App.py` obsługuje teraz oba backendy: XLSX (domyślny) i SQLite.

```bash
# Ranking z backendem SQLite
.venv/bin/python App.py --backend sqlite --db ttp_official.sqlite --category V --years 2025 --classes B

# Ranking z backendem XLSX (domyślne)
.venv/bin/python App.py --backend xlsx --category V --years 2025 --classes B

# Lista lat dostępnych w bazie SQLite
.venv/bin/python App.py --backend sqlite --db ttp_official.sqlite --list-years
```

### 4.2 Zapis raportu do pliku

```bash
.venv/bin/python SQL/App_sqlite.py \
  --db ttp_official.sqlite \
  --category V \
  --years 2025 \
  --classes B \
  --output txt/ranking_v_2025_b.txt
```

### 4.3 Eksploracja danych

```bash
# Dostępne lata w bazie
.venv/bin/python SQL/App_sqlite.py --db ttp_official.sqlite --list-years

# Dostępne klasy dla kategorii V
.venv/bin/python SQL/App_sqlite.py --db ttp_official.sqlite --category V --years 2025 --list-classes
```

---

## 5. Eksport historii zmian (progress)

Historia zmian punktów pozwala śledzić, jak ELO pary zmieniało się
od turnieju do turnieju.

### 5.1 Podstawowe użycie

```bash
# Eksport historii kategorii V, klasa B
.venv/bin/python SQL/progress_export_sqlite.py \
  --db ttp_official.sqlite \
  --category V \
  --years 2025 \
  --classes B \
  --output progress_v_2025_b.csv
```

### 5.2 Format CSV

Plik CSV zawiera kolumny:
- `season`, `tournament_code`, `tournament_name`, `event_date`
- `event_id`, `cat_code`, `base_category`, `class_code`
- `rank`, `pair_id`, `pair`, `group`
- `punkty_przed`, `punkty_po`, `roznica_punktow`

Separator: `;` (średnik), kodowanie: UTF-8-BOM.

---

## 6. Zarządzanie migracjami

### 6.1 Co to jest migracja?

Migracja to sekwencja instrukcji SQL, które modyfikują schemat bazy danych.
Framework migracji (`migrations.py`) śledzi, które migracje zostały już
zastosowane, i umożliwia bezpieczną ewolucję schematu.

### 6.2 Dodawanie nowej migracji

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

### 6.3 Ręczne uruchomienie migracji

```bash
# Uruchom wszystkie oczekujące migracje
.venv/bin/python SQL/migrations.py ttp_official.sqlite

# Uruchom migracje do konkretnej wersji
.venv/bin/python SQL/migrations.py ttp_official.sqlite --target 3
```

### 6.4 Automatyczne migracje

Migracje uruchamiają się automatycznie przy:
- pierwszym imporcie danych (`import_official_ttp_to_sqlite.py`)
- każdym uruchomieniu `sqlite_ranking_service.py` (jeśli wywoływane przez App_sqlite)

---

## 7. Konfiguracja algorytmu ELO

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

---

## 8. Algorytm ELO — jak działa

### 8.1 Para startowa
Każda nowa para (nie widziana wcześniej) otrzymuje domyślne ELO
z `config.txt` (np. 900 dla klasy B).

### 8.2 Porównanie w turnieju
W obrębie jednego turnieju (tego samego `tournament_code` + `cat_code`)
każda para jest porównywana z każdą inną.

### 8.3 Wynik meczu
- Niższa lokata = wygrana (`actual = 1.0`)
- Wyższa lokata = porażka (`actual = 0.0`)
- Ta sama lokata = remis (`actual = 0.5`)

### 8.4 Aktualizacja ELO
```
nowe_ELO = stare_ELO + (actual - expected) * K / (n-1)
```
Gdzie:
- `expected = 1 / (1 + 10^((rating_B - rating_A) / D))`
- `n` = liczba par w turnieju
- `K` = współczynnik z config.txt

---

## 9. Schemat bazy danych

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
| `schema_version` | Wersja schematu (migracje) |

---

## 10. Rozwiązywanie problemów

### Problem: "Nie znaleziono wiersza nagłówka z wymaganymi kolumnami"
**Przyczyna:** Plik XLSX nie ma wszystkich wymaganych kolumn.
**Rozwiązanie:** Sprawdź, czy plik ma nagłówek z kolumnami wymienionymi w sekcji 3.1.

### Problem: "Brak danych dla kategorii X w latach Y"
**Przyczyna:** Brak wyników dla wybranych filtrów.
**Rozwiązanie:** Sprawdź dostępne lata (`--list-years`) i klasy (`--list-classes`).

### Problem: Import wstawia duplikaty
**Przyczyna:** Import jest idempotentny —uplicates nie powinny wystąpić.
Jeśli się pojawiają, użyj `--replace` lub sprawdź, czy plik nie został
już wcześniej zaimportowany.

### Problem: Zły wynik rankingu (pary mają dziwne ELO)
**Przyczyna:** Zła kolejność turniejów w bazie.
**Rozwiązanie:** Sprawdź `event_date` w tabeli `tournaments` —
jeśli jest NULL, sortowanie odbywa się wg kolejności importu.

---

## 11. Szybki start (TL;DR)

```bash
# 1. Aktywuj środowisko
.venv/bin/activate

# 2. Importuj dane
.venv/bin/python SQL/import_official_ttp_to_sqlite.py "_Oficjalne dane.xlsx" ttp_official.sqlite

# 3. Licz ranking
.venv/bin/python SQL/App_sqlite.py --db ttp_official.sqlite --category V --years 2025

# 4. Eksportuj historię
.venv/bin/python SQL/progress_export_sqlite.py --db ttp_official.sqlite --category V --years 2025

# 5. Sprawdź migracje
.venv/bin/python SQL/migrations.py ttp_official.sqlite --status
```

---

## 12. Kontakt i wsparcie

- Autor: Macina222
- Repozytorium: https://github.com/Macina222/Turnieje-TP-System-ELO
- Problemy: https://github.com/Macina222/Turnieje-TP-System-ELO/issues