# Veturilo – zbieranie danych

Automatyczne zbieranie stanu stacji roweru miejskiego Veturilo (Warszawa) z otwartego feedu Nextbike (`nextbike-live.json`, zapasowo GBFS `nextbike_vw`), co 5 minut, przez GitHub Actions.

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
  loose/RRRR-MM-DD.jsonl.gz    # rowery stojące poza stacjami (co 5 min)
  info/RRRR-MM-DD.json.gz      # lokalizacje i pojemności stacji (raz dziennie)
```

Pomiary są wyrównane do pełnych 5 minut (:00, :05, ...). Dane do 2026-10-22 14:02 UTC pochodzą ze starszej wersji skryptu (bez pól `source`, `booked_bikes`, `bike_numbers`).

Jeden rekord w `status`:

| Pole | Znaczenie |
|---|---|
| `fetched_at` | czas pobrania (UTC) |
| `source` | źródło pomiaru: `nextbike-live` albo `gbfs` |
| `feed_last_updated` | znacznik czasu feedu (tylko GBFS; w `nextbike-live` `null`) |
| `station_id` | id stacji (łączy się z `info`) |
| `bikes` | dostępne rowery |
| `docks` | wolne stojaki – **nie** jest twardym limitem, patrz uwagi |
| `is_renting`, `is_returning` | czy stacja działa |
| `last_reported` | kiedy stacja ostatnio raportowała (tylko GBFS; w `nextbike-live` `null`) |
| `booked_bikes` | rowery zarezerwowane (tylko `nextbike-live`) |
| `bike_numbers` | numery rowerów stojących na stacji (tylko `nextbike-live`) – pozwala odtworzyć przejazdy: rower znika ze stacji A i pojawia się na B |
| `bike_types` / `vehicle_types` | rozbicie na typy rowerów (`nextbike-live` / GBFS) |

Rekord w `loose`: `fetched_at`, `bike_number`, `place_id`, `lat`, `lon`, `bike_types`. Jeśli w danym pomiarze nie było żadnego roweru poza stacją, zapisywany jest jeden rekord z `bike_number: null` (żeby odróżnić „zero rowerów” od „brak pomiaru”). Feed obejmuje też rowery Veturilo wywiezione poza Warszawę.

Rekord stacji w `info`: `station_id`, `name`, `lat`, `lon`, `capacity` (liczba stojaków), `number`, `special_racks`, `terminal_type`, `rack_locks`, `place_type`.

## Wczytanie w Pythonie

```python
import glob, pandas as pd

status = pd.concat(pd.read_json(f, lines=True) for f in sorted(glob.glob("data/status/*.jsonl.gz")))
status["fetched_at"] = pd.to_datetime(status["fetched_at"]).dt.tz_convert("Europe/Warsaw")
```

## Uwagi

- **Pojemność stacji jest „miękka”.** Stacje Veturilo 3.0 (`terminal_type: "sign"`, `rack_locks: false`) przyjmują rowery także wtedy, gdy wszystkie stojaki są zajęte – wtedy `bikes > capacity` i `docks = 0` (w pierwszej godzinie danych: 39% rekordów). W modelu nie należy odrzucać zwrotów przy `docks == 0`.
- Harmonogram GitHub Actions bywa opóźniony o kilka–kilkanaście minut. Każdy run mierzy przez 57 minut, a następny czeka w kolejce (`concurrency`), więc luki między runami są zwykle krótkie, ale mogą się zdarzyć.
- Ręczne uruchomienie: `iterations = 1` to szybki test, `iterations = 0` to pełna godzina jak w harmonogramie.
- Rozmiar danych: ok. 13 KB na pomiar po kompresji, czyli ok. 3–4 MB dziennie (~100 MB miesięcznie).
- GitHub wyłącza zaplanowane workflow w repozytoriach bez aktywności przez 60 dni. Commity z danymi liczą się jako aktywność, ale co tydzień zajrzyjcie do zakładki Actions, czy nie ma błędów.
- Darmowy limit Actions: repozytorium **publiczne** – bez limitu minut; **prywatne** – 2000 min/miesiąc, a ten workflow zużywa ok. 1 h na godzinę (~720 h/miesiąc). **Dlatego repozytorium z danymi musi być publiczne** (dane i tak są otwarte), albo trzeba skrócić zbieranie.
- Inne miasto Nextbike: ustaw `CITY_IDS` (id miasta w `nextbike-live`) i `GBFS_ROOT` (np. `https://gbfs.nextbike.net/maps/gbfs/v2/nextbike_<ID>/gbfs.json`).
