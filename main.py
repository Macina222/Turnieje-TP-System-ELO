import os
from pathlib import Path

from ranking_service import (
    format_ranking_table,
    load_ranking_config,
    przetworz_turniej,
)

project_dir = Path(__file__).resolve().parent
config = load_ranking_config(project_dir / 'config.txt')

baza_par = {}
rsc_dir = project_dir / 'rsc'

# Przetwarzanie wszystkich plików w folderze rsc
for root, dirs, files in os.walk(rsc_dir):
    for file in sorted(files):  # Sortowanie plików, aby zapewnić powtarzalność kolejności przetwarzania
        sciezka = Path(root) / file
        try:
            przetworz_turniej(sciezka, baza_par, config.k_factor, config.d_factor)
        except Exception as e:
            print(f"Błąd podczas przetwarzania pliku {sciezka}: {e}")

# Tworzenie rankingu
ranking = sorted(baza_par.values(), key=lambda p: p.elo, reverse=True)
report = format_ranking_table(ranking)

# Wyświetlanie rankingu w konsoli
print(report)
