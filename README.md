# Turnieje TP System ELO

Prosty kalkulator rankingu ELO dla par tanecznych na podstawie wyników turniejów Tańców Polskich. Projekt przetwarza pliki z wynikami zapisane w katalogu `rsc/`, aktualizuje wspólny ranking par i zapisuje końcową tabelę do `ranking.txt`.

## Cel projektu

System ma oszacować siłę pary tanecznej na podstawie zajmowanych lokat. Zamiast przechowywać wyłącznie miejsca z pojedynczego turnieju, projekt buduje jeden globalny ranking ELO, który zmienia się po każdym kolejnym przetworzonym pliku z wynikami.

W praktyce oznacza to, że:

- każda para startuje z tym samym rankingiem początkowym `1000.0`,
- każda kolejna lista wyników wpływa na aktualny ranking,
- wyższe miejsce oznacza zwycięstwo nad parami sklasyfikowanymi niżej,
- remis lokat jest traktowany jak remis w pojedynku,
- ta sama para ma jeden wspólny ranking we wszystkich przetworzonych plikach.

## Jak działa system

### 1. Dane wejściowe

Silnik rankingu korzysta z plików tekstowych CSV w katalogu `rsc/`. Każdy plik jest traktowany jako jeden zestaw wyników do przeliczenia, zwykle odpowiadający jednej kategorii w konkretnym turnieju.

Oczekiwany format pliku:

```csv
Lokata;Para;Ośrodek;Instruktor
1;Nazwisko1 Imię1, Nazwisko2 Imię2;Nazwa ośrodka;Imię Nazwisko
2;Nazwisko3 Imię3, Nazwisko4 Imię4;Nazwa ośrodka;Imię Nazwisko
```

W samym obliczaniu rankingu wykorzystywane są tylko pola:

- `Lokata`
- `Para`

Kolumny `Ośrodek` i `Instruktor` są obecnie wczytywane z pliku, ale nie wpływają na wynik ELO.

### 2. Budowa bazy par

Podczas przetwarzania projektu każda para jest identyfikowana po krotce:

```python
(tancerz1, tancerz2)
```

Jeżeli para pojawia się po raz pierwszy, otrzymuje ranking początkowy `1000.0`. Jeżeli była już wcześniej przetwarzana, system używa jej bieżącego ELO.

To ważne, bo oznacza również, że spójność zapisu nazwisk ma znaczenie. Nawet drobna różnica w zapisie nazw może zostać potraktowana jako inna para.

### 3. Zamiana turnieju na serię pojedynków

Dla każdego pliku wejściowego system porównuje każdą parę z każdą inną parą z tego samego zestawu wyników.

Zasada jest następująca:

- niższa `Lokata` oznacza wygraną,
- wyższa `Lokata` oznacza porażkę,
- taka sama `Lokata` oznacza remis.

Przykład:

- para z miejsca `1` wygrywa z każdą parą z miejsc `2`, `3`, `4` itd.,
- para z miejsca `5` przegrywa z parami z miejsc `1` do `4`,
- dwie pary sklasyfikowane ex aequo dostają wynik `0.5` przeciwko sobie.

### 4. Obliczenie oczekiwanego wyniku

Dla każdej pary porównań liczony jest klasyczny składnik ELO:

```text
expected = 1 / (1 + 10 ^ ((ranking_b - ranking_a) / 400))
```

Im wyższy ranking przeciwnika, tym większy zysk za zwycięstwo i mniejsza strata za porażkę.

### 5. Aktualizacja ELO

Po zsumowaniu wszystkich wirtualnych pojedynków z danego pliku system aktualizuje ranking według wzoru:

```text
nowe_elo = stare_elo + suma(actual - expected) * efektywne_k
```

Domyślny współczynnik `K` wynosi `32`, ale w kodzie jest dodatkowo dzielony przez liczbę przeciwników w danym pliku:

```text
efektywne_k = K / (n - 1)
```

Dzięki temu łączna zmiana rankingu dla jednej kategorii nie rośnie liniowo wraz z liczbą uczestników.

### 6. Ranking końcowy

Po przetworzeniu wszystkich plików z katalogu `rsc/` pary są sortowane malejąco po `ELO`, a wynik trafia do pliku `ranking.txt` i jednocześnie jest wypisywany w konsoli.

## Przepływ programu

1. `main.py` przechodzi po katalogu `rsc/`.
2. Każdy plik przekazuje do `Processer.przetworz_turniej(...)`.
3. `Processer.py` odczytuje lokaty i mapuje wpisy na obiekty par.
4. `Kalkulator.py` przelicza zmianę rankingu dla wszystkich par z danego pliku.
5. Zaktualizowane ELO wraca do wspólnej bazy par.
6. Po przetworzeniu wszystkich plików tworzony jest `ranking.txt`.

## Moduły i ich odpowiedzialność

### `main.py`

Punkt wejścia aplikacji.

Odpowiada za:

- utworzenie wspólnej bazy par `baza_par`,
- przejście po wszystkich plikach w katalogu `rsc/`,
- wywołanie przetwarzania dla każdego pliku,
- zbudowanie końcowego rankingu,
- zapis wyniku do `ranking.txt`.

To tutaj ustawiony jest również domyślny współczynnik `K=32` przekazywany do przeliczeń.

### `Processer.py`

Warstwa importu danych turniejowych.

Odpowiada za:

- odczyt pliku CSV z separatorem `;`,
- pobranie lokaty i nazwy pary z każdego wiersza,
- rozdzielenie pola `Para` na dwóch tancerzy,
- utworzenie nowych obiektów `Para`, jeśli para jeszcze nie istnieje,
- zbudowanie listy danych wejściowych dla kalkulatora ELO,
- przepisanie nowo obliczonego ELO z powrotem do bazy.

To ten moduł decyduje, jak dane z pliku są zamieniane na obiekty domenowe używane przez silnik rankingu.

### `Kalkulator.py`

Silnik obliczeniowy rankingu.

Odpowiada za:

- obliczenie oczekiwanego wyniku pary względem innej pary,
- porównanie każdej pary z każdą inną parą w obrębie jednego pliku wyników,
- obsługę zwycięstw, porażek i remisów lokat,
- przeliczenie zmiany ELO na podstawie sumy wszystkich porównań.

To najważniejszy moduł z punktu widzenia logiki systemu.

### `Para.py`

Minimalny model danych reprezentujący parę taneczną.

Przechowuje:

- `tancerz1`,
- `tancerz2`,
- `elo`.

Moduł zawiera też pomocnicze metody do pobrania identyfikatora i tekstowej reprezentacji pary.

### `rsc/`

Katalog z danymi wejściowymi dla kalkulatora.

Znajdują się tu ręcznie przygotowane lub wyselekcjonowane pliki wyników, które są bezpośrednio przetwarzane przez `main.py`. Obecna implementacja zakłada, że to właśnie zawartość tego katalogu definiuje zakres liczonego rankingu.

### `ranking.txt`

Plik wyjściowy generowany po uruchomieniu programu. Zawiera końcową tabelę z miejscem, nazwą pary i obliczonym ELO.

## Katalog `web-scraper/`

W repozytorium znajduje się też osobna część pomocnicza do pobierania danych z archiwum wyników.

### `web-scraper/main.py`

Scraper oparty o Playwright, który pobiera dane z `https://archiwum-tp.cioff.pl`.

Odpowiada za:

- pobranie listy sezonów,
- pobranie listy turniejów dla danego roku,
- wejście na stronę turnieju,
- odczyt tabel wyników dla wszystkich kategorii,
- normalizację nazw kolumn,
- zapis całości do pliku CSV.

Wynikiem jest plik `web-scraper/wyniki_par.csv` o szerszej strukturze niż dane w `rsc/`.

### `web-scraper/diagnoza.py`

Narzędzie diagnostyczne do analizy struktury HTML strony z wynikami. Służy do sprawdzania selektorów i struktury DOM, gdy scraper wymaga poprawki.

### `web-scraper/wyniki_par.csv`

Przykładowy wynik działania scrapera. Zawiera pełniejsze dane niż kalkulator ELO potrzebuje bezpośrednio.

### `web-scraper/wyniki_par_struktura.json`

Plik pomocniczy z zapisanym stanem lub diagnozą struktury strony. Może być używany przy debugowaniu scrapera.

## Ważna uwaga o danych

Scraper i kalkulator nie są obecnie spięte w jeden automatyczny pipeline.

To znaczy:

- `web-scraper/main.py` zapisuje szeroki plik CSV z kolumnami typu `rok`, `turniej`, `kategoria`, `miejsce`, `para`,
- `main.py` oczekuje uproszczonych plików w katalogu `rsc/` z nagłówkami `Lokata;Para;Ośrodek;Instruktor`,
- przed użyciem danych ze scrapera w kalkulatorze potrzebne jest ich dopasowanie do formatu wejściowego silnika rankingu.

Dodatkowo scraper zapisuje pole `para` w formacie z separatorem `;`, natomiast `Processer.py` oczekuje zapisu:

```text
Nazwisko1 Imię1, Nazwisko2 Imię2
```

## Uruchomienie

### Obliczenie rankingu

```bash
python main.py
```

Po uruchomieniu:

- ranking pojawi się w konsoli,
- ten sam wynik zostanie zapisany do `ranking.txt`.

### Uruchomienie scrapera

Wymagane biblioteki:

```bash
pip install playwright pandas
playwright install chromium
```

Przykład użycia:

```bash
python web-scraper/main.py --year 2025 --output web-scraper/wyniki_par.csv
```

## Założenia i ograniczenia obecnej wersji

- ranking jest liczony sekwencyjnie w kolejności przetwarzania plików,
- każda para ma jedno globalne ELO, niezależnie od kategorii,
- system nie rozróżnia rangi turnieju ani jego ważności,
- brak dodatkowej walidacji literówek i wariantów nazw par,
- wynik zależy wyłącznie od lokat, bez uwzględniania punktów sędziowskich,
- dane wejściowe muszą być poprawnie przygotowane przed uruchomieniem programu.

## Podsumowanie

Projekt składa się z dwóch części:

- rdzenia obliczeniowego ELO (`main.py`, `Processer.py`, `Kalkulator.py`, `Para.py`),
- narzędzi do pozyskiwania i diagnozowania danych (`web-scraper/`).

Rdzeń liczy ranking na podstawie już przygotowanych plików w `rsc/`, a scraper pomaga zebrać dane źródłowe z archiwum wyników. Dzięki temu repozytorium pozwala zarówno budować dane wejściowe, jak i przeliczać z nich końcowy ranking par.
