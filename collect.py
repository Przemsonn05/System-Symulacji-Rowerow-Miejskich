"""
Zbieranie danych o stanie stacji Veturilo (Nextbike).

Co robi:
- co INTERVAL_SEC sekund pobiera stan wszystkich stacji i dopisuje rekordy do
  data/status/RRRR-MM-DD.jsonl.gz (jeden plik na dzien, UTC),
- zapisuje rowery stojace poza stacjami do data/loose/RRRR-MM-DD.jsonl.gz,
- raz dziennie zapisuje informacje o stacjach (lokalizacje, pojemnosci)
  do data/info/RRRR-MM-DD.json.gz,
- raz dziennie zapisuje stan floty i ustawienia systemu (cennik, typy rowerow)
  do data/system/RRRR-MM-DD.json.gz,
- opcjonalnie (gdy ustawione sa klucze API) zbiera dane o ruchu drogowym,
  ktorych nie da sie pobrac wstecz: predkosci autobusow ZTM (data/bus_speed),
  predkosci na arteriach i utrudnienia z TomTom (data/traffic_flow, data/incidents).

Zrodla danych (sprawdzane po kolei, uzywane jest pierwsze dzialajace):
1. oficjalny feed Nextbike "nextbike-live.json" dla Warszawy (city=812) -
   jedyny, ktory podaje numery rowerow na stacjach (bike_numbers), co pozwala
   odtwarzac pojedyncze przejazdy (skad -> dokad),
2. GBFS Nextbike dla Veturilo (system nextbike_vw) - zapasowo, bez numerow
   rowerow, przeliczany do tego samego formatu.

Pomiary sa wyrownane do siatki co INTERVAL_SEC (np. :00, :05, :10 ...),
pierwszy pomiar robiony jest od razu po starcie - chyba ze przy DURATION_MIN
start wypadl mniej niz START_SKIP_SEC po punkcie siatki (wtedy poprzedni run
z lancucha juz go zmierzyl i czekamy na nastepny punkt).

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
  WARSAW_API_KEY  klucz api.um.warszawa.pl - wlacza predkosci autobusow (data/bus_speed)
  TOMTOM_API_KEY  klucz TomTom - wlacza predkosci na arteriach (data/traffic_flow)
                  i utrudnienia w ruchu (data/incidents)
  TOMTOM_EVERY    co ktory pomiar pytac TomTom (domyslnie 3 = co 15 min)
"""

import datetime as dt
import gzip
import json
import os
import sys
import time
import math
import urllib.error
import urllib.parse
import urllib.request

OUT_DIR = os.environ.get("OUT_DIR", "data")
ITERATIONS = int(os.environ.get("ITERATIONS", "1"))
DURATION_MIN = float(os.environ.get("DURATION_MIN", "0"))
INTERVAL_SEC = int(os.environ.get("INTERVAL_SEC", "300"))
START_SKIP_SEC = 90  # patrz main(): unikanie duplikatu na styku runow
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


def ebike_battery(place):
    """Numer roweru -> poziom baterii [%] dla rowerow elektrycznych w danym miejscu."""
    return {
        str(b.get("number")): b["pedelec_battery"]
        for b in place.get("bike_list") or []
        if b.get("pedelec_battery") is not None
    }


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
            # Stacja z active_place == 0 jest wylaczona, choc moga na niej stac rowery.
            active = p.get("active_place", 1) != 0 and not p.get("maintenance", False)
            stations.append(
                {
                    "station_id": str(p.get("uid")),
                    "bikes": p.get("bikes_available_to_rent", p.get("bikes")),
                    # free_racks = wolne stojaki; stacje Veturilo 3.0 przyjmuja
                    # zwroty takze przy free_racks == 0 (pojemnosc "miekka").
                    "docks": p.get("free_racks"),
                    "is_renting": active,
                    "is_returning": active,
                    "active_place": p.get("active_place"),
                    "maintenance": p.get("maintenance"),
                    "last_reported": None,  # feed live nie podaje tego pola
                    "booked_bikes": p.get("booked_bikes"),
                    "bike_types": p.get("bike_types"),
                    "bike_numbers": p.get("bike_numbers"),
                    "ebike_battery": ebike_battery(p) or None,
                }
            )
        loose = []
        for p in loose_places:
            battery = ebike_battery(p)
            for num in p.get("bike_numbers") or [p.get("name")]:
                loose.append(
                    {
                        "bike_number": str(num),
                        "place_id": str(p.get("uid")),
                        "lat": p.get("lat"),
                        "lon": p.get("lng"),
                        "bike_types": p.get("bike_types"),
                        "battery": battery.get(str(num)),
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


def save_system(day):
    """Raz dziennie: stan floty i ustawienia systemu (cennik, typy rowerow).

    Jesli w trakcie zbierania zmieni sie cennik albo wielkosc floty, tego nie da
    sie potem odtworzyc. Kazda czesc pobierana osobno, brak jednej nie blokuje reszty.
    """
    path = os.path.join(OUT_DIR, "system", f"{day}.json.gz")
    if os.path.exists(path):
        return
    out = {"fetched_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
    try:
        raw = fetch_json(LIVE_URL)
        countries = raw.get("countries", [])
        # Bez list stacji - te sa w status/info.
        out["live_country"] = [{k: v for k, v in c.items() if k != "cities"} for c in countries]
        out["live_city"] = [
            {k: v for k, v in ci.items() if k != "places"}
            for c in countries
            for ci in c.get("cities", [])
        ]
    except Exception as e:
        log(f"System: brak danych z nextbike-live: {e}")
    for feed in ("system_information", "vehicle_types", "system_pricing_plans"):
        try:
            out[feed] = fetch_json(f"{GBFS_DIRECT_BASES[0]}/{feed}.json", quiet=True)
        except Exception as e:
            log(f"System: brak {feed}: {e}")
    if len(out) == 1:
        return  # nic nie pobrano, sprobujemy przy nastepnym pomiarze
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    log(f"Zapisano dane o systemie ({', '.join(k for k in out if k != 'fetched_at')}) -> {path}")


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


# ---------------------------------------------------------------------------
# Ruch drogowy - dane, ktorych nie da sie pobrac wstecz, wiec zbieramy je razem
# z Veturilo. Kazde zrodlo wlacza sie tylko, gdy ustawiony jest jego klucz API.
# Bledy tych zrodel nigdy nie przerywaja zbierania danych o rowerach.
# ---------------------------------------------------------------------------

WARSAW_API_KEY = os.environ.get("WARSAW_API_KEY", "").strip()
TOMTOM_API_KEY = os.environ.get("TOMTOM_API_KEY", "").strip()
# Co ktory pomiar pytac TomTom (3 x 5 min = co 15 min). Darmowy plan ma limit
# zapytan dziennie: 10 punktow x 96 = 960 zapytan + 96 o utrudnienia.
TOMTOM_EVERY = int(os.environ.get("TOMTOM_EVERY", "3"))
EXTRA_BUDGET_SEC = 90  # maks. czas na dodatkowe zrodla w jednym pomiarze

ZTM_URL = (
    "https://api.um.warszawa.pl/api/action/busestrams_get/"
    "?resource_id=f2e5503e-927d-4ad3-9500-4ab9e55deb59&type=1&apikey={key}"
)
# Siatka ~550 x 550 m, w ktorej usredniamy predkosc autobusow.
CELL_LAT, CELL_LON = 0.005, 0.008
# Punkty pomiaru predkosci TomTom: glowne arterie, przy ktorych stoja stacje.
# TomTom dopasowuje punkt do najblizszego odcinka drogi (zapisujemy jego poczatek i koniec).
# 26.10.2026: dwa punkty przeniesione na glowna jezdnie (stare dopasowywaly sie do
# bocznych odcinkow i prawie nie zmienialy predkosci); nowe nazwy, zeby nie mieszac serii:
#   jerozolimskie_rondo_de_gaulle (52.2316, 21.0245) -> jerozolimskie_centrum
#   grochowska_praga (52.2440, 21.0890, ul. Ostroleka) -> grochowska_kobielska
TOMTOM_POINTS = [
    ("jerozolimskie_centrum", 52.23121, 21.01855),
    ("marszalkowska_pl_konstytucji", 52.2215, 21.0155),
    ("niepodleglosci_pole_mokotowskie", 52.2120, 21.0060),
    ("pulawska_mokotow", 52.1930, 21.0230),
    ("wislostrada_centrum", 52.2420, 21.0290),
    ("trasa_lazienkowska", 52.2190, 21.0400),
    ("solidarnosci_wola", 52.2440, 20.9980),
    ("prymasa_tysiaclecia", 52.2350, 20.9580),
    ("grochowska_kobielska", 52.24534, 21.08513),
    ("modlinska_bialoleka", 52.3000, 20.9900),
]
WARSAW_BBOX = "20.85,52.10,21.27,52.37"  # minLon,minLat,maxLon,maxLat
TOMTOM_FLOW_URL = (
    "https://api.tomtom.com/traffic/services/4/flowSegmentData/absolute/10/json"
    "?point={lat},{lon}&unit=KMPH&key={key}"
)
TOMTOM_INCIDENTS_URL = (
    "https://api.tomtom.com/traffic/services/5/incidentDetails"
    "?bbox={bbox}&fields={fields}&language=pl-PL&timeValidityFilter=present&key={key}"
)
TOMTOM_INCIDENT_FIELDS = (
    "{incidents{type,geometry{type,coordinates},properties{id,iconCategory,"
    "magnitudeOfDelay,events{description},startTime,endTime,from,to,length,delay}}}"
)

_prev_buses = {}  # numer pojazdu -> (czas GPS, lat, lon) z poprzedniego pomiaru


def fetch_keyed(url, key):
    """fetch_json bez ponawiania i bez klucza API w komunikatach bledow."""
    try:
        return fetch_json(url, retries=1, quiet=True)
    except RuntimeError as e:
        # Komunikat ma postac "<url>: <blad>" - ucinamy parametry adresu (z kluczem).
        where, _, err = str(e).replace(key, "***").partition(": ")
        raise RuntimeError(f"{where.split('?')[0]}: {err}") from None


def haversine_km(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = (
        math.sin((p2 - p1) / 2) ** 2
        + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    )
    return 6371 * 2 * math.asin(math.sqrt(a))


def bus_speeds(prev, buses):
    """Predkosci autobusow miedzy dwoma pomiarami, usrednione w komorkach siatki.

    Zwraca (rekordy komorek, aktualne pozycje). Predkosc liczona z czasu GPS
    pojazdu, wiec obejmuje tez postoje na przystankach i swiatlach - to miara
    plynnosci ruchu w danej okolicy, a nie predkosc chwilowa.
    """
    cur = {}
    for b in buses:
        try:
            t = dt.datetime.strptime(b["Time"], "%Y-%m-%d %H:%M:%S")
            cur[str(b["VehicleNumber"])] = (t, float(b["Lat"]), float(b["Lon"]))
        except (KeyError, TypeError, ValueError):
            continue
    if not cur:
        return [], cur
    # Pojazdy, ktore od dawna nie wysylaja pozycji (zajezdnia, awaria GPS), pomijamy.
    # Porownujemy z najswiezszym pojazdem, wiec strefa czasowa nie ma znaczenia.
    newest = max(t for t, _, _ in cur.values())
    cur = {v: p for v, p in cur.items() if (newest - p[0]).total_seconds() <= 300}

    cells = {}
    for v, (t1, lat1, lon1) in cur.items():
        if v not in prev:
            continue
        t0, lat0, lon0 = prev[v]
        sec = (t1 - t0).total_seconds()
        if not 120 <= sec <= 900:
            continue
        kmh = haversine_km(lat0, lon0, lat1, lon1) / sec * 3600
        if kmh > 90:
            continue  # skok pozycji GPS
        key = (
            math.floor((lat0 + lat1) / 2 / CELL_LAT),
            math.floor((lon0 + lon1) / 2 / CELL_LON),
        )
        cells.setdefault(key, []).append(kmh)

    records = []
    for (i, j), speeds in sorted(cells.items()):
        speeds.sort()
        records.append(
            {
                "cell_lat": round((i + 0.5) * CELL_LAT, 4),
                "cell_lon": round((j + 0.5) * CELL_LON, 4),
                "n": len(speeds),
                "speed_mean": round(sum(speeds) / len(speeds), 1),
                "speed_median": round(speeds[len(speeds) // 2], 1),
                "stopped_share": round(sum(s < 3 for s in speeds) / len(speeds), 2),
            }
        )
    return records, cur


def save_bus_speeds(ts, day):
    global _prev_buses
    raw = fetch_keyed(ZTM_URL.format(key=WARSAW_API_KEY), WARSAW_API_KEY)
    buses = raw.get("result")
    if not isinstance(buses, list):
        # API zwraca wtedy komunikat tekstowy, np. o zlym kluczu.
        raise RuntimeError(f"API Warszawy: {str(buses)[:120]}")
    records, _prev_buses_new = bus_speeds(_prev_buses, buses)
    _prev_buses = _prev_buses_new
    if not records:
        log(f"Autobusy: {len(buses)} pozycji, brak poprzedniego pomiaru do policzenia predkosci")
        return
    path = os.path.join(OUT_DIR, "bus_speed", f"{day}.jsonl.gz")
    append_jsonl(path, ({"fetched_at": ts, **r} for r in records))
    n = sum(r["n"] for r in records)
    log(f"Autobusy: {len(buses)} pozycji, predkosc z {n} pojazdow w {len(records)} komorkach -> {path}")


def save_tomtom_flow(ts, day, deadline):
    out = []
    for name, lat, lon in TOMTOM_POINTS:
        if time.time() > deadline:
            log("TomTom: przekroczony czas, pomijam reszte punktow")
            break
        try:
            raw = fetch_keyed(
                TOMTOM_FLOW_URL.format(lat=lat, lon=lon, key=TOMTOM_API_KEY), TOMTOM_API_KEY
            )
        except Exception as e:
            log(f"TomTom {name}: {e}")
            continue
        f = raw.get("flowSegmentData", {})
        coords = f.get("coordinates", {}).get("coordinate") or [{}]
        out.append(
            {
                "fetched_at": ts,
                "point": name,
                "frc": f.get("frc"),
                "current_speed": f.get("currentSpeed"),
                "free_flow_speed": f.get("freeFlowSpeed"),
                "current_travel_time": f.get("currentTravelTime"),
                "free_flow_travel_time": f.get("freeFlowTravelTime"),
                "confidence": f.get("confidence"),
                "road_closure": f.get("roadClosure"),
                "seg_start": [coords[0].get("latitude"), coords[0].get("longitude")],
                "seg_end": [coords[-1].get("latitude"), coords[-1].get("longitude")],
            }
        )
    if out:
        path = os.path.join(OUT_DIR, "traffic_flow", f"{day}.jsonl.gz")
        append_jsonl(path, out)
        log(f"TomTom: predkosc na {len(out)}/{len(TOMTOM_POINTS)} odcinkach -> {path}")


def save_tomtom_incidents(ts, day):
    url = TOMTOM_INCIDENTS_URL.format(
        bbox=WARSAW_BBOX,
        fields=urllib.parse.quote(TOMTOM_INCIDENT_FIELDS),
        key=TOMTOM_API_KEY,
    )
    raw = fetch_keyed(url, TOMTOM_API_KEY)
    out = []
    for inc in raw.get("incidents", []):
        p = inc.get("properties", {})
        geom = inc.get("geometry", {})
        c = geom.get("coordinates") or []
        first = c[0] if geom.get("type") == "LineString" and c else c
        out.append(
            {
                "fetched_at": ts,
                "incident_id": p.get("id"),
                # 1 wypadek, 6 korek, 7 zamkniety pas, 8 zamknieta droga, 9 roboty drogowe ...
                "icon_category": p.get("iconCategory"),
                "magnitude": p.get("magnitudeOfDelay"),
                "delay_sec": p.get("delay"),
                "length_m": p.get("length"),
                "start_time": p.get("startTime"),
                "end_time": p.get("endTime"),
                "from": p.get("from"),
                "to": p.get("to"),
                "description": "; ".join(
                    e.get("description", "") for e in p.get("events") or []
                ),
                "lon": first[0] if len(first) == 2 else None,
                "lat": first[1] if len(first) == 2 else None,
            }
        )
    path = os.path.join(OUT_DIR, "incidents", f"{day}.jsonl.gz")
    # Jak w "loose": pusty pomiar zapisujemy jako jeden znacznik.
    append_jsonl(path, out or [{"fetched_at": ts, "incident_id": None}])
    log(f"TomTom: {len(out)} utrudnien w ruchu -> {path}")


def save_traffic(slot):
    """Dodatkowe zrodla; kazde w osobnym try, zeby jedno nie blokowalo innych."""
    if not (WARSAW_API_KEY or TOMTOM_API_KEY):
        return
    now = dt.datetime.now(dt.timezone.utc)
    ts = now.isoformat(timespec="seconds")
    day = now.strftime("%Y-%m-%d")
    deadline = time.time() + EXTRA_BUDGET_SEC
    if WARSAW_API_KEY:
        try:
            save_bus_speeds(ts, day)
        except Exception as e:
            log(f"Autobusy: pomiar nieudany: {e}")
    if TOMTOM_API_KEY and slot % TOMTOM_EVERY == 0:
        try:
            save_tomtom_incidents(ts, day)
        except Exception as e:
            log(f"TomTom utrudnienia: pomiar nieudany: {e}")
        save_tomtom_flow(ts, day, deadline)


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
    # W lancuchu runow poprzedni run robi ostatni pomiar dokladnie w punkcie siatki,
    # a ten startuje kilkanascie sekund pozniej. Pomiar od razu bylby duplikatem,
    # wiec tuz po punkcie siatki czekamy na nastepny.
    since_slot = time.time() % INTERVAL_SEC
    if deadline is not None and since_slot < START_SKIP_SEC:
        log(f"Start {since_slot:.0f} s po punkcie siatki - czekam na nastepny pomiar")
        time.sleep(INTERVAL_SEC - since_slot)
    done = failures = 0
    while True:
        done += 1
        label = f"{done}" if deadline else f"{done}/{ITERATIONS}"
        slot = round(time.time() / INTERVAL_SEC)  # numer slotu na siatce co INTERVAL_SEC
        try:
            day = save_status(src)
            try:
                save_info(src, day)
            except Exception as e:
                log(f"Nie udalo sie zapisac informacji o stacjach: {e}")
            try:
                save_system(day)
            except Exception as e:
                log(f"Nie udalo sie zapisac danych o systemie: {e}")
        except Exception as e:
            failures += 1
            log(f"Pomiar {label} nieudany: {e}")
            if failures >= 3 and failures == done:
                log("BLAD: trzy pierwsze pomiary nieudane. Koncze od razu.")
                sys.exit(1)
            # Zrodlo moglo przestac dzialac - sprobuj wybrac inne na nastepny pomiar.
            src = pick_source() or src

        try:
            save_traffic(slot)
        except Exception as e:
            log(f"Dane o ruchu: blad: {e}")

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
