import pandas as pd
from pathlib import Path
import sys
import os

# Dodajemy katalog nadrzędny do ścieżki, żeby móc zaimportować legacy
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from legacy.ranking_service import (
    load_ranking_config,
    aktualizacja_rankingu,
    extract_base_and_class,
    get_default_elo_for_class,
    format_class_for_display
)

def run_new_ranking(file_path: str = "data_new.xlsx", output_dir: str = "txt"):
    print("Wczytywanie konfiguracji...")
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.txt")
    config = load_ranking_config(config_path)
    
    print(f"Wczytywanie danych z {file_path}...")
    # Czytamy plik z pominięciem 3 pierwszych wierszy (indeks 0, 1, 2)
    df = pd.read_excel(file_path, header=3)
    
    # Odwracamy kolejność, żeby przetwarzać najstarsze turnieje jako pierwsze
    df = df.iloc[::-1].reset_index(drop=True)
    
    # Słownik do trzymania punktów ELO dla danej pary i kategorii bazowej
    # Klucz: (pair_id, base_category) -> elo (float)
    elos = {}
    
    # Słowniki pomocnicze do zapamiętywania nazwisk i klas par
    pair_names = {}
    pair_classes = {} # Klucz: (pair_id, base_category) -> class (str)
    
    # Grupujemy po sezonie i turnieju (z zachowaniem oryginalnej kolejności dzięki sort=False)
    groups = df.groupby(['season', 'turnament code', 'cat code'], sort=False)
    
    print("Przetwarzanie turniejów...")
    for (season, t_code, cat_code), group in groups:
        base_cat, klasa = extract_base_and_class(str(cat_code))
        if not base_cat:
            continue
            
        lista_do_kalkulatora = []
        for _, row in group.iterrows():
            if pd.isna(row['pair id']):
                continue
                
            try:
                # Pair id z excela może być floatem (np. 911.0)
                pair_id = str(int(float(row['pair id'])))
            except ValueError:
                pair_id = str(row['pair id'])
                
            rank = int(row['rank'])
            pair_name = str(row['pair']).strip()
            pair_names[pair_id] = pair_name
            
            key = (pair_id, base_cat)
            
            if key not in elos:
                # Inicjujemy ELO dla nowej klasy/kategorii zgodnie z poleceniem
                elos[key] = get_default_elo_for_class(klasa, config.class_default_elos)
                pair_classes[key] = klasa
                
            lista_do_kalkulatora.append({
                "id": pair_id,
                "elo": elos[key],
                "place": rank
            })
            
        if len(lista_do_kalkulatora) > 1:
            # Aktualizujemy ELO dla par w danym turnieju
            aktualizacja_rankingu(lista_do_kalkulatora, config.k_factor, config.d_factor)
            
            # Zapisujemy wyliczone punkty z powrotem do głównego słownika
            for wpis in lista_do_kalkulatora:
                pid = wpis["id"]
                elos[(pid, base_cat)] = float(wpis["elo"])
                
    # Zapis wyników
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    
    categories = set(key[1] for key in elos.keys())
    
    print("Zapisywanie raportów...")
    for base_cat in sorted(categories):
        cat_pairs = []
        for (pid, c), elo in elos.items():
            if c == base_cat:
                cat_pairs.append({
                    "name": pair_names[pid],
                    "elo": elo,
                    "klasa": pair_classes[(pid, c)]
                })
                
        # Sortujemy malejąco po punktach ELO
        cat_pairs.sort(key=lambda x: x["elo"], reverse=True)
        
        header = f"{'Miejsce':<8} | {'Para':<50} | {'ELO':<10} | Klasa"
        separator = "-" * 82
        lines = [
            f"Kategoria bazowa: {base_cat}",
            f"Raport wygenerowany z: {file_path}",
            "",
            header, 
            separator
        ]
        
        for place, p in enumerate(cat_pairs, start=1):
            klasa_display = format_class_for_display(p["klasa"])
            lines.append(f"{place:<8} | {p['name']:<50} | {p['elo']:<10.2f} | {klasa_display}")
            
        report_text = "\n".join(lines)
        out_file = out_path / f"ranking_new_{base_cat.lower()}.txt"
        out_file.write_text(report_text, encoding="utf-8")
        print(f"Utworzono: {out_file}")

if __name__ == "__main__":
    run_new_ranking()
