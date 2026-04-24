import os
from pathlib import Path

from app_config import load_ranking_config
from Processer import przetworz_turniej

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

# Zapisywanie rankingu do pliku i wyświetlanie w konsoli
with open(project_dir / 'ranking.txt', 'w', encoding='utf-8') as f:
    header = f"{'Miejsce':<8} | {'Para':<50} | {'ELO':<10}"
    separator = "-" * 75
    
    print(header)
    print(separator)
    f.write(header + '\n')
    f.write(separator + '\n')
    
    for i, para in enumerate(ranking, 1):
        nazwa_pary = f"{para.tancerz1}, {para.tancerz2}"
        line = f"{i:<8} | {nazwa_pary:<50} | {para.elo:<10.2f}"
        print(line)
        f.write(line + '\n')