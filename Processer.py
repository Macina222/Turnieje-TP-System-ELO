import csv
from pathlib import Path

import Para
import Kalkulator
from app_config import load_ranking_config


def przetworz_turniej(
    sciezka_do_pliku,
    baza_danych,
    wskaznik_k=None,
    wskaznik_d=None,
    config_path: str | Path | None = None,
):
    """
    Czyta wyniki turnieju, aktualizuje istniejące pary lub dodaje nowe,
    a następnie przelicza ELO.
    """
    if wskaznik_k is None or wskaznik_d is None:
        config = load_ranking_config(config_path)
        if wskaznik_k is None:
            wskaznik_k = config.k_factor
        if wskaznik_d is None:
            wskaznik_d = config.d_factor

    lista_do_kalkulatora = []

    # Wczytywanie pliku tekstowego / CSV
    with open(sciezka_do_pliku, 'r', encoding='utf-8') as plik:
        # Zakładamy że nagłówki to: Lokata;Para;Ośrodek;Instruktor
        czytnik = csv.DictReader(plik, delimiter=';')

        for wiersz in czytnik:
            lokata = int(wiersz['Lokata'])

            # Podział stringa "Nazwisko Imie, Nazwisko Imie"
            nazwiska = wiersz['Para'].split(', ')
            if len(nazwiska) != 2:
                continue  # Pomijamy błędy w formacie

            tancerz1, tancerz2 = nazwiska[0], nazwiska[1]
            id_pary = (tancerz1, tancerz2)

            # Jeśli pary nie ma w bazie, tworzymy nową z bazowym ELO
            if id_pary not in baza_danych:
                baza_danych[id_pary] = Para.Para(tancerz1, tancerz2)

            # Przygotowanie słownika zgodnie z wymaganiami funkcji obliczającej
            lista_do_kalkulatora.append({
                'id': id_pary,
                'elo': baza_danych[id_pary].elo,
                'place': lokata
            })

    # Obliczamy i aktualizujemy słowniki w liście
    Kalkulator.aktualizacja_rankingu(lista_do_kalkulatora, wskaznik_k, wskaznik_d)

    # Przepisujemy wyliczone nowe ELO z powrotem do naszych obiektów w bazie
    for wpis in lista_do_kalkulatora:
        baza_danych[wpis['id']].elo = wpis['elo']

    sorted(baza_danych.values(), key=lambda para: para.elo, reverse=True)
