# Symulacja systemu rowerów miejskich Veturilo

Projekt z przedmiotu *Symulacja systemów dyskretnych*: stochastyczna symulacja zdarzeń dyskretnych (DES) systemu roweru miejskiego Veturilo w Warszawie. Model jest kalibrowany i walidowany na **własnych danych**: co 5 minut zapisujemy stan wszystkich 348 stacji razem z numerami stojących na nich rowerów, co pozwala odtworzyć każdy przejazd.

**Pytania projektu:** jak powstaje problem pustych i przepełnionych stacji, od czego zależy popyt (pora dnia, pogoda, kalendarz, otoczenie stacji) i jak różne strategie relokacji rowerów wpływają na utracony popyt.

## Stan projektu

| Etap | Stan | Gdzie |
|---|---|---|
| Zbieranie danych live (co 5 min, od 22.10.2026) | ✅ działa samo, nieprzerwanie od 23.10 | [`collect.py`](collect.py), GitHub Actions |
| Dane statyczne i historyczne | ✅ gotowe, w repozytorium | `data/static/` |
| Preprocessing: stany stacji, przejazdy, relokacje, kontekst, cechy stacji | ✅ | `python -m src.data.build` |
| Analiza opisowa i hipoteza H2 | ✅ wstępnie (4 doby danych) – powtórzyć ok. 5.11 na ~2 tygodniach | `notebooks/` |
| Model popytu, macierz OD, kalibracja | ⏳ następny etap | – |
| Symulacja DES i scenariusze relokacji | ⏳ | – |
| Wizualizacja 3D (Streamlit + pydeck) | ⏳ | – |

## Szybki start

```bash
git pull                              # nowe dane zbierają się co godzinę
pip install -r requirements.txt
python -m src.data.build              # ok. 1 min -> processed/
```

To wystarczy – wszystkie dane statyczne (kalendarz, OSM, populacja, komunikacja, odległości między stacjami) są w repozytorium. `python -m src.data.fetch_static` trzeba uruchomić tylko, żeby dociągnąć pogodę i jakość powietrza z ostatnich dni (lub odtworzyć dane statyczne od zera).

```python
import pandas as pd
hourly = pd.read_parquet("processed/station_hourly.parquet")      # popyt: stacja x godzina
ctx = pd.read_parquet("processed/context_hourly.parquet")          # pogoda, kalendarz, ...
panel = hourly.merge(ctx, left_on="hour", right_on="time", how="left")

trips = pd.read_parquet("processed/trips.parquet")
user_trips = trips[(trips["type"] == "user") & ~trips["is_flicker"] & ~trips["too_fast"] & ~trips["is_long"]]
```

**Czas we wszystkich plikach jest w UTC.** Godzinę i dzień tygodnia w czasie warszawskim liczyć przez `tz_convert("Europe/Warsaw")` (w `context_hourly` są gotowe `local_hour`, `local_date`, `day_type`).

## Struktura repozytorium

```
collect.py                      zbieranie danych live (uruchamiane przez GitHub Actions)
.github/workflows/collect.yml   harmonogram zbierania
src/data/                       przygotowanie danych
  fetch_static.py               pobranie danych statycznych -> data/static/
  build.py                      przetworzenie danych live -> processed/
  trips.py                      odtwarzanie przejazdów z numerów rowerów
  aggregates.py                 tabele pochodne (stacja x godzina, puste stacje, flota)
  context.py, features.py       kontekst godzinowy, cechy otoczenia stacji
  calendar_data.py, events_data.py   daty kalendarzy i wydarzeń ze źródłami
notebooks/                      analiza opisowa, hipoteza H2
data/                           dane surowe (dopisywane automatycznie) + data/static/
processed/                      wyniki build (poza repozytorium – odtwarza je build)
```

## Dane

### Dane zbierane na żywo (`data/`)

[`collect.py`](collect.py) pobiera oficjalny feed Nextbike (`nextbike-live.json`, Warszawa) i dopisuje pliki dzienne (UTC):

| Folder | Co zawiera | Częstość |
|---|---|---|
| `status/` | stan każdej stacji: liczba rowerów, wolne stojaki, czy stacja działa, **numery rowerów**, bateria e-rowerów | 5 min |
| `loose/` | rowery zostawione poza stacjami (numer, pozycja, bateria) | 5 min |
| `info/` | stacje: nazwa, położenie, pojemność (liczba stojaków), typ terminala | dziennie |
| `system/` | wielkość floty deklarowana przez operatora, cennik, typy rowerów | dziennie |
| `traffic_flow/`, `incidents/` | TomTom: prędkość na 10 głównych arteriach, utrudnienia drogowe | 30 min |

Dane od 22.10.2026; luki tylko 22.10 przed uruchomieniem łańcucha zbierania. Dane sprzed 23.10 08:00 UTC nie mają części pól (np. stan aktywności stacji, bateria) – `build` obsługuje to automatycznie. 26.10 dwa punkty TomTom przeniesiono na główne jezdnie (nowe nazwy `jerozolimskie_centrum`, `grochowska_kobielska`).

### Dane statyczne i historyczne (`data/static/`)

| Plik | Co zawiera | Źródło |
|---|---|---|
| `calendar.csv` | 1.10.2026–30.06.2027 dzień po dniu: typ dnia, święta, długie weekendy, ferie i przerwy szkolne (mazowieckie), okresy zajęć/sesji/przerw UW, PW, SGH, WUM | dokumenty uczelni, MEN – [źródła dat](data/static/calendar_sources.md) |
| `events.csv` | mecze Legii, wydarzenia na PGE Narodowym, wydarzenia miejskie do 31.12.2026 (ze źródłem i flagą pewności) | strony organizatorów |
| `weather_hourly.parquet`, `air_quality_hourly.parquet` | pogoda (temperatura, opad, wiatr, zachmurzenie) i jakość powietrza co godzinę | Open-Meteo |
| `osm/` | POI (restauracje, bary, biura, uczelnie, metro, ...), drogi rowerowe, budynki Śródmieścia, granica miasta | OpenStreetMap |
| `station_network_distance.parquet` | odległość po drogach rowerowych między każdą parą stacji | graf OSM |
| `population_h3.parquet` | liczba mieszkańców w heksagonach ~400 m | Kontur Population |
| `transit_stops.parquet` | przystanki z liczbą odjazdów w typową środę (autobus, tramwaj, metro, SKM) | GTFS ZTM (mkuran.pl) |
| `elevation.csv` | wysokość terenu każdej stacji | Open-Meteo (Copernicus) |

Daty niepotwierdzone w dokumentach źródłowych są oznaczone jako niepewne (zajęcia i przerwy SGH, dzień rektorski WUM, 8 z 23 wydarzeń).

## Przygotowanie danych (`python -m src.data.build`)

1. **Czyszczenie pomiarów** – wczytanie obu formatów plików, usunięcie duplikatów (< 60 s po poprzednim pomiarze), usunięcie stacji wyłączonych, oznaczenie błędnych odczytów (`is_spike` – chwilowy skok liczby rowerów; `numbers_mismatch` – liczba numerów ≠ liczba rowerów).
2. **Odtworzenie przejazdów** – rower znika ze stacji A i pojawia się na stacji B → przejazd A → B. Czas znany z dokładnością ±5 min. Odrzucane są przeskoki GPS (zmiana stacji bez zniknięcia, < 0,5 km). Oznaczane są:
   - `same_station` – powrót na tę samą stację, w tym `is_flicker` – artefakt feedu (rower „znika” na jeden pomiar),
   - `from_loose` / `to_loose` – przejazd z/do miejsca poza stacją,
   - `too_fast` – nierealna prędkość > 30 km/h (błędna pozycja),
   - `is_long` – dłużej niż 4 h (zwykle wycofanie do serwisu).
3. **Relokacje operatora** (`type = service`) – ≥ 4 rowery przeniesione razem między tą samą parą stacji w tym samym odstępie pomiarów.
4. **Tabele dla modelu** – popyt stacja × godzina z czasem dostępności roweru, okresy pustych stacji, flota w czasie.
5. **Kontekst godzinowy** – pogoda, zmrok, typ dnia, kalendarze, wydarzenia, wskaźnik korków TomTom (`1 − prędkość / prędkość swobodna`), utrudnienia.
6. **Cechy stacji** – liczba POI w promieniu 300 m, odległość do metra, uczelni, dworca i centrum, drogi rowerowe, mieszkańcy w promieniu 500 m, odjazdy komunikacji, wysokość terenu.
7. **Kontrola jakości** – `processed/quality_report.md`: luki, artefakty, **bilans przepływów** (w 98,5% odstępów zmiana liczby rowerów na stacji zgadza się z odtworzonymi przejazdami).

### Pliki wynikowe (`processed/`) i dla kogo

| Plik | Zawartość | Do czego | Kto |
|---|---|---|---|
| `station_hourly.parquet` | stacja × godzina: wypożyczenia, zwroty, relokacje, minuty z pustą stacją, `departure_rate_per_h` (wypożyczenia na godzinę dostępności roweru) | **kalibracja popytu λ** | Osoba 2 |
| `trips.parquet` | przejazdy: skąd, dokąd, kiedy, czas, dystans prosty i po drogach, e-rower, typ user/service | **macierz OD, czasy jazdy** | Osoba 2 |
| `observed_timeseries.parquet` | stan każdej stacji co 5 min | **stan początkowy, walidacja** | Osoba 2 |
| `rebalancing_observed.parquet` | relokacje: czas, stacja źródłowa i docelowa, liczba rowerów | **obserwowana strategia operatora** | Osoba 2, 3 |
| `fleet_timeseries.parquet` | rowery na stacjach / poza stacjami / w drodze / poza obiegiem vs flota operatora | **wielkość floty** | Osoba 2, 3 |
| `empty_periods.parquet` | okresy pustych stacji (popyt ocenzurowany) | korekta popytu | Osoba 2 |
| `context_hourly.parquet` | pogoda, kalendarz, wydarzenia, korki co godzinę | model popytu, scenariusze | Osoba 2, 3 |
| `stations.parquet` | stacje: położenie, pojemność, statystyki, cechy otoczenia | model popytu, mapy | wszyscy |

Pogrubione zastosowania wystarczają do zbudowania symulacji DES. Kontekst i cechy stacji służą do wyjaśniania popytu i scenariuszy – nie trzeba ich używać w pierwszej wersji modelu.

<details>
<summary>Pełna lista kolumn</summary>

| Plik | Kolumny |
|---|---|
| `observed_timeseries` | `time`, `station_id`, `bikes`, `docks`, `ebikes`, `ebikes_low` (bateria < 20%), `is_empty` (bikes = 0), `is_overfull` (bikes > capacity – dozwolone), `is_spike` (pomijać), `numbers_mismatch` |
| `station_hourly` | `station_id`, `hour`, `departures`, `arrivals`, `departures_ebike`, `service_out`, `service_in`, `minutes_observed`, `minutes_empty`, `minutes_overfull`, `minutes_available`, `departure_rate_per_h`, `mean_bikes`, `min_bikes`, `mean_ebikes` |
| `trips` | `bike`, `from_station`, `to_station` (id stacji albo `loose:<id>`), `from_type`, `to_type` (station/loose), `from_lat`, `from_lon`, `to_lat`, `to_lon`, `t_departure` (ostatni pomiar w A), `t_arrival` (pierwszy w B), `duration_min`, `distance_km` (w linii prostej), `network_km` (po drogach rowerowych), `elev_diff_m`, `is_ebike`, `battery_start`, `type` (user/service), `same_station`, `is_flicker`, `from_loose`, `to_loose`, `is_long`, `too_fast` |
| `rebalancing_observed` | `from_station`, `to_station`, `t_departure`, `t_arrival`, `n_bikes`, `bikes`, `distance_km`, `network_km`, `duration_min` |
| `fleet_timeseries` | `time`, `at_stations`, `loose_warsaw`, `loose_outside`, `in_use` (w drodze < 4 h), `away_long` (> 4 h), `ebikes_parked`, `seen_total`, `set_point_bikes`, `operator_available_bikes` |
| `empty_periods` | `station_id`, `start`, `end`, `duration_min`, `n_obs`, `censored_end` (koniec nieznany) |
| `stations` | `station_id`, `name`, `lat`, `lon`, `capacity`, `terminal_type`, statystyki (`share_empty`, `share_overfull`, `share_inactive`, `mean_bikes`), `n_{restaurant,bar,cafe,office,university,school,mall,attraction,park,metro,train_station,tram_stop}_300m`, `dist_{metro,university,train_station,center,transit_stop}_m`, `cycleway_m_300m`, `population_500m`, `n_transit_stops_300m`, `departures_{bus,tram,metro,rail,total}_300m`, `bldg_height_mean_300m` (tylko Śródmieście), `elevation_m` |
| `context_hourly` | `time`, `local_date`, `local_hour`, `dow`, `is_weekend`, `day_type`, pogoda (`temperature_2m`, `precipitation`, `rain`, `snowfall`, `wind_speed_10m`, `cloud_cover`, …), `pm2_5`, `pm10`, `european_aqi`, `sun_elevation`, `is_dark`, `is_holiday`, `is_long_weekend`, `is_bridge_day`, `school_break`, `{uw,pw,sgh,wum}_period`, `{…}_classes_day`, `n_uni_classes`, `n_uni_exams`, `n_events`, `n_events_large`, `event_names`, `congestion`, `n_road_closures`, `n_incidents`, `n_jam_incidents` |

</details>

## Wstępne wyniki

*Dane z 22–26.10.2026 (4 doby, w tym 1 pełny dzień roboczy) – liczby do aktualizacji po zebraniu ~2 tygodni. Szczegóły: [`analiza_opisowa.ipynb`](notebooks/analiza_opisowa.ipynb), [`puste_i_przepelnione_stacje.ipynb`](notebooks/puste_i_przepelnione_stacje.ipynb).*

**Popyt**
- **8–12 tys. przejazdów na dobę** (piątek 11,8 tys., sobota 9,2 tys., niedziela 8,1 tys.).
- Dzień roboczy ma **szczyt poranny o 8:00** (~580 przejazdów/h) i **większy popołudniowy o 16:00** (~1240/h); w weekend ruch zaczyna się później i rozkłada równiej.
- Pogoda działa wyraźnie: w niedzielę 25.10 po rozpoczęciu deszczu (~18:00) przejazdów było kilkukrotnie mniej niż o tej porze w sobotę.

**Przejazdy**
- Mediana: **15 min i 2,0 km** po drogach rowerowych (droga jest średnio 1,26× dłuższa niż linia prosta).
- **73% przejazdów trwa ≤ 20 min** – tyle, ile jest darmowe w cenniku.
- 3,6% przejazdów kończy się poza stacją, średnio ok. 200 m od najbliższej stacji.

**Stacje**
- **Puste stacje są skoncentrowane** (H2): Gini czasu pustek = 0,73; 10% stacji odpowiada za połowę, a 20% za 74% czasu, w którym stacje są puste; 48% stacji nie było pustych ani razu.
- **Przepełnienie jest częste i dozwolone**: ok. 40% pomiarów ma więcej rowerów niż stojaków – stacje Veturilo 3.0 przyjmują rowery ponad pojemność.

**Operator i flota**
- **Ok. 65 relokacji na dobę**, zwykle po 4–5 rowerów.
- Operator deklaruje 4566 rowerów, a **w obiegu jest ok. 3600** (maks. ~3700); nawet z rowerami nieobecnymi > 4 h najwyżej ~3900. Ok. 650–950 rowerów jest stale poza obiegiem (serwis, magazyn).
- **E-rowery** to ok. 8% stojących rowerów, ale **19% przejazdów** – wypożyczane ok. 2,4× częściej niż zwykłe.

## Hipotezy

| | Hipoteza | Stan | Dane |
|---|---|---|---|
| **H2** | Problem pustych stacji jest skoncentrowany na niewielkiej części stacji | wstępnie potwierdzona (Gini 0,73, top 20% = 74%) | `observed_timeseries`, notebook H2 |
| | Opad i zmrok obniżają popyt silniej niż sama temperatura | do sprawdzenia | `station_hourly` + `context_hourly` |
| | E-rowery tworzą osobny strumień popytu (dłuższe trasy, wybór zależny od baterii) | do sprawdzenia | `trips` (`is_ebike`, `battery_start`) |
| | Darmowe 20 min kształtuje rozkład czasu przejazdu | widoczne w danych; uwzględnić w modelu czasu jazdy | `trips` |
| | Relokacje operatora nie nadążają za stacjami, które najczęściej się opróżniają | do sprawdzenia | `rebalancing_observed` + `empty_periods` |
| | Popyt stacji zależy od otoczenia (biura, uczelnie, metro, gęstość zaludnienia) | do sprawdzenia | `station_hourly` + `stations` |

## Wskazówki do modelu

- **Pojemność jest miękka** – zwrotów nie blokować przy `docks = 0`.
- **Popyt na pustej stacji jest niewidoczny** – λ szacować z czasu, gdy na stacji były rowery (`departure_rate_per_h`, `empty_periods`).
- **Flota nie jest stała** – ok. 650–950 rowerów poza obiegiem (`fleet_timeseries`).
- **E-rowery** warto modelować osobno.
- Z `trips` odfiltrować `is_flicker`, `too_fast`, `is_long`; w `station_hourly` jest to już zrobione.
- `duration_min` zawyża czas jazdy średnio o ok. 5 min (odstęp pomiarów).
- Dni nietypowe w okresie zbierania: 31.10–2.11 (Wszystkich Świętych), 11.11, 24–26.12; zmiana czasu 25.10 (liczyć w UTC).
- Do kalibracji ≥ 2 tygodnie danych + osobny tydzień do walidacji.

## Zbieranie danych – szczegóły techniczne

<details>
<summary>GitHub Actions, sekrety, odtwarzanie danych statycznych</summary>

- Workflow [`.github/workflows/collect.yml`](.github/workflows/collect.yml) działa łańcuchowo: każdy run mierzy co 5 min przez 57 min i uruchamia następny; cron co godzinę wznawia łańcuch, gdyby się przerwał. Wymaga publicznego repozytorium i uprawnień *Read and write* dla workflow.
- Ręczne uruchomienie: Actions → *Zbieranie danych Veturilo* → *Run workflow* (`iterations = 1` – test, `0` – pełna godzina).
- Kontrola raz w tygodniu: brak czerwonych runów w Actions i ciągłość commitów `Dane ...`.
- TomTom wymaga sekretu `TOMTOM_API_KEY` (pomiar co 30 min mieści się w darmowym limicie). Dane ZTM (`WARSAW_API_KEY`) nie są zbierane.
- `python -m src.data.fetch_static [--only KROK ...] [--force KROK ...]` – kroki: `calendar events weather air_quality elevation population gtfs osm`. Gotowe pliki są pomijane; pogoda i jakość powietrza dociągane przyrostowo. Grafy dróg OSM (~130 MB, poza repo) budowane tylko z `--force osm`.
- Poza repozytorium: `processed/`, `data/static/cache/`, grafy i cache w `data/static/osm/`.

</details>
