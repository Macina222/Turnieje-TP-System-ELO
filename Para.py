class Para:
    def __init__(self, tancerz1, tancerz2, elo = 350.0):
        self.tancerz1 = tancerz1
        self.tancerz2 = tancerz2
        self.elo = elo

    def pobierz_id(self):
        # Tuple (krotka) jest idealna jako unikalny identyfikator pary
        return self.tancerz1, self.tancerz2

    # Dodatkowa metoda __str__, aby ładnie wyświetlać informacje o obiekcie
    def __str__(self):
        return f"Para: {self.tancerz1} i {self.tancerz2} (Ranking: {self.elo})"
