# Symulacja systemu rowerów miejskich Veturilo

Projekt z przedmiotu *Symulacja systemów dyskretnych*: stochastyczna symulacja zdarzeń dyskretnych (DES) systemu roweru miejskiego Veturilo w Warszawie, kalibrowana na **własnych danych**. Co 5 minut zapisujemy stan wszystkich 348 stacji razem z **numerami stojących na nich rowerów**. Dzięki temu odtwarzamy każdy przejazd (skąd, dokąd, kiedy) i każdą relokację operatora, chociaż operator nie publikuje takich danych.

**Pytania projektu**
1. Jak powstaje problem pustych (i przepełnionych) stacji i gdzie się koncentruje?
2. Od czego zależy popyt: pora dnia, typ dnia, pogoda, kalendarz (uczelnie, szkoły, święta), otoczenie stacji?
3. Jak różne strategie relokacji rowerów zmieniają utracony popyt (klient przychodzi na pustą stację)?

## Stan prac (3.11.2026)

| Etap | Stan | Gdzie |
|---|---|---|
| Zbieranie danych live co 5 min | ✅ działa samo od 22.10, bez luk od 26.10 (pokrycie 97,7%) | [`collect.py`](collect.py), GitHub Actions |
| Dane statyczne i historyczne (kalendarz, wydarzenia, pogoda, OSM, populacja, komunikacja) | ✅ w repozytorium | `data/static/` |
| Preprocessing: przejazdy, relokacje, puste stacje, kontekst, cechy stacji, raport jakości | ✅ | `python -m src.data.build` |
| Analiza opisowa + test hipotezy H2 | ✅ wstępnie; przeliczyć na pełnych 2 tygodniach (~5.11) | `notebooks/` |
| Wizualizacja 3D odtwarzająca rzeczywisty dzień | ✅ prototyp | `unity/`, `python -m src.viz.export` |
| Model popytu λ(stacja, godzina), macierz OD, kalibracja | ⏳ następny etap | – |
| Symulacja DES i porównanie strategii relokacji | ⏳ | – |

**Ilość danych.** Na 3.11 mamy 12 pełnych dób: 7 dni roboczych, 2 soboty, 2 niedziele/święta, ok. 104 tys. przejazdów. To wystarcza do analizy opisowej i modelu dla dni roboczych. Na weekendy i wpływ pogody potrzeba więcej danych: na razie temperatura to tylko 1–14 °C, a opad wystąpił w ok. 20 godzinach. Planowo: kalibracja na ≥ 2 tygodniach + osobny tydzień do walidacji.

## Ściąga na prezentację

1. **Dane są nasze, nie gotowe.** Feed Nextbike pokazuje tylko „ile rowerów stoi teraz”. Zbieramy go co 5 min z numerami rowerów i z tego **sami odtwarzamy przejazdy** (rower znika z A i pojawia się w B).
2. **Dane są wiarygodne.** W 98,5% 5-minutowych odstępów zmiana liczby rowerów na stacji zgadza się z odtworzonymi przyjazdami i odjazdami (bilans przepływów w `quality_report.md`). Artefakty feedu (migotanie, przeskoki GPS, nierealne prędkości) są oznaczone flagami.
3. **Skala:** ok. 10 tys. przejazdów w dzień roboczy, 7 tys. w weekend; ok. 70 relokacji operatora na dobę.
4. **Problem do rozwiązania:** puste stacje są skoncentrowane (H2: Gini 0,68). Popytu na pustej stacji nie widać w danych (popyt ocenzurowany), więc szacujemy go z czasu, gdy rowery były dostępne.
5. **Kontekst:** każda godzina ma pogodę, zmrok, typ dnia, kalendarze uczelni i szkół, wydarzenia i korki TomTom. Każda stacja ma cechy otoczenia (POI, metro, uczelnie, mieszkańcy, komunikacja, wysokość terenu).
6. **Wizualizacja 3D** odtwarza rzeczywisty dzień, a w tym samym formacie przyjmie wynik symulacji DES, więc pokażemy model obok rzeczywistości.

## Dane

### Dane live (`data/`, dopisywane automatycznie co godzinę)

Po co: z nich odtwarzamy **przejazdy, relokacje i stan stacji w czasie**, czyli wszystko, czego potrzebuje symulacja (popyt, czasy jazdy, macierz OD, strategia operatora, stan początkowy, walidacja).

| Folder | Co zawiera | Częstość | Źródło |
|---|---|---|---|
| `status/` | każda stacja: liczba rowerów i e-rowerów, wolne stojaki, czy działa, **numery rowerów**, bateria e-rowerów | 5 min | Nextbike |
| `loose/` | rowery zostawione poza stacjami (numer, pozycja, bateria) | 5 min | Nextbike |
| `info/` | stacje: nazwa, położenie, pojemność, typ terminala | dziennie | Nextbike |
| `system/` | flota deklarowana przez operatora, cennik, typy rowerów | dziennie | Nextbike |
| `traffic_flow/` | prędkość vs prędkość swobodna na 10 głównych arteriach | 30 min | TomTom |
| `incidents/` | utrudnienia i zamknięcia dróg | 30 min | TomTom |

Pliki dzienne w UTC. Dane sprzed 23.10 ok. 10:00 nie mają części pól (aktywność stacji, bateria); `build` obsługuje to automatycznie.

### Dane statyczne i historyczne (`data/static/`)

Po co: **wyjaśniają popyt** (dlaczego na tej stacji, o tej porze, przy tej pogodzie) i pozwalają budować scenariusze (np. deszczowy dzień, sesja na uczelniach, mecz na Narodowym).

| Plik | Co zawiera | Źródło |
|---|---|---|
| `calendar.csv` (+ `calendar_sources.md`) | 1.10.2026–30.06.2027 dzień po dniu: typ dnia, święta, długie weekendy, ferie i przerwy szkolne, okresy zajęć/sesji UW, PW, SGH, WUM | MEN, dokumenty uczelni |
| `events.csv` | mecze Legii, wydarzenia na PGE Narodowym i miejskie do 31.12.2026 (źródło + flaga pewności) | strony organizatorów |
| `weather_hourly.parquet` | temperatura, opad, wiatr, zachmurzenie co godzinę | Open-Meteo (archiwum) |
| `air_quality_hourly.parquet` | PM2.5, PM10, NO₂, europejski AQI co godzinę | Open-Meteo |
| `osm/` | POI (lokale, biura, uczelnie, metro…), drogi rowerowe, budynki Śródmieścia, granica miasta | OpenStreetMap |
| `station_network_distance.parquet` | odległość po drogach rowerowych dla każdej pary stacji | graf OSM |
| `population_h3.parquet` | mieszkańcy w heksagonach ~400 m | Kontur Population |
| `transit_stops.parquet` | przystanki z liczbą odjazdów w typową środę | GTFS ZTM |
| `elevation.csv` | wysokość terenu każdej stacji | Open-Meteo (Copernicus) |

## Przetwarzanie (`python -m src.data.build`, ok. 1–2 min)

1. **Czyszczenie pomiarów:** duplikaty, stacje wyłączone, oznaczenie błędnych odczytów (`is_spike`, `numbers_mismatch`).
2. **Odtworzenie przejazdów** z numerów rowerów (czas ±5 min). Odrzucane są przeskoki GPS; flagi: `is_flicker` (artefakt feedu), `too_fast` (> 30 km/h), `is_long` (> 4 h, zwykle serwis), `from_loose`/`to_loose` (poza stacją).
3. **Relokacje operatora:** ≥ 4 rowery przeniesione razem między tą samą parą stacji (`type = service`).
4. **Tabele dla modelu:** popyt stacja × godzina z czasem dostępności roweru, okresy pustych stacji, flota w czasie.
5. **Kontekst godzinowy:** pogoda, jakość powietrza, położenie słońca, kalendarze, wydarzenia, wskaźnik korków (`1 − prędkość/prędkość swobodna`, średnia z 10 korytarzy).
6. **Cechy stacji:** POI w promieniu 300 m, odległość do metra, uczelni, dworca, centrum, mieszkańcy w promieniu 500 m, odjazdy komunikacji, wysokość.
7. **Raport jakości** `processed/quality_report.md`: luki, artefakty, bilans przepływów.

### Wyniki (`processed/`, poza repozytorium – odtwarza je `build`)

| Plik | Zawartość | Do czego |
|---|---|---|
| `station_hourly.parquet` | stacja × godzina: wypożyczenia, zwroty, relokacje, minuty pustej stacji, `departure_rate_per_h` | **kalibracja popytu λ** |
| `trips.parquet` | przejazdy: skąd, dokąd, kiedy, czas, dystans (prosty i po drogach), e-rower, user/service | **macierz OD, czasy jazdy** |
| `observed_timeseries.parquet` | stan każdej stacji co 5 min | **stan początkowy, walidacja** |
| `rebalancing_observed.parquet` | relokacje: czas, skąd, dokąd, ile rowerów | **strategia bazowa operatora** |
| `fleet_timeseries.parquet` | rowery na stacjach / poza / w drodze / poza obiegiem vs flota deklarowana | **wielkość floty** |
| `empty_periods.parquet` | okresy pustych stacji | korekta popytu ocenzurowanego |
| `context_hourly.parquet` | pogoda, kalendarz, wydarzenia, korki co godzinę | model popytu, scenariusze |
| `stations.parquet` | stacje: położenie, pojemność, statystyki, cechy otoczenia | model popytu, mapy |

Pogrubione zastosowania wystarczą do pierwszej wersji DES. **Czas we wszystkich plikach jest w UTC.** W `context_hourly` są gotowe `local_hour`, `local_date`, `day_type`.

<details>
<summary>Pełna lista kolumn</summary>

| Plik | Kolumny |
|---|---|
| `observed_timeseries` | `time`, `station_id`, `bikes`, `docks`, `ebikes`, `ebikes_low` (bateria < 20%), `is_empty`, `is_overfull` (bikes > capacity – dozwolone), `is_spike` (pomijać), `numbers_mismatch` |
| `station_hourly` | `station_id`, `hour`, `departures`, `arrivals`, `departures_ebike`, `service_out`, `service_in`, `minutes_observed`, `minutes_empty`, `minutes_overfull`, `minutes_available`, `departure_rate_per_h`, `mean_bikes`, `min_bikes`, `mean_ebikes` |
| `trips` | `bike`, `from_station`, `to_station` (id stacji albo `loose:<id>`), `from_type`, `to_type`, `from_lat`, `from_lon`, `to_lat`, `to_lon`, `t_departure`, `t_arrival`, `duration_min`, `distance_km`, `network_km`, `elev_diff_m`, `is_ebike`, `battery_start`, `type` (user/service), `same_station`, `is_flicker`, `from_loose`, `to_loose`, `is_long`, `too_fast` |
| `rebalancing_observed` | `from_station`, `to_station`, `t_departure`, `t_arrival`, `n_bikes`, `bikes`, `distance_km`, `network_km`, `duration_min` |
| `fleet_timeseries` | `time`, `at_stations`, `loose_warsaw`, `loose_outside`, `in_use` (< 4 h), `away_long` (> 4 h), `ebikes_parked`, `seen_total`, `set_point_bikes`, `operator_available_bikes` |
| `empty_periods` | `station_id`, `start`, `end`, `duration_min`, `n_obs`, `censored_end` |
| `stations` | `station_id`, `name`, `lat`, `lon`, `capacity`, `terminal_type`, `share_empty`, `share_overfull`, `share_inactive`, `mean_bikes`, `n_<typ POI>_300m`, `dist_{metro,university,train_station,center,transit_stop}_m`, `cycleway_m_300m`, `population_500m`, `n_transit_stops_300m`, `departures_{bus,tram,metro,rail,total}_300m`, `bldg_height_mean_300m`, `elevation_m` |
| `context_hourly` | `time`, `local_date`, `local_hour`, `dow`, `is_weekend`, `day_type`, pogoda (`temperature_2m`, `precipitation`, `rain`, `wind_speed_10m`, `cloud_cover`, …), `pm2_5`, `pm10`, `european_aqi`, `sun_elevation`, `is_dark`, `is_holiday`, `is_long_weekend`, `is_bridge_day`, `school_break`, `{uw,pw,sgh,wum}_period`, `n_uni_classes`, `n_uni_exams`, `n_events`, `n_events_large`, `event_names`, `congestion`, `congestion_max`, `congestion_stable`, `n_corridors`, `n_road_closures`, `n_incidents`, `n_jam_incidents` |

</details>

## Hipotezy

| | Hipoteza | Stan |
|---|---|---|
| **H2** | Puste stacje są skoncentrowane na niewielkiej części stacji | **wstępnie potwierdzona**: Gini 0,68, 20% stacji = 68% czasu pustek |
| | Opad i zmrok obniżają popyt silniej niż sama temperatura | widoczne (deszcz 25.10), za mało godzin z opadem na test |
| | Darmowe 20 min kształtuje rozkład czasu przejazdu | widoczne: 73% przejazdów ≤ 20 min |
| | E-rowery to osobny strumień popytu (częściej wybierane, zależne od baterii) | widoczne: 8% stojących rowerów, 19% przejazdów |
| | Relokacje operatora nie nadążają za stacjami, które najczęściej się opróżniają | do sprawdzenia (`rebalancing_observed` + `empty_periods`) |
| | Popyt stacji zależy od otoczenia (biura, uczelnie, metro, mieszkańcy) | do sprawdzenia (`station_hourly` + `stations`) |

## Wstępne wyniki (23.10–2.11, 11 pełnych dób)

Szczegóły i wykresy: [`analiza_opisowa.ipynb`](notebooks/analiza_opisowa.ipynb), [`puste_i_przepelnione_stacje.ipynb`](notebooks/puste_i_przepelnione_stacje.ipynb).

- **Popyt:** dzień roboczy średnio **9,9 tys.** przejazdów (8,3–11,8 tys.), sobota 7,5 tys., niedziela/święto 6,9 tys. Weekend Wszystkich Świętych (31.10–1.11) to ok. 5,8 tys./dobę.
- **Profil dnia roboczego:** szczyt poranny o 8:00 (~610/h), większy popołudniowy o 16:00 (~960/h).
- **Przejazdy:** mediana **15 min i 1,8 km** po drogach rowerowych (1,26× dłużej niż w linii prostej); 73% ≤ 20 min; 3,3% kończy się poza stacją.
- **Stacje:** Gini czasu pustek 0,68 (10% stacji = 44%, 20% = 68% czasu pustek); 31% stacji nie było pustych ani razu. Ok. 40% pomiarów to stacja przepełniona – na Veturilo 3.0 to dozwolone.
- **Operator:** ok. **72 relokacje na dobę**, zwykle po 4 rowery.
- **Flota:** operator deklaruje 4566 rowerów, w obiegu jest ok. **3640** (maks. ~3730); 300–400 rowerów nie pojawia się dłużej niż 4 h (serwis, magazyn).

## Wskazówki do modelu

- **Pojemność jest miękka:** zwrotów nie blokować przy `docks = 0`. Klient traci tylko na pustej stacji.
- **Popyt na pustej stacji jest niewidoczny:** λ szacować z czasu dostępności roweru (`departure_rate_per_h`, `empty_periods`).
- **Flota nie jest stała** (`fleet_timeseries`); **e-rowery** warto modelować osobno.
- Z `trips` odfiltrować `is_flicker`, `too_fast`, `is_long` (w `station_hourly` już zrobione). `duration_min` zawyża czas jazdy średnio o ok. 5 min.
- Dni nietypowe: 31.10–2.11, 11.11, 24–26.12; zmiana czasu 25.10 (wszystko liczyć w UTC).

## Wizualizacja 3D (Unity)

Scena 3D Warszawy, która **odtwarza wybrany dzień z danych** co 5 minut:
- stacje jako słupki (wysokość = liczba rowerów, kolor = zapełnienie, pusta pulsuje na czerwono),
- każdy przejazd jako świecący rower jadący po trasie, e-rowery osobnym kolorem,
- relokacje jako ciężarówki z liczbą przewożonych rowerów,
- budynki Śródmieścia, drogi rowerowe, metro, uczelnie z OSM,
- słońce, zmrok, zachmurzenie i deszcz według danych pogodowych,
- panel: zegar, pogoda, korki, KPI (rowery w drodze, puste stacje, relokacje), wykresy dnia, oś czasu, karta stacji po kliknięciu.

**Przepływ:** `processed/` → `python -m src.viz.export` (pliki JSON, ok. 1 MB na dzień) → `unity/Assets/StreamingAssets/veturilo/` → Unity: otworzyć folder `unity/` w Unity Hub (Unity 6), pusta scena, **Play**. Scena jest budowana w całości w kodzie. Ten sam eksport przyjmie wynik symulacji DES (`--source sim`). Instrukcja, sterowanie i scenariusz pokazu: [`unity/README.md`](unity/README.md).

## Struktura repozytorium

```
collect.py                  zbieranie danych live (Nextbike co 5 min, TomTom co 30 min)
.github/workflows/collect.yml   harmonogram zbierania (łańcuch runów co godzinę)
requirements.txt            pakiety Python

src/data/                   przygotowanie danych
  fetch_static.py           pobranie danych statycznych -> data/static/ (kroki: calendar events weather
                            air_quality elevation population gtfs osm)
  calendar_data.py          daty kalendarza szkolnego i akademickiego ze źródłami
  events_data.py            lista wydarzeń w Warszawie ze źródłami
  osm.py, gtfs.py, population.py   pobranie OSM, rozkładów ZTM, gęstości zaludnienia
  network.py                odległości między stacjami po drogach rowerowych
  build.py                  przetworzenie danych live -> processed/ + raport jakości
  raw.py                    odczyt surowych plików z data/
  trips.py                  odtwarzanie przejazdów i relokacji z numerów rowerów
  aggregates.py             tabele pochodne: stacja × godzina, puste stacje, flota, bilans
  context.py                kontekst godzinowy (pogoda, słońce, kalendarz, wydarzenia, korki)
  features.py               cechy otoczenia stacji
  config.py                 ścieżki i stałe
src/viz/export.py           eksport processed/ -> JSON dla Unity

notebooks/
  analiza_opisowa.ipynb               przejazdy, relokacje, rowery poza stacjami, flota, e-rowery
  puste_i_przepelnione_stacje.ipynb   hipoteza H2: krzywa Lorenza, Gini, stabilność, mapa

unity/                      projekt Unity: skrypty w Assets/VeturiloViz/Scripts/ (opis w unity/README.md)
data/                       dane live + data/static/
processed/                  wyniki build (poza repozytorium)
```

## Szybki start

```bash
git pull                                               # nowe dane co godzinę
pip install -r requirements.txt
python -m src.data.fetch_static --only weather air_quality   # dociągnięcie pogody z ostatnich dni
python -m src.data.build                               # -> processed/
python -m src.viz.export                               # -> dane dla Unity (opcjonalnie)
```

```python
import pandas as pd
hourly = pd.read_parquet("processed/station_hourly.parquet")
ctx = pd.read_parquet("processed/context_hourly.parquet")
panel = hourly.merge(ctx, left_on="hour", right_on="time", how="left")

trips = pd.read_parquet("processed/trips.parquet")
user_trips = trips[(trips["type"] == "user") & ~trips["is_flicker"] & ~trips["too_fast"] & ~trips["is_long"]]
```

<details>
<summary>Zbieranie danych – szczegóły techniczne</summary>

- Workflow [`.github/workflows/collect.yml`](.github/workflows/collect.yml) działa łańcuchowo: każdy run mierzy co 5 min przez 57 min i uruchamia następny; cron co godzinę wznawia łańcuch, gdyby się przerwał. Wymaga publicznego repozytorium i uprawnień *Read and write* dla workflow.
- Ręczne uruchomienie: Actions → *Zbieranie danych Veturilo* → *Run workflow* (`iterations = 1` – test, `0` – pełna godzina).
- Kontrola raz w tygodniu: brak czerwonych runów w Actions i ciągłość commitów `Dane ...`.
- TomTom wymaga sekretu `TOMTOM_API_KEY` (pomiar co 30 min mieści się w darmowym limicie). 26.10 dwa punkty TomTom przeniesiono na główne jezdnie; wskaźnik korków łączy je z poprzednikami.
- `fetch_static` pomija gotowe pliki (`--force KROK` tworzy ponownie); pogoda i jakość powietrza są dociągane przyrostowo. Grafy dróg OSM (~130 MB, poza repo, potrzebne do tras w wizualizacji) – `--only osm --force osm`.
- Poza repozytorium: `processed/`, `data/static/cache/`, grafy i cache w `data/static/osm/`, dane eksportu w `unity/Assets/StreamingAssets/veturilo/`.

</details>
