"""
Zbieranie danych o stanie stacji Veturilo (Nextbike).

Co robi:
- co INTERVAL_SEC sekund pobiera stan wszystkich stacji i dopisuje rekordy do
  data/status/RRRR-MM-DD.jsonl.gz (jeden plik na dzien, UTC),
- raz dziennie zapisuje informacje o stacjach (lokalizacje, pojemnosci)
  do data/info/RRRR-MM-DD.json.gz.

Zrodla danych (sprawdzane po kolei, uzywane jest pierwsze dzialajace):
1. GBFS Nextbike (kilka znanych wariantow adresu),
2. oficjalny feed Nextbike "nextbike-live.json" dla Warszawy (city=812),
   przeliczany do tego samego formatu co GBFS.

Uzycie:
  python collect.py                      # jeden pomiar (dobry test)
  ITERATIONS=11 python collect.py        # 11 pomiarow co 5 min (~55 min)

Zmienne srodowiskowe:
  GBFS_ROOT     wlasny adres gbfs.json (sprawdzany jako pierwszy)
  CITY_IDS      id miast Nextbike dla feedu zapasowego (domyslnie 812 = Warszawa)
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
import urllib.error
import urllib.request

OUT_DIR = os.environ.get("OUT_DIR", "data")
ITERATIONS = int(os.environ.get("ITERATIONS", "1"))
INTERVAL_SEC = int(os.environ.get("INTERVAL_SEC", "300"))
CITY_IDS = os.environ.get("CITY_IDS", "812")
USER_AGENT = "Mozilla/5.0 (student project; bike-share simulation)"

GBFS_ROOTS = [
    u
    for u in [
        os.environ.get("GBFS_ROOT"),
        "https://gbfs.nextbike.net/maps/gbfs/v2/nextbike_vp/gbfs.json",
        "https://gbfs.nextbike.net/maps/gbfs/v1/nextbike_vp/gbfs.json",
        "https://api.nextbike.net/maps/gbfs/v1/nextbike_vp/gbfs.json",
    ]
    if u
]
# Bezposrednie adresy feedow, gdyby gbfs.json nie odpowiadal.
GBFS_DIRECT_BASES = [
    "https://gbfs.nextbike.net/maps/gbfs/v2/nextbike_vp/pl",
    "https://gbfs.nextbike.net/maps/gbfs/v2/nextbike_vp/en",
]
LIVE_URL = f"https://api.nextbike.net/maps/nextbike-live.json?city={CITY_IDS}"


def log(msg):
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now} UTC] {msg}", flush=True)


def fetch_json(url, retries=3, quiet=False):
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            last_err = f"HTTP {e.code}"
            if e.code in (400, 401, 403, 404, 410):
                break  # ponawianie nic nie da
        except Exception as e:  # siec, timeout, zly JSON
            last_err = repr(e)
        if attempt < retries:
            time.sleep(3 * attempt)
    if not quiet:
        log(f"  nie dziala: {url} ({last_err})")
    raise RuntimeError(f"{url}: {last_err}")


# ---------------------------------------------------------------------------
# Zrodla danych. Kazde zrodlo zwraca (status, info), gdzie:
#   status = {"last_updated": int, "stations": [{station_id, bikes, docks, ...}]}
#   info   = surowe dane o stacjach (zapisywane raz dziennie)
# ---------------------------------------------------------------------------


class GbfsSource:
    def __init__(self, status_url, info_url):
        self.status_url = status_url
        self.info_url = info_url
        self.name = f"GBFS ({status_url})"

    def fetch_status(self):
        raw = fetch_json(self.status_url)
        stations = []
        for s in raw.get("data", {}).get("stations", []):
            rec = {
                "station_id": str(s.get("station_id")),
                "bikes": s.get("num_bikes_available"),
                "docks": s.get("num_docks_available"),
                "is_renting": s.get("is_renting"),
                "is_returning": s.get("is_returning"),
                "last_reported": s.get("last_reported"),
            }
            if "vehicle_types_available" in s:
                rec["vehicle_types"] = s["vehicle_types_available"]
            stations.append(rec)
        return {"last_updated": raw.get("last_updated"), "stations": stations}

    def fetch_info(self):
        return fetch_json(self.info_url) if self.info_url else None


class LiveSource:
    """Oficjalny feed Nextbike (nextbike-live.json), przeliczany do formatu GBFS."""

    name = f"nextbike-live ({LIVE_URL})"

    def _places(self):
        raw = fetch_json(LIVE_URL)
        places = []
        for country in raw.get("countries", []):
            for city in country.get("cities", []):
                for p in city.get("places", []):
                    if p.get("spot") and not p.get("bike"):  # stacja, nie luzny rower
                        places.append(p)
        return places

    def fetch_status(self):
        stations = []
        for p in self._places():
            stations.append(
                {
                    "station_id": str(p.get("uid")),
                    "bikes": p.get("bikes_available_to_rent", p.get("bikes")),
                    "docks": p.get("free_racks"),
                    "is_renting": not p.get("maintenance", False),
                    "is_returning": not p.get("maintenance", False),
                    "last_reported": None,
                    "bike_types": p.get("bike_types"),
                }
            )
        return {"last_updated": int(time.time()), "stations": stations}

    def fetch_info(self):
        stations = [
            {
                "station_id": str(p.get("uid")),
                "name": p.get("name"),
                "lat": p.get("lat"),
                "lon": p.get("lng"),
                "capacity": p.get("bike_racks"),
                "number": p.get("number"),
            }
            for p in self._places()
        ]
        return {"source": "nextbike-live", "data": {"stations": stations}}


def candidate_sources():
    for root_url in GBFS_ROOTS:
        try:
            root = fetch_json(root_url)
            data = root["data"]
            lang = "pl" if "pl" in data else next(iter(data))
            feeds = {f["name"]: f["url"] for f in data[lang]["feeds"]}
            if "station_status" in feeds:
                yield GbfsSource(feeds["station_status"], feeds.get("station_information"))
        except Exception:
            pass
    for base in GBFS_DIRECT_BASES:
        yield GbfsSource(f"{base}/station_status.json", f"{base}/station_information.json")
    yield LiveSource()


def pick_source():
    """Zwraca pierwsze zrodlo, ktore faktycznie zwraca stacje."""
    log("Szukam dzialajacego zrodla danych...")
    for src in candidate_sources():
        try:
            status = src.fetch_status()
            n = len(status["stations"])
            if n > 0:
                log(f"OK: {src.name}, {n} stacji")
                return src
            log(f"  pusta odpowiedz: {src.name}")
        except Exception:
            pass
    return None


# ---------------------------------------------------------------------------


def save_info(src, day):
    path = os.path.join(OUT_DIR, "info", f"{day}.json.gz")
    if os.path.exists(path):
        return
    info = src.fetch_info()
    if info is None:
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as f:
        json.dump(info, f, ensure_ascii=False)
    n = len(info.get("data", {}).get("stations", []))
    log(f"Zapisano informacje o stacjach: {n} -> {path}")


def save_status(src):
    fetched_at = dt.datetime.now(dt.timezone.utc)
    status = src.fetch_status()
    if not status["stations"]:
        raise RuntimeError("odpowiedz bez stacji")
    day = fetched_at.strftime("%Y-%m-%d")
    path = os.path.join(OUT_DIR, "status", f"{day}.jsonl.gz")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    ts = fetched_at.isoformat(timespec="seconds")
    # Dopisywanie do gzip tworzy plik wieloczlonowy - gzip i pandas czytaja go poprawnie.
    with gzip.open(path, "at", encoding="utf-8") as f:
        for s in status["stations"]:
            rec = {"fetched_at": ts, "feed_last_updated": status["last_updated"], **s}
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    log(f"Zapisano stan {len(status['stations'])} stacji -> {path}")
    return day


def main():
    src = pick_source()
    if src is None:
        log("BLAD: zadne zrodlo danych nie dziala (szczegoly powyzej). Koncze od razu.")
        sys.exit(1)

    failures = 0
    for i in range(ITERATIONS):
        start = time.time()
        try:
            day = save_status(src)
            try:
                save_info(src, day)
            except Exception as e:
                log(f"Nie udalo sie zapisac informacji o stacjach: {e}")
        except Exception as e:
            failures += 1
            log(f"Pomiar {i + 1}/{ITERATIONS} nieudany: {e}")
            if failures >= 3 and failures == i + 1:
                log("BLAD: trzy pierwsze pomiary nieudane. Koncze od razu.")
                sys.exit(1)

        if i < ITERATIONS - 1:
            time.sleep(max(0, INTERVAL_SEC - (time.time() - start)))

    log(f"Koniec: {ITERATIONS - failures}/{ITERATIONS} udanych pomiarow")
    if failures == ITERATIONS:
        sys.exit(1)


if __name__ == "__main__":
    main()