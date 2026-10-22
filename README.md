# Veturilo – zbieranie danych

Automatyczne zbieranie stanu stacji roweru miejskiego Veturilo (Warszawa) z otwartego feedu GBFS Nextbike, co 5 minut, przez GitHub Actions.

## Uruchomienie (ok. 5 minut)

1. Utwórz repozytorium na GitHubie (może być prywatne) i wrzuć do niego:
   - `collect.py`
   - `.github/workflows/collect.yml` (dokładnie ta ścieżka)
2. W repozytorium: **Settings → Actions → General → Workflow permissions** → zaznacz **Read and write permissions** → Save.
3. Zakładka **Actions** → „Zbieranie danych Veturilo” → **Run workflow**, żeby od razu sprawdzić, czy działa.
4. Po ok. godzinie w repozytorium pojawi się folder `data/`. Potem workflow uruchamia się sam co godzinę.

## Struktura danych

```
data/
  status/RRRR-MM-DD.jsonl.gz   # stan stacji co 5 min (jeden plik na dzień, UTC)
  info/RRRR-MM-DD.json.gz      # lokalizacje i pojemności stacji (raz dziennie)
```

Jeden rekord w `status`:

| Pole | Znaczenie |
|---|---|
| `fetched_at` | czas pobrania (UTC) |
| `station_id` | id stacji (łączy się z `info`) |
| `bikes` | dostępne rowery |
| `docks` | wolne miejsca |
| `is_renting`, `is_returning` | czy stacja działa |
| `last_reported` | kiedy stacja ostatnio raportowała (unix time) |
| `vehicle_types` | rozbicie na typy rowerów, jeśli feed je podaje |

## Wczytanie w Pythonie

```python
import glob, pandas as pd

status = pd.concat(pd.read_json(f, lines=True) for f in sorted(glob.glob("data/status/*.jsonl.gz")))
status["fetched_at"] = pd.to_datetime(status["fetched_at"]).dt.tz_convert("Europe/Warsaw")
```

## Uwagi

- Harmonogram GitHub Actions bywa opóźniony o kilka–kilkanaście minut, więc w danych mogą być małe luki. Na potrzeby modelu to nie problem.
- GitHub wyłącza zaplanowane workflow w repozytoriach bez aktywności przez 60 dni. Commity z danymi liczą się jako aktywność, ale co tydzień zajrzyjcie do zakładki Actions, czy nie ma błędów.
- Darmowy limit Actions: repozytorium **publiczne** – bez limitu minut; **prywatne** – 2000 min/miesiąc, a ten workflow zużywa ok. 1 h na godzinę (~720 h/miesiąc). **Dlatego repozytorium z danymi musi być publiczne** (dane i tak są otwarte), albo trzeba skrócić zbieranie.
- Inne miasto Nextbike: ustaw zmienną `GBFS_ROOT` na inny `gbfs.json` (np. `nextbike_<ID>`).
