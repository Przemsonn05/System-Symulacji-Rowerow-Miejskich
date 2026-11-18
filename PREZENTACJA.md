# 🚲 Prezentacja: Silnik Agentowy i Eksperymenty Symulacji Rowerów Miejskich (Issue #7)

> **Podsumowanie realizacji zadania Osoby 3: Transformacja silnika DES w pełny system wieloagentowy (ABM) z protokołem Contract Net, dynamicznym polem ciśnienia oraz pakietem zaawansowanych eksperymentów emergencji.**

---

## 🎯 1. Cel i Główne Założenia

Głównym celem zadania było przekształcenie scentralizowanego silnika symulacji SimPy w **rozproszony model wieloagentowy**:
- **Zasada ograniczonej wiedzy („Nikt nie widzi całego miasta”)**: Każdy agent (Klient, Stacja, Ciężarówka, Dyspozytor) działa w oparciu o własny, lokalny widok stanu, nie mając wglądu w globalną sytuację całego systemu.
- **Emergencja zachowań**: Zjawiska takie jak fale pustek czy efekt stadny wyłaniają się spontanicznie ze sprzężeń zwrotnych pomiędzy decyzjami użytkowników a działaniami floty relokacyjnej.
- **100% zgodności wstecznej**: Wszystkie dotychczasowe testy (39/39) oraz schematy danych zostały zachowane.

---

## 🏛️ 2. Nowa Architektura Agentowa (`src/agents/`)

Utworzono dedykowany moduł agentowy składający się z wyspecjalizowanych klas:

### A. Baza agentowa (`src/agents/base.py`)
- Klasa bazowa `Agent` definiująca interfejs: `perceive(view)`, `act()`, `on_message(msg)` oraz `send()`.
- System asynchronicznych komunikatów `AgentMessage`.
- Dedykowane klasy widoków izolujące stan silnika: `StationView`, `AppView`, `TruckView`, `DispatcherView`.

### B. Agent-Stacja (`src/agents/station.py`)
- **Prognoza zapotrzebowania $\hat{B}(t+H)$**: Estymacja bilansu rowerów na stacji na horyzont $H=30$–$60$ min:
  $$\hat{B}(t+H) = B_{obecne} + \text{dostawy ciężarówek} + \text{spodziewane zwroty} - \text{spodziewane wypożyczenia}$$
  Wariant `oracle=False` opiera się na oczekiwanych przepływach, a `oracle=True` stanowi punkt odniesienia idealnej informacji.
- **Histereza sygnału bez migotania (flicker-free)**: Sygnał deficytu aktywuje się poniżej $10\%$ pojemności, a wyłącza dopiero powyżej $25\%$. Sygnał nadmiaru aktywuje się powyżej $90\%$ i wyłącza poniżej $75\%$.
- **Kolejka oczekujących FIFO z cierpliwością**: Oczekiwanie na zwrot roweru; jeśli klient nie doczeka się roweru w czasie swojej cierpliwości (`patience_min`), rezygnuje z usługi.

### C. Pole Ciśnienia na Grafie (`src/agents/field.py`)
- Modelowanie rozchodzenia się deficytu w sąsiedztwie stacji (do $1.5$ km).
- Rzadka macierz wag przestrzennych $W$ (`scipy.sparse.csr_matrix`): $w_{ij} = \exp(-d_{ij} / \ell)$.
- Równanie dyfuzji:
  $$p \leftarrow (1 - \alpha) s + \alpha W p$$
  Dla $\alpha=0$ otrzymujemy $p=s$. Wynik zapisywany jest jako kolumna `pressure` w `station_timeseries.parquet`.

### D. Agent-Ciężarówka (`src/agents/truck.py`)
- Realizacja zadań relokacyjnych w warunkach miejskich (jazda ulicami z uwzględnieniem godzinowej kongestii TomTom).
- **Obsługa zmian pracy**: Ciężarówka pracuje w określonych godzinach (np. 6:00–22:00); kończy rozpoczęte zadanie po upływie zmiany, lecz nie podejmuje nowych.
- **Wycena ofert w przetargu**: Wyliczanie szacowanego czasu dojazdu, załadunku i rozładunku na potrzeby aukcji.

### E. Agent-Dyspozytor (`src/agents/dispatcher.py`)
- **Przetarg Contract Net co 5 minut**:
  1. Zbiera sygnały ze stacji i mapy ciśnienia.
  2. Łączy stacje w pary dawca-biorca.
  3. Ogłasza zadania wolnym autom na zmianie (`task_announced`).
  4. Zbiera oferty czasowe (`bid`).
  5. Przydziela zadanie najszybszej ciężarówce (`task_awarded`), deterministycznie rozstrzygając remisy (niższe ID).
  6. Rezerwuje obsługiwane stacje przed zdublowaniem zleceń.

---

## 🗂️ 3. Siedem Strategii Relokacji

W silniku zaimplementowano pełen wachlarz 7 strategii zarządzania flotą:
1. `none`: Brak relokacji rowerów (punkt odniesienia).
2. `operator`: Wierna powtórka historycznych zleceń operatora Veturilo.
3. `threshold`: Reaktywna interwencja progowa (poniżej 20% lub powyżej 80% napełnienia stacji).
4. `night`: Nocne bilansowanie stacji (0:00–5:00) pod kątem porannego odpływu netto (6:00–10:00).
5. `predictive`: Proaktywne reagowanie na prognozowane opustoszenie stacji w ciągu najbliższej godziny.
6. `pressure`: Sterowanie oparte na emergentnym polu ciśnienia w sąsiedztwie stacji na grafie.
7. `operator_rule`: Heurystyczna reguła operatora odzwierciedlająca rzeczywiste godziny pracy i progi interwencji.

---

## 🔄 4. Integracja z Silnikiem i Zgodność Kontraktów

Zaktualizowany silnik `src/simulation/engine.py`:
- **Nowe zdarzenia agentowe**: Rejestracja w `events.parquet`: `signal_on`, `signal_off`, `task_announced`, `bid`, `task_awarded`, `user_wait_start`, `user_wait_end`, `user_walk`, `user_leave`.
- **Kolumna `pressure`**: Dodana do `station_timeseries.parquet` zgodnie z wymaganiami wizualizacji 3D i metryk.
- **Tabela `user_outcomes.parquet`**: Zapis indywidualnych losów klientów (`request_id`, `user_id`, `user_type`, `has_app`, `decision`, `wait_time`, `stations_visited`).
- **Symulacja wielodniowa (`days=N`)**: Przechodzenie stanu między dobami z zachowaniem rowerów w drodze o północy.

---

## 🧪 5. Pakiet Eksperymentów (`src/simulation/agent_experiments.py`)

Zrealizowano pełny moduł wykonawczy dla wszystkich wymaganych badań:
- **H3 (Optymalizacja Pareto)**: 7 strategii $\times$ flota 1–4 aut; analiza utraconego popytu, kilometrów i godzin pracy; testy rangowe Wilcoxona z korektą Holma.
- **H5b (Wpływ korków)**: Symulacja mnożników kongestii $\alpha \in [0.0, 1.0, 1.5, 2.0]$.
- **Przejście fazowe (emergencja)**: Skalowanie floty od 2000 do 5000 rowerów (algorytm największych reszt) i identyfikacja punktu krytycznego załamania.
- **Efekt stadny (emergencja)**: Analiza zachowań przy udziale aplikacji mobilnej 0–100% i opóźnieniach danych 0, 5, 10 min.
- **Zasięg ciśnienia**: Badanie wpływu promienia dyfuzji $\ell \in [0.5, 3.0]$ km.
- **Scenariusze Co-Jeśli**: Deszcz, mróz (-30% popytu), przerwa na uczelniach, mecz na stadionie, +N rowerów zamiast +1 ciężarówki.
- **Analiza wrażliwości**: Wykres Tornado ($\pm 20\%$) oraz analiza metodą Morrisa przy użyciu biblioteki `SALib`.

---

## 📊 6. Weryfikacja i Jakość Kodu

- **77 testów przechodzi pomyślnie (100% sukcesu)**:
  - `tests/test_simulation.py`: 39 oryginalnych testów (niezmienniki, CRN, bilans, analityczny model M/M/2/2).
  - `tests/test_agents.py`: 20 nowych testów agentowych (wielodniowość, aukcje Contract Net, histereza, dyfuzja, brak widzenia przyszłości, determinizm).
  - `tests/test_metrics.py` & `tests/test_export_sim.py`: 18 testów metryk i eksportu 3D.
- **Czysty kod bez komentarzy**: Wszystkie pliki `.py` zostały napisane rygorystycznie bez komentarzy inline i blokowych (`#`), zgodnie z wytyczną użytkownika.
- **Kompletna dokumentacja**:
  - `docs/simulation.md` (zaktualizowany opis, diagram sekwencji Mermaid).
  - `docs/ODD.md` (protokół ODD+D wg standardu modelowania wieloagentowego).

---

## 🚀 7. Podsumowanie

Wszystkie wymagania zawarte w GitHub Issue #7 zostały zrealizowane. Kod silnika jest w pełni przetestowany, modułowy, gotowy do obliczeń wielkoskalowych i wdrożenia do repozytorium projektu.
