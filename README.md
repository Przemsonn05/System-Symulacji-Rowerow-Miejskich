# Symulacja systemu rowerów miejskich Veturilo

Projekt z przedmiotu *Symulacja systemów dyskretnych*. Budujemy **symulację komputerową systemu Veturilo w Warszawie**: wirtualne stacje, rowery, klientów, którzy je wypożyczają i oddają, oraz samochody operatora, które przewożą rowery między stacjami. Symulacja ma odtwarzać rzeczywistość, więc jej parametry (ilu klientów, kiedy, skąd, dokąd) bierzemy z **danych, które sami zbieramy** od 22.10.2026.

Gdy model będzie zgodny z rzeczywistością, możemy na nim sprawdzać rzeczy, których nie da się przetestować na prawdziwym systemie, np. „co by było, gdyby operator przewoził rowery inaczej albo częściej”.

## O co pytamy

Silnik DES i kamień milowy na 5 XI: [instrukcja, model i kontrakty danych](docs/simulation.md). Na Windows uruchom `./run_milestone.ps1`; pełne wyniki lokalne powstają w `results/h3/REPORT.md`.

1. **Skąd biorą się puste stacje?** Klient przychodzi, a roweru nie ma: to podstawowy problem systemu. Chcemy wiedzieć, gdzie i kiedy to się dzieje.
2. **Od czego zależy liczba wypożyczeń?** Pora dnia, dzień tygodnia, pogoda, zajęcia na uczelniach, święta, otoczenie stacji (metro, biura, uczelnie).
3. **Która strategia przewożenia rowerów najlepiej zmniejsza liczbę klientów, którzy odchodzą z niczym?** To odpowiemy symulacją.

## Stan prac (4.11.2026)

| Etap | Stan |
|---|---|
| Automatyczne zbieranie danych co 5 minut | ✅ działa samo od 22.10, bez przerw od 26.10 |
| Dane dodatkowe: pogoda, kalendarz, wydarzenia, mapa miasta, mieszkańcy, komunikacja | ✅ pobrane, są w repozytorium |
| Przetworzenie danych: odtworzenie przejazdów, relokacji, pustych stacji | ✅ jedno polecenie: `python -m src.data.build` |
| Analiza opisowa i test pierwszej hipotezy (2 notebooki) | ✅ wstępnie; do przeliczenia na pełnych 2 tygodniach |
| Wizualizacja 3D odtwarzająca prawdziwy dzień (z pokazem z komentarzem) | ✅ działa |
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

## Modele zachowań, kalibracja i walidacja (`python -m src.model.pipeline`, ok. 10 min)

Jedno polecenie buduje modele, kalibruje je, sprawdza na dniach, których model „nie widział”, i testuje hipotezy H1, H4, H5a. Wyniki trafiają do `processed/model/`, a raport z tabelami i wykresami to notebook [`modele_walidacja.ipynb`](notebooks/modele_walidacja.ipynb). Podział dni ustawia `--calib OD DO --valid OD DO` (domyślnie kalibracja 23–29.10, walidacja 30.10–4.11); `--build` najpierw przebudowuje `processed/`, `--quick` to szybki test łańcucha.

| Plik (`src/model/`) | Co robi |
|---|---|
| `demand.py` | **model popytu**: regresja ujemna dwumianowa wypożyczeń na stację × godzinę: własny poziom każdej stacji w każdej porze dnia, wspólny profil godzinowy osobno dla dni roboczych i weekendów oraz 3 czynniki wybrane na danych (temperatura z członem kwadratowym, przycięta do zakresu danych, i korki). Godziny pustej stacji są wyłączone przez offset „minuty z rowerem”. Daje λ, czyli średnią liczbę chętnych na godzinę. Pełny model ze wszystkimi czynnikami służy tylko do hipotez. |
| `od.py` | **cel podróży**: macierz OD z przejazdów + model grawitacyjny (popularność celu × e^(−β·km)); w symulacji macierz wygładzona grawitacją |
| `duration.py` | **czas jazdy**: log-normalny zależny od odległości, osobno powroty na tę samą stację; czas z danych jako przedział ±5 min |
| `calibration.py` | **kalibracja** Optuną parametrów klienta (`empty_retry_probability`, `max_walk_km`, `full_redirect_probability`) i **walidacja** w symulacji `src/simulation`: doba po dobie od stanu z północy, przewozy operatora z danych, metryki, modele bazowe (persystencja, średnia historyczna, stan z północy) |
| `hypotheses.py` | **H1, H4, H5a**: współczynniki z 95% CI (błędy klastrowane po godzinie), test LR członu T² |
| `pipeline.py` | cały łańcuch jednym poleceniem |

Wyniki dla symulacji (Osoba 3): `processed/model/demand_model.pkl`, `od_model.pkl`, `duration_model.pkl` (dopasowane na wszystkich dniach) i `sim_params.json` (skalibrowane parametry klienta). W symulacji: `od_model` jako `od_matrix` (OD zależne od pory dnia), `duration_model` jako `ride_time_model` z `ride_sigma` z `sim_params.json`, λ z `demand.rate(station_ids, context_rows)` (przykład: `HourlyRates` w `src/model/calibration.py`).

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

## Hipotezy

Hipotezy H1–H6 pochodzą z planu projektu (issues #1–#3). Trzy dodatkowe (oznaczone literami A–C) wynikły z analizy zebranych danych.

### Podsumowanie

| | Hipoteza | Stan | Czym badamy |
|---|---|---|---|
| **H1** | Pogoda wpływa na liczbę przejazdów | pierwszy sygnał, za mało danych | model popytu |
| **H2** | Puste stacje to problem niewielkiej części stacji | ✅ wstępnie potwierdzona | dane (notebook) |
| **H3** | Lepsza strategia relokacji zmniejsza utracony popyt | ✅ eksperyment wstępny; do kalibracji | symulacja DES |
| **H4** | Zajęcia na uczelniach zwiększają popyt przy uczelniach | ⏳ do zbadania | model popytu |
| **H5a** | W korki ludzie częściej wybierają rower | ⏳ do zbadania | model popytu |
| **H5b** | Korki spowalniają ciężarówki i osłabiają relokację | ⏳ do zbadania | symulacja DES |
| **H6** | Otoczenie stacji wyjaśnia różnice w popycie | ⏳ do zbadania | model popytu |
| **A** | Darmowe 20 minut kształtuje długość jazdy | ✅ widoczne w danych | dane |
| **B** | E-rowery to osobna grupa klientów | ✅ widoczne w danych | dane |
| **C** | Operator nie nadąża tam, gdzie najczęściej brakuje rowerów | ⏳ do zbadania | dane |

### H1. Pogoda

**Hipoteza:** deszcz i zmrok zmniejszają liczbę przejazdów bardziej niż sama temperatura. Temperatura działa jak „odwrócone U”: za zimno i za gorąco zniechęca do roweru.

**Stan:** pierwszy sygnał. W niedzielę 25.10 po rozpoczęciu deszczu (ok. 18:00) przejazdów było kilka razy mniej niż o tej porze w sobotę. Danych jest jednak za mało: ok. 20 godzin z deszczem i temperatury tylko 1–14 °C.

**Do zbadania:** wpływ opadu, temperatury i zmroku w modelu popytu (regresja ujemna dwumianowa), z 95% przedziałami ufności i testem członu kwadratowego temperatury. Potrzeba więcej dni deszczowych i mroźnych.

**Po co:** scenariusze „deszczowy dzień” i „krótki zimowy dzień” w symulacji.

### H2. Koncentracja pustych stacji

**Hipoteza:** brak rowerów nie rozkłada się równo po mieście. Niewielka część stacji odpowiada za większość czasu, w którym stacje są puste.

**Stan:** ✅ wstępnie potwierdzona ([notebook](notebooks/puste_i_przepelnione_stacje.ipynb)). Współczynnik Giniego czasu pustek wynosi 0,68. 10% najczęściej pustych stacji odpowiada za 44% czasu pustek, a 20% stacji za 68%. Co trzecia stacja (31%) nie była pusta ani razu.

**Do zbadania:** powtórzyć na ≥ 2 tygodniach danych (z bootstrapem po dniach) i sprawdzić, czy często puste są co dzień te same stacje.

**Po co:** strategia relokacji może skupić się na kilkudziesięciu stacjach zamiast na wszystkich 340.

### H3. Strategie relokacji

**Hipoteza:** lepsza strategia przewożenia rowerów wyraźnie zmniejsza utracony popyt (klientów, którzy odchodzą od pustej stacji), a każda kolejna ciężarówka daje coraz mniejszy zysk.

**Stan:** ✅ wykonano wstępne porównanie 3 strategii × 1–4 ciężarówki × 30 replikacji. [Raport z 95% CI, Wilcoxonem i frontem Pareto](docs/milestone-2026-11-05/REPORT.md). Dla strategii progowej z 4 ciężarówkami średni utracony popyt spadł z 379,8 do 149,4 na dobę w przyjętym modelu. Popyt i OD są estymatami roboczymi, a parametry jazdy i agentów wymagają kalibracji; wynik nie rozstrzyga jeszcze H3 dla rzeczywistego Veturilo.

**Do zbadania:** porównanie strategii (brak, obecna strategia operatora, progowa, nocna, predykcyjna) z 1–4 ciężarówkami. Każdy wariant w 30 powtórzeniach ze wspólnymi liczbami losowymi, wynik ze średnią i 95% przedziałem ufności, porównanie testem Wilcoxona. Wynik to wykres „utracony popyt vs kilometry ciężarówek”.

### H4. Kalendarz akademicki i szkolny

**Hipoteza:** w dni zajęć popyt na stacjach w pobliżu uczelni jest wyraźnie wyższy niż w dni wolne od zajęć.

**Stan:** ⏳ do zbadania. Kalendarze UW, PW, SGH, WUM i szkół są gotowe (`data/static/calendar.csv`).

**Do zbadania:** interakcja „dzień zajęć × stacja przy uczelni” w modelu popytu. Najlepiej porównać okres zajęć z przerwą świąteczną albo sesją, bo na razie prawie wszystkie zebrane dni to dni zajęć.

### H5. Korki

**H5a. Hipoteza:** przy większych korkach ludzie częściej wybierają rower.
**Do zbadania:** wskaźnik korków z TomTom w modelu popytu, z kontrolą godziny, żeby nie pomylić efektu korka z efektem szczytu.

**H5b. Hipoteza:** korki spowalniają ciężarówki operatora, więc relokacja działa gorzej.
**Do zbadania:** scenariusz w symulacji z wolniejszymi ciężarówkami.

**Stan:** ⏳ do zbadania. Dane o ruchu z TomTom są zbierane co 30 minut.

### H6. Otoczenie stacji

**Hipoteza:** to, co jest wokół stacji (biura, uczelnie, lokale, metro, liczba mieszkańców), wyjaśnia większość różnic w popycie między stacjami. Stacje „biurowe” mają szczyt rano, a „restauracyjne” wieczorem.

**Stan:** ⏳ do zbadania. Dane są gotowe (`station_hourly` + `stations`).

**Do zbadania:** cechy otoczenia × pora dnia w modelu popytu, sprawdzone na stacjach pominiętych przy dopasowaniu modelu (leave-stations-out).

**Po co:** model popytu, który przewidzi ruch także dla nowej, hipotetycznej stacji.

### A. Darmowe 20 minut

**Hipoteza:** darmowe pierwsze 20 minut w cenniku kształtuje to, jak długo ludzie jeżdżą.

**Stan:** ✅ widoczne w danych. 73% przejazdów kończy się w ciągu 20 minut.

**Do zbadania:** jak wyraźne jest „spiętrzenie” tuż przed 20. minutą.

**Wniosek dla modelu:** czasu jazdy nie można losować z prostego rozkładu. Musi uwzględniać ten próg.

### B. E-rowery

**Hipoteza:** e-rowery to osobna grupa klientów.

**Stan:** ✅ widoczne w danych. E-rowery to 8% rowerów na stacjach, ale 19% przejazdów.

**Do zbadania:** czy klienci wybierają e-rower zależnie od poziomu baterii i czy jeżdżą nim dalej.

**Wniosek dla modelu:** e-rowery modelujemy jako osobny strumień popytu.

### C. Relokacje operatora

**Hipoteza:** operator nie nadąża z dowożeniem rowerów tam, gdzie najczęściej ich brakuje.

**Stan:** ⏳ do zbadania.

**Do zbadania:** porównać przewozy operatora (`rebalancing_observed`) z okresami pustych stacji (`empty_periods`): czy rowery trafiają na stacje często puste i jak szybko po opustoszeniu.

**Po co:** jeśli się potwierdzi, jest miejsce na lepszą strategię, którą przetestujemy w symulacji (H3).

## Wizualizacja 3D (Unity)

Interaktywna scena 3D Warszawy, w której **odtwarzamy wybrany prawdziwy dzień** w przyspieszonym tempie. Korzysta ze wszystkich zebranych danych:

| Co widać | Skąd |
|---|---|
| **stacje** jako słupki w trzech widokach: *zapełnienie* (pusta pulsuje na czerwono), *bilans 1 h* (które stacje tracą, a które zyskują rowery), *H2* (gdzie najczęściej brakuje rowerów) | stan stacji co 5 min |
| **każdy przejazd** jako świecący rower jadący po drogach rowerowych (e-rowery innym kolorem), rowery zostawione poza stacjami | odtworzone przejazdy, `data/loose` |
| **łuki OD**: najczęstsze trasy ostatniej godziny; **ślady całego dnia** narastające do wieczora (główne korytarze rowerowe) | przejazdy |
| **utracony popyt**: heksagony rosnące tam, gdzie klienci przychodzą do pustej stacji (szacunek) | stan stacji + popyt z `station_hourly` |
| **ciężarówki operatora** z liczbą przewożonych rowerów | relokacje |
| **miasto:** ok. 180 tys. budynków całej Warszawy z oknami, Wisła, mosty, zieleń i ok. 90 tys. drzew, główne ulice z latarniami, metro M1/M2, tory, drogi rowerowe, granica miasta | OpenStreetMap |
| **pora dnia i pogoda:** słońce, zmierzch (zapalają się okna i latarnie), gwiazdy, cienie chmur sunące z wiatrem, mgła, deszcz i mokre, błyszczące ulice | Open-Meteo |
| **grafika (URP):** bloom, tonemapping, SSAO, Wisła odbijająca miasto i światła | – |
| **korki i utrudnienia** na 10 arteriach, **wydarzenia** (słup światła nad stadionem), **mieszkańcy** (heksagony) | TomTom, `events.csv`, Kontur |
| **panele:** zegar, pogoda, jakość powietrza, KPI, wykresy dnia, lista stacji pustych najdłużej, karta stacji z otoczeniem | wszystko powyżej |

**Kliknięcie roweru lub ciężarówki** – kamera jedzie za nim (skąd, dokąd, dystans, czas). **X** dzieli ekran na pół i porównuje dwa dni o tej samej godzinie (np. dzień roboczy i niedzielę); po zbudowaniu DES ten sam widok pokaże model obok rzeczywistości.

Klawisz **T** uruchamia **pokaz z komentarzem** (ok. 2 min): kamera, widoki i napisy prowadzą przez cały dzień, od porannego szczytu przez hipotezę H2 do zmierzchu. Liczby w napisach pochodzą z danych.

Po co: wizualizacja pozwala **zobaczyć** problem (np. jak rano pustoszeją stacje na osiedlach, a zapełnia się centrum). Docelowo pokaże też wynik symulacji w tym samym widoku, obok prawdziwego dnia.

**Jak uruchomić:**
1. `python -m src.viz.export` – dane z `processed/` → pliki JSON w `unity/Assets/StreamingAssets/veturilo/` (ok. 1 MB na dzień).
2. Unity Hub → *Add project from disk* → folder `unity/` (Unity 6000.0.85f1) → scena `Assets/Scenes/Veturilo.unity` → **Play**.
3. Do prezentacji bez edytora: menu **Veturilo → Zbuduj aplikację (Windows)** → `unity/Build/Veturilo.exe`.

Instrukcja, sterowanie i scenariusz pokazu: [`unity/README.md`](unity/README.md).

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
src/model/                  modele zachowań, kalibracja, walidacja, hipotezy
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
python -m src.model.pipeline                                 # -> processed/model/ (wyniki w notebooks/modele_walidacja.ipynb)
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
- `fetch_static` pomija gotowe pliki (`--force KROK` tworzy ponownie); kroki: `calendar events weather air_quality elevation population gtfs osm`. Grafy dróg OSM (~150 MB, poza repo): `--only osm --force osm`. Podkład mapy (`basemap.parquet`) i policzone trasy wizualizacji (`viz_routes_*.parquet`) są w repo – graf jest potrzebny tylko do tras nowych par stacji.
- Poza repozytorium: `processed/`, `data/static/cache/`, grafy i cache w `data/static/osm/`, dane eksportu w `unity/Assets/StreamingAssets/veturilo/`.

</details>
