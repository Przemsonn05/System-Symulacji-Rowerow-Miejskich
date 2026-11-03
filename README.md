# Symulacja systemu rowerów miejskich Veturilo

Projekt z przedmiotu *Symulacja systemów dyskretnych*. Budujemy **symulację komputerową systemu Veturilo w Warszawie**: wirtualne stacje, rowery, klientów, którzy je wypożyczają i oddają, oraz samochody operatora, które przewożą rowery między stacjami. Symulacja ma odtwarzać rzeczywistość, więc jej parametry (ilu klientów, kiedy, skąd, dokąd) bierzemy z **danych, które sami zbieramy** od 22.10.2026.

Gdy model będzie zgodny z rzeczywistością, możemy na nim sprawdzać rzeczy, których nie da się przetestować na prawdziwym systemie, np. „co by było, gdyby operator przewoził rowery inaczej albo częściej”.

## O co pytamy

1. **Skąd biorą się puste stacje?** Klient przychodzi, a roweru nie ma: to podstawowy problem systemu. Chcemy wiedzieć, gdzie i kiedy to się dzieje.
2. **Od czego zależy liczba wypożyczeń?** Pora dnia, dzień tygodnia, pogoda, zajęcia na uczelniach, święta, otoczenie stacji (metro, biura, uczelnie).
3. **Która strategia przewożenia rowerów najlepiej zmniejsza liczbę klientów, którzy odchodzą z niczym?** To odpowiemy symulacją.

## Stan prac (3.11.2026)

| Etap | Stan |
|---|---|
| Automatyczne zbieranie danych co 5 minut | ✅ działa samo od 22.10, bez przerw od 26.10 |
| Dane dodatkowe: pogoda, kalendarz, wydarzenia, mapa miasta, mieszkańcy, komunikacja | ✅ pobrane, są w repozytorium |
| Przetworzenie danych: odtworzenie przejazdów, relokacji, pustych stacji | ✅ jedno polecenie: `python -m src.data.build` |
| Analiza opisowa i test pierwszej hipotezy (2 notebooki) | ✅ wstępnie; do przeliczenia na pełnych 2 tygodniach |
| Wizualizacja 3D odtwarzająca prawdziwy dzień | ✅ działający prototyp |
| Model popytu: ilu klientów na której stacji o której godzinie | ⏳ następny krok |
| Symulacja i porównanie strategii relokacji | ⏳ |

**Czy danych jest już dość?** Mamy 12 pełnych dób (7 dni roboczych, 2 soboty, 2 niedziele/święta), ok. 104 tys. przejazdów.
- Na **dni robocze**: tak, można zaczynać model.
- Na **weekendy**: za mało (tylko 2 soboty i 2 niedziele, w tym długi weekend Wszystkich Świętych).
- Na **wpływ pogody**: za mało. Do tej pory było 1–14 °C i tylko ok. 20 godzin z deszczem, więc model nie ma się jeszcze z czego nauczyć, jak działa deszcz czy mróz.

Plan: model kalibrujemy na ≥ 2 tygodniach, a sprawdzamy na kolejnym tygodniu, którego model „nie widział”.

## Najważniejsze w 6 punktach (do prezentacji)

1. **Dane są nasze.** Operator nie udostępnia listy przejazdów. Publikuje tylko, ile rowerów stoi teraz na każdej stacji i jakie mają numery. Zapisujemy to co 5 minut i **sami odtwarzamy przejazdy**: jeśli rower nr 12345 zniknął ze stacji A, a 15 min później pojawił się na stacji B, to ktoś przejechał z A do B.
2. **Sprawdziliśmy, że to działa.** Jeśli na stacji przybyły 3 rowery, to powinniśmy widzieć 3 przejazdy kończące się na niej. Zgadza się to w 98,5% przypadków. Błędy feedu (rower „znika” na chwilę, skacze GPS) są wykrywane i oznaczane.
3. **Skala:** ok. 10 tys. przejazdów w dzień roboczy i ok. 7 tys. w weekend. Operator wykonuje ok. 70 przewozów rowerów dziennie.
4. **Problem pustych stacji jest skupiony** w niewielkiej części miasta (hipoteza H2, opis niżej). Strategia relokacji może więc skupić się na kilkudziesięciu stacjach.
5. **Wiemy, co działo się wokół:** każda godzina ma pogodę, zmrok, typ dnia, kalendarze uczelni i szkół, wydarzenia i korki. Każda stacja ma opis otoczenia.
6. **Wizualizacja 3D** pokazuje prawdziwy dzień, a później w tym samym widoku pokaże wynik symulacji. Model i rzeczywistość będzie można porównać obok siebie.

## Dane

### 1. Dane zbierane na żywo (`data/`)

Skrypt [`collect.py`](collect.py) uruchamia się sam na serwerach GitHuba (GitHub Actions) i co godzinę dopisuje nowe pomiary do repozytorium. Nikt nie musi mieć włączonego komputera.

| Folder | Co tam jest | Jak często | Do czego się przyda |
|---|---|---|---|
| `status/` | dla każdej stacji: ile rowerów (w tym elektrycznych), ile wolnych stojaków, czy stacja działa, **numery rowerów**, bateria e-rowerów | co 5 min | **najważniejsze**: z numerów odtwarzamy przejazdy i relokacje, z liczby rowerów puste stacje |
| `loose/` | rowery zostawione poza stacją (numer, miejsce, bateria) | co 5 min | przejazdy kończące się poza stacją |
| `info/` | lista stacji: nazwa, położenie, liczba stojaków | raz dziennie | mapa stacji, pojemność w modelu |
| `system/` | ile rowerów operator deklaruje, cennik | raz dziennie | porównanie z liczbą rowerów faktycznie w użyciu |
| `traffic_flow/` | prędkość ruchu na 10 głównych ulicach (TomTom) | co 30 min | wskaźnik korków: czy w korki ludzie częściej wybierają rower |
| `incidents/` | wypadki, zamknięte drogi (TomTom) | co 30 min | jw. |

### 2. Dane statyczne i historyczne (`data/static/`)

Pobrane raz (pogoda jest dociągana na bieżąco). Same nie mówią nic o rowerach, ale **wyjaśniają, dlaczego popyt jest taki, a nie inny**. Pozwolą też budować scenariusze typu „deszczowy dzień” albo „sesja na uczelniach”.

| Plik | Co tam jest | Do czego się przyda |
|---|---|---|
| `calendar.csv` | każdy dzień do 30.06.2027: dzień roboczy/weekend/święto, długie weekendy, ferie, zajęcia i sesje na UW, PW, SGH, WUM (źródła dat: `calendar_sources.md`) | studenci to duża część użytkowników; święta i ferie zmieniają ruch |
| `events.csv` | mecze Legii, koncerty na Narodowym, imprezy miejskie do końca 2026 | nietypowy ruch przy stadionach |
| `weather_hourly.parquet` | temperatura, deszcz, wiatr, zachmurzenie co godzinę | wpływ pogody na popyt |
| `air_quality_hourly.parquet` | smog (PM2.5, PM10, NO₂) co godzinę | czy smog zniechęca do roweru |
| `osm/` | z OpenStreetMap: lokale, biura, uczelnie, metro, drogi rowerowe, budynki Śródmieścia | opis otoczenia stacji; mapa 3D |
| `station_network_distance.parquet` | odległość po drogach rowerowych między każdą parą stacji | czas jazdy w symulacji |
| `population_h3.parquet` | ilu ludzi mieszka w każdym fragmencie miasta | stacje na osiedlach vs w centrum |
| `transit_stops.parquet` | przystanki i liczba odjazdów autobusów, tramwajów, metra | rower jako dojazd do komunikacji |
| `elevation.csv` | wysokość terenu przy każdej stacji | pod górkę jeździ się rzadziej (np. skarpa wiślana) |

## Jak przetwarzamy dane (`python -m src.data.build`, ok. 1–2 min)

Surowe pomiary to miliony wierszy „stacja X, godzina Y, 7 rowerów, numery …”. `build` zamienia je w tabele gotowe do analizy i do modelu:

1. **Czyszczenie:** usuwa powtórzone pomiary i wyłączone stacje, oznacza podejrzane odczyty.
2. **Odtworzenie przejazdów:** śledzi każdy numer roweru. Odrzuca pozorne przejazdy: przeskok GPS o kilkaset metrów, rower, który „zniknął” tylko na jeden pomiar, jazdę szybszą niż 30 km/h, „przejazd” dłuższy niż 4 h (to zwykle zabranie roweru do serwisu).
3. **Relokacje:** gdy 4 lub więcej rowerów naraz przenosi się między tymi samymi stacjami, to nie klienci, tylko samochód operatora.
4. **Tabele dla modelu:** ile wypożyczeń i zwrotów miała każda stacja w każdej godzinie, kiedy stacje były puste, ile rowerów jest w obiegu.
5. **Kontekst godzinowy:** do każdej godziny dopisuje pogodę, położenie słońca, typ dnia, kalendarze, wydarzenia i korki.
6. **Cechy stacji:** dla każdej stacji liczy, co jest w okolicy (lokale, biura, uczelnie w promieniu 300 m, odległość do metra i centrum, mieszkańców w promieniu 500 m).
7. **Raport jakości** (`processed/quality_report.md`): czy były przerwy w zbieraniu, ile błędów odrzucono, czy bilans rowerów się zgadza.

### Co powstaje (`processed/`)

Folder nie jest w repozytorium. Każdy odtwarza go u siebie poleceniem `build`.

| Plik | Co zawiera (prościej) | Do czego w symulacji |
|---|---|---|
| `station_hourly.parquet` | każda stacja × każda godzina: ile wypożyczeń, ile zwrotów, ile minut była pusta | **ilu klientów przychodzi na stację** (popyt) |
| `trips.parquet` | lista wszystkich przejazdów: skąd, dokąd, kiedy, ile trwał, ile km, czy e-rower | **dokąd jadą klienci i jak długo** |
| `observed_timeseries.parquet` | stan każdej stacji co 5 minut | **od czego startuje symulacja** i z czym porównujemy jej wynik |
| `rebalancing_observed.parquet` | przewozy rowerów przez operatora | **obecna strategia operatora** – punkt odniesienia dla naszych strategii |
| `fleet_timeseries.parquet` | ile rowerów jest na stacjach, w drodze, w serwisie | **ile rowerów wpuścić do symulacji** |
| `empty_periods.parquet` | każdy okres, gdy stacja była pusta | poprawka popytu (patrz niżej) |
| `context_hourly.parquet` | pogoda, kalendarz, wydarzenia, korki co godzinę | wyjaśnienie zmian popytu, scenariusze |
| `stations.parquet` | stacje: położenie, liczba stojaków, otoczenie | wyjaśnienie różnic między stacjami |

**Czas we wszystkich plikach jest w UTC** (czas uniwersalny). W `context_hourly` są gotowe kolumny z czasem warszawskim (`local_hour`, `local_date`, `day_type`).

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

## Notebooki – co już przeanalizowaliśmy

Oba notebooki czytają gotowe pliki z `processed/` (najpierw trzeba uruchomić `build`). Liczby w nich pochodzą z pierwszych dni zbierania. Po ponownym uruchomieniu przeliczą się na aktualnych danych (wartości poniżej są już przeliczone na 23.10–2.11).

### [`analiza_opisowa.ipynb`](notebooks/analiza_opisowa.ipynb) – jak wygląda system

| Sekcja | Co pokazuje | Co wyszło |
|---|---|---|
| 1. Przejazdy w czasie | liczba przejazdów na dzień i na godzinę, dni robocze vs weekend | dzień roboczy ok. **9,9 tys.** przejazdów, sobota 7,5 tys., niedziela 6,9 tys. W dzień roboczy dwa szczyty: rano o 8:00 (~610/h, dojazd do pracy i na uczelnię) i większy po południu o 16:00 (~960/h). W weekend ruch zaczyna się później. |
| 2. Czas i długość | rozkład czasu i dystansu przejazdu | typowy przejazd to **15 min i 1,8 km**. 73% przejazdów mieści się w 20 min, które są darmowe. |
| 3. Relokacje operatora | kiedy, skąd i dokąd operator przewozi rowery | ok. **70 przewozów dziennie**, zwykle po 4 rowery |
| 4. Rowery poza stacjami | gdzie ludzie zostawiają rowery poza stacją | ok. 3% przejazdów, zwykle blisko stacji |
| 5. Flota | ile rowerów jest faktycznie w obiegu | operator deklaruje 4566 rowerów, a w obiegu jest ok. **3640**; 300–400 stale w serwisie lub magazynie |
| 6. E-rowery | jak często wybierane są rowery elektryczne | to ok. 8% rowerów na stacjach, ale **19% przejazdów**: ludzie wybierają je ponad dwa razy chętniej |

### [`puste_i_przepelnione_stacje.ipynb`](notebooks/puste_i_przepelnione_stacje.ipynb) – test hipotezy H2

1. Dla każdej stacji liczy, **przez jaki procent czasu była pusta**, a przez jaki przepełniona (więcej rowerów niż stojaków).
2. Układa stacje od najrzadziej do najczęściej pustych i rysuje **krzywą Lorenza** z **współczynnikiem Giniego**. To ta sama miara, którą opisuje się nierówność dochodów: 0 znaczy, że każda stacja jest pusta tak samo często, 1 znaczy, że cały problem dotyczy jednej stacji.
3. Sprawdza **stabilność wyniku**: liczy go osobno dla każdego dnia i z pominięciem po kolei każdego dnia. Dzięki temu wiemy, że wynik nie bierze się z jednego nietypowego dnia.
4. Rysuje **mapę stacji często pustych**.

## Hipotezy – co sprawdzamy i co już wiemy

**H2. Puste stacje to problem niewielkiej części stacji, a nie całego systemu.**
*Status: wstępnie potwierdzona.* 10% najczęściej pustych stacji odpowiada za prawie połowę (44%) całego czasu, w którym jakaś stacja była pusta. 20% stacji odpowiada za ponad dwie trzecie (68%). Jednocześnie co trzecia stacja (31%) nie była pusta ani razu. Współczynnik Giniego wynosi 0,68, czyli koncentracja jest wyraźna.
*Co z tego wynika:* operator nie musi pilnować wszystkich 340 stacji. Wystarczy dobrze obsłużyć kilkadziesiąt, a symulacja pokaże, które.
*Do zrobienia:* powtórzyć na ≥ 2 tygodniach, sprawdzić, czy to te same stacje w różne dni.

**Pogoda: deszcz i zmrok zmniejszają liczbę przejazdów bardziej niż sama temperatura.**
*Status: widać, ale za mało danych na test.* W niedzielę 25.10 po rozpoczęciu deszczu (ok. 18:00) przejazdów było kilka razy mniej niż o tej porze w sobotę. Godzin z deszczem było jednak dotąd tylko ok. 20.
*Co z tego wynika:* jeśli się potwierdzi, symulacja dostanie scenariusze „deszczowy dzień” i „krótki zimowy dzień”.

**Darmowe 20 minut wpływa na to, jak długo ludzie jeżdżą.**
*Status: widoczne w danych.* 73% przejazdów kończy się w ciągu 20 minut.
*Co z tego wynika:* czas jazdy w symulacji nie może być losowany z prostego rozkładu. Musi uwzględniać tę granicę.

**E-rowery to osobna grupa klientów.**
*Status: widoczne w danych.* E-rowery to 8% rowerów na stacjach, a 19% przejazdów.
*Co z tego wynika:* w symulacji warto modelować e-rowery osobno. Do sprawdzenia: czy klienci wybierają e-rower zależnie od poziomu baterii i czy jeżdżą nim dalej.

**Operator nie nadąża z dowożeniem rowerów tam, gdzie najczęściej ich brakuje.**
*Status: do sprawdzenia.* Porównamy listę przewozów operatora z listą okresów pustych stacji.
*Co z tego wynika:* jeśli się potwierdzi, to jest miejsce na lepszą strategię, którą przetestujemy w symulacji.

**Liczba wypożyczeń zależy od otoczenia stacji (biura, uczelnie, metro, mieszkańcy).**
*Status: do sprawdzenia.* Dane są gotowe (`station_hourly` + `stations`).
*Co z tego wynika:* model popytu, który działa także dla nowej, hipotetycznej stacji.

## Ważne przy budowie modelu

- **Stacja nie blokuje zwrotów.** Na stacjach Veturilo 3.0 można zostawić rower ponad liczbę stojaków (ok. 40% pomiarów to stacja przepełniona). W symulacji klient traci tylko wtedy, gdy stacja jest **pusta**.
- **Na pustej stacji nie widać popytu.** Jeśli stacja była pusta przez godzinę, to w danych jest 0 wypożyczeń, choć klienci przychodzili. Dlatego popyt liczymy tylko z czasu, gdy rowery były dostępne (kolumna `departure_rate_per_h`), a nie z samej liczby wypożyczeń.
- **Liczba rowerów w systemie się zmienia** (serwis, magazyn): patrz `fleet_timeseries`.
- Z `trips` trzeba odfiltrować oznaczone błędy: `is_flicker`, `too_fast`, `is_long` (w `station_hourly` jest to już zrobione). Czas przejazdu jest zawyżony średnio o ok. 5 min, bo mierzymy co 5 min.
- Dni nietypowe: 31.10–2.11 (Wszystkich Świętych), 11.11, 24–26.12; zmiana czasu 25.10 (dlatego wszystko w UTC).

## Wizualizacja 3D (Unity)

Interaktywna scena 3D Warszawy, w której **odtwarzamy wybrany prawdziwy dzień** (np. piątek 23.10) w przyspieszonym tempie:
- **stacje** to słupki: wysokość to liczba rowerów, kolor to zapełnienie, a pusta stacja pulsuje na czerwono,
- **każdy przejazd z danych** to świecący rower jadący od stacji do stacji (e-rowery innym kolorem),
- **przewozy operatora** to ciężarówki z liczbą przewożonych rowerów,
- **miasto:** budynki Śródmieścia, drogi rowerowe, metro, uczelnie (z OpenStreetMap),
- **pora dnia i pogoda z danych:** słońce, zmrok, chmury, deszcz,
- **panel:** zegar, pogoda, korki, liczba rowerów w drodze i pustych stacji, wykresy dnia, oś czasu; po kliknięciu stacji jej karta.

Po co: wizualizacja pozwala **zobaczyć** problem (np. jak rano pustoszeją stacje na osiedlach, a zapełnia się centrum). Docelowo pokaże też wynik symulacji w tym samym widoku, obok prawdziwego dnia.

Jak to działa: `python -m src.viz.export` zamienia dane z `processed/` na pliki JSON (ok. 1 MB na dzień) w `unity/Assets/StreamingAssets/veturilo/`. Potem w Unity Hub otwieramy folder `unity/` (Unity 6), tworzymy pustą scenę i wciskamy **Play**: cała scena buduje się z kodu. Instrukcja, sterowanie i scenariusz 3-minutowego pokazu: [`unity/README.md`](unity/README.md).

## Pliki w repozytorium

```
collect.py                  zbieranie danych na żywo (Nextbike co 5 min, TomTom co 30 min)
.github/workflows/collect.yml   automatyczne uruchamianie collect.py na GitHubie
requirements.txt            potrzebne biblioteki Pythona

src/data/                   przygotowanie danych
  fetch_static.py           pobranie danych dodatkowych do data/static/
  calendar_data.py          daty roku szkolnego i akademickiego (ze źródłami)
  events_data.py            lista wydarzeń w Warszawie (ze źródłami)
  osm.py                    pobranie mapy z OpenStreetMap
  gtfs.py                   rozkłady jazdy ZTM -> liczba odjazdów z przystanków
  population.py             gęstość zaludnienia
  network.py                odległości między stacjami po drogach rowerowych
  build.py                  główny skrypt: dane surowe -> processed/ + raport jakości
  raw.py                    odczyt surowych plików z data/
  trips.py                  odtwarzanie przejazdów i relokacji z numerów rowerów
  aggregates.py             tabele: stacja × godzina, puste stacje, flota, bilans
  context.py                kontekst godzinowy (pogoda, słońce, kalendarz, wydarzenia, korki)
  features.py               opis otoczenia stacji
  config.py                 ścieżki i stałe
src/viz/export.py           przygotowanie danych dla wizualizacji 3D

notebooks/                  analizy (opis wyżej)
unity/                      projekt wizualizacji 3D (opis w unity/README.md)
data/                       dane zebrane na żywo + data/static/ (dane dodatkowe)
processed/                  wyniki build (tworzone lokalnie, nie ma ich w repozytorium)
```

## Jak uruchomić

```bash
git pull                                                     # nowe dane dochodzą co godzinę
pip install -r requirements.txt                              # raz
python -m src.data.fetch_static --only weather air_quality   # pogoda z ostatnich dni
python -m src.data.build                                     # -> processed/
python -m src.viz.export                                     # -> dane dla Unity (opcjonalnie)
```

Przykład wczytania danych w Pythonie:

```python
import pandas as pd
hourly = pd.read_parquet("processed/station_hourly.parquet")    # popyt: stacja × godzina
ctx = pd.read_parquet("processed/context_hourly.parquet")        # pogoda, kalendarz, ...
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
- `fetch_static` pomija gotowe pliki (`--force KROK` tworzy ponownie); kroki: `calendar events weather air_quality elevation population gtfs osm`. Grafy dróg OSM (~130 MB, poza repo, potrzebne do tras w wizualizacji): `--only osm --force osm`.
- Poza repozytorium: `processed/`, `data/static/cache/`, grafy i cache w `data/static/osm/`, dane eksportu w `unity/Assets/StreamingAssets/veturilo/`.

</details>
