# 2. Dane i ich przygotowanie

*Osoba 1. Wersja robocza na danych do 18.11.2026 (26 pełnych dób). Liczby do przeliczenia na wersji `dane-final` (1.12).*

## 2.1. Skąd są dane

Operator Veturilo nie udostępnia listy przejazdów. Publikuje tylko bieżący stan systemu w standardzie **GBFS** (General Bikeshare Feed Specification): listę stacji, liczbę rowerów i wolnych stojaków na każdej stacji, numery stojących rowerów, poziom baterii e-rowerów oraz rowery pozostawione poza stacjami. Dlatego dane zbieramy sami.

| Źródło | Co zapisujemy | Jak często | Folder |
|---|---|---|---|
| GBFS `station_status` | rowery, e-rowery, wolne stojaki, **numery rowerów**, bateria | co 5 min | `data/status/` |
| GBFS `free_bike_status` | rowery poza stacjami (położenie, numer) | co 5 min | `data/loose/` |
| GBFS `station_information` | nazwa, położenie, liczba stojaków | raz dziennie | `data/info/` |
| GBFS `system_information` | deklarowana flota, cennik | raz dziennie | `data/system/` |
| TomTom Traffic | prędkość ruchu na 10 arteriach, wypadki, zamknięcia | co 30 min | `data/traffic_flow/`, `data/incidents/` |

Zbieranie działa samo na GitHub Actions ([`collect.py`](../../collect.py), [`collect.yml`](../../.github/workflows/collect.yml)): każde uruchomienie mierzy co 5 min przez 57 min, zapisuje wynik do repozytorium i uruchamia następne; harmonogram co godzinę wznawia łańcuch, gdyby się przerwał. Dane zbieramy od **22.10.2026**, bez przerw od 26.10. Sezon Veturilo kończy się **30.11**, więc cały materiał obejmuje ok. 5 tygodni jesieni.

Dane dodatkowe (`data/static/`, skrypt `python -m src.data.fetch_static`): kalendarz (dni robocze, święta, zajęcia i sesje UW, PW, SGH, WUM), wydarzenia (mecze, koncerty), pogoda i jakość powietrza co godzinę (Open-Meteo), mapa OpenStreetMap (lokale, biura, uczelnie, metro, drogi rowerowe, budynki, granice dzielnic), sieć dróg rowerowych do odległości między stacjami, liczba mieszkańców, rozkład komunikacji miejskiej (GTFS), wysokość terenu.

## 2.2. Od pomiarów do przejazdów

Całość robi jedno polecenie `python -m src.data.build` (1–2 min). Kroki:

1. **Czyszczenie pomiarów.** Usuwamy duplikaty (< 60 s) i stacje nieaktywne. Oznaczamy, ale nie usuwamy, podejrzane odczyty: chwilowe skoki o ≥ 4 rowery, które od razu wracają (`is_spike`), oraz niezgodność liczby numerów z liczbą rowerów (`numbers_mismatch`, 0,14% rekordów).
2. **Odtworzenie przejazdów z numerów rowerów** ([`trips.py`](../../src/data/trips.py)). Rower nr *X* znika ze stacji A i po pewnym czasie pojawia się na stacji B → przejazd A→B. Czas wypożyczenia i zwrotu znamy z dokładnością do kroku pomiaru (5 min). Odrzucamy: przeskoki GPS rowerów poza stacją (< 0,5 km bez zniknięcia), „mignięcia” feedu (powrót na tę samą stację ≤ 10 min, `is_flicker`), jazdę szybszą niż 30 km/h (`too_fast`) i nieobecność dłuższą niż 4 h (`is_long`, zwykle serwis).
3. **Relokacje operatora.** Co najmniej 4 rowery znikające razem z jednej stacji i pojawiające się razem na innej to przewóz ciężarówką (`rebalancing_observed`, `type = service`).
4. **Tabele dla modelu i agentów** (tabela niżej) oraz kontekst godzinowy (pogoda, kalendarz, korki).
5. **Raport jakości** `processed/quality_report.md` i tabela `daily_check` (jakość każdego dnia).
6. **Wersja danych** `python -m src.data.manifest` → `processed/MANIFEST.json`: zakres dat, liczba dni, sumy SHA-256 plików.

**Sprawdzenie odtworzenia.** Zmiana liczby rowerów na stacji między pomiarami zgadza się z liczbą odtworzonych wypożyczeń i zwrotów w 98,5% przypadków.

## 2.3. Co powstaje

| Plik | Zawartość | Kto używa |
|---|---|---|
| `observed_timeseries` | stan każdej stacji co 5 min | start symulacji, metryki emergencji |
| `trips` | przejazdy: skąd, dokąd, kiedy, czas, km po drogach rowerowych, e-rower, bateria | model celu i czasu jazdy |
| `station_hourly` | stacja × godzina: wypożyczenia, zwroty, minuty pustej stacji | model popytu |
| `empty_periods` | każdy okres pustej stacji | H2, poprawka popytu |
| `rebalancing_observed` | przewozy operatora | strategia `operator`, hipoteza C |
| `fleet_timeseries` | rowery na stacjach, w drodze, w serwisie | wielkość floty |
| `context_hourly` | pogoda, kalendarz, wydarzenia, korki | wyjaśnienie popytu |
| `stations` | położenie, stojaki, otoczenie (POI, mieszkańcy, metro, uczelnie), dzielnica | różnice między stacjami |
| `trip_features` | opis przejazdu: pora, typ dnia, dzień zajęć, czas, km, e-rower, bateria, otoczenie startu i celu, trasa dojazdowa | typy klientów (Osoba 2) |
| `commute_pairs` | stałe trasy dojazdowe i ich regularność | stali bywalcy (Osoba 2) |
| `operator_shifts`, `operator_rule.json` | godziny pracy i reguła operatora | ciężarówki (Osoba 3) |
| `district_flows` | dzielnica × godzina: przyjazdy, wyjazdy, bilans | „oddychanie miasta” |
| `daily_check`, `MANIFEST.json` | jakość dni, wersja danych | wybór dni, powtarzalność |

### Dane dla agentów

- **Trasy dojazdowe.** Para stacji (A, B) jest *dojazdowa*, jeśli w co najmniej 3 dni robocze jest przejazd A→B w 6:30–9:30 **i** B→A w 15:00–19:00. Na 18 dniach roboczych: **1231 par**. *Regularność*: w ilu dniach roboczych przejazd powtarza się o podobnej godzinie (±15 min); mediana 4 dni rano, maksimum 18 (codziennie). Klientów nie da się rozpoznać, więc regularność jest dolnym oszacowaniem liczby stałych bywalców.
- **Zmiany pracy operatora.** Liczba przewozów w każdej godzinie, osobno dla dni roboczych i wolnych; godzina pracy = godzina, w której średnia liczba przewozów to co najmniej połowa godziny najbardziej pracowitej (dni zwijania sezonu wykluczone). Dni robocze: 0:00–1:00, 9:00–14:00, 19:00–23:00; dni wolne: 1:00, 8:00–16:00, 20:00–23:00. Plik mówi, **kiedy** operator pracuje, a nie **ile ma aut**.
- **Reguła operatora** (z hipotezy C): dowóz, gdy zapełnienie celu ma medianę 14%; zabranie przy medianie 210% (stacje przepełnione ponad stojaki); 4 rowery na kurs (kwartyle 4–6); ok. 61 kursów w dzień roboczy i 71 w wolny.
- **Opóźnienie aplikacji.** Z danych nie da się go zmierzyć: pola `last_reported` i `feed_last_updated` są puste, a pytamy co 5 min. Narzędzie do pomiaru w terenie: [`tools/app_latency.py`](../../tools/app_latency.py) (pytanie API jednej stacji co 10–15 s przy ręcznym wypożyczeniu). Jeśli pomiaru nie będzie, opóźnienie jest parametrem scenariusza (0 / 5 / 10 min).

## 2.4. Jakość i zakres

| | |
|---|---|
| Zakres (UTC) | 22.10 13:08 – 18.11 22:35 |
| Pokrycie siatki 5 min | 98,1% (9 luk > 15 min, najdłuższa 3,5 h 22.10; po ok. godzinie 10–12.11 i 16.11) |
| Pełne doby | 26: 18 roboczych, 4 soboty, 4 niedziele i święta |
| Stacje aktywne | 343–344 |
| Przejazdy klientów | ok. 216 tys. (ok. 206 tys. po odrzuceniu mignięć, zbyt szybkich i > 4 h) |
| Relokacje | 1718 przewozów, 8479 rowerów |
| Pogoda | −4…14 °C, 60 h mrozu (5–10.11 i 15.11), 49 h z opadem > 0,1 mm (najwięcej 10.11: 9 mm) |

Dzień 11.11 (Święto Niepodległości) ma pokrycie 88% i nie jest pełną dobą. Dni „zwijania sezonu” wykrywa `daily_check.wind_down` (aktywnych stacji < 85% albo rowerów na stacjach < 75% mediany wcześniejszych pełnych dni); do 18.11 nie ma takich dni. Po 30.11 sprawdzamy ostatnie dni sezonu i wykluczamy oznaczone z kalibracji i z `operator_shifts`.

**Czas** we wszystkich plikach jest w UTC; czas warszawski w kolumnach `local_hour`, `local_date`, `day_type`.

**Podział dni (propozycja zespołu):** kalibracja 26.10–15.11, walidacja 16.11–27.11; dni 28–30.11 osobno.

## 2.5. Ograniczenia danych

Pełna lista: [ograniczenia.md](ograniczenia.md). Najważniejsze dla tego rozdziału: rozdzielczość 5 min (czasy przejazdów ±5 min), relokacje widoczne tylko przy ≥ 4 rowerach, brak tożsamości klientów, utraceni klienci nieobserwowalni, tylko jesień (brak zimy i lata).
