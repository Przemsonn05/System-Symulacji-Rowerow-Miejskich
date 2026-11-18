# Kontrakty między częściami projektu

**Termin uzgodnienia: 13.11.** Wersja robocza przygotowana przez Osobę 1 – sekcje 2 i 3 są propozycją do akceptacji przez Osobę 3, sekcja 1 do uzupełnienia przez Osoby 2 i 3. Po uzgodnieniu zmiana kontraktu = wpis w historii na dole i informacja dla całego zespołu.

Bez tych ustaleń 19.11 każdy będzie miał swoją część, ale nic nie będzie się łączyć.

---

## 1. Jak silnik wywołuje agenta-klienta (Osoba 2 + Osoba 3)

> Do uzupełnienia przez Osoby 2 i 3. Minimum, które musi być ustalone:

- obiekt klienta: pola (`user_type`, `has_app`, stacja startu, cel, cierpliwość / maksymalny czas czekania, maksymalne dojście),
- kiedy silnik pyta agenta o decyzję (przyjście na pustą stację, pełna stacja przy zwrocie, sygnał z aplikacji),
- co agent zwraca (czekaj *n* min / idź do stacji *X* / zrezygnuj),
- jak agent widzi stan stacji (opóźnienie aplikacji – parametr z zadania 1c, domyślnie 0 / 5 / 10 min),
- skąd parametry: `processed/model/sim_params.json` (Osoba 2), typy klientów z `processed/trip_features.parquet` i `commute_pairs.parquet` (Osoba 1).

---

## 2. Schemat `events.parquet` (Osoba 3 + Osoba 1)

Jeden wiersz = jedno zdarzenie. Wizualizacja 3D (`python -m src.viz.export_sim`) czyta **wszystkie** typy poniżej; brakujące typy są po prostu pomijane, więc silnik może dodawać je stopniowo.

### Kolumny wspólne

| kolumna | typ | opis |
|---|---|---|
| `time` | timestamp UTC | chwila zdarzenia |
| `minute` | float | minuty od początku symulacji |
| `event` | str | typ (tabela niżej) |
| `station_id` | str | stacja, której dotyczy zdarzenie |
| `to_station` | str / null | stacja docelowa (przejście, przejazd, zadanie) |
| `request_id` | int / null | klient (jedno przyjście = jedno `request_id`) |
| `user_id` | int / null | **nowe**: tożsamość klienta (np. stały bywalec) |
| `user_type` | str / null | **nowe**: `commuter`, `student`, `leisure`, `ebike` (inne = brak) |
| `has_app` | bool / null | **nowe**: czy klient widzi stan stacji w aplikacji |
| `truck_id` | int / null | ciężarówka (0, 1, ...) |
| `bike` | str / null | numer roweru |
| `n_bikes` | int / null | **nowe**: liczba rowerów (załadunek, zadanie) |
| `load` | int / null | rowerów na ciężarówce przy wyjeździe |

### Typy zdarzeń

| `event` | stan | co pokazuje 3D |
|---|---|---|
| `user_arrival` | jest | – |
| `walk_to_alternative` | jest | ludzik idzie do sąsiedniej stacji (linia trasy) |
| `lost_demand` | jest | ludzik czeka przy pustej stacji, potem odchodzi z ✕; licznik utraconych klientów |
| `rental`, `return`, `user_arrival_destination`, `redirect_return` | jest | rowery w drodze (z `trips.parquet`) |
| `truck_departure`, `truck_arrival` | jest | ciężarówka jedzie po drogach, numer, ładunek |
| `truck_load`, `truck_unload` | jest | liczba rowerów w zadaniu, pasek zdarzeń |
| `user_wait_start`, `user_wait_end` | **nowe** | ludzie czekający przy stacji (cierpliwość) |
| `user_walk`, `user_leave` | **nowe** | jak `walk_to_alternative` / `lost_demand`, z `user_type` |
| `signal_on`, `signal_off` | **nowe** | czerwony sygnał „potrzebuję rowerów” nad stacją |
| `task_announced`, `bid`, `task_awarded` | **nowe** | linia od stacji, która potrzebuje rowerów, do ciężarówki z zadaniem (dziś liczona z kolejności `truck_*`) |

### Przykładowy przebieg (do sprawdzenia formatu)

[`docs/przyklad_przebiegu/`](przyklad_przebiegu/) – pierwsze 12 h przebiegu `operator_2 / seed_1000` (5.11) z dopisanymi **wszystkimi nowymi** typami zdarzeń i kolumną `pressure`. Wartości nowych zdarzeń są umowne (losowane), liczy się format. Tworzy go `python tools/przyklad_przebiegu.py <katalog przebiegu>`.

- `task_awarded`: `station_id` = skąd zabrać rowery, `to_station` = dokąd dowieźć, `truck_id`, `n_bikes`; dodatkowo `task_id` (wspólne dla `task_announced` / `bid` / `task_awarded`) i `cost_min` w `bid`.
- `user_walk` **zastępuje** `walk_to_alternative` (silnik zapisuje jedno albo drugie, inaczej 3D pokaże dwa ludziki). `lost_demand` zostaje obok `user_leave` – z niego liczy się licznik utraconych klientów.
- Braki w kolumnach nullable (`pd.NA`, `Int64`, `string`, `boolean`) są obsługiwane przez eksport 3D (test `tests/test_export_sim.py`).

### `station_timeseries.parquet`

Co 5 min: `time`, `station_id`, `bikes`, `capacity`, `docks`, `is_empty`, `is_overfull` (jak dziś) + **nowa** kolumna `pressure` ∈ [−1, 1] (−1 = brakuje rowerów, +1 = za dużo; sygnał stacji). Bez niej 3D liczy ciśnienie z zapełnienia.

---

## 3. Z czego liczą się metryki (Osoba 1 + Osoba 3)

`src/metrics` (`emergence_report`, `compare`) przyjmuje katalog przebiegu i używa **tylko** tabel co 5 min, tak samo dla danych i modelu:

| plik | wymagane kolumny | po co |
|---|---|---|
| `station_timeseries.parquet` | `time`, `station_id`, `bikes` | pustki, fale, Moran, Gini |
| `stations.parquet` | `station_id`, `lat`, `lon`, `capacity` | sąsiedztwo stacji |
| `trips.parquet` | `type`, `t_departure`, `t_arrival`, `from_lat`, `from_lon`, `to_lat`, `to_lon` | rytm dnia, bilans dzielnic |
| `context_hourly.parquet` | `time`, `day_type` | typ dnia (opcjonalnie, inaczej z `processed/`) |
| `kpis.json`, `events.parquet` | – | tylko wizualizacja 3D |

**Które przebiegi mają pełne tabele (do 3D i metryk).** Przy ok. 5000 przebiegów zapisujemy tylko wyniki zbiorcze, poza listą:

- ziarno 1000, dzień walidacyjny **wtorek 17.11** (dzień roboczy, pełne pokrycie; 19.11 odpada – w dniu zamrożenia listy nie był jeszcze pełną dobą),
- strategie: `none_1`, `operator_2`, `threshold_2`, `pressure_2` (silnik agentowy, Contract Net) – te 4 przebiegi są już policzone i wyeksportowane do 3D (19.11); po 3.12 dochodzi najlepsza strategia z H3,
- dwa poziomy aplikacji (0% i 80% klientów z aplikacją, opóźnienie 5 min) – do efektu stadnego, po zamrożeniu `sim_params.json`.

Sprawdzone 19.11: zdarzenia silnika agentowego (`user_wait_*`, `user_walk`, `user_leave`, `signal_on/off`, `task_announced`, `bid`, `task_awarded`, `truck_load/unload`) i kolumna `pressure` wczytują się do 3D bez zmian w eksporcie.

Eksport: `python -m src.viz.export_sim <katalogi przebiegów>` (do 4 przebiegów jednej daty → widok „Strategie” w 3D).

---

## Historia

- 2026-11-08 – wersja robocza sekcji 2 i 3 (Osoba 1).
- 2026-11-15 – przykładowy przebieg z nowymi zdarzeniami agentów (`docs/przyklad_przebiegu/`), doprecyzowane pola `task_awarded` i `user_walk` (Osoba 1).
- 2026-11-19 – lista przebiegów z pełnymi tabelami: 17.11, ziarno 1000, `none_1` / `operator_2` / `threshold_2` / `pressure_2`; eksport z prawdziwego silnika agentowego sprawdzony (Osoba 1).
