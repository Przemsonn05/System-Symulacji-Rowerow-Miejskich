# Hipotezy z danych: H2, A, B, C (Osoba 1)

Wygenerowane przez `python -m src.metrics.hypotheses` na pełnych dniach z `processed/` (16 dni).
Wyniki są wstępne do czasu zamrożenia danych (`dane-final`, 1.12).

## H2. Puste stacje są skupione na niewielu stacjach

- Gini czasu pustek: **0.67** (95% przedział bootstrap po dniach z poprawką na obciążenie 0.65–0.70;
  bez jednego dnia 0.67–0.68; w pojedynczych dniach
  0.81 / 0.85 / 0.97 min / mediana / max – w jednym dniu
  więcej stacji nie jest pusta ani razu, więc Gini dnia jest wyższy niż Gini całego okresu).
- Czy co dzień te same stacje: średni Jaccard zbiorów „10% najczęściej pustych” między parami dni
  **0.16** (gdyby wybór był losowy: 0.05).
- **Wniosek:** potwierdzona – skupienie jest duże i stabilne, a często puste są w większości te same stacje.

### 10 stacji najczęściej pustych w porannym szczycie (dni robocze 7–10) – do obserwacji w terenie (Osoba 2)

| # | stacja | dzielnica | pusta średnio (7–10) | pusta w ciągu całej doby |
|---|---|---|---|---|
| 1 | Metro Centrum | Śródmieście | 71 min | 9% |
| 2 | Marymoncka - Dewajtis | Bielany | 50 min | 4% |
| 3 | Emilii Plater - al. Jerozolimskie | Śródmieście | 49 min | 8% |
| 4 | Żwirki i Wigury - Woronicza | Ochota | 43 min | 7% |
| 5 | Rembrandta – Miedza  | Targówek | 36 min | 3% |
| 6 | Plac Zawiszy | Ochota | 29 min | 4% |
| 7 | Żwirki i Wigury - Racławicka | Ochota | 28 min | 2% |
| 8 | Jana Olbrachta - Antka Rozpylacza | Wola | 28 min | 5% |
| 9 | Wolność - Bellottiego | Wola | 28 min | 8% |
| 10 | Emilii Plater - Złota | Śródmieście | 25 min | 6% |

Plik: `top10_puste_rano.csv` (z współrzędnymi).

## A. Darmowe 20 minut kształtuje długość jazdy

Czasy mają dokładność ±5 min (pomiary co 5 min, czas zawyżony średnio o ok. 5 min), więc liczymy przejazdy
w krokach 5 min. Proste gładkie rozkłady nie pasują do całego rozkładu (drugi garb ok. 50–60 min), dlatego
sprawdzamy lokalnie: czy przy progu (kroki 20→25 i 25→30 min) liczba przejazdów spada ostrzej, niż wynika
z trendu sąsiednich kroków (15→20, 30→35, 35→40, 40→45).

| czas [min] | przejazdy | następny krok / ten krok | oczekiwane z trendu |
|---|---|---|---|
| 5 | 3806 | 9.65 |  |
| 10 | 36713 | 0.96 |  |
| 15 | 35113 | 0.62 |  |
| 20 | 21820 | 0.48 | 0.63 |
| 25 | 10475 | 0.45 | 0.66 |
| 30 | 4664 | 0.65 |  |
| 35 | 3033 | 0.71 |  |
| 40 | 2145 | 0.79 |  |
| 45 | 1689 | 0.85 |  |
| 50 | 1433 | 0.82 |  |
| 55 | 1170 | 0.86 |  |
| 60 | 1011 | 0.64 |  |

- Przejazdów ≤ 20 min: 76%, ≤ 25 min: 85% (n = 127406, 17 dni).
- Przy progu liczba przejazdów maleje z kroku na krok średnio **0.72×** tego, co wynika z trendu
  (95% bootstrap po dniach 0.70–0.74; 1 = brak efektu, < 1 = ostrzejszy spadek).
- **Wniosek:** widoczne – tuż za granicą darmowego czasu przejazdów ubywa wyraźnie szybciej niż obok, czyli ludzie kończą jazdę przed 20. minutą.
  W symulacji czas jazdy nie może być losowany z gładkiego rozkładu.

## B. E-rowery to osobna grupa klientów

- Udział e-rowerów w przejazdach stacja→stacja: 20% (n = 24904).
- Dystans: mediana **1.97 km** e-rowerem vs 1.90 km zwykłym
  (Mann–Whitney, jednostronnie p = 6.8e-08); czas: 15 vs 15 min.
- Bateria: mediana na starcie 56%. Wypożyczeń z baterią < 20%: **10%**,
  a wśród e-rowerów stojących na stacjach rozładowanych jest 18% (test dwumianowy p = 1.1e-228).
- Dystans wg baterii (mediana km): [0, 20): 1.57, [20, 40): 1.95, [40, 60): 2.02, [60, 80): 2.05, [80, 101): 2.10;
  Spearman bateria–km ρ = 0.10 (p = 6.3e-52).
- **Wniosek:** potwierdzona – e-rowerem jeździ się dalej, a rozładowane rowery są omijane.

## C. Czy operator nadąża

- Okresy pustej stacji w dzień (6–22, znany koniec): 3314; zakończone dowozem ciężarówki:
  **7%**; wśród pustek ≥ 30 min: 11% (n = 1398).
- Gdy ciężarówka kończy pustkę, przyjeżdża po medianie **45 min** od opróżnienia.
- Czy jeździ do stacji najczęściej pustych: Spearman (udział pustek vs dowozy na dzień) ρ = 0.74
  (p = 8.3e-62); do 20% najczęściej pustych trafia 43% dowozów.
- **Wniosek:** operator nie nadąża – większość pustek kończą klienci, a nie ciężarówki.
  Uwaga: widzimy tylko przewozy ≥ 4 rowerów.

### Reguła operatora (dla strategii `operator_rule`, Osoba 3) → `processed/operator_rule.json`

- Dowóz, gdy cel ma zapełnienie: mediana 12% (kwartyle 0%–25%); do pustej stacji 26% dowozów.
- Zabranie, gdy start ma zapełnienie: mediana 217% (kwartyle 167%–270%).
- Rowerów na kurs: mediana 4 (kwartyle 4–6, max 13).
- Godziny pracy: dni robocze 0, 10, 11, 12, 13, 14, 19, 20, 21, 22, 23; wolne 1, 8, 9, 10, 11, 12, 13, 14, 15, 20, 21, 22.
- Kursów na dobę: dni robocze 66, wolne 80.
