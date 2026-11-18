# Protokół ODD+D: Model Symulacji Systemu Roweru Miejskiego (Veturilo)

Model wieloagentowy (ABM) zintegrowany z symulacją zdarzeń dyskretnych (DES) w bibliotece SimPy. Struktura protokołu ODD+D (Overview, Design concepts, Details + Human Decision-Making; Müller et al., 2013).

---

## I. Overview (Przegląd)

### 1. Cel modelu (Purpose)
Celem modelu jest symulacja dynamiki miejskiego systemu wypożyczalni rowerów w Warszawie ze szczególnym uwzględnieniem:
- Zjawisk emergentnych: fale pustek stacji, efekt stadny wywołany asymetrią i opóźnieniem informacji w aplikacji mobilnej.
- Porównania strategii dyspozytora w warunkach ograniczeń logistycznych (flota ciężarówek, czas pracy, kongestia drogowa).
- Oceny hipotez H3 (efektywność relokacji vs koszty przejazdów) i H5b (wpływ korków ulicznych na skuteczność przewozów).

### 2. Podmioty, zmienne stanu i skale (Entities, state variables, and scales)
- **Agenci-Klienci (`ClientAgent`)**:
  - Zmienne: `request_id`, `user_id`, `user_type` (`commuter`, `student`, `leisure`, `ebike`), `has_app` (bool), `origin_station`, `dest_station`, `patience_min`, `max_walk_km`, `decision` (`rented`, `waited`, `walked`, `abandoned`).
- **Agenci-Stacje (`StationAgent`)**:
  - Zmienne: `station_id`, `capacity`, `inventory` (lista obiektów `Bike`), `waiting_queue` (kolejka FIFO oczekujących klientów), `signal_state` (`normal`, `deficit`, `surplus`), `signal_value` $\in [-1, 1]$, `empty_minutes`, `overfull_minutes`.
- **Agenci-Ciężarówki (`TruckAgent`)**:
  - Zmienne: `truck_id`, `capacity` (domyślnie 20), `cargo` (przewożone rowery), `position` (indeks stacji), `busy` (status zajętości), `shift_hours` (godziny pracy, np. 6:00–22:00), przebyte kilometry, czas pracy.
- **Agent-Dyspozytor (`DispatcherAgent`)**:
  - Zmienne: `strategy`, `reserved_stations` (zbiór stacji z aktywnym zadaniem relokacji), licznik zadań.
- **Pole ciśnienia (`PressureField`)**:
  - Zmienne: macierz wag przestrzennych $W$, zasięg $\ell$, parametr tłumienia $\alpha$.
- **Skala czasowa i przestrzenna**:
  - Czas dyskretny/ciągły: minuty od początku symulacji, rozdzielczość 5-minutowa dla ocen dyspozytora i próbkowania stanów.
  - Przestrzeń: 348 rzeczywistych stacji Veturilo w Warszawie, macierze odległości i czasów przejazdu oparte na sieci drogowej i rowerowej OpenStreetMap (OSM).

### 3. Przegląd procesów i harmonogram (Process overview and scheduling)
1. **Generowanie popytu**: Niejednorodny proces Poissona (NHPP) z thinningiem Lewisa–Shedlera dla każdej stacji.
2. **Zachowanie klienta**: Przyjście na stację $\to$ sprawdzenie dostępności roweru $\to$ opcjonalne oczekiwanie w kolejce FIFO $\to$ próba dojścia do stacji alternatywnej (z aplikacji lub na ślepo) $\to$ wypożyczenie lub rezygnacja (utracony popyt).
3. **Ocena stanu stacji (co 5 min)**: Wyliczenie prognozy $\hat{B}(t+H)$, aktualizacja sygnału histerezy (`signal_on`/`signal_off`), dyfuzja ciśnienia $p$ na grafie.
4. **Przetarg dyspozytora (co 5 min)**: Wyznaczenie par stacji dawca-biorca, ogłoszenie zadań (Contract Net), licytacja wolnych ciężarówek na zmianie, przydział zadań najszybszym pojazdom.
5. **Ruch ciężarówek**: Przejazd z uwzględnieniem godzinowej kongestii TomTom, załadunek, transport, rozładunek, zwolnienie rezerwacji stacji.

---

## II. Design Concepts (Koncepcje projektowe)

### 1. Teoretyczne podstawy decyzji (Theoretical Background)
- Klienci podejmują decyzje w oparciu o model wyboru dyskretnego (Random Utility / Logit) oraz heurystyki ograniczonej racjonalności (bounded rationality).
- Dyspozytor stosuje protokół Contract Net (Smith, 1980) zapewniający rozproszoną licytację zadań w systemie wieloagentowym.
- Rozchodzenie się deficytów modelowane jest równaniem dyfuzji ciepła na grafie stacji (Heat Kernel / Laplacian smoothing).

### 2. Emergencja (Emergence)
- **Fale pustek**: Brak rowerów na stacjach węzłowych rozprzestrzenia się na sąsiednie stacje w wyniku przekierowań pieszych i odpływu pojazdów.
- **Efekt stadny**: Klienci korzystający z opóźnionej aplikacji mobilnej masowo kierują się do stacji z rzekomo dostępnymi rowerami, doprowadzając do ich błyskawicznego wyczerpania przed dotarciem kolejnych użytkowników.
- **Przejście fazowe**: Nagłe załamanie przepustowości systemu przy spadku całkowitej liczby rowerów poniżej punktu krytycznego.

### 3. Zdolności adaptacyjne i uczenie (Adaptation & Learning)
- Stacje adaptują swój sygnał na podstawie krótko- i średnioterminowego bilansu przewidywanych zwrotów.
- Klienci ze statusem stałych dojeżdżających (`commuter`) posiadają pamięć historyczną (doświadczenie z poprzednich dni symulacji wielodniowej), co modyfikuje ich skłonność do korzystania z danej stacji.

### 4. Cele agentów (Objectives)
- Klient: minimalizacja całkowitego czasu podróży (dojście + jazda + oczekiwanie) i unikanie rezygnacji.
- Stacja: utrzymanie zapełnienia w bezpiecznym korytarzu 20%–80% pojemności.
- Dyspozytor: minimalizacja utraconego popytu przy ograniczeniu całkowitego przebiegu kilometrowego floty ciężarówek (optymalizacja Pareto).

### 5. Dostęp do informacji (Sensing / Information Horizon)
- Zasada decentralizacji informacji: żaden agent nie dysponuje pełną wiedzą o całym stanie miasta.
- Klient bez aplikacji widzi tylko stację, przy której się znajduje.
- Klient z aplikacją widzi stany stacji z opóźnieniem $\Delta t \in \{0, 5, 10\}$ min.
- Stacja zna tylko swój inwentarz, kolejkę i zgłoszone dostawy; cele jadących rowerzystów są ukryte (z wyjątkiem eksperymentu `oracle=True`).

### 6. Interakcje (Interaction)
- Bezpośrednie: licytacja zadań między dyspozytorem a ciężarówkami (Contract Net), przekazywanie rowerów klientom z kolejki FIFO.
- Pośrednie (stigmergia): modyfikacja liczby rowerów na stacjach wpływająca na decyzje kolejnych klientów i ruchy pojazdów logistycznych.

### 7. Losowość (Stochasticity)
- Czasy przyjść użytkowników (proces Poissona), czasy jazdy rowerem (rozkład log-normalny), zachowania alternatywne (próba dojścia, rezygnacja).
- Wszystkie strumienie losowe synchronizowane są mechanizmem Common Random Numbers (CRN) z wykorzystaniem `SeedSequence`, gwarantując deterministyczną powtarzalność.

---

## III. Details (Szczegóły techniczne)

### 1. Inicjalizacja (Initialization)
- Stany początkowe stacji pobierane z obserwowanych danych empirycznych Veturilo o północy.
- Pozycje początkowe ciężarówek przypisane deterministycznie do kolejnych stacji węzłowych.

### 2. Dane wejściowe (Input data)
- Geometria stacji, współrzędne, pojemności nominalne ze zbioru `stations.parquet`.
- Macierze odległości i czasów jazdy z modelu OSMnx i sieci dróg OpenStreetMap.
- Profile kongestii drogowej z agregacji danych TomTom dla Warszawy.

### 3. Zdarzenia i format wyjścia (Submodels & Outputs)
- Zdarzenia rejestrowane w `events.parquet`: `user_arrival`, `user_wait_start`, `user_wait_end`, `user_walk`, `user_leave`, `rental`, `return`, `signal_on`, `signal_off`, `task_announced`, `bid`, `task_awarded`, `truck_departure`, `truck_arrival`, `truck_load`, `truck_unload`.
- Serie czasowe co 5 min w `station_timeseries.parquet` wzbogacone o kolumnę `pressure`.
- Statystyki indywidualne klientów w `user_outcomes.parquet`.
