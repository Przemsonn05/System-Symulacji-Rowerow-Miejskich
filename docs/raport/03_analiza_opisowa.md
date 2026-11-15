# 3. Analiza opisowa

*Osoba 1. Wersja robocza na 23 pełnych dobach (23.10–15.11.2026). Wykresy: [`analiza_opisowa.ipynb`](../../notebooks/analiza_opisowa.ipynb), [`puste_i_przepelnione_stacje.ipynb`](../../notebooks/puste_i_przepelnione_stacje.ipynb), [`emergencja.png`](../wyniki/emergencja.png). Szczegóły hipotez: [`hipotezy_osoba1.md`](../wyniki/hipotezy_osoba1.md). Liczby do przeliczenia na `dane-final`.*

## 3.1. Ile się jeździ

| Typ dnia | dni | przejazdy / dzień (średnio) |
|---|---|---|
| roboczy | 15 | ok. 8 640 |
| sobota | 4 | ok. 6 830 |
| niedziela, święto | 4 | ok. 5 970 |

W pierwszych dwóch tygodniach (do 8.11) dzień roboczy miał ok. 9 700 przejazdów; spadek w drugiej połowie listopada zbiega się z ochłodzeniem (7–10.11 mróz do −4 °C, 10.11 deszcz 9 mm). Rozdzielenie wpływu pogody i pory roku to hipoteza H1 (Osoba 2).

**Rytm dnia (dni robocze).** Dwa szczyty: poranny o 8:00 (ok. 550 przejazdów/h) i popołudniowy o 16:00 (ok. 810/h); popołudniowy jest wyższy, bo łączy powroty z pracy i jazdy rekreacyjne. W dni wolne jeden szeroki szczyt 12:00–15:00 (ok. 550/h) i więcej jazd nocnych (0:00–2:00).

**Jak długo i jak daleko.** Typowy przejazd stacja→stacja trwa 15 min (mediana; czas zawyżony średnio o ok. 5 min przez krok pomiaru) i ma 1,9 km po drogach rowerowych. 77% przejazdów mieści się w darmowych 20 minutach.

## 3.2. Flota i operator

- W obiegu jest ok. **3 480 rowerów** na stacjach (mediana), wobec 4 566 deklarowanych przez operatora. Różnica to rowery w drodze, poza stacjami i w serwisie.
- Operator robi ok. **62 przewozy w dzień roboczy i 70 w wolny**, zwykle po 4 rowery (widzimy tylko przewozy ≥ 4 rowerów). Pracuje głównie w nocy (19:00–1:00) i przed południem (9:00–14:00), a nie w szczycie popołudniowym.
- Rowery zostawiane poza stacjami: ok. 5% przejazdów kończy się lub zaczyna poza stacją.

## 3.3. E-rowery (hipoteza B)

E-rowery to ok. 8% floty, ale **20% przejazdów** stacja→stacja. Jeździ się nimi trochę dalej (mediana 1,97 vs 1,89 km, p < 10⁻¹³), w tym samym czasie. Klienci omijają rozładowane: wypożyczeń z baterią < 20% jest 9%, choć takich e-rowerów na stacjach jest 16% (p ≈ 10⁻²²⁴). Im więcej baterii, tym dłuższa jazda (Spearman ρ = 0,09). **Wniosek:** e-rowerzyści to osobny typ klienta, wybór roweru zależy od baterii.

## 3.4. Darmowe 20 minut (hipoteza A)

Czasy znamy co 5 min, dlatego porównujemy kroki 5-minutowe, a nie minuty. Tuż za progiem (kroki 20→25 i 25→30 min) liczba przejazdów spada **0,71×** tego, co wynika z trendu sąsiednich kroków (95% bootstrap po dniach 0,69–0,73). Ludzie kończą jazdę przed 20. minutą. **Wniosek dla modelu:** czasu jazdy nie można losować z gładkiego rozkładu (log-normalnego); potrzebne jest „ucięcie” na progu.

## 3.5. Puste stacje (hipoteza H2)

- **Skupienie.** Gini czasu pustek **0,67** (95% CI 0,65–0,70): 10% stacji odpowiada za 44% czasu pustek, 20% stacji za 68%; 24% stacji nie było puste ani razu.
- **Stabilność.** Zbiory „10% najczęściej pustych” z różnych dni pokrywają się 3× częściej niż losowo (Jaccard 0,15 vs 0,05): co dzień puste są w dużej części te same stacje.
- **Gdzie.** Najczęściej puste rano (dni robocze 7–10): Metro Centrum (średnio 61 min w szczycie), Marymoncka – Dewajtis, Emilii Plater – al. Jerozolimskie, Żwirki i Wigury – Woronicza ([pełna lista 10 stacji](../wyniki/top10_puste_rano.csv)).
- **Jak długo.** Mediana okresu pustki 25 min, 10% pustek trwa ponad 95 min.

## 3.6. Czy operator nadąża (hipoteza C)

Operator jeździ we właściwe miejsca: liczba dowozów na stację silnie zależy od tego, jak często stacja jest pusta (Spearman ρ = 0,76), a do 20% najczęściej pustych stacji trafia 44% dowozów. Ale **kończy tylko 8% pustek w dzień** (12% pustek ≥ 30 min), średnio po 45 min (mediana) od opróżnienia. Większość pustek kończą klienci, którzy oddają rowery. Jest więc miejsce na lepszą strategię (H3).

## 3.7. „Oddychanie miasta” (bilans dzielnic)

W dzień roboczy rano (7–10) rowery odpływają z dzielnic mieszkalnych (Mokotów −25, Praga-Południe −18, Ursynów −14, Bielany −10 rowerów na dzień) i spływają do Śródmieścia (+9) i na Ochotę (+5). Po południu (16–19) kierunek się odwraca (Praga-Południe +33, Mokotów +14, Bielany +13). Wyjątkiem jest Wola, która traci rowery i rano, i po południu – operator musi je tam dowozić.

## 3.8. Czy danych jest dość

Na dni robocze tak (15 dni). Na weekendy na granicy (4 soboty, 4 niedziele i święta). Na pogodę lepiej niż w pierwszej wersji: są dni z mrozem (do −4 °C) i z deszczem, ale tylko listopadowe (−4…14 °C). Zbieramy do końca sezonu (30.11): ok. 35 pełnych dni, w tym 5 weekendów i 2 święta.
