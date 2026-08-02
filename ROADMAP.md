# Roadmap

## Done

- Kalkulator ELO dla wielu par.
- Ranking na oficjalnym formacie `data_new.xlsx`.
- Glowne `App.py` podpiete do `new_ranking_service.py`.
- GUI/CLI z filtrami sezonow, kategorii i klas.
- Wybor innego pliku XLSX w GUI oraz przez `--input-excel`.
- Zapis raportu rankingu do `txt/`.
- Eksport historii zmian punktow do CSV przez `new_progress_export.py`.
- Wykres historii ELO par przez `new_pair_progress_plot.py`.
- Identyfikacja par przez `pair id`.
- Podstawowe testy regresyjne nowego backendu.

## In Progress

- Ulepszenie ergonomii GUI.
- Konsultacje z Komisja ds. tancow polskich odnosnie kierunku rozwoju projektu.
- Porzadkowanie starej sciezki `rsc/` jako legacy.

## Planned

- Pelna integracja z systemem CIOFF.
- Stabilny import oficjalnych danych do SQLite lub innego docelowego magazynu.
- Rok pilotazowy w oficjalnych rozgrywkach TTP PS CIOFF.
- Szersze testy porownujace wyniki XLSX, CSV progress i ewentualny backend SQLite.
