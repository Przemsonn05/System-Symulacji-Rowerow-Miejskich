# Raport końcowy – spis rozdziałów

**Termin: 14.01.** Koordynuje Osoba 1. Każdy rozdział to osobny plik w tym folderze (`01_wstep.md`, ...); rysunki w `docs/raport/rys/`. Wszystkie wyniki końcowe liczymy na wersji danych `dane-final` (1.12) i parametrach `sim_params.json` zamrożonych 3.12.

| # | Rozdział | Kto | Skąd materiał | Stan |
|---|---|---|---|---|
| 1 | Wstęp i główne pytanie | wszyscy | README („O co pytamy”) | ⏳ |
| 2 | Dane i ich przygotowanie | Osoba 1 | `src/data/`, `processed/quality_report.md`, `MANIFEST.json` | ⏳ |
| 3 | Analiza opisowa | Osoba 1 | `notebooks/analiza_opisowa.ipynb`, `docs/wyniki/hipotezy_osoba1.md` | ⏳ |
| 4 | Opis modelu agentowego (protokół ODD) | Osoba 3, Osoba 2 | `docs/simulation.md`, `docs/kontrakty.md` | ⏳ |
| 5 | Parametry z danych | Osoba 2 | `processed/model/`, `trip_features`, `operator_rule.json` | ⏳ |
| 6 | Sprawdzenie poprawności programu (weryfikacja) | Osoba 3 | `tests/`, `src/simulation/verify.py` | ⏳ |
| 7 | Kalibracja i walidacja | Osoba 2 | `notebooks/modele_walidacja.ipynb`, `docs/wyniki/emergencja.md` | ⏳ |
| 8 | Eksperymenty | Osoba 3 | `results/h3_*/REPORT.md` | ⏳ |
| 9 | Emergencja | Osoba 1, Osoba 3 | `docs/wyniki/emergencja.md` (`python -m src.metrics`) | ⏳ |
| 10 | Hipotezy | wszyscy | H1, H4, H5a: `src/model/hypotheses.py`; H2, A, B, C: `docs/wyniki/hipotezy_osoba1.md`; H3, H5b: eksperymenty | ⏳ |
| 11 | Wnioski i ograniczenia | wszyscy | [ograniczenia.md](ograniczenia.md) | ⏳ |
| 12 | Kto co robił, jak uruchomić, fragmenty kodu | Osoba 1 | [powtarzalnosc.md](powtarzalnosc.md), `run_all.ps1` | ⏳ |

Prezentacja: wizualizacja 3D (`unity/Build/Veturilo.exe`), tryb pokazu (T), podzielony ekran dane | model (X), cztery strategie (Z), film nagrany z trybu pokazu.
