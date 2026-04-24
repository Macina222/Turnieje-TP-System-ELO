class Para:
    def __init__(self, tancerz1, tancerz2, ranking=1200):
        if tancerz1.sex == tancerz2.sex:
            raise ValueError("Para musi składać się z osób różnej płci.")
        
        # Rozpoznawanie tancerza i tancerki (opcjonalne, ułatwia czytelność)
        if tancerz1.sex.upper() in ['M', 'MĘŻCZYZNA', 'MALE']:
            self.tancerz = tancerz1
            self.tancerka = tancerz2
        else:
            self.tancerz = tancerz2
            self.tancerka = tancerz1
            
        self.ranking = ranking
        self.name = f"{self.tancerka.name} & {self.tancerz.name}"

    @property
    def _klucz_porownania(self):
        # Zwraca posortowaną krotkę numerów książeczek do celów porównawczych
        return tuple(sorted([int(self.tancerz.nr_ksiazeczki), int(self.tancerka.nr_ksiazeczki)]))

    def __lt__(self, other):
        if not isinstance(other, Para):
            return NotImplemented
        return self._klucz_porownania < other._klucz_porownania

    def __eq__(self, other):
        if not isinstance(other, Para):
            return False
        return self._klucz_porownania == other._klucz_porownania

    def __repr__(self):
        return f"Para({self.name}, ranking={self.ranking})"
