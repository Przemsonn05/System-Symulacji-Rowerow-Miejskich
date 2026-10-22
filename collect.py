"""
Zbieranie danych o stanie stacji Veturilo (Nextbike).

Co robi:
- co INTERVAL_SEC sekund pobiera stan wszystkich stacji i dopisuje rekordy do
  data/status/RRRR-MM-DD.jsonl.gz (jeden plik na dzien, UTC),
- zapisuje rowery stojace poza stacjami do data/loose/RRRR-MM-DD.jsonl.gz,
- raz dziennie zapisuje informacje o stacjach (lokalizacje, pojemnosci)
  do data/info/RRRR-MM-DD.json.gz.

Zrodla danych (sprawdzane po kolei, uzywane jest pierwsze dzialajace):
1. oficjalny feed Nextbike "nextbike-live.json" dla Warszawy (city=812) -
   jedyny, ktory podaje numery rowerow na stacjach (bike_numbers), co pozwala
   odtwarzac pojedyncze przejazdy (skad -> dokad),
2. GBFS Nextbike dla Veturilo (system nextbike_vw) - zapasowo, bez numerow
   rowerow, przeliczany do tego samego formatu.

Pomiary sa wyrownane do siatki co INTERVAL_SEC (np. :00, :05, :10 ...),
pierwszy pomiar robiony jest od razu po starcie.

Uzycie:
  python collect.py                      # jeden pomiar (dobry test)
  ITERATIONS=11 python collect.py        # 11 pomiarow co 5 min
  DURATION_MIN=57 python collect.py      # pomiary co 5 min przez 57 minut

Zmienne srodowiskowe:
  GBFS_ROOT     wlasny adres gbfs.json (sprawdzany jako pierwszy z GBFS)
  CITY_IDS      id miast Nextbike dla feedu live (domyslnie 812 = Warszawa)
  ITERATIONS    liczba pomiarow w jednym uruchomieniu (domyslnie 1)
  DURATION_MIN  jesli > 0: zamiast ITERATIONS mierz az do uplywu tylu minut
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
DURATION_MIN = float(os.environ.get("DURATION_MIN", "0"))
INTERVAL_SEC = int(os.environ.get("INTERVAL_SEC", "300"))
CITY_IDS = os.environ.get("CITY_IDS", "812")
USER_AGENT = "Mozilla/5.0 (student project; bike-share simulation)"

# nextbike_vw = "VETURILO 3.0" (sprawdzone w system_information.json).
GBFS_ROOTS = [
    u
    for u in [
        os.environ.get("GBFS_ROOT"),
        "https://gbfs.nextbike.net/maps/gbfs/v2/nextbike_vw/gbfs.json",
        "https://gbfs.nextbike.net/maps/gbfs/v1/nextbike_vw/gbfs.json",
    ]
    if u
]
# Bezposrednie adresy feedow, gdyby gbfs.json nie odpowiadal.
GBFS_DIRECT_BASES = [
    "https://gbfs.nextbike.net/maps/gbfs/v2/nextbike_vw/pl",
    "https://gbfs.nextbike.net/maps/gbfs/v2/nextbike_vw/en",
]
# api.nextbike.net przekierowuje (301) na maps2.nextbike.net; urllib podaza
# za przekierowaniem, ale od razu uzywamy docelowego adresu.
LIVE_URL = f"https://maps2.nextbike.net/maps/nextbike-live.json?city={CITY_IDS}"


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
# Zrodla danych. Kazde zrodlo zwraca z fetch_status() slownik:
#   {"source": str, "feed_last_updated": int | None,
#    "stations": [{station_id, bikes, docks, ...}],
#    "loose": [{bike_number, lat, lon, ...}] | None}
# a z fetch_info() surowe dane o stacjach (zapisywane raz dziennie).
# ---------------------------------------------------------------------------


class GbfsSource:
    kind = "gbfs"

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
        return {
            "source": self.kind,
            "feed_last_updated": raw.get("last_updated"),
            "stations": stations,
            "loose": None,  # GBFS v2 Nextbike nie podaje luznych rowerow
        }

    def fetch_info(self):
        return fetch_json(self.info_url) if self.info_url else None


class LiveSource:
    """Oficjalny feed Nextbike (nextbike-live.json), przeliczany do formatu GBFS."""

    kind = "nextbike-live"
    name = f"nextbike-live ({LIVE_URL})"

    def _places(self):
        """Zwraca (stacje, luzne_rowery) z jednego zapytania."""
        raw = fetch_json(LIVE_URL)
        stations, loose = [], []
        for country in raw.get("countries", []):
            for city in country.get("cities", []):
                for p in city.get("places", []):
                    if p.get("bike"):
                        loose.append(p)  # rower zostawiony poza stacja
                    elif p.get("spot"):
                        stations.append(p)
        return stations, loose

    def fetch_status(self):
        places, loose_places = self._places()
        stations = []
        for p in places:
            stations.append(
                {
                    "station_id": str(p.get("uid")),
                    "bikes": p.get("bikes_available_to_rent", p.get("bikes")),
                    # free_racks = wolne stojaki; stacje Veturilo 3.0 przyjmuja
                    # zwroty takze przy free_racks == 0 (pojemnosc "miekka").
                    "docks": p.get("free_racks"),
                    "is_renting": not p.get("maintenance", False),
                    "is_returning": not p.get("maintenance", False),
                    "last_reported": None,  # feed live nie podaje tego pola
                    "booked_bikes": p.get("booked_bikes"),
                    "bike_types": p.get("bike_types"),
                    "bike_numbers": p.get("bike_numbers"),
                }
            )
        loose = []
        for p in loose_places:
            for num in p.get("bike_numbers") or [p.get("name")]:
                loose.append(
                    {
                        "bike_number": str(num),
                        "place_id": str(p.get("uid")),
                        "lat": p.get("lat"),
                        "lon": p.get("lng"),
                        "bike_types": p.get("bike_types"),
                    }
                )
        return {
            "source": self.kind,
            "feed_last_updated": None,  # feed live nie ma znacznika czasu
            "stations": stations,
            "loose": loose,
        }

    def fetch_info(self):
        places, _ = self._places()
        stations = [
            {
                "station_id": str(p.get("uid")),
                "name": p.get("name"),
                "lat": p.get("lat"),
                "lon": p.get("lng"),
                "capacity": p.get("bike_racks"),
                "number": p.get("number"),
                "special_racks": p.get("special_racks"),
                "terminal_type": p.get("terminal_type"),
                "rack_locks": p.get("rack_locks"),
                "place_type": p.get("place_type"),
            }
            for p in places
        ]
        return {"source": self.kind, "data": {"stations": stations}}


def candidate_sources():
    yield LiveSource()
    for root_url in GBFS_ROOTS:
        try:
            root = fetch_json(root_url, quiet=True)
            data = root["data"]
            lang = "pl" if "pl" in data else next(iter(data))
            feeds = {f["name"]: f["url"] for f in data[lang]["feeds"]}
            if "station_status" in feeds:
                yield GbfsSource(feeds["station_status"], feeds.get("station_information"))
        except Exception:
            pass
    for base in GBFS_DIRECT_BASES:
        yield GbfsSource(f"{base}/station_status.json", f"{base}/station_information.json")


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


def append_jsonl(path, records):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    # Dopisywanie do gzip tworzy plik wieloczlonowy - gzip i pandas czytaja go poprawnie.
    with gzip.open(path, "at", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


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
    ts = fetched_at.isoformat(timespec="seconds")
    head = {
        "fetched_at": ts,
        "source": status["source"],
        "feed_last_updated": status["feed_last_updated"],
    }

    path = os.path.join(OUT_DIR, "status", f"{day}.jsonl.gz")
    append_jsonl(path, ({**head, **s} for s in status["stations"]))
    msg = f"Zapisano stan {len(status['stations'])} stacji -> {path}"

    # Zapisujemy tez pusta liste jako jeden znacznik, zeby odroznic
    # "zero luznych rowerow" od "brak pomiaru".
    if status["loose"] is not None:
        loose_path = os.path.join(OUT_DIR, "loose", f"{day}.jsonl.gz")
        loose = status["loose"] or [{"bike_number": None}]
        append_jsonl(loose_path, ({"fetched_at": ts, **b} for b in loose))
        msg += f", {len(status['loose'])} rowerow poza stacjami"
    log(msg)
    return day


def next_slot():
    """Najblizsza wielokrotnosc INTERVAL_SEC, oddalona o co najmniej pol odstepu."""
    now = time.time()
    nxt = (now // INTERVAL_SEC + 1) * INTERVAL_SEC
    if nxt - now < INTERVAL_SEC / 2:
        nxt += INTERVAL_SEC
    return nxt


def main():
    src = pick_source()
    if src is None:
        log("BLAD: zadne zrodlo danych nie dziala (szczegoly powyzej). Koncze od razu.")
        sys.exit(1)

    deadline = time.time() + DURATION_MIN * 60 if DURATION_MIN > 0 else None
    done = failures = 0
    while True:
        done += 1
        label = f"{done}" if deadline else f"{done}/{ITERATIONS}"
        try:
            day = save_status(src)
            try:
                save_info(src, day)
            except Exception as e:
                log(f"Nie udalo sie zapisac informacji o stacjach: {e}")
        except Exception as e:
            failures += 1
            log(f"Pomiar {label} nieudany: {e}")
            if failures >= 3 and failures == done:
                log("BLAD: trzy pierwsze pomiary nieudane. Koncze od razu.")
                sys.exit(1)
            # Zrodlo moglo przestac dzialac - sprobuj wybrac inne na nastepny pomiar.
            src = pick_source() or src

        if deadline is None and done >= ITERATIONS:
            break
        nxt = next_slot()
        if deadline is not None and nxt > deadline:
            break
        time.sleep(max(0, nxt - time.time()))

    log(f"Koniec: {done - failures}/{done} udanych pomiarow")
    if failures == done:
        sys.exit(1)


if __name__ == "__main__":
    main()
