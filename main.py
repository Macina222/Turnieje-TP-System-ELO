import os
from Processer import przetworz_turniej

baza_par = {}
rsc_dir = 'rsc'

# Przetwarzanie wszystkich plików w folderze rsc
for root, dirs, files in os.walk(rsc_dir):
    for file in sorted(files):  # Sortowanie plików, aby zapewnić powtarzalność kolejności przetwarzania
        sciezka = os.path.join(root, file)
        try:
            przetworz_turniej(sciezka, baza_par, 32)
        except Exception as e:
            print(f"Błąd podczas przetwarzania pliku {sciezka}: {e}")

# Tworzenie rankingu
ranking = sorted(baza_par.values(), key=lambda p: p.elo, reverse=True)

# Zapisywanie rankingu do pliku i wyświetlanie w konsoli
with open('ranking.txt', 'w', encoding='utf-8') as f:
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