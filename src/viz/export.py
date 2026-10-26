"""Eksport danych z processed/ do wizualizacji 3D w Unity.

    python -m src.viz.export                     # wszystkie dni
    python -m src.viz.export --days 2026-10-23 2026-10-24
    python -m src.viz.export --out sciezka/do/StreamingAssets/veturilo

Wynik (domyslnie unity/Assets/StreamingAssets/veturilo/):
  index.json            lista dni + metadane (zrodlo danych, poczatek ukladu wspolrzednych)
  city.json             budynki Srodmiescia (obrys + wysokosc), drogi rowerowe, wybrane POI
  stations.json         stacje: pozycja, pojemnosc, statystyki
  routes.json           trasy stacja -> stacja (po grafie rowerowym, jesli jest; inaczej prosto)
  truck_routes.json     trasy relokacji (po grafie drogowym, jesli jest; inaczej prosto)
  day_RRRR-MM-DD.json   jeden dzien: stan stacji co 5 min, przejazdy, relokacje, pogoda, KPI

Wspolrzedne: metry w ukladzie lokalnym, poczatek = Palac Kultury (x = wschod, z = polnoc).
Czasy w dniu: sekundy od lokalnej polnocy (Europe/Warsaw), dzien 25.10 ma 25 h.

Ten sam format moze zapisywac symulacja DES (--source sim + pliki w formacie processed/),
wiec wizualizacja dziala bez zmian dla danych rzeczywistych i symulowanych.
"""

import argparse
import datetime as dt
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from src.data.config import CENTER_LAT, CENTER_LON, OSM_DIR, PROCESSED, ROOT, TZ

DEFAULT_OUT = ROOT / "unity" / "Assets" / "StreamingAssets" / "veturilo"
SLOT_SEC = 300
M_PER_DEG_LAT = 110_574.0
M_PER_DEG_LON = 111_320.0 * math.cos(math.radians(CENTER_LAT))
POI_EXPORT = ["metro", "train_station", "university", "mall", "attraction"]
WEEKDAYS_PL = ["pon", "wt", "śr", "czw", "pt", "sob", "nd"]


def log(msg):
    print(msg, flush=True)


def to_xz(lat, lon):
    """Stopnie -> metry w ukladzie lokalnym (rzut rownoodlegly, blad < 0,1% w Warszawie)."""
    x = (np.asarray(lon, dtype=float) - CENTER_LON) * M_PER_DEG_LON
    z = (np.asarray(lat, dtype=float) - CENTER_LAT) * M_PER_DEG_LAT
    return x, z


def flat_ints(xs, zs):
    out = np.empty(2 * len(xs), dtype=np.int64)
    out[0::2] = np.round(xs)
    out[1::2] = np.round(zs)
    return out.tolist()


def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
    log(f"  {path.name}: {path.stat().st_size / 1e6:.1f} MB")


# ---------------------------------------------------------------------------
# Miasto: budynki, drogi rowerowe, POI
# ---------------------------------------------------------------------------


def _lines_xz(geom, tol):
    """LineString/MultiLineString (stopnie) -> lista list punktow w metrach."""

    parts = list(geom.geoms) if geom.geom_type.startswith("Multi") else [geom]
    out = []
    for g in parts:
        c = np.asarray(g.coords)
        if len(c) < 2:
            continue
        x, z = to_xz(c[:, 1], c[:, 0])
        from shapely.geometry import LineString

        line = LineString(np.column_stack([x, z])).simplify(tol)
        cc = np.asarray(line.coords)
        if len(cc) >= 2:
            out.append(flat_ints(cc[:, 0], cc[:, 1]))
    return out


def export_city(out):
    from shapely import wkb
    from shapely.geometry import Polygon

    city = {"buildings": [], "cycleways": [], "pois": []}

    bpath = OSM_DIR / "buildings_srodmiescie.parquet"
    if bpath.exists():
        b = pd.read_parquet(bpath)
        for geom_b, h in zip(b["geometry"], b["height_m"].fillna(12.0)):
            geom = wkb.loads(geom_b)
            polys = list(geom.geoms) if geom.geom_type == "MultiPolygon" else [geom]
            for p in polys:
                if p.geom_type != "Polygon" or p.is_empty:
                    continue
                c = np.asarray(p.exterior.coords)
                x, z = to_xz(c[:, 1], c[:, 0])
                pm = Polygon(np.column_stack([x, z])).simplify(0.5)
                if pm.is_empty or pm.geom_type != "Polygon" or pm.area < 15:
                    continue
                cc = np.asarray(pm.exterior.coords)[:-1]
                if len(cc) < 3:
                    continue
                city["buildings"].append({"h": round(float(max(h, 3.0)), 1), "p": flat_ints(cc[:, 0], cc[:, 1])})
    else:
        log("  brak buildings_srodmiescie.parquet - miasto bez budynkow")

    cpath = OSM_DIR / "cycleways.parquet"
    if cpath.exists():
        c = pd.read_parquet(cpath)
        for geom_b in c["geometry"]:
            for pts in _lines_xz(wkb.loads(geom_b), 2.0):
                city["cycleways"].append({"p": pts})

    ppath = OSM_DIR / "pois.parquet"
    if ppath.exists():
        p = pd.read_parquet(ppath)
        p = p[p["category"].isin(POI_EXPORT)].copy()
        # uczelnie i atrakcje: tylko nazwane i wieksze obiekty, zeby nie zasmiecac sceny
        big = p["category"].isin(["university", "attraction", "mall"])
        p = p[~big | (p["name"].notna() & (p["area_m2"].fillna(0) > 2000))]
        p = p.drop_duplicates(["category", "name"]) if len(p) else p
        x, z = to_xz(p["lat"], p["lon"])
        for cat, name, xi, zi in zip(p["category"], p["name"].fillna(""), x, z):
            city["pois"].append({"c": cat, "n": str(name), "x": round(float(xi), 1), "z": round(float(zi), 1)})

    log(f"  miasto: {len(city['buildings'])} budynkow, {len(city['cycleways'])} odcinkow drog rowerowych, "
        f"{len(city['pois'])} POI")
    write_json(out / "city.json", city)


# ---------------------------------------------------------------------------
# Trasy po grafie OSM (opcjonalnie)
# ---------------------------------------------------------------------------


class Router:
    """Najkrotsze trasy stacja -> stacja po grafie OSM (graf z fetch_static --only osm).

    Bez pliku grafu zwraca odcinek prosty. Trasy sa cache'owane w data/static/osm/.
    """

    def __init__(self, kind, stations):
        self.kind = kind
        self.st = stations.set_index("station_id")
        self.graph_path = OSM_DIR / f"graph_{kind}.graphml"
        self.cache_path = OSM_DIR / f"viz_routes_{kind}.parquet"
        self.cache = {}
        if self.cache_path.exists():
            c = pd.read_parquet(self.cache_path)
            self.cache = {(a, b): json.loads(p) for a, b, p in zip(c["from_station"], c["to_station"], c["pts"])}
        self.g = None

    def _straight(self, a, b):
        x, z = to_xz(self.st.loc[[a, b], "lat"], self.st.loc[[a, b], "lon"])
        return flat_ints(x, z)

    def _load_graph(self):
        import osmnx as ox
        from scipy.sparse import csr_matrix

        log(f"  trasy {self.kind}: wczytuje {self.graph_path.name}...")
        g = ox.load_graphml(self.graph_path)
        g = ox.truncate.largest_component(g, strongly=True)
        nodes = list(g.nodes)
        idx = {n: i for i, n in enumerate(nodes)}
        edges, geoms = {}, {}
        for u, v, d in g.edges(data=True):
            k = (idx[u], idx[v])
            length = float(d.get("length", np.inf))
            if length < edges.get(k, np.inf):
                edges[k] = length
                geoms[k] = np.asarray(d["geometry"].coords) if "geometry" in d else None
        rows, cols = zip(*edges)
        self.mat = csr_matrix((list(edges.values()), (rows, cols)), shape=(len(nodes), len(nodes)))
        self.geoms = geoms
        self.node_xy = np.array([[g.nodes[n]["x"], g.nodes[n]["y"]] for n in nodes])
        ids = list(self.st.index)
        near = ox.distance.nearest_nodes(g, self.st["lon"].to_numpy(), self.st["lat"].to_numpy())
        self.snap = {sid: idx[n] for sid, n in zip(ids, near)}
        self.g = g

    def _path_coords(self, pred_row, src, dst):
        seq = [dst]
        while seq[-1] != src:
            p = pred_row[seq[-1]]
            if p < 0:
                return None
            seq.append(p)
        seq.reverse()
        pts = [self.node_xy[seq[0]]]
        for u, v in zip(seq[:-1], seq[1:]):
            geom = self.geoms.get((u, v))
            if geom is not None and len(geom) > 2:
                # geometria krawedzi moze byc zapisana w odwrotnym kierunku
                if np.hypot(*(geom[0] - self.node_xy[u])) > np.hypot(*(geom[-1] - self.node_xy[u])):
                    geom = geom[::-1]
                pts.extend(geom[1:])
            else:
                pts.append(self.node_xy[v])
        return np.asarray(pts)

    def routes(self, pairs):
        """pairs: lista (from_station, to_station) -> slownik para -> lista int [x,z,...]."""
        from shapely.geometry import LineString

        todo = [p for p in set(pairs) if p not in self.cache and p[0] != p[1]]
        if todo and self.graph_path.exists():
            from scipy.sparse.csgraph import dijkstra

            if self.g is None:
                self._load_graph()
            by_src = {}
            for a, b in todo:
                by_src.setdefault(a, []).append(b)
            srcs = list(by_src)
            log(f"  trasy {self.kind}: licze {len(todo)} nowych par z {len(srcs)} stacji...")
            for i in range(0, len(srcs), 25):
                chunk = srcs[i : i + 25]
                _, pred = dijkstra(self.mat, directed=True, indices=[self.snap[a] for a in chunk],
                                   return_predecessors=True)
                for k, a in enumerate(chunk):
                    for b in by_src[a]:
                        c = self._path_coords(pred[k], self.snap[a], self.snap[b])
                        if c is None:
                            continue
                        lat = np.concatenate([[self.st.at[a, "lat"]], c[:, 1], [self.st.at[b, "lat"]]])
                        lon = np.concatenate([[self.st.at[a, "lon"]], c[:, 0], [self.st.at[b, "lon"]]])
                        x, z = to_xz(lat, lon)
                        line = LineString(np.column_stack([x, z])).simplify(3.0)
                        cc = np.asarray(line.coords)
                        self.cache[(a, b)] = flat_ints(cc[:, 0], cc[:, 1])
            pd.DataFrame(
                [(a, b, json.dumps(p)) for (a, b), p in self.cache.items()],
                columns=["from_station", "to_station", "pts"],
            ).to_parquet(self.cache_path, index=False)
        elif todo:
            log(f"  trasy {self.kind}: brak {self.graph_path.name} - trasy w linii prostej "
                f"(uruchom fetch_static --only osm, zeby jechaly po drogach)")
        return {p: self.cache.get(p) or self._straight(*p) for p in set(pairs)}


# ---------------------------------------------------------------------------
# Dni
# ---------------------------------------------------------------------------


def sun_elevation(times_utc):
    """Wysokosc slonca [stopnie] nad Warszawa dla kazdej chwili (liczona, wiec znana takze dla godzin bez danych)."""
    from astral import Observer
    from astral.sun import elevation

    obs = Observer(latitude=CENTER_LAT, longitude=CENTER_LON)
    return [round(float(elevation(obs, t.to_pydatetime())), 1) for t in times_utc]


def local_days(times):
    loc = times.dt.tz_convert(TZ)
    return sorted(loc.dt.date.unique())


def day_bounds(day):
    start = pd.Timestamp(day).tz_localize(TZ)
    end = pd.Timestamp(day + dt.timedelta(days=1)).tz_localize(TZ)
    return start.tz_convert("UTC"), end.tz_convert("UTC")


def slot_matrix(ot, col, stations_order, slots):
    wide = ot.pivot_table(index="time", columns="station_id", values=col, aggfunc="last")
    wide = wide.reindex(columns=stations_order)
    wide = wide.reindex(wide.index.union(slots)).sort_index().ffill(limit=2).reindex(slots)
    # ffill(limit=2) = co najwyzej 10 min wstecz; dalej -1 (brak danych)
    return wide.fillna(-1).astype(int)


def export(out, days_wanted=None, source="observed"):
    log(f"Eksport do {out}")
    st = pd.read_parquet(PROCESSED / "stations.parquet")
    ot = pd.read_parquet(PROCESSED / "observed_timeseries.parquet")
    ot = ot[~ot["is_spike"]]
    trips = pd.read_parquet(PROCESSED / "trips.parquet")
    reb = pd.read_parquet(PROCESSED / "rebalancing_observed.parquet")
    cx = pd.read_parquet(PROCESSED / "context_hourly.parquet")
    fleet = pd.read_parquet(PROCESSED / "fleet_timeseries.parquet")

    # --- stacje
    st = st[st["station_id"].isin(ot["station_id"].unique())].reset_index(drop=True)
    sx, sz = to_xz(st["lat"], st["lon"])
    order = list(st["station_id"])
    sidx = {s: i for i, s in enumerate(order)}

    def col(name, default=0.0):
        return st[name].fillna(default).to_numpy() if name in st else np.full(len(st), default)

    stations = []
    for i, r in st.iterrows():
        stations.append({
            "id": str(r["station_id"]),
            "name": str(r["name"]),
            "x": round(float(sx[i]), 1),
            "z": round(float(sz[i]), 1),
            "cap": int(r["capacity"]) if pd.notna(r["capacity"]) else 10,
            "shareEmpty": round(float(col("share_empty")[i]), 3),
            "shareOverfull": round(float(col("share_overfull")[i]), 3),
            "meanBikes": round(float(col("mean_bikes")[i]), 1),
            "nRestaurants": int(col("n_restaurant_300m")[i]),
            "nOffices": int(col("n_office_300m")[i]),
            "nUniversities": int(col("n_university_300m")[i]),
            "distMetro": int(col("dist_metro_m", -1)[i]),
            "elevation": round(float(col("elevation_m")[i]), 1),
        })
    write_json(out / "stations.json", {"stations": stations})

    export_city(out)

    # --- dni
    days = local_days(ot["time"])
    if days_wanted:
        days = [d for d in days if d.isoformat() in days_wanted]

    trips_u = trips[
        (trips["type"] == "user") & ~trips["is_flicker"] & ~trips["too_fast"] & ~trips["is_long"]
        & ~trips["same_station"]
    ].copy()
    st_pairs = trips_u[(trips_u["from_type"] == "station") & (trips_u["to_type"] == "station")
                       & trips_u["from_station"].isin(sidx) & trips_u["to_station"].isin(sidx)]

    day_ranges = [day_bounds(d) for d in days]
    in_days = np.zeros(len(st_pairs), dtype=bool)
    for a, b in day_ranges:
        in_days |= (st_pairs["t_departure"] >= a).to_numpy() & (st_pairs["t_departure"] < b).to_numpy()
    pairs = list(zip(st_pairs["from_station"][in_days], st_pairs["to_station"][in_days]))
    bike_routes = Router("bike", st).routes(pairs)
    route_keys = sorted(bike_routes)
    route_idx = {k: i for i, k in enumerate(route_keys)}
    write_json(out / "routes.json", {"routes": [{"p": bike_routes[k]} for k in route_keys]})

    reb_ok = reb[reb["from_station"].isin(sidx) & reb["to_station"].isin(sidx)]
    truck_routes = Router("drive", st).routes(list(zip(reb_ok["from_station"], reb_ok["to_station"])))
    tkeys = sorted(truck_routes)
    tidx = {k: i for i, k in enumerate(tkeys)}
    write_json(out / "truck_routes.json", {"routes": [{"p": truck_routes[k]} for k in tkeys]})

    index = {
        "source": source,
        "generated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "originLat": CENTER_LAT,
        "originLon": CENTER_LON,
        "slotSec": SLOT_SEC,
        "days": [],
    }
    for day, (a, b) in zip(days, day_ranges):
        length = int((b - a).total_seconds())
        n_slots = length // SLOT_SEC
        slots = pd.date_range(a, periods=n_slots, freq=f"{SLOT_SEC}s")
        bikes = slot_matrix(ot, "bikes", order, slots)
        ebikes = slot_matrix(ot, "ebikes", order, slots)
        coverage = float((bikes.to_numpy() >= 0).any(axis=1).mean())

        cap = st["capacity"].fillna(10).to_numpy()
        bv = bikes.to_numpy()
        known = bv >= 0
        kpi_empty = ((bv == 0) & known).sum(axis=1)
        kpi_over = ((bv > cap) & known).sum(axis=1)
        kpi_at = np.where(known, bv, 0).sum(axis=1)
        kpi_known = known.any(axis=1)
        fl = fleet.set_index("time")["in_use"]
        fl = fl[~fl.index.duplicated()].reindex(fl.index.union(slots)).sort_index().ffill(limit=2).reindex(slots)

        # przejazdy uzytkownikow tego dnia (wg chwili wyjazdu)
        t = trips_u[(trips_u["t_departure"] >= a) & (trips_u["t_departure"] < b)].sort_values("t_departure")
        dep = ((t["t_departure"] - a).dt.total_seconds()).round().astype(int).to_numpy()
        arr = ((t["t_arrival"] - a).dt.total_seconds()).round().astype(int).to_numpy()
        rix, fx, fz, tx, tz = [], [], [], [], []
        fxs, fzs = to_xz(t["from_lat"], t["from_lon"])
        txs, tzs = to_xz(t["to_lat"], t["to_lon"])
        for k, (f_, to_, ft, tt) in enumerate(zip(t["from_station"], t["to_station"], t["from_type"], t["to_type"])):
            key = (f_, to_)
            if ft == "station" and tt == "station" and key in route_idx:
                rix.append(route_idx[key]); fx.append(0); fz.append(0); tx.append(0); tz.append(0)
            else:
                rix.append(-1)
                fx.append(int(round(fxs[k]))); fz.append(int(round(fzs[k])))
                tx.append(int(round(txs[k]))); tz.append(int(round(tzs[k])))
        from_i = [sidx.get(s, -1) for s in t["from_station"]]
        to_i = [sidx.get(s, -1) for s in t["to_station"]]

        # relokacje operatora
        r = reb_ok[(reb_ok["t_departure"] >= a) & (reb_ok["t_departure"] < b)].sort_values("t_departure")
        r_dep = ((r["t_departure"] - a).dt.total_seconds()).round().astype(int).to_numpy()
        r_arr = ((r["t_arrival"] - a).dt.total_seconds()).round().astype(int).to_numpy()
        # relokacja widoczna w danych co 5 min trwa czesto "0" - dajemy ciezarowce min. 6 min jazdy
        r_arr = np.maximum(r_arr, r_dep + 360)

        # kontekst godzinowy - zawsze pelna siatka od lokalnej polnocy (w dniu niepelnym
        # brakujace godziny uzupelnione najblizsza znana wartoscia), indeks = godzina od polnocy
        hours_idx = pd.date_range(a, b, freq="h", inclusive="left")
        raw = cx[(cx["time"] >= a) & (cx["time"] < b)].drop_duplicates("time").set_index("time").sort_index()
        events = sorted({e.strip() for v in raw.get("event_names", pd.Series(dtype=str)).dropna()
                         for e in str(v).split(";") if e.strip()})
        c = raw.reindex(hours_idx).ffill().bfill()
        c["local_hour"] = hours_idx.tz_convert(TZ).hour
        c["sun_elevation"] = sun_elevation(hours_idx + pd.Timedelta(minutes=30))

        def carr(name, default=0.0, nd=2):
            if name not in c:
                return [default] * len(c)
            return [round(float(v), nd) if pd.notna(v) else default for v in c[name]]

        hours_local = [int(h) for h in c["local_hour"]] if "local_hour" in c else list(range(len(c)))
        trips_per_hour = np.bincount(np.clip(dep // 3600, 0, 24), minlength=25)[: math.ceil(length / 3600)]

        offset = int(a.tz_convert(TZ).utcoffset().total_seconds())
        day_type = str(c["day_type"].iloc[0]) if "day_type" in c and len(c) else ""
        uni = int(c["n_uni_classes"].max()) if "n_uni_classes" in c and len(c) else 0

        doc = {
            "date": day.isoformat(),
            "label": f"{WEEKDAYS_PL[day.weekday()]} {day.day:02d}.{day.month:02d}",
            "dayType": day_type,
            "uniClasses": uni,
            "events": events,
            "startEpoch": int(a.timestamp()),
            "tzOffsetSec": offset,
            "lengthSec": length,
            "slotSec": SLOT_SEC,
            "coverage": round(coverage, 3),
            "states": [{"b": bikes[s].tolist(), "e": ebikes[s].tolist()} for s in order],
            "kpi": {
                "empty": kpi_empty.astype(int).tolist(),
                "overfull": kpi_over.astype(int).tolist(),
                "atStations": kpi_at.astype(int).tolist(),
                "inUse": fl.fillna(-1).astype(int).tolist(),
                "known": kpi_known.astype(int).tolist(),
                "tripsPerHour": trips_per_hour.astype(int).tolist(),
            },
            "trips": {
                "dep": dep.tolist(), "arr": arr.tolist(), "route": rix,
                "ebike": t["is_ebike"].fillna(False).astype(int).tolist(),
                "fromSt": from_i, "toSt": to_i,
                "fx": fx, "fz": fz, "tx": tx, "tz": tz,
            },
            "trucks": {
                "dep": r_dep.tolist(), "arr": r_arr.tolist(),
                "route": [tidx[(f_, to_)] for f_, to_ in zip(r["from_station"], r["to_station"])],
                "n": r["n_bikes"].astype(int).tolist(),
                "fromSt": [sidx[s] for s in r["from_station"]], "toSt": [sidx[s] for s in r["to_station"]],
            },
            "hours": {
                "localHour": hours_local,
                "temp": carr("temperature_2m", 10.0, 1),
                "precip": carr("precipitation", 0.0, 2),
                "cloud": carr("cloud_cover", 50.0, 0),
                "wind": carr("wind_speed_10m", 0.0, 1),
                "sunElevation": carr("sun_elevation", 0.0, 1),
                "weatherCode": [int(v) for v in carr("weather_code", 0, 0)],
                "congestion": carr("congestion", 0.0, 3),
                "aqi": carr("european_aqi", 0.0, 0),
            },
        }
        fname = f"day_{day.isoformat()}.json"
        log(f"Dzien {day} ({doc['label']}): pokrycie {coverage:.0%}, {len(dep)} przejazdow, "
            f"{len(r_dep)} relokacji")
        write_json(out / fname, doc)
        index["days"].append({
            "date": day.isoformat(), "label": doc["label"], "file": fname,
            "trips": int(len(dep)), "coverage": round(coverage, 3), "dayType": day_type,
        })
    write_json(out / "index.json", index)
    log("Gotowe.")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--days", nargs="*", help="daty RRRR-MM-DD (domyslnie wszystkie)")
    ap.add_argument("--source", default="observed", help="observed | sim (etykieta w wizualizacji)")
    args = ap.parse_args()
    export(args.out, set(args.days) if args.days else None, args.source)


if __name__ == "__main__":
    main()
