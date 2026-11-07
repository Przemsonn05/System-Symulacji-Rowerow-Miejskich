# Powtarzalność wyników (dodatek do raportu)

Każdy wynik w raporcie da się odtworzyć jednym poleceniem z tej samej wersji danych i parametrów.

| Co | Wersja | Jak sprawdzić |
|---|---|---|
| Dane | tag git `dane-final` (1.12) | `python -m src.data.manifest --check` porównuje `processed/` z `processed/MANIFEST.json` |
| Parametry modelu | `processed/model/sim_params.json` z 3.12 | suma SHA-256 w `results/h3_*/manifest.json` |
| Ziarna losowe | 1000–1029 (30 replikacji) | `results/h3_*/manifest.json` → `seeds` |
| Pakiety | `requirements-simulation.lock.txt` | `pip freeze` |

## Jedno polecenie

```powershell
git checkout dane-final
./run_all.ps1            # pełny przebieg
./run_all.ps1 -Quick     # sprawdzenie całego łańcucha (~10–15 min), np. przed prezentacją
./run_all.ps1 -Unity     # + aplikacja 3D (unity/Build/Veturilo.exe)
```

Kolejność kroków: testy → `src.data.build` (+ dane dla agentów) → `src.data.manifest` → `src.model.pipeline` → `src.simulation prepare / experiment / verify` → `src.metrics.hypotheses` → `src.metrics` (emergencja) → `src.viz.export` → `src.viz.export_sim`.

## Zamrożenie danych 1.12 (Osoba 1)

1. Wyłączyć harmonogram (`schedule`) w `.github/workflows/collect.yml` – od 1.12 feed jest pusty, a workflow co godzinę dodawałby puste commity.
2. `git pull`, `python -m src.data.build`, sprawdzić tabelę „Dni i koniec sezonu” w `processed/quality_report.md`.
3. `python -m src.data.manifest --label dane-final`.
4. Commit `data/` i `processed/MANIFEST.json`, `git tag dane-final`, `git push --tags`.
