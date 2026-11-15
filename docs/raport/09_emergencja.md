# 9. Emergencja

*Osoba 1 (miary, dane) i Osoba 3 (eksperymenty). Wersja robocza: część „dane” na 23 pełnych dobach (23.10–15.11.2026), część „model” na jednym przebiegu (`operator_2`, ziarno 1000, 5.11). Pełne wyniki: [`emergencja.md`](../wyniki/emergencja.md), [`emergence.json`](../wyniki/emergence.json), wykres [`emergencja.png`](../wyniki/emergencja.png). Do uzupełnienia przez Osobę 3: emergencja wg strategii, przejście fazowe, efekt stadny (sekcja 9.5).*

## 9.1. Co mierzymy

Emergencja to zjawiska, których nikt nie zaprogramował, a które powstają z zachowania wielu agentów naraz. W systemie rowerowym najważniejsze jest **pustoszenie stacji jedna po drugiej**: klient przy pustej stacji idzie do sąsiedniej i ją też opróżnia.

Miary są w [`src/metrics/emergence.py`](../../src/metrics/emergence.py) i działają **bez zmian** na danych (`processed/`) i na wyniku symulacji (katalog przebiegu). Obie strony liczymy z tabel stanu co 5 min (`observed_timeseries` / `station_timeseries`), a nie z dokładnych czasów zdarzeń symulacji – inaczej model „widziałby” krótkie pustki, których dane nie widzą.

| Miara | Definicja |
|---|---|
| Rytm dnia | przejazdy w każdej godzinie, dni robocze i wolne osobno |
| Skupienie pustek | krzywa Lorenza i Gini udziału czasu pustej stacji; udział 10% i 20% najczęściej pustych |
| Długość pustek | rozkład długości okresów pustej stacji (mediana, p90) |
| Skupiska w przestrzeni | indeks Morana *I* udziału pustek; sąsiedzi ≤ 1 km, wagi standaryzowane wierszami, p z 999 permutacji |
| Fale pustek | chwila pustoszenia stacji ma „następcę”, jeśli w ciągu 20 min pustoszeje stacja ≤ 800 m od niej; fala = spójny ciąg takich zdarzeń |
| Bilans dzielnic | przyjazdy − wyjazdy w dzielnicy rano (7–10) i po południu (16–19), dzień roboczy |

## 9.2. Czy fale to nie przypadek (modele zerowe)

Rano stacje na osiedlach pustoszeją razem z powodu szczytu, a nie z powodu siebie nawzajem. Całkiem losowe wymieszanie czasów dałoby więc zawsze „istotne” fale. Dlatego używamy dwóch uczciwych modeli zerowych (po 1000 losowań):

- **inny dzień** – każda stacja dostaje swoje chwile pustoszenia z losowego **innego dnia tego samego typu**. Zachowuje porę dnia i częstość pustek stacji, zrywa powiązanie z sąsiadami w danym dniu.
- **zamiana miejsc** – stacje o podobnym udziale pustek (ten sam decyl) zamieniają się położeniem. Zachowuje czasy, zrywa geografię.

p = (1 + liczba losowań ≥ dane) / (1 + liczba losowań).

## 9.3. Wyniki: dane

| Miara | Wartość |
|---|---|
| Gini pustek | **0,67**; 10% stacji = 44% czasu pustek; 24% stacji nigdy pustych |
| Długość pustki | mediana 25 min, p90 95 min |
| Moran *I* (udział pustek) | **0,61** (p = 0,001); w porannym szczycie 0,20 (p = 0,001) |
| Chwile pustoszenia | 182 na dzień |
| W fali (z sąsiadem) | **47,7%** |
| Fale ≥ 3 stacji | 10,3 na dzień; największa: 42 stacje |

| Model zerowy | Statystyka | Dane | Średnia modelu | × | p |
|---|---|---|---|---|---|
| inny dzień | udział w fali | 0,477 | 0,425 | **1,12** | **0,001** |
| inny dzień | średnia wielkość fali (≥ 2) | 3,56 | 3,09 | **1,15** | **0,001** |
| inny dzień | liczba fal ≥ 3 | 235 | 219 | 1,07 | 0,14 |
| zamiana miejsc | udział w fali | 0,477 | 0,446 | **1,07** | **0,001** |
| zamiana miejsc | liczba fal ≥ 3 | 235 | 211 | **1,11** | **0,029** |
| zamiana miejsc | średnia wielkość fali (≥ 2) | 3,56 | 3,50 | 1,02 | 0,34 |

**Wniosek.** Pustki są skupione na niewielu stacjach, leżą obok siebie i rozchodzą się falami. Fale są **większe i częstsze**, niż wynikałoby z samej pory dnia (model „inny dzień”) i z samej częstości pustek stacji (model „zamiana miejsc”). Efekt jest umiarkowany (o 7–15% ponad model zerowy), ale stabilny: na 16 dniach p wynosiło 0,015, na 23 dniach 0,001. To emergencja widoczna w prawdziwych danych.

## 9.4. Dane vs model

| Miara | Dane | Model (`operator_2`, 5.11) | Odtworzony? |
|---|---|---|---|
| Przejazdy / dzień roboczy | 8 637 | 8 593 | tak |
| Godzina szczytu | 16 | 16 | tak |
| Gini pustek | 0,67 | 0,81 | nie – za mocne skupienie |
| Nigdy pusta | 24% | 68% | nie |
| Pustka: mediana / p90 | 25 / 95 min | 25 / 93 min | tak |
| Moran *I* | 0,61 | 0,23 | nie – za słabe skupiska |
| Chwile pustoszenia / dzień | 182 | 484 | nie – za dużo |
| W fali | 48% | 62% | częściowo |
| Fale vs zamiana miejsc | 1,07× (p = 0,001) | 1,06× (p = 0,10) | nie |

Obecny silnik (bez agentów) odtwarza rytm dnia i długość pustek, ale pustoszeje za często, na zbyt wielu stacjach naraz i bez wzoru przestrzennego: jego fale nie różnią się od losowych. Oczekujemy, że poprawią to agenci-klienci (czekanie, wybór sąsiedniej stacji, aplikacja) i kalibracja na wielu metrykach naraz. Model ma jeden dzień, więc test „inny dzień” jest dla niego niedostępny – do porównania końcowego potrzebne są przebiegi z pełnymi tabelami na całym tygodniu walidacyjnym ([kontrakty, sekcja 3](../kontrakty.md)).

## 9.5. Emergencja w eksperymentach (Osoba 3)

> Do uzupełnienia po 3.12 (zamrożenie `sim_params.json`):
> - fale pustek i Moran wg strategii relokacji (`none`, `operator`, `threshold`, nowe strategie agentowe),
> - przejście fazowe: udział pustych stacji i wielkość fal w funkcji liczby rowerów,
> - efekt stadny: fale przy 0% i 80% klientów z aplikacją (opóźnienie 0 / 5 / 10 min),
> - zasięg „ciśnienia” stacji a wielkość fal.

## 9.6. Jak odtworzyć

```powershell
python -m src.metrics processed --sim <katalog przebiegu> --perm 1000 --out docs/wyniki
```

W Pythonie: `from src.metrics import emergence_report, compare` → `emergence_report("processed")`, `compare(raport_dane, raport_model)`. Testy na małych, ręcznie ułożonych przykładach: [`tests/test_metrics.py`](../../tests/test_metrics.py).
