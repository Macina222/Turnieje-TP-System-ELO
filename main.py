"""
Legacy punkt wejścia budujący jeden globalny ranking z całego `rsc/`.

Ten skrypt nie filtruje danych po latach ani kategoriach. Działa krok po kroku:
1. wczytuje parametry K i D z `config.txt`,
2. przechodzi po wszystkich plikach wynikowych w `rsc/`,
3. dla każdego pliku wywołuje `przetworz_turniej`,
4. sortuje wszystkie pary po końcowym ELO,
5. wypisuje tabelę rankingu w konsoli.

Jest to prostsza, historyczna ścieżka uruchomienia. Nowszy interfejs użytkownika
znajduje się w `App.py`, ale oba warianty korzystają z tego samego backendu.
"""

import os
from pathlib import Path

from ranking_service import (
    format_ranking_table,
    load_ranking_config,
    przetworz_turniej,
)


def main() -> None:
    """Uruchamia pełne przetwarzanie wszystkich plików wynikowych w repozytorium."""

    project_dir = Path(__file__).resolve().parent
    config = load_ranking_config(project_dir / "config.txt")

    baza_par = {}
    rsc_dir = project_dir / "rsc"

    for root, _dirs, files in os.walk(rsc_dir):
        for file in sorted(files):
            sciezka = Path(root) / file
            try:
                przetworz_turniej(sciezka, baza_par, config.k_factor, config.d_factor)
            except Exception as exc:
                print(f"Błąd podczas przetwarzania pliku {sciezka}: {exc}")

    ranking = sorted(baza_par.values(), key=lambda p: p.elo, reverse=True)
    report = format_ranking_table(ranking)
    print(report)


if __name__ == "__main__":
    main()
