# Symulacja systemu rowerów miejskich Veturilo

Projekt z przedmiotu *Symulacja systemów dyskretnych*. Budujemy **agentową symulację Veturilo w Warszawie**: stacje, rowery, klienci, którzy je wypożyczają i oddają, oraz ciężarówki operatora, które przewożą rowery między stacjami. Wszystkie liczby w modelu (ilu klientów, kiedy, skąd, dokąd) bierzemy z **danych, które sami zbieramy co 5 minut** od 22.10.2026.

Gdy model zachowuje się jak prawdziwe miasto, sprawdzamy na nim to, czego nie da się przetestować na żywym systemie, np. „co by było, gdyby operator przewoził rowery inaczej albo miał więcej ciężarówek”.

**Główne pytania**
1. **Skąd biorą się puste stacje?** Gdzie i kiedy klient przychodzi, a roweru nie ma.
2. **Od czego zależy liczba wypożyczeń?** Pora dnia, dzień tygodnia, pogoda, zajęcia na uczelniach, korki, otoczenie stacji.
3. **Która strategia przewożenia rowerów najlepiej zmniejsza liczbę klientów odchodzących z niczym?** Na to odpowiada symulacja.

**Ważne linki:** [silnik symulacji](docs/simulation.md) · [kontrakty między częściami](docs/kontrakty.md) · [raport końcowy](docs/raport/README.md) · [przykładowy przebieg z agentami](docs/przyklad_przebiegu/) · [wyniki emergencji](docs/wyniki/emergencja.md) · [hipotezy z danych](docs/wyniki/hipotezy_osoba1.md) · [eksperyment H3 z 5.11](docs/milestone-2026-11-05/REPORT.md) · [wizualizacja 3D](unity/README.md)

---

## Spis treści

1. [Jak uruchomić](#jak-uruchomić)
2. [Stan prac (19.11.2026)](#stan-prac-19112026)
3. [Najważniejsze wyniki](#najważniejsze-wyniki)
4. [Hipotezy](#hipotezy)
5. [Dane](#dane)
6. [Modele, symulacja, metryki, 3D: jak to działa](#modele-symulacja-metryki-3d-jak-to-działa)
7. [Pliki w repozytorium](#pliki-w-repozytorium)

---

## Jak uruchomić

```bash
git pull                                                     # nowe dane dochodzą co godzinę
pip install -r requirements.txt                              # raz (symulacja: requirements-simulation.txt)
python -m src.data.fetch_static --only weather air_quality   # dociągnięcie pogody z ostatnich dni
python -m src.data.build                                     # dane surowe -> processed/   (1–2 min)
python -m src.model.pipeline                                 # modele + kalibracja + walidacja -> processed/model/  (ok. 10 min)
python -m src.metrics.hypotheses                             # hipotezy H2, A, B, C -> docs/wyniki/
python -m src.metrics processed --sim <katalog przebiegu>    # emergencja: dane vs symulacja -> docs/wyniki/emergencja.md
python -m src.viz.export                                     # dane -> Unity
python -m src.viz.export_sim <katalogi przebiegów>           # symulacja -> Unity (do 4 strategii)
python -m pytest                                             # testy
```

**Albo wszystko naraz:** `./run_all.ps1` (Windows/PowerShell; `-Quick` = szybkie sprawdzenie łańcucha w 10–15 min). Uruchamianie symulacji i eksperymentów: [`docs/simulation.md`](docs/simulation.md). Wizualizacja: Unity 6000.0.85f1, projekt `unity/`, scena `Assets/Scenes/Veturilo.unity` → Play ([szczegóły](unity/README.md)).

Folder `processed/` nie jest w repozytorium: każdy tworzy go u siebie poleceniem `build`.

---

## Stan prac (19.11.2026)

Legenda: ✅ zrobione · 🟡 zrobione częściowo / wstępnie · ⬜ do zrobienia

**Terminy:** 19.11 – dane dla agentów, modele w silniku, silnik przerobiony na agentów · 26.11 – stabilne API `emergence_report` · **30.11** – koniec sezonu Veturilo (koniec danych) · **1.12** – zamrożenie danych (`dane-final`, [instrukcja](docs/raport/powtarzalnosc.md)) · 3.12 – wszyscy agenci gotowi, zamrożenie `sim_params.json` · 17.12 – eksperymenty i hipotezy · 14.01 – raport końcowy.

### W skrócie

| Część | Stan |
|---|---|
| Zbieranie danych (co 5 min, automatycznie) | ✅ działa samo od 22.10; 26 pełnych dób (18 roboczych), ok. 216 tys. przejazdów, pokrycie 98% (krótkie luki 10–12.11 i 16.11) |
| Przetwarzanie danych + dane dla agentów | ✅ jedno polecenie `build` |
| Pomiar emergencji (te same metryki dla danych i symulacji) | ✅ przeliczone na 26 dniach i na przebiegu silnika agentowego |
| Hipotezy z danych H2, A, B, C | ✅ przeliczone na 26 dniach (ostatecznie na `dane-final`) |
| Modele popytu, celu podróży i czasu jazdy + kalibracja i walidacja | 🟡 działają w silniku agentowym, kalibracja na 19 dniach; brak typów klientów i osobnego agenta-klienta |
| Silnik agentowy (SimPy + `src/agents/`): stacja, ciężarówka, dyspozytor Contract Net, pole „ciśnienia”, 7 strategii | ✅ (18.11, Osoba 3); eksperymenty do policzenia po 3.12 |
| Wizualizacja 3D: prawdziwy dzień i symulacja obok siebie | ✅ zbudowany `Veturilo.exe`, wczytuje przebiegi silnika agentowego; brak filmu |
| Raport końcowy | 🟡 spis rozdziałów i podział pracy; wersje robocze rozdziałów 2, 3, 9, 12 (Osoba 1), materiał do rozdziału 4 (`docs/ODD.md`) |

### Osoba 1: dane dla agentów, emergencja, 3D, raport

| Zadanie | Stan | Szczegóły |
|---|---|---|
| 1a. Dane na pełnym okresie | 🟡 | `processed/` i oba notebooki (`analiza_opisowa`, `puste_i_przepelnione_stacje`) przeliczone na 26 pełnych dobach (23.10–18.11); są dni z mrozem (do −4 °C, 5–10.11 i 15.11) i deszczem (10.11: 9 mm). Kontrola „zwijania sezonu” działa (`daily_check.wind_down`, tabela w `quality_report.md`): do 18.11 brak takich dni. **Zostaje na 1.12:** wyłączyć `cron` w `collect.yml`, ostatni `build`, `MANIFEST.json` z etykietą i tag `dane-final` ([instrukcja](docs/raport/powtarzalnosc.md)). |
| 1b. Opis przejazdów i trasy dojazdowe | ✅ | `trip_features.parquet` (pora, typ dnia, dzień zajęć, czas, km, e-rower, bateria, otoczenie startu i celu, dzielnice) i `commute_pairs.parquet`: 1231 par A→B rano / B→A po południu (≥ 3 dni robocze), regularność ±15 min (mediana 4 dni, max 18). |
| 1c. Opóźnienie aplikacji | 🟡 | Z zebranych danych nie da się go zmierzyć (feed nie podaje czasu aktualizacji). Gotowe narzędzie do pomiaru w terenie: [`tools/app_latency.py`](tools/app_latency.py). **Pomiar trzeba zrobić do 30.11** (wymaga wypożyczenia roweru na miejscu); jeśli się nie uda, opóźnienie zostaje parametrem scenariusza `app_delay_min` (0/5/10 min) – silnik już go obsługuje. |
| 1d. Zmiany ciężarówek operatora | ✅ | `operator_shifts.parquet` (godziny pracy osobno dla dni roboczych i wolnych, bez dni zwijania sezonu) + `operator_rule.json` (dowóz przy zapełnieniu ok. 14%, 4 rowery na kurs, ok. 61 kursów w dzień roboczy). |
| 1e. Bilans dzielnic | ✅ | `district_flows.parquet` (dzielnica × godzina: przyjazdy, wyjazdy, bilans). |
| 2. Metryki emergencji (`src/metrics/`) | ✅ | Rytm dnia, Gini i krzywa Lorenza pustek, długość pustek, indeks Morana, fale pustek, bilans dzielnic, modele zerowe „inny dzień” i „zamiana miejsc” (1000 razy), `emergence_report()`, `compare()`, testy. Przeliczone na 26 dniach i porównane z przebiegiem **silnika agentowego** (`operator_2`, 17.11): [`emergencja.md`](docs/wyniki/emergencja.md). |
| 3. Hipotezy H2, A, B, C | ✅ | Przeliczone na 26 dniach, wyniki niżej i w [`hipotezy_osoba1.md`](docs/wyniki/hipotezy_osoba1.md); 10 stacji najczęściej pustych rano dla Osoby 2: [`top10_puste_rano.csv`](docs/wyniki/top10_puste_rano.csv). Ostatecznie na `dane-final`. |
| 4. Wizualizacja 3D | 🟡 | Gotowe: wczytanie symulacji (`export_sim`), podzielony ekran dane \| model (X), 4 strategie z licznikiem utraconych klientów (Z), agenci-klienci (J), decyzje dyspozytora (O), fale pustek (B), „ciśnienie” (Y), pasek zdarzeń, pokaz z komentarzem (T), zbudowany `Veturilo.exe`. **19.11:** eksport sprawdzony na prawdziwym silniku agentowym (zdarzenia `user_wait_*`, `user_walk`, `user_leave`, `signal_on/off`, `task_announced`, `bid`, `task_awarded`, `truck_load/unload`, kolumna `pressure`): 4 przebiegi 17.11 (`none_1`, `operator_2`, `threshold_2`, `pressure_2`, ziarno 1000); lista przebiegów z pełnymi tabelami w [kontraktach](docs/kontrakty.md); `run_all.ps1` liczy i eksportuje też `pressure_2`. Do zrobienia: **film** z pokazu, przebiegi z aplikacją 0% / 80% (po 3.12). |
| 5. Raport i `run_all.ps1` | 🟡 | `run_all.ps1` (z `-Quick`, domyślnie dzień walidacyjny 17.11) ✅, [spis rozdziałów](docs/raport/README.md) ✅, [ograniczenia](docs/raport/ograniczenia.md) i [powtarzalność](docs/raport/powtarzalnosc.md) ✅, testy na GitHubie ✅, issues #1–#3 zamknięte, #5–#7 założone ✅. Wersje robocze rozdziałów [2](docs/raport/02_dane.md), [3](docs/raport/03_analiza_opisowa.md), [9](docs/raport/09_emergencja.md) (część Osoby 1, dane vs silnik agentowy), [12](docs/raport/12_kto_co_jak_uruchomic.md), przeliczone na 26 dniach. |

### Osoba 2: klienci, parametry z danych, kalibracja, walidacja

| Zadanie | Stan | Szczegóły |
|---|---|---|
| 1. Modele w silniku | ✅ | `demand_model.pkl`, `od_model.pkl`, `duration_model.pkl`, `sim_params.json` działają w silniku agentowym (kalibracja 23.10–10.11, walidacja 11–17.11). **Do zrobienia: przeliczyć H3 na tych modelach** (eksperyment z 5.11 jest na roboczych parametrach). |
| 2. Typy klientów | ⬜ | Reguły (dojeżdżający, student, rekreacyjny, e-rowerzysta, pozostali), udziały typów na stacji × godzinie, kontrola Gaussian Mixture. Dane wejściowe gotowe (`trip_features`). Silnik ma już pole `user_type` w zdarzeniach. |
| 3. Cel i czas jazdy osobno dla typów | ⬜ | Model grawitacyjny dla każdego typu; próg 20 min w czasie jazdy (obecny rozkład log-normalny go nie odtwarza, por. hipoteza A); wybór e-roweru zależny od baterii (por. hipoteza B). |
| 4. Agent-klient (`src/agents/user.py`) | 🟡 | W silniku (Osoba 3) klient czeka w kolejce FIFO przy pustej stacji z limitem cierpliwości, idzie do sąsiedniej albo rezygnuje i może mieć aplikację z opóźnieniem (`app_share`, `app_delay_min`). Brakuje: osobnego agenta z wyborem logit, typów klientów, pamięci stałych dojeżdżających, testów. |
| 5. Kalibracja | 🟡 | Zachowanie przy pustej stacji wprost z danych (`spillover.py`: 19% klientów pustej stacji wypożycza u sąsiada do ok. 600 m); Optuna dobiera resztę na 19 dniach (`empty_retry_probability` = 0,19, `max_walk_km` = 0,83, `full_redirect_probability` = 0,23). Do zrobienia: parametry agenta-klienta, ocena kilku metryk naraz, opis pewności parametrów, źródło każdego parametru w `sim_params.json`. |
| 6. Walidacja wzorców | 🟡 | Walidacja 11–17.11: RMSE zapełnienia stacji 3,46 (model bazowy 3,97). Porównanie metryk emergencji dane vs silnik agentowy w [`emergencja.md`](docs/wyniki/emergencja.md): rytm dnia odtworzony, wzór przestrzenny pustek nie (Moran 0,04 vs 0,60). Do zrobienia: tabela „wzorzec – dane – model – czy odtworzony” na tygodniu walidacyjnym; porównanie z wersją uproszczoną. |
| 7. Hipotezy H1, H4, H5a, H6 | 🟡 | H1, H4, H5a: oszacowania w notebooku [`modele_walidacja.ipynb`](notebooks/modele_walidacja.ipynb). H6: brak w kodzie. Do zrobienia: pełne dane, H6 na stacjach pominiętych przy dopasowaniu. |

### Osoba 3: silnik agentowy, dyspozytor, eksperymenty

Szczegóły: [`docs/simulation.md`](docs/simulation.md), [`docs/ODD.md`](docs/ODD.md), [prezentacja](PREZENTACJA_silnik_agentowy_issue_7.md), `python demo.py`.

| Zadanie | Stan | Szczegóły |
|---|---|---|
| Fundament | ✅ | Graf stacji, silnik SimPy, rowery z numerami, ciężarówki z korkami (TomTom), wspólne liczby losowe, dziennik zdarzeń (`events.parquet`). |
| 1. Wspólna klasa `Agent` (`src/agents/base.py`) | ✅ | `Agent`, `AgentMessage`, widoki lokalne (`StationView`, `AppView`, `TruckView`, `DispatcherView`): żaden agent nie widzi całego miasta. |
| 2. Agent-stacja | ✅ | Prognoza na horyzont H, sygnał „brakuje / nadmiar” z histerezą (`signal_on/off`), kolejka FIFO czekających. |
| 3. „Ciśnienie” na grafie (`field.py`) | ✅ | Dyfuzja sygnału na sąsiadów do 1,5 km (`pressure_radius_km`), kolumna `pressure` w `station_timeseries`. |
| 4. Agent-ciężarówka | ✅ | Jazda w korkach, zmiany pracy (`truck_shift_hours`), oferty w przetargu. |
| 5. Agent-dyspozytor | ✅ | Contract Net (`task_announced` → `bid` → `task_awarded`), 7 strategii: `none`, `operator`, `threshold`, `night`, `predictive`, `pressure`, `operator_rule`. |
| 6. Połączenie z klientami Osoby 2 | 🟡 | Modele Osoby 2 i aplikacja z opóźnieniem działają w silniku, symulacja wielodniowa. Brak: osobnego agenta-klienta z typami, stałych dojeżdżających. |
| 7. Testy | ✅ | 77 testów (w tym `tests/test_agents.py`: przetarg, histereza, dyfuzja, kolejka, zmiany pracy, wiele dni, wszystkie strategie). |
| 8. Eksperymenty | 🟡 | Kod gotowy (`agent_experiments.py`): H3 dla 7 strategii, H5b, przejście fazowe, efekt stadny, zasięg „ciśnienia”, „co jeśli”, tornado i Morris (SALib). Wyniki do policzenia na `sim_params.json` z 3.12. Orientacyjnie (17.11, 1 przebieg): utracony popyt `none_1` 542, `operator_2` 469, `pressure_2` 472, `threshold_2` 366. |
| 9. Dokumentacja | ✅ | `docs/simulation.md` (agenci, diagram Contract Net), `docs/ODD.md` (ODD+D). |

---

## Najważniejsze wyniki

1. **Dane są nasze.** Operator nie udostępnia listy przejazdów, tylko stan stacji i numery stojących rowerów. Zapisujemy to co 5 minut i **sami odtwarzamy przejazdy**: rower nr 12345 zniknął ze stacji A, a 15 min później pojawił się na B, więc ktoś przejechał z A do B.
2. **Odtworzenie działa.** Przyrost rowerów na stacji zgadza się z liczbą odtworzonych przejazdów w 98,5% przypadków. Błędy feedu (rower „znika” na chwilę, skoki GPS) są wykrywane i odrzucane.
3. **Skala:** ok. 8,3 tys. przejazdów w dzień roboczy, 6,8 tys. w sobotę, 6 tys. w niedzielę. Szczyty o 8:00 (~540/h) i 16:00 (~790/h). Typowy przejazd: 15 min i 1,9 km. Operator robi ok. 60–70 przewozów dziennie, zwykle po 4 rowery. Na stacjach stoi ok. 3 490 rowerów (operator deklaruje 4 566). Z ochłodzeniem w listopadzie przejazdów ubywa (do 8.11: ok. 9,7 tys. w dzień roboczy, od 9.11: ok. 6,1 tys.).
4. **Puste stacje są skupione:** 10% stacji odpowiada za 44% czasu pustek, często to te same stacje i leżą obok siebie (Moran I = 0,60; H2).
5. **Pustki rozchodzą się falami:** prawie połowa (47%) przypadków opróżnienia stacji ma sąsiada (≤ 800 m), który opróżnił się w ciągu 20 min. Fal jest więcej i są większe, niż wynikałoby z samej pory dnia i z tego, jak często stacje bywają puste (oba modele zerowe: p ≤ 0,002). To emergencja widoczna w danych.
6. **Operator jeździ we właściwe miejsca, ale nie nadąża** (hipoteza C): kończy tylko 8% pustek, dowozi średnio 50 min po opróżnieniu stacji. Jest więc miejsce na lepszą strategię.
7. **Silnik agentowy odtwarza rytm dnia** (szczyt o 16:00, popyt dnia 17.11), ale stacje pustoszeją w nim za często (340 vs 176 razy na dobę) i bez wzoru przestrzennego (Moran 0,04 vs 0,60; fale nie różnią się od losowych). Lepsza relokacja zmniejsza utracony popyt (17.11: bez relokacji 542, operator 469, progowa 366 klientów) i liczbę fal. Brakujący wzór przestrzenny to zadanie dla agenta-klienta (typy, aplikacja) i kalibracji na wielu metrykach.

**Czy danych jest dość?** Na dni robocze tak (18). Na weekendy na granicy (4 soboty, 4 niedziele i święta). Pogoda: −4…14 °C, 60 h mrozu, 49 h z opadem – tylko jesień. Dane zbieramy do końca sezonu (30.11).

---

## Hipotezy

H1–H6 pochodzą z planu projektu, A–C wynikły z analizy danych.

| | Hipoteza | Stan | Wynik / co dalej | Kto |
|---|---|---|---|---|
| **H1** | Pogoda zmienia liczbę wypożyczeń (deszcz, zmrok, temperatura jako „odwrócone U”) | 🟡 | Pierwsze oszacowanie w modelu popytu (13 dni). Od 7.11 są dni z mrozem (do −4 °C) i deszczem – do przeliczenia na pełnych danych. | Osoba 2 |
| **H2** | Puste stacje to problem niewielkiej części stacji | ✅ | Gini czasu pustek 0,67 (95% CI 0,65–0,70), 10% stacji = 44% pustek (26 dni); zbiory najczęściej pustych stacji z różnych dni pokrywają się 3× częściej niż losowo; skupiska w przestrzeni (Moran 0,60). [Top 10 rano](docs/wyniki/top10_puste_rano.csv). | Osoba 1 |
| **H3** | Lepsza strategia przewożenia zmniejsza utracony popyt; każda kolejna ciężarówka daje mniej | 🟡 | Wstępnie: strategia progowa z 4 ciężarówkami zmniejsza utracony popyt z 380 do 149 klientów/dobę, ale na roboczych parametrach. Do przeliczenia na modelach Osoby 2 i 6 strategiach. [Raport](docs/milestone-2026-11-05/REPORT.md). | Osoba 3 |
| **H4** | Zajęcia na uczelniach zwiększają popyt przy uczelniach | 🟡 | Model gotowy, ale prawie wszystkie zebrane dni to dni zajęć; trzeba porównać z przerwą świąteczną. | Osoba 2 |
| **H5a** | W korki ludzie częściej wybierają rower | 🟡 | Pierwsze oszacowanie w modelu popytu (z kontrolą godziny). | Osoba 2 |
| **H5b** | Korki spowalniają ciężarówki i psują relokację | ⬜ | Silnik umie spowalniać ciężarówki; eksperyment do zrobienia. | Osoba 3 |
| **H6** | Otoczenie stacji wyjaśnia różnice w popycie | ⬜ | Dane gotowe (`stations` + `station_hourly`); potrzebne do scenariusza „nowa stacja”. | Osoba 2 |
| **A** | Darmowe 20 minut kształtuje długość jazdy | ✅ | 77% przejazdów mieści się w 20 min; tuż za progiem przejazdów ubywa szybciej (0,71× trendu, CI 0,68–0,72). Model czasu jazdy musi to uwzględnić. | Osoba 1 |
| **B** | E-rowery to osobna grupa klientów | ✅ | 8% rowerów, ale 20% przejazdów; jeździ się nimi dalej; klienci omijają rozładowane (9% wypożyczeń z baterią < 20% przy 15% takich rowerów na stacjach). | Osoba 1 |
| **C** | Operator nie nadąża tam, gdzie brakuje rowerów | ✅ | Jeździ we właściwe miejsca (ρ = 0,77), ale kończy tylko 8% pustek w dzień, po medianie 50 min. Reguła operatora dla symulacji: `operator_rule.json`. | Osoba 1 |

---

## Dane

### Zbierane na żywo (`data/`)

Skrypt [`collect.py`](collect.py) działa sam na GitHub Actions i co godzinę dopisuje pomiary do repozytorium. Zbieranie kończy się z sezonem (30.11).

| Folder | Co zawiera | Jak często |
|---|---|---|
| `status/` | każda stacja: liczba rowerów i e-rowerów, wolne stojaki, **numery rowerów**, bateria | co 5 min |
| `loose/` | rowery zostawione poza stacją | co 5 min |
| `info/` | lista stacji: nazwa, położenie, liczba stojaków | raz dziennie |
| `system/` | deklarowana flota, cennik | raz dziennie |
| `traffic_flow/`, `incidents/` | prędkość ruchu na 10 arteriach, wypadki i zamknięcia dróg (TomTom) | co 30 min |

### Dane dodatkowe (`data/static/`)

Kalendarz (dni robocze, święta, zajęcia i sesje UW/PW/SGH/WUM, ferie), wydarzenia (mecze, koncerty), pogoda i smog co godzinę, mapa z OpenStreetMap (lokale, biura, uczelnie, metro, drogi rowerowe, budynki), odległości między stacjami po drogach rowerowych, liczba mieszkańców, przystanki komunikacji, wysokość terenu. Źródła dat kalendarza: `data/static/calendar_sources.md`.

### Co robi `python -m src.data.build`

Czyści pomiary → odtwarza przejazdy z numerów rowerów (odrzuca skoki GPS, „mignięcia”, jazdę > 30 km/h, „przejazdy” > 4 h) → wykrywa przewozy operatora (≥ 4 rowery naraz między tymi samymi stacjami) → liczy tabele dla modelu i dane dla agentów → dopisuje kontekst (pogoda, kalendarz, korki) → pisze raport jakości `processed/quality_report.md`.

### Co powstaje (`processed/`)

| Plik | Co zawiera | Do czego |
|---|---|---|
| `station_hourly` | stacja × godzina: wypożyczenia, zwroty, minuty pustej stacji | popyt |
| `trips` | wszystkie przejazdy: skąd, dokąd, kiedy, czas, km, e-rower | cel i czas jazdy |
| `observed_timeseries` | stan każdej stacji co 5 min | start symulacji, porównanie z wynikiem |
| `rebalancing_observed` | przewozy operatora | strategia `operator` |
| `fleet_timeseries` | rowery na stacjach, w drodze, w serwisie | wielkość floty w symulacji |
| `empty_periods` | każdy okres pustej stacji | H2, poprawka popytu |
| `context_hourly` | pogoda, kalendarz, wydarzenia, korki co godzinę | wyjaśnienie popytu, scenariusze |
| `stations` | położenie, stojaki, otoczenie, dzielnica, typ otoczenia | różnice między stacjami |
| `trip_features` | opis każdego przejazdu (typ dnia, otoczenie, bateria, trasa dojazdowa) | typy klientów |
| `commute_pairs` | stałe trasy dojazdowe i ich regularność | stali bywalcy |
| `operator_shifts`, `operator_rule.json` | godziny pracy i reguła operatora | zmiany ciężarówek, strategia operatora |
| `district_flows` | dzielnica × godzina: przyjazdy, wyjazdy, bilans | „oddychanie miasta” |
| `daily_check` | jakość każdego dnia (pokrycie, flota, relokacje) | wybór dni do kalibracji |
| `MANIFEST.json` | zakres dat i sumy kontrolne plików | powtarzalność (`dane-final`) |

**Czas we wszystkich plikach jest w UTC.** Czas warszawski: kolumny `local_hour`, `local_date`, `day_type` w `context_hourly`.

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
| `stations` | `station_id`, `name`, `lat`, `lon`, `capacity`, `terminal_type`, `district`, `land_use`, `share_empty`, `share_overfull`, `share_inactive`, `mean_bikes`, `n_<typ POI>_300m`, `dist_{metro,university,train_station,center,transit_stop}_m`, `cycleway_m_300m`, `population_500m`, `n_transit_stops_300m`, `departures_{bus,tram,metro,rail,total}_300m`, `bldg_height_mean_300m`, `elevation_m` |
| `context_hourly` | `time`, `local_date`, `local_hour`, `dow`, `is_weekend`, `day_type`, pogoda (`temperature_2m`, `precipitation`, `rain`, `wind_speed_10m`, `cloud_cover`, …), `pm2_5`, `pm10`, `european_aqi`, `sun_elevation`, `is_dark`, `is_holiday`, `is_long_weekend`, `is_bridge_day`, `school_break`, `{uw,pw,sgh,wum}_period`, `n_uni_classes`, `n_uni_exams`, `n_events`, `n_events_large`, `event_names`, `congestion`, `congestion_max`, `congestion_stable`, `n_corridors`, `n_road_closures`, `n_incidents`, `n_jam_incidents` |

Przykład w Pythonie (tylko prawdziwe przejazdy klientów):

```python
import pandas as pd
trips = pd.read_parquet("processed/trips.parquet")
user_trips = trips[(trips["type"] == "user") & ~trips["is_flicker"] & ~trips["too_fast"] & ~trips["is_long"]]
```

</details>

---

## Modele, symulacja, metryki, 3D: jak to działa

### Modele zachowań (`src/model/`, Osoba 2)

`python -m src.model.pipeline` buduje modele, kalibruje je i sprawdza na dniach, których nie widziały (domyślnie kalibracja 23.10–10.11, walidacja 11–17.11; zmiana: `--calib OD DO --valid OD DO`). Wyniki: `processed/model/`, opis z wykresami: [`modele_walidacja.ipynb`](notebooks/modele_walidacja.ipynb).

- **Popyt** (`demand.py`): ilu chętnych przychodzi na każdą stację w każdej godzinie. Uwzględnia porę dnia, typ dnia, temperaturę i korki; godziny pustej stacji nie zaniżają popytu. Błąd sumy wypożyczeń: +6%, korelacja godzina po godzinie 0,92.
- **Cel podróży** (`od.py`): dokąd jadą; z danych, wygładzone modelem grawitacyjnym (każdy km zmniejsza szansę wyboru celu 2,2 raza).
- **Czas jazdy** (`duration.py`): zależy od odległości; e-rowerem o 15% krócej.
- **Interakcja przez puste stacje** (`spillover.py`): pomiar w danych, ilu klientów pustej stacji wypożycza rower na sąsiedniej i jak daleko idą (ok. 20%, do ok. 600 m). Te wartości trafiają wprost do symulacji jako zachowanie klienta przy pustej stacji.
- **Kalibracja i walidacja** (`calibration.py`): Optuna dobiera tylko zachowanie klienta przy pełnej stacji (tego nie widać w danych); walidacja dzień po dniu w silniku symulacji, z modelami bazowymi.
- **Hipotezy H1, H4, H5a** (`hypotheses.py`).

### Silnik symulacji (`src/simulation/`, Osoba 3)

Symulacja zdarzeń dyskretnych w SimPy. Klienci przychodzą losowo w tempie z modelu popytu, wypożyczają konkretny rower, jadą do celu; przy pustej stacji idą do sąsiedniej albo rezygnują (utracony popyt). Ciężarówki jeżdżą po drogach z korkami z TomTom. Strategie: `none` (nikt nie przewozi), `operator` (odtworzenie prawdziwych przewozów), `threshold` (reakcja poniżej 20% / powyżej 80% zapełnienia). Wynik zapisuje się w tym samym formacie co dane (`observed_timeseries.parquet` itd.) plus `events.parquet`, więc działają na nim metryki i wizualizacja. Instrukcja: [`docs/simulation.md`](docs/simulation.md).

### Pomiar emergencji (`src/metrics/`, Osoba 1)

Emergencja to zjawiska, których nikt nie zaprogramował, a które powstają z zachowania wielu ludzi naraz, np. stacje pustoszejące jedna po drugiej. `python -m src.metrics` liczy te same miary dla danych i symulacji: rytm dnia, skupienie pustek (Gini), długość pustek, skupiska w przestrzeni (indeks Morana), fale pustek, bilans dzielnic oraz test, czy to nie przypadek (losowe wymieszanie). Wyniki: [`docs/wyniki/emergencja.md`](docs/wyniki/emergencja.md).

### Wizualizacja 3D (`unity/`, Osoba 1)

Cała Warszawa w 3D (budynki, Wisła, metro, drogi rowerowe, pogoda, pora dnia), na której odtwarzamy prawdziwy dzień: stacje jako słupki (pusta pulsuje na czerwono), każdy przejazd jako jadący rower, ciężarówki operatora, korki, wydarzenia, utracony popyt. W tym samym widoku wynik symulacji:

| Klawisz | Co pokazuje |
|---|---|
| **X** | podzielony ekran: prawdziwy dzień \| model tego dnia |
| **Z** | do 4 strategii obok siebie z licznikiem utraconych klientów |
| **J** | agenci-klienci: czekają, idą do sąsiedniej stacji, odchodzą (✕) |
| **O** | decyzje dyspozytora: łuk od ciężarówki do stacji |
| **B** | fale pustek |
| **Y** | „ciśnienie”: gdzie brakuje rowerów (czerwony), gdzie jest za dużo (niebieski) |
| **T** | pokaz z komentarzem (ok. 2 min) do prezentacji |

Pełne sterowanie i budowanie `.exe`: [`unity/README.md`](unity/README.md).

---

## Pliki w repozytorium

```
collect.py                  zbieranie danych na żywo (GitHub Actions: .github/workflows/collect.yml)
run_all.ps1                 cały łańcuch jednym poleceniem (-Quick)
run_milestone.ps1           odtworzenie kamienia milowego z 5.11
requirements*.txt           biblioteki Pythona

src/data/                   Osoba 1: dane surowe -> processed/ (build.py), dane dla agentów (agents.py),
                            odtwarzanie przejazdów (trips.py), kontekst, otoczenie stacji, wersja danych (manifest.py)
src/metrics/                Osoba 1: metryki emergencji (emergence.py), hipotezy H2, A, B, C (hypotheses.py)
src/model/                  Osoba 2: popyt, cel podróży, czas jazdy, kalibracja, walidacja, H1/H4/H5a
src/simulation/             Osoba 3: silnik SimPy, strategie, eksperymenty, weryfikacja
src/agents/                 Osoba 2 i 3: agenci (do utworzenia)
src/viz/                    Osoba 1: eksport danych i symulacji do Unity
tools/app_latency.py        pomiar opóźnienia aplikacji w terenie (do 30.11)
tools/przyklad_przebiegu.py przykładowy przebieg z nowymi zdarzeniami agentów (-> docs/przyklad_przebiegu/)
tests/                      testy (pytest)
notebooks/                  analiza opisowa, puste stacje (H2), modele i walidacja
docs/                       wyniki (wyniki/), kamień milowy 5.11, kontrakty, przykładowy przebieg, raport (raport/)
unity/                      projekt wizualizacji 3D
data/                       dane zbierane na żywo + data/static/ (dane dodatkowe)
processed/                  wyniki build (lokalnie, poza repozytorium)
```

<details>
<summary>Zbieranie danych – szczegóły techniczne</summary>

- Workflow [`collect.yml`](.github/workflows/collect.yml) działa łańcuchowo: każdy run mierzy co 5 min przez 57 min i uruchamia następny; cron co godzinę wznawia łańcuch, gdyby się przerwał. Wymaga publicznego repozytorium i uprawnień *Read and write* dla workflow. **1.12: wyłączyć cron** (patrz [powtarzalność](docs/raport/powtarzalnosc.md)).
- Ręczne uruchomienie: Actions → *Zbieranie danych Veturilo* → *Run workflow* (`iterations = 1` – test, `0` – pełna godzina).
- Kontrola raz w tygodniu: brak czerwonych runów w Actions i ciągłość commitów `Dane ...`.
- TomTom wymaga sekretu `TOMTOM_API_KEY`. 26.10 dwa punkty TomTom przeniesiono na główne jezdnie; wskaźnik korków łączy je z poprzednikami.
- `fetch_static` pomija gotowe pliki (`--force KROK` tworzy ponownie); kroki: `calendar events weather air_quality elevation population gtfs osm`. Grafy dróg OSM (~150 MB, poza repo): `--only osm --force osm`. Podkład mapy i trasy wizualizacji są w repo.
- Poza repozytorium: `processed/`, `data/static/cache/`, grafy i cache w `data/static/osm/`, eksport w `unity/Assets/StreamingAssets/veturilo/`.

</details>
