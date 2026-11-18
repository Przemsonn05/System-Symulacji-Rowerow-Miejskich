# Emergencja: pomiar zjawisk, których nikt nie zaprogramował

Wygenerowane przez `python -m src.metrics`. Wszystkie metryki liczone z tabel stanów co 5 min (dane: `observed_timeseries`, symulacja: `station_timeseries`), tylko pełne dni.

| metryka | dane | symulacja |
|---|---|---|
| dni | 26 | 1 |
| przejazdy / dzień roboczy | 8330 | 7367 |
| godzina szczytu | 16 | 16 |
| Gini pustek | 0.669 | 0.837 |
| 10% stacji = udział pustek | 0.438 | 0.666 |
| nigdy pusta | 0.239 | 0.717 |
| pustka: mediana [min] | 25 | 30 |
| pustka: p90 [min] | 95 | 122 |
| Moran I (pustki) | 0.597 | 0.0392 |
| Moran p | 0.001 | 0.171 |
| chwile pustoszenia / dzień | 176 | 340 |
| w fali (z sąsiadem) | 0.468 | 0.359 |
| fale ≥ 3 stacje / dzień | 10 | 13 |
| największa fala | 42 | 11 |
| fale vs inny dzień (×) | 1.14 | nan |
| p (inny dzień) | 0.000999 | nan |
| fale vs zamiana miejsc (×) | 1.1 | 1.02 |
| p (zamiana miejsc) | 0.002 | 0.439 |

## Jak czytać

- **Gini pustek / 10% stacji**: skupienie czasu pustek na niewielu stacjach (H2).
- **Moran I**: czy stacje często puste leżą obok siebie (sąsiad ≤ 1 km, wagi standaryzowane wierszami; 0 = brak wzoru, > 0 = skupiska). p z 999 permutacji.
- **Fale pustek**: stacja pustoszeje, a w ciągu 20 min pustoszeje stacja do 800 m od niej; fala = spójny ciąg takich zdarzeń. „W fali” = udział chwil pustoszenia, które mają sąsiada w fali.
- **Modele zerowe** (czy fale to nie przypadek): *inny dzień* – dla każdej stacji jej chwile pustoszenia z losowego innego dnia tego samego typu (zachowuje porę dnia i częstość pustek, zrywa powiązanie z sąsiadami tego dnia); *zamiana miejsc* – stacje o podobnym udziale pustek (decyle) zamieniają się położeniem. „×” = dane / średnia modelu zerowego, p = (1 + liczba prób ≥ dane) / (1 + liczba prób).

## Testy fal: dane

| model zerowy | statystyka | dane | średnia modelu | 95% modelu | × | p |
|---|---|---|---|---|---|---|
| inny_dzien | linked_share | 0.471 | 0.413 | 0.433 | 1.14 | 0.001 |
| inny_dzien | n_cascades_ge3 | 258 | 235 | 261 | 1.10 | 0.075 |
| inny_dzien | mean_size_ge2 | 3.47 | 2.99 | 3.13 | 1.16 | 0.001 |
| zamiana_miejsc | linked_share | 0.471 | 0.429 | 0.446 | 1.10 | 0.002 |
| zamiana_miejsc | n_cascades_ge3 | 258 | 225 | 244 | 1.15 | 0.002 |
| zamiana_miejsc | mean_size_ge2 | 3.47 | 3.37 | 3.59 | 1.03 | 0.205 |

## Testy fal: symulacja

| model zerowy | statystyka | dane | średnia modelu | 95% modelu | × | p |
|---|---|---|---|---|---|---|
| inny_dzien | – | brak (za mało dni tego samego typu) | | | | |
| zamiana_miejsc | linked_share | 0.36 | 0.353 | 0.401 | 1.02 | 0.439 |
| zamiana_miejsc | n_cascades_ge3 | 13 | 13.5 | 18 | 0.96 | 0.625 |
| zamiana_miejsc | mean_size_ge2 | 2.71 | 2.69 | 3.1 | 1.01 | 0.418 |

![dane vs symulacja](emergencja.png)
