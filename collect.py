"""
Zbieranie danych o stanie stacji Veturilo (Nextbike, format GBFS).

Co robi:
- co INTERVAL_SEC sekund pobiera station_status i dopisuje rekordy do
  data/status/RRRR-MM-DD.jsonl.gz (jeden plik na dzien, UTC),
- raz dziennie zapisuje station_information (lokalizacje, pojemnosci)
  do data/info/RRRR-MM-DD.json.gz.

Uzycie:
  python collect.py                      # jeden pomiar
  ITERATIONS=11 python collect.py        # 11 pomiarow co 5 min (~55 min)

Zmienne srodowiskowe:
  GBFS_ROOT     adres gbfs.json (domyslnie Veturilo, Warszawa)
  ITERATIONS    liczba pomiarow w jednym uruchomieniu (domyslnie 1)
  INTERVAL_SEC  odstep miedzy pomiarami w sekundach (domyslnie 300)
  OUT_DIR       katalog na dane (domyslnie data)
"""

import datetime as dt
import gzip
import json
import os
import sys
import time
import urllib.request

GBFS_ROOT = os.environ.get(
    "GBFS_ROOT", "https://gbfs.nextbike.net/maps/gbfs/v2/nextbike_vp/gbfs.json"
)
FALLBACK_BASE = "https://gbfs.nextbike.net/maps/gbfs/v2/nextbike_vp/pl"
OUT_DIR = os.environ.get("OUT_DIR", "data")
ITERATIONS = int(os.environ.get("ITERATIONS", "1"))
INTERVAL_SEC = int(os.environ.get("INTERVAL_SEC", "300"))
PREFERRED_LANG = "pl"


def log(msg):
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now} UTC] {msg}", flush=True)


def fetch_json(url, retries=3):
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "student-project-bike-sim/1.0"}
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:  # siec, timeout, zly JSON
            last_err = e
            log(f"Blad pobierania {url} (proba {attempt}/{retries}): {e}")
            time.sleep(5 * attempt)
    raise RuntimeError(f"Nie udalo sie pobrac {url}: {last_err}")


def discover_feeds():
    """Zwraca slownik {nazwa_feedu: url} na podstawie gbfs.json."""
    try:
        root = fetch_json(GBFS_ROOT)
        data = root["data"]
        lang = PREFERRED_LANG if PREFERRED_LANG in data else next(iter(data))
        return {f["name"]: f["url"] for f in data[lang]["feeds"]}
    except Exception as e:
        log(f"Nie udalo sie odczytac gbfs.json ({e}), uzywam adresow domyslnych")
        return {
            "station_status": f"{FALLBACK_BASE}/station_status.json",
            "station_information": f"{FALLBACK_BASE}/station_information.json",
        }


def save_station_information(feeds, day):
    path = os.path.join(OUT_DIR, "info", f"{day}.json.gz")
    if os.path.exists(path):
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    info = fetch_json(feeds["station_information"])
    with gzip.open(path, "wt", encoding="utf-8") as f:
        json.dump(info, f, ensure_ascii=False)
    n = len(info.get("data", {}).get("stations", []))
    log(f"Zapisano station_information: {n} stacji -> {path}")


def save_status_snapshot(feeds):
    fetched_at = dt.datetime.now(dt.timezone.utc)
    status = fetch_json(feeds["station_status"])
    stations = status.get("data", {}).get("stations", [])
    day = fetched_at.strftime("%Y-%m-%d")
    path = os.path.join(OUT_DIR, "status", f"{day}.jsonl.gz")
    os.makedirs(os.path.dirname(path), exist_ok=True)

    ts = fetched_at.isoformat(timespec="seconds")
    # Dopisywanie do gzip tworzy plik wieloczlonowy - gzip i pandas czytaja go poprawnie.
    with gzip.open(path, "at", encoding="utf-8") as f:
        for s in stations:
            record = {
                "fetched_at": ts,
                "feed_last_updated": status.get("last_updated"),
                "station_id": s.get("station_id"),
                "bikes": s.get("num_bikes_available"),
                "docks": s.get("num_docks_available"),
                "is_renting": s.get("is_renting"),
                "is_returning": s.get("is_returning"),
                "last_reported": s.get("last_reported"),
            }
            if "vehicle_types_available" in s:  # np. rowery elektryczne osobno
                record["vehicle_types"] = s["vehicle_types_available"]
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    log(f"Zapisano stan {len(stations)} stacji -> {path}")
    return day


def main():
    feeds = discover_feeds()
    if "station_status" not in feeds:
        log(f"Brak feedu station_status. Dostepne: {list(feeds)}")
        sys.exit(1)

    failures = 0
    for i in range(ITERATIONS):
        start = time.time()
        try:
            day = save_status_snapshot(feeds)
            if "station_information" in feeds:
                save_station_information(feeds, day)
        except Exception as e:
            failures += 1
            log(f"Pomiar {i + 1}/{ITERATIONS} nieudany: {e}")

        if i < ITERATIONS - 1:
            time.sleep(max(0, INTERVAL_SEC - (time.time() - start)))

    if failures == ITERATIONS:
        sys.exit(1)  # wszystkie proby nieudane - niech workflow pokaze blad


if __name__ == "__main__":
    main()
