# Hipotezy z danych: H2, A, B, C (Osoba 1)

Wygenerowane przez `python -m src.metrics.hypotheses` na pełnych dniach z `processed/` (23 dni).
Wyniki są wstępne do czasu zamrożenia danych (`dane-final`, 1.12).

## H2. Puste stacje są skupione na niewielu stacjach

- Gini czasu pustek: **0.67** (95% przedział bootstrap po dniach z poprawką na obciążenie 0.65–0.70;
  bez jednego dnia 0.67–0.68; w pojedynczych dniach
  0.81 / 0.89 / 0.97 min / mediana / max – w jednym dniu
  więcej stacji nie jest pusta ani razu, więc Gini dnia jest wyższy niż Gini całego okresu).
- Czy co dzień te same stacje: średni Jaccard zbiorów „10% najczęściej pustych” między parami dni
  **0.15** (gdyby wybór był losowy: 0.05).
- **Wniosek:** potwierdzona – skupienie jest duże i stabilne, a często puste są w większości te same stacje.

### 10 stacji najczęściej pustych w porannym szczycie (dni robocze 7–10) – do obserwacji w terenie (Osoba 2)

| # | stacja | dzielnica | pusta średnio (7–10) | pusta w ciągu całej doby |
|---|---|---|---|---|
| 1 | Metro Centrum | Śródmieście | 61 min | 7% |
| 2 | Marymoncka - Dewajtis | Bielany | 45 min | 3% |
| 3 | Emilii Plater - al. Jerozolimskie | Śródmieście | 37 min | 5% |
| 4 | Żwirki i Wigury - Woronicza | Ochota | 36 min | 6% |
| 5 | Rembrandta – Miedza  | Targówek | 27 min | 2% |
| 6 | al. Niepodległości - Batorego | Śródmieście | 27 min | 4% |
| 7 | Żwirki i Wigury - Racławicka | Ochota | 25 min | 3% |
| 8 | Wolność - Bellottiego | Wola | 24 min | 7% |
| 9 | Emilii Plater - Złota | Śródmieście | 24 min | 4% |
| 10 | Plac Zawiszy | Ochota | 22 min | 3% |

Plik: `top10_puste_rano.csv` (z współrzędnymi).

## A. Darmowe 20 minut kształtuje długość jazdy

Czasy mają dokładność ±5 min (pomiary co 5 min, czas zawyżony średnio o ok. 5 min), więc liczymy przejazdy
w krokach 5 min. Proste gładkie rozkłady nie pasują do całego rozkładu (drugi garb ok. 50–60 min), dlatego
sprawdzamy lokalnie: czy przy progu (kroki 20→25 i 25→30 min) liczba przejazdów spada ostrzej, niż wynika
z trendu sąsiednich kroków (15→20, 30→35, 35→40, 40→45).

| czas [min] | przejazdy | następny krok / ten krok | oczekiwane z trendu |
|---|---|---|---|
| 5 | 5190 | 9.20 |  |
| 10 | 47723 | 0.95 |  |
| 15 | 45498 | 0.62 |  |
| 20 | 28027 | 0.48 | 0.63 |
| 25 | 13348 | 0.44 | 0.66 |
| 30 | 5841 | 0.66 |  |
| 35 | 3829 | 0.70 |  |
| 40 | 2698 | 0.79 |  |
| 45 | 2127 | 0.85 |  |
| 50 | 1800 | 0.85 |  |
| 55 | 1529 | 0.84 |  |
| 60 | 1286 | 0.65 |  |

- Przejazdów ≤ 20 min: 77%, ≤ 25 min: 85% (n = 164632, 25 dni).
- Przy progu liczba przejazdów maleje z kroku na krok średnio **0.71×** tego, co wynika z trendu
  (95% bootstrap po dniach 0.69–0.73; 1 = brak efektu, < 1 = ostrzejszy spadek).
- **Wniosek:** widoczne – tuż za granicą darmowego czasu przejazdów ubywa wyraźnie szybciej niż obok, czyli ludzie kończą jazdę przed 20. minutą.
  W symulacji czas jazdy nie może być losowany z gładkiego rozkładu.

## B. E-rowery to osobna grupa klientów

- Udział e-rowerów w przejazdach stacja→stacja: 20% (n = 33091).
- Dystans: mediana **1.97 km** e-rowerem vs 1.89 km zwykłym
  (Mann–Whitney, jednostronnie p = 5.3e-14); czas: 15 vs 15 min.
- Bateria: mediana na starcie 57%. Wypożyczeń z baterią < 20%: **9%**,
  a wśród e-rowerów stojących na stacjach rozładowanych jest 16% (test dwumianowy p = 1.9e-224).
- Dystans wg baterii (mediana km): [0, 20): 1.59, [20, 40): 1.93, [40, 60): 2.00, [60, 80): 2.06, [80, 101): 2.08;
  Spearman bateria–km ρ = 0.09 (p = 2e-61).
- **Wniosek:** potwierdzona – e-rowerem jeździ się dalej, a rozładowane rowery są omijane.

## C. Czy operator nadąża

- Okresy pustej stacji w dzień (6–22, znany koniec): 3790; zakończone dowozem ciężarówki:
  **8%**; wśród pustek ≥ 30 min: 12% (n = 1653).
- Gdy ciężarówka kończy pustkę, przyjeżdża po medianie **45 min** od opróżnienia.
- Czy jeździ do stacji najczęściej pustych: Spearman (udział pustek vs dowozy na dzień) ρ = 0.76
  (p = 5.4e-65); do 20% najczęściej pustych trafia 44% dowozów.
- **Wniosek:** operator nie nadąża – większość pustek kończą klienci, a nie ciężarówki.
  Uwaga: widzimy tylko przewozy ≥ 4 rowerów.

### Reguła operatora (dla strategii `operator_rule`, Osoba 3) → `processed/operator_rule.json`

- Dowóz, gdy cel ma zapełnienie: mediana 14% (kwartyle 6%–30%); do pustej stacji 24% dowozów.
- Zabranie, gdy start ma zapełnienie: mediana 210% (kwartyle 164%–260%).
- Rowerów na kurs: mediana 4 (kwartyle 4–6, max 13).
- Godziny pracy: dni robocze 0, 9, 10, 11, 12, 13, 14, 19, 20, 21, 22, 23; wolne 1, 8, 9, 10, 11, 12, 13, 14, 15, 16, 20, 21, 22, 23.
- Kursów na dobę: dni robocze 62, wolne 70.
