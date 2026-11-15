# 12. Kto co robił, jak uruchomić, fragmenty kodu

*Osoba 1 (koordynacja). Wersja robocza 15.11.2026 – podział pracy do potwierdzenia przez cały zespół przed 14.01.*

## 12.1. Podział pracy

| Osoba | Zakres | Foldery | Rozdziały |
|---|---|---|---|
| **Osoba 1** | zbieranie danych, przygotowanie danych i danych dla agentów, metryki emergencji, hipotezy H2, A, B, C, wizualizacja 3D, koordynacja raportu | `collect.py`, `src/data/`, `src/metrics/`, `src/viz/`, `unity/`, `tools/`, `docs/raport/` | 2, 3, 9 (z Osobą 3), 12 |
| **Osoba 2** | modele popytu, celu podróży i czasu jazdy, typy klientów, agent-klient, kalibracja i walidacja, hipotezy H1, H4, H5a, H6 | `src/model/`, `src/agents/` (klient) | 4 (z Osobą 3), 5, 7 |
| **Osoba 3** | silnik symulacji (SimPy), agenci stacja / ciężarówka / dyspozytor, strategie relokacji, weryfikacja, eksperymenty H3, H5b, przejście fazowe, efekt stadny, analiza wrażliwości | `src/simulation/`, `src/agents/` | 4, 6, 8, 9 (z Osobą 1) |
| wszyscy | wstęp, hipotezy, wnioski i ograniczenia | – | 1, 10, 11 |

Zadania i postęp: issues na GitHubie (#5 Osoba 1, #6 Osoba 2, #7 Osoba 3), stan prac w [README](../../README.md#stan-prac-15112026).

## 12.2. Jak uruchomić

Wymagania: Python 3.12+ (testowane na 3.14), `pip install -r requirements.txt` (symulacja: `requirements-simulation.txt`, dokładne wersje: `requirements-simulation.lock.txt`), do 3D Unity 6000.0.85f1.

```powershell
./run_all.ps1            # cały łańcuch: testy → dane → modele → symulacja (H3) → hipotezy → emergencja → eksport 3D
./run_all.ps1 -Quick     # to samo w ok. 10–15 min (3 replikacje, 100 permutacji) – sprawdzenie przed prezentacją
./run_all.ps1 -Unity     # + zbudowanie unity/Build/Veturilo.exe
```

Kroki pojedynczo:

| Krok | Polecenie | Wynik |
|---|---|---|
| Dane | `python -m src.data.build`, `python -m src.data.manifest` | `processed/`, `MANIFEST.json` |
| Modele | `python -m src.model.pipeline` | `processed/model/` (`sim_params.json`) |
| Symulacja | `python -m src.simulation prepare / run / experiment` | `results/` |
| Hipotezy z danych | `python -m src.metrics.hypotheses` | `docs/wyniki/hipotezy_osoba1.md` |
| Emergencja | `python -m src.metrics processed --sim <przebieg>` | `docs/wyniki/emergencja.md` |
| 3D | `python -m src.viz.export`, `python -m src.viz.export_sim <przebiegi>` | `unity/Assets/StreamingAssets/veturilo/` |
| Testy | `python -m pytest` | – (też automatycznie na GitHubie przy zmianach w `src/` i `tests/`) |

Powtarzalność (wersja danych `dane-final`, `sim_params.json` z 3.12, ziarna 1000–1029): [powtarzalnosc.md](powtarzalnosc.md).

## 12.3. Fragmenty kodu

**Odtworzenie przejazdu z numerów rowerów** (idea; pełna wersja z odrzucaniem błędów feedu w [`src/data/trips.py`](../../src/data/trips.py)):

```python
# dla kazdego roweru: kolejne miejsca, w ktorych go widzimy (pomiar co 5 min)
for bike, seen in snapshots.groupby("bike"):
    for prev, nxt in zip(seen[:-1], seen[1:]):
        if nxt.time - prev.time > STEP and prev.place != nxt.place:   # zniknal i pojawil sie gdzie indziej
            trips.append((bike, prev.place, nxt.place, prev.time, nxt.time))
```

**Fale pustek** ([`src/metrics/emergence.py`](../../src/metrics/emergence.py), `cascade_stats`): chwila pustoszenia stacji łączy się z wcześniejszą chwilą pustoszenia sąsiada (≤ 800 m, ≤ 20 min); fale to spójne składowe grafu tych połączeń (`scipy.sparse.csgraph.connected_components`).

**Model zerowy „inny dzień”** (`_day_swap`): dla każdej stacji chwile pustoszenia z losowego innego dnia tego samego typu – zachowuje porę dnia i częstość pustek, zrywa powiązanie z sąsiadami.

**Ten sam kod dla danych i modelu** ([`src/metrics/io.py`](../../src/metrics/io.py), `load_run`): katalog `processed/` i katalog przebiegu symulacji wczytują się do tej samej struktury (stan stacji co 5 min, stacje, przejazdy), więc każda miara działa na obu bez zmian.

**Kontrakt silnik ↔ metryki ↔ 3D**: [docs/kontrakty.md](../kontrakty.md), przykładowy przebieg z nowymi zdarzeniami agentów: [docs/przyklad_przebiegu/](../przyklad_przebiegu/).
