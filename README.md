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
  - opcjonalnie jedną lub wiele klas/podkategorii, np. `B`, `A`, `S`, `OPEN`,
  - zapis wyniku do wskazanego pliku.
- Osobny skrypt `progress_export.py` zapisuje do CSV historię zmian punktów par
  po każdym turnieju: punkty przed, punkty po, różnicę i lokatę.
- Dla kategorii bazowej zbierane są wszystkie pasujące podkategorie z plików `rsc/`, a filtr klas może zawęzić ten zestaw.
- `main.py` nadal istnieje jako prosty, starszy skrypt liczący jeden globalny ranking ze wszystkich plików `rsc/`. Korzysta z funkcji backendu, ale nie obsługuje filtrów lat, kategorii ani klas.

## Struktura repozytorium

- `App.py` — aplikacja użytkowa: GUI, interaktywny tryb terminalowy i tryb CLI z argumentami.
- `ranking_service.py` — scalony backend rankingu: model pary, wczytywanie `config.txt`, przetwarzanie pojedynczych turniejów, obliczanie zmian ELO, filtrowanie lat/kategorii/klas, budowa rankingu, formatowanie raportu i zapis wyniku.
- `progress_export.py` — eksport CSV pokazujący postęp par turniej po turnieju.
- `main.py` — legacy script przetwarzający całe `rsc/` i wypisujący wynik w konsoli.
- `config.txt` — parametry algorytmu ELO: `K`, `D` oraz domyślne ELO dla klas.
- `rsc/` — dane wejściowe, zorganizowane w podkatalogach roczników.
- `web-scraper/main.py` — scraper archiwum wyników; zapisuje dane do CSV albo bezpośrednio do `rsc/`.
- `web-scraper/diagnoza.py` — skrypt pomocniczy do sprawdzania struktury HTML strony archiwum.
- `web-scraper/wyniki_par.csv`, `web-scraper/wyniki_par_struktura.json`, `web-scraper/diagnoza_dom.html` — przykładowe lub diagnostyczne artefakty pracy scrapera.

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
rsc/{rok}/{dd-mm-turniej}-{kategoria}.txt
```

Przykład:

```text
rsc/2025/05-11-dobczyce-i.txt
rsc/2025/12-04-krakow-vb.txt
rsc/2024/19-10-wilanow-iiic.txt
```

## Agregacja kategorii

Aplikacja operuje na kategoriach bazowych `I`, `II`, `III`, `IV`, `V`, `VI`, `VII`, `VIII`.

Każda kategoria bazowa zbiera wszystkie pliki, których końcówka kategorii należy do tej samej rodziny. Przykłady:

- `V` obejmuje między innymi `V`, `VA`, `VB`, `VS`, `VOPEN`, `VAB`.
- `III` obejmuje między innymi `IIIA`, `IIIB`, `IIIC`, `IIIOPEN`.
- `IV` obejmuje między innymi `IVA`, `IVB`, `IVOPEN`.

Mapowanie działa po prefiksie kategorii z priorytetem dłuższych numerów rzymskich, więc `VI` nie wpada do `V`, a `VIII` nie wpada do `VII`.

Klasa jest wyciągana z sufiksu po kategorii bazowej:

- `VB` oznacza kategorię bazową `V` i klasę `B`.
- `VOPEN` oznacza kategorię bazową `V` i klasę `OPEN`.
- `V` oznacza kategorię bazową `V` bez sufiksu klasy.

GUI i CLI pozwalają ograniczyć ranking do wybranych klas. Brak wyboru klas oznacza wszystkie klasy dostępne dla wskazanej kategorii i lat.

## Jak liczony jest ranking

1. Para jest identyfikowana jako krotka `(tancerz1, tancerz2)`.
2. Nowa para startuje z domyślnym ELO dla klasy odczytanej z nazwy pliku, np. `defaulteloB` dla klasy `B`; pary z `OPEN` oraz klas innych niż `S`, `A`, `B`, `C` korzystają z `defaulteloOPEN`.
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

7. Wskaźniki `K`, `D` i domyślne ELO klas są wczytywane z pliku `config.txt` w katalogu projektu.
8. Aktualna zawartość `config.txt` ustawia `K = 50`, `D = 250`, `C = 1100`, `B = 1100`, `A = 1200`, `S = 1300`, `OPEN = 1000`.
9. W `App.py` ranking jest budowany sekwencyjnie: lata rosnąco, a w obrębie roku pliki według daty z nazwy `{dd}-{mm}-...`.
10. `main.py` korzysta z tej samej funkcji przetwarzania turnieju, ale jako legacy script nie przekazuje klas z nazw plików i traktuje wszystkie dane jako jeden globalny ranking.

### Konfiguracja

Plik `config.txt` w katalogu głównym projektu:

```text
K=50
D=250
defaulteloC=1100
defaulteloB=1100
defaulteloA=1200
defaulteloS=1300
defaulteloOPEN=1000
```

## Uruchamianie

### 1. Zalecany sposób: `App.py`

Jeżeli `tkinter` jest dostępny:

```bash
python3 App.py
```

Uruchomi się okno z wyborem lat, kategorii i klas.

Jeżeli `tkinter` nie jest dostępny:

```bash
python3 App.py
```

Uruchomi się tryb terminalowy z pytaniami o lata, kategorię, klasy i zapis wyniku.

### 2. Tryb CLI z argumentami

```bash
python3 App.py --category V --years 2025
python3 App.py --category V --classes B A --years 2025
python3 App.py --category III --years 2022 2023 2024
python3 App.py --category IV --years 2021-2025 --output ranking_iv_2021_2025.txt
python3 App.py --cli
```

Zasady:

- `--category` przyjmuje kategorię bazową, np. `V` albo `III`.
- `--years` przyjmuje pojedyncze lata i zakresy, np. `2024 2025` albo `2021-2025`.
- jeśli w trybie argumentowym nie podasz `--years`, zostaną użyte wszystkie dostępne lata z `rsc/`.
- `--classes` przyjmuje klasy do uwzględnienia, np. `B A`, `S OPEN` albo numery pozycji z listy klas; brak argumentu oznacza wszystkie klasy.
- `--output` zapisuje raport do pliku.
- `--cli` wymusza tryb terminalowy nawet wtedy, gdy `tkinter` jest dostępny.

### 3. Legacy script

```bash
python3 main.py
```

To polecenie:

- przetwarza całe `rsc/`,
- nie filtruje po latach, kategoriach ani klasach,
- wypisuje wynik w konsoli.

### 4. Eksport postępu par do CSV

```bash
python3 progress_export.py --category V --years 2025
python3 progress_export.py --category V --classes B A --years 2024-2025
python3 progress_export.py --category III --years 2022 2023 2024 --output progress_iii.csv
python3 progress_export.py
```

Bez argumentów skrypt pyta w terminalu o lata, kategorię, opcjonalnie klasy
i ścieżkę zapisu. Plik CSV ma domyślnie separator średnika i zawiera m.in.:

- rok, datę turnieju, nazwę turnieju i plik źródłowy,
- kategorię bazową, podkategorię i klasę,
- lokatę pary na turnieju,
- nazwiska tancerzy,
- `punkty_przed`, `punkty_po` i `roznica_punktow`.

### 5. Wykres ELO pary z CSV postępu

Wykres korzysta z CSV wygenerowanego przez `progress_export.py` i wymaga paczki
`seaborn` oraz biblioteki rysującej `matplotlib`:

```bash
python3 -m pip install seaborn matplotlib
```

Przykłady:

```bash
python3 pair_progress_plot.py progress_v_S_OPEN_A_B_bez_sufiksu_DEBIUT_2023_2024_2025.csv --pair "Pasiut Paweł, Ziółek Weronika"
python3 pair_progress_plot.py --input progress_v_S_OPEN_A_B_bez_sufiksu_DEBIUT_2023_2024_2025.csv --list-pairs --search "Pasiut"
python3 pair_progress_plot.py --input progress_v_S_OPEN_A_B_bez_sufiksu_DEBIUT_2023_2024_2025.csv --pair "Pasiut Paweł, Ziółek Weronika" --output wykres_pasiut_ziolek.png
```

Jeśli nie podasz ścieżki CSV, skrypt użyje najnowszego pliku `progress*.csv`
z katalogu projektu. Na osi Y pokazuje `punkty_po`, czyli ELO pary po danym
występie, a na osi X kolejne występy pary uporządkowane chronologicznie.

## Raport wynikowy

Raport generowany przez `App.py` zawiera:

- kategorię bazową,
- klasy uwzględnione w przebiegu,
- listę wybranych lat,
- liczbę przetworzonych plików,
- listę uwzględnionych podkategorii,
- tabelę rankingu,
- listę pominiętych plików, jeśli podczas wczytywania pojawił się błąd.

Domyślna nazwa pliku wyjściowego ma postać zbliżoną do:

```text
ranking_v_B_A_2025.txt
ranking_iii_S_OPEN_A_B_C_2022_2023_2024.txt
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

Tryb `--organise-data` zapisuje dane bezpośrednio do struktury `rsc/{rok}/{dd-mm-turniej}-{kategoria}.txt`, czyli do formatu używanego przez kalkulator rankingu.

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
