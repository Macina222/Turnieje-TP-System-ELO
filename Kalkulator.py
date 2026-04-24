def oblicz_oczekiwane_elo(rating_a, rating_b):
    return 1 / (1 + 10 ** ((rating_b - rating_a) / 400))

def aktualizacja_rankingu(lista_par, wskaznik_k):
    """
    lista_par: lista słowników w formacie [{'couple': obiekt_Para, 'place': int}]
    """
    n = len(lista_par)
    if n < 2:
        return

    zmiany = [0] * n

    for i in range(n):
        for j in range(n):
            if i == j:
                continue

            expected = oblicz_oczekiwane_elo(lista_par[i]['couple'].rating, lista_par[j]['couple'].rating)

            place_i = lista_par[i]['place']
            place_j = lista_par[j]['place']

            # Logika punktacji: mniejsze miejsce = wygrana
            if place_i < place_j:
                actual = 1.0  # Para 'i' wygrała
            elif place_i > place_j:
                actual = 0.0  # Para 'i' przegrała
            else:
                actual = 0.5  # Remis (zajęli to samo miejsce)

            zmiany[i] += (actual - expected)

    efektywne_k = wskaznik_k / (n-1)
    for i in range(n):
        lista_par[i]['couple'].rating += zmiany[i] * efektywne_k