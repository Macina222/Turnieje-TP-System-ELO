def oblicz_oczekiwane_elo(ranking_a, ranking_b, wskaznik_d):
    return 1 / (1 + 10 ** ((ranking_b - ranking_a) / wskaznik_d))


def aktualizacja_rankingu(lista_par, wskaznik_k, wskaznik_d):
    if wskaznik_d == 0:
        raise ValueError("Wskaznik D nie moze byc rowny 0.")

    n = len(lista_par)
    if n < 2:
        return

    zmiany = [0] * n
    for i in range(n):
        for j in range(n):
            if i == j:
                continue

            expected = oblicz_oczekiwane_elo(
                lista_par[i]['elo'],
                lista_par[j]['elo'],
                wskaznik_d,
            )
            place_i = lista_par[i]['place']
            place_j = lista_par[j]['place']

            if place_i < place_j:
                actual = 1.0
            elif place_i > place_j:
                actual = 0.0
            else:
                actual = 0.5

            zmiany[i] += (actual - expected)

    efektywne_k = wskaznik_k / (n-1)
    for i in range(n):
        lista_par[i]['elo'] += zmiany[i] * efektywne_k
