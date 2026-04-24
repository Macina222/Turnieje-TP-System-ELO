# Turnieje TP System ELO - Kalkulator Rankingu

## Opis Projektu

Ten projekt to prototypowy kalkulator rankingu ELO/MMR (Matchmaking Rating) stworzony z myślą o Konkursach Tańców Polskich PS Cioff. Jego głównym celem jest dostarczenie użytkownikom (tancerzom, sędziom, organizatorom) narzędzia do przybliżonej oceny performance'u danej pary tanecznej w oparciu o wyniki konkursów. System ma na celu zwiększenie obiektywności i transparentności oceny, a także umożliwienie śledzenia postępów par w czasie.

## Jak działa system ELO/MMR?

System ELO/MMR to metoda rankingowa, która pierwotnie została stworzona do oceny umiejętności graczy w szachach, a następnie zaadaptowana do wielu innych dziedzin, w tym gier komputerowych i sportu. W kontekście Konkursów Tańców Polskich, działa on następująco:

1.  **Ranking początkowy:** Każda nowa para taneczna otrzymuje początkowy ranking ELO.
2.  **Mecze (konkursy):** Po każdym konkursie, w którym para bierze udział, jej ranking jest aktualizowany.
3.  **Zmiana rankingu:** Zmiana rankingu zależy od wyniku konkursu oraz od różnicy rankingów między rywalizującymi parami:
    *   Jeśli para wygrywa z parą o wyższym rankingu, zyskuje więcej punktów ELO.
    *   Jeśli para wygrywa z parą o niższym rankingu, zyskuje mniej punktów ELO.
    *   Analogicznie, przegrana z parą o niższym rankingu skutkuje większą utratą punktów, a przegrana z parą o wyższym rankingu – mniejszą.
4.  **Współczynnik K:** Kluczowym elementem jest współczynnik K, który określa maksymalną możliwą zmianę rankingu po pojedynczym "meczu". Wyższy współczynnik K oznacza szybsze zmiany rankingu, co jest często stosowane dla nowych par lub w początkowych fazach systemu.

Dzięki temu systemowi, ranking ELO/MMR ma za zadanie odzwierciedlać aktualne umiejętności i formę pary tanecznej, dostarczając dynamicznej i relatywnej oceny ich występu.