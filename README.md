# Symulacja systemu rowerów miejskich Veturilo

Projekt z przedmiotu *Symulacja systemów dyskretnych*: stochastyczna symulacja zdarzeń dyskretnych (DES) systemu Veturilo w Warszawie, kalibrowana i walidowana na **własnych danych zbieranych co 5 minut**.

## Stan projektu

| Etap | Stan |
|---|---|
| Zbieranie danych live (GitHub Actions, co 5 min, od 22.10.2026) | ✅ działa nieprzerwanie od 23.10 |
| Dane statyczne: pogoda, kalendarze, wydarzenia, OSM, populacja, komunikacja | ✅ `python -m src.data.fetch_static` |
| Preprocessing: szereg czasowy stacji, przejazdy, relokacje, kontekst | ✅ `python -m src.data.build` |
| Analiza opisowa i hipoteza H2 | ✅ wstępnie (notebooki) – do powtórzenia na ≥ 2 tygodniach danych |
| Kalibracja modelu popytu i symulacja DES | ⏳ następny etap |
| Wizualizacja 3D (Streamlit + pydeck) | ⏳ |

## Dane

**Live** – zbierane przez [`collect.py`](collect.py) z oficjalnego feedu Nextbike (`nextbike-live.json`) do `data/`:

- **stan każdej z 348 stacji co 5 min** – liczba rowerów, wolne stojaki, czy stacja działa, **numery rowerów na stacji** (z nich odtwarzamy pojedyncze przejazdy) i bateria e-rowerów,
- rowery zostawione poza stacjami (pozycja),
- raz dziennie: lokalizacje i pojemności stacji, wielkość floty, cennik,
- ruch drogowy z TomTom co 30 min: prędkość na 10 arteriach i utrudnienia.

**Statyczne / historyczne** – pobierane raz do `data/static/`: pogoda i jakość powietrza (Open-Meteo), kalendarz świąt, szkół (ferie mazowieckie) i uczelni (UW, PW, SGH, WUM) ze [źródłami dat](data/static/calendar_sources.md), wydarzenia (mecze, PGE Narodowy, wydarzenia miejskie), OpenStreetMap (POI, drogi rowerowe, grafy dróg), populacja (Kontur), odjazdy komunikacji miejskiej (GTFS ZTM), wysokość terenu.

## Przygotowanie danych (`src/data/`)

```bash
pip install -r requirements.txt
python -m src.data.fetch_static   # raz (potem korzysta z cache, dociąga tylko nowe dni pogody)
python -m src.data.build          # po każdym git pull – ok. 1 min
```

Co robi `build`:

1. **Czyszczenie pomiarów** – oba formaty plików (przed i po dodaniu numerów rowerów), usunięcie duplikatów < 60 s, odfiltrowanie stacji wyłączonych. Czas wszędzie w UTC.
2. **Odtworzenie przejazdów** – rower znika ze stacji A i pojawia się na B → przejazd A → B (czas ±5 min). Odrzucane są przeskoki GPS (zmiana stacji bez zniknięcia, < 0,5 km); oznaczane: powroty na tę samą stację, migotanie feedu, przejazdy do/z miejsc poza stacjami, nierealnie szybkie (> 30 km/h) i dłuższe niż 4 h (serwis).
3. **Relokacje operatora** – ≥ 4 rowery przeniesione razem między tą samą parą stacji.
4. **Kontekst godzinowy** – pogoda, zmrok, typ dnia, kalendarze, wydarzenia, wskaźnik korków.
5. **Cechy stacji** – POI w promieniu 300 m, odległość do metra/uczelni/dworca/centrum, drogi rowerowe, populacja, komunikacja, wysokość terenu.
6. **Kontrola jakości** – `processed/quality_report.md` (tworzy go `build`): luki, artefakty, bilans przepływów (w 98,5% odstępów zmiana liczby rowerów na stacji zgadza się z odtworzonymi przejazdami).

### Pliki wynikowe (`processed/`)

| Plik | Zawartość | Do czego |
|---|---|---|
| `station_hourly.parquet` | stacja × godzina: wypożyczenia, zwroty, relokacje, czas, gdy stacja była pusta | **kalibracja popytu λ** |
| `trips.parquet` | przejazdy: skąd, dokąd, kiedy, czas, dystans (prosty i po drogach), e-rower, typ user/service | **macierz OD, czasy jazdy** |
| `observed_timeseries.parquet` | stan każdej stacji co 5 min | **stan początkowy, walidacja** |
| `rebalancing_observed.parquet` | relokacje operatora: czas, para stacji, liczba rowerów | **strategia operatora** |
| `fleet_timeseries.parquet` | rowery na stacjach / w drodze / poza obiegiem vs flota operatora | **wielkość floty** |
| `empty_periods.parquet` | okresy pustych stacji | popyt ocenzurowany |
| `stations.parquet` | stacje + cechy otoczenia | model popytu (opcjonalnie) |
| `context_hourly.parquet` | pogoda, kalendarz, wydarzenia, korki co godzinę | model popytu, scenariusze |

Pogrubione pliki wystarczają do symulacji DES. Cechy otoczenia i kontekst są potrzebne dopiero do wyjaśniania popytu i scenariuszy.

<details>
<summary>Pełna lista kolumn</summary>

| Plik | Kolumny |
|---|---|
| `observed_timeseries` | `time`, `station_id`, `bikes`, `docks`, `ebikes`, `ebikes_low` (bateria < 20%), `is_empty`, `is_overfull` |
| `station_hourly` | `station_id`, `hour`, `departures`, `arrivals`, `departures_ebike`, `service_out`, `service_in`, `minutes_observed`, `minutes_empty`, `minutes_overfull`, `minutes_available`, `departure_rate_per_h`, `mean_bikes`, `min_bikes`, `mean_ebikes` |
| `trips` | `bike`, `from`, `to` (id stacji albo `loose:<id>`), `from_type`, `to_type`, współrzędne, `t_departure`, `t_arrival`, `duration_min`, `distance_km`, `network_km`, `elev_diff_m`, `is_ebike`, `battery_start`, `type`, `same_station`, `is_flicker`, `from_loose`, `to_loose`, `is_long`, `too_fast` |
| `rebalancing_observed` | `from`, `to`, `t_departure`, `t_arrival`, `n_bikes`, `bikes`, `distance_km`, `network_km`, `duration_min` |
| `fleet_timeseries` | `time`, `at_stations`, `loose_warsaw`, `loose_outside`, `in_use`, `away_long`, `ebikes_parked`, `seen_total`, `set_point_bikes`, `operator_available_bikes` |
| `empty_periods` | `station_id`, `start`, `end`, `duration_min`, `n_obs`, `censored_end` |
| `stations` | `station_id`, `name`, `lat`, `lon`, `capacity`, statystyki (`share_empty`, `share_overfull`, `share_inactive`, `mean_bikes`), `n_{kategoria}_300m`, `dist_{metro,university,train_station,center,transit_stop}_m`, `cycleway_m_300m`, `population_500m`, `departures_{bus,tram,metro,rail,total}_300m`, `bldg_height_mean_300m`, `elevation_m` |
| `context_hourly` | `time`, `local_hour`, `dow`, `day_type`, pogoda, jakość powietrza, `sun_elevation`, `is_dark`, flagi kalendarza (`is_holiday`, `is_long_weekend`, `school_break`, `{uczelnia}_period`, `n_uni_classes` …), `n_events`, `n_events_large`, `congestion`, `n_incidents` |

</details>

## Wstępne wyniki

*Na danych z 22–26.10.2026 (ok. 4 doby, w tym 1 pełny dzień roboczy) – liczby zmienią się po zebraniu kolejnych tygodni.*

- **~9–12 tys. przejazdów na dobę**; w dzień roboczy szczyt poranny o 8:00 (~580/h) i popołudniowy o 16:00 (~1240/h), w weekend ruch zaczyna się później.
- **Krótkie przejazdy**: mediana 15 min i 2,0 km po drogach rowerowych; 72% przejazdów trwa ≤ 20 min – tyle, ile jest darmowe w cenniku.
- **Puste stacje są skoncentrowane**: Gini czasu pustek = 0,74; 10% stacji odpowiada za ponad połowę czasu, gdy stacje są puste, a połowa stacji nie była pusta ani razu.
- **Przepełnienie jest częste i dozwolone**: ok. 40% pomiarów ma więcej rowerów niż stojaków – stacje Veturilo 3.0 przyjmują rowery ponad pojemność.
- **Operator relokuje ok. 65 grup rowerów na dobę** (zwykle 4–5 rowerów).
- **E-rowery** to ~8% stojących rowerów, ale ~19% przejazdów.
- **Flota nie jest stała**: operator deklaruje 4566 rowerów, w obiegu widać naraz ok. 4100.
- Przykład wpływu pogody: w niedzielę 25.10 po rozpoczęciu deszczu (~18:00) liczba przejazdów spadła kilkukrotnie względem soboty.

## Hipotezy

| | Hipoteza | Stan |
|---|---|---|
| **H2** | Problem pustych stacji jest skoncentrowany na niewielkiej części stacji | wstępnie potwierdzona (Gini 0,74) – [notebook](notebooks/puste_i_przepelnione_stacje.ipynb) |
| | Opad i zmrok obniżają popyt silniej niż sama temperatura | do sprawdzenia (`context_hourly`) |
| | E-rowery tworzą osobny strumień popytu (dłuższe trasy, wybór zależny od baterii) | do sprawdzenia (`trips`) |
| | Próg 20 min darmowej jazdy kształtuje rozkład czasu przejazdu | widoczne w danych; do uwzględnienia w modelu |
| | Relokacje operatora nie nadążają za stacjami, które najczęściej się opróżniają | do sprawdzenia (`rebalancing_observed` × `empty_periods`) |

Analiza opisowa: [`notebooks/analiza_opisowa.ipynb`](notebooks/analiza_opisowa.ipynb).

## Uwagi do modelu

- **Pojemność jest miękka** – zwroty nie są blokowane przy `docks = 0`.
- **Popyt na pustych stacjach jest niewidoczny** – λ szacować z czasu, gdy na stacji były rowery (`departure_rate_per_h`).
- Czas zdarzeń znany z dokładnością do 5 min; `duration_min` zawyża czas jazdy średnio o ok. 5 min.
- Z `trips` odfiltruj `is_flicker`, `too_fast`, `is_long` (w `station_hourly` już odfiltrowane).
- Dni nietypowe: 31.10–2.11, 11.11, 24–26.12; zmiana czasu 25.10 – liczyć w UTC.
- Do kalibracji potrzeba ≥ 2 tygodni danych + osobnego tygodnia do walidacji.

<details>
<summary>Zbieranie danych – szczegóły techniczne</summary>

Workflow [`.github/workflows/collect.yml`](.github/workflows/collect.yml) działa łańcuchowo: każdy run mierzy co 5 min przez 57 min i uruchamia następny; cron co godzinę wznawia łańcuch, gdyby się przerwał. Wymaga publicznego repozytorium i uprawnień *Read and write* dla workflow. Ręcznie: Actions → *Zbieranie danych Veturilo* → *Run workflow* (`iterations = 1` – test, `0` – pełna godzina). TomTom wymaga sekretu `TOMTOM_API_KEY` (pomiar co 30 min, w darmowym limicie); dane ZTM (`WARSAW_API_KEY`) nie są obecnie zbierane.

Duże pliki (`data/static/osm/`, `data/static/cache/`) i `processed/` nie są w repozytorium – odtwarzają je `fetch_static` i `build`.

</details>
