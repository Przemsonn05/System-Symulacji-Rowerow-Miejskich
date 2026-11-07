"""Eksport danych z processed/ do wizualizacji 3D w Unity.

    python -m src.viz.export                     # wszystkie dni
    python -m src.viz.export --days 2026-10-23 2026-10-24
    python -m src.viz.export --out sciezka/do/StreamingAssets/veturilo
    python -m src.viz.export --source sim --runs results/sim/threshold_2/seed_1000 ...   # model (= export_sim)

Wynik (domyslnie unity/Assets/StreamingAssets/veturilo/):
  index.json            lista dni + metadane (zrodlo danych, poczatek ukladu wspolrzednych)
  city.json             budynki Srodmiescia (obrys + wysokosc), drogi rowerowe, wybrane POI
  basemap.json          podklad: granica miasta, Wisla i woda, zielen, drzewa, glowne ulice, mosty, tory, metro,
                        mieszkancy (heksagony)
  buildings.json        budynki calej Warszawy (OSM) w kafelkach 2 x 2 km
  stations.json         stacje: pozycja, pojemnosc, statystyki, cechy otoczenia
  routes.json           trasy stacja -> stacja (po grafie rowerowym, jesli jest; inaczej prosto)
  truck_routes.json     trasy relokacji (po grafie drogowym, jesli jest; inaczej prosto)
  day_RRRR-MM-DD.json   jeden dzien: stan stacji co 5 min, przejazdy, relokacje, pogoda, KPI,
                        korki TomTom, utrudnienia, wydarzenia, rowery poza stacjami, szacowany utracony popyt,
                        fale pustek (src.metrics), przejazdy dojazdowe (trip_features)
  sim_*.json            wynik symulacji DES - osobnym poleceniem python -m src.viz.export_sim

Wspolrzedne: metry w ukladzie lokalnym, poczatek = Palac Kultury (x = wschod, z = polnoc).
Czasy w dniu: sekundy od lokalnej polnocy (Europe/Warsaw), dzien 25.10 ma 25 h.

Symulacja DES ma ten sam format dnia (src/viz/export_sim.py); lista symulacji w index.json ("sims")
jest zachowywana przy ponownym eksporcie danych rzeczywistych.
"""

import argparse
import datetime as dt
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from src.data.config import BBOX, CENTER_LAT, CENTER_LON, DATA, OSM_DIR, PROCESSED, ROOT, STATIC, TZ
from src.data.context import TOMTOM_CORRIDORS
from src.data.raw import iter_jsonl

DEFAULT_OUT = ROOT / "unity" / "Assets" / "StreamingAssets" / "veturilo"
SLOT_SEC = 300
STEP_SEC = 1800  # krok danych TomTom (pomiar co 30 min)
CORRIDOR_LABELS = {
    "jerozolimskie": "Al. Jerozolimskie",
    "marszalkowska_pl_konstytucji": "Marszałkowska",
    "niepodleglosci_pole_mokotowskie": "al. Niepodległości",
    "pulawska_mokotow": "Puławska",
    "wislostrada_centrum": "Wisłostrada",
    "trasa_lazienkowska": "Trasa Łazienkowska",
    "solidarnosci_wola": "al. Solidarności",
    "prymasa_tysiaclecia": "Prymasa Tysiąclecia",
    "grochowska": "Grochowska",
    "modlinska_bialoleka": "Modlińska",
}
# kategorie TomTom pokazywane na mapie: 1 wypadek, 6 korek, 7 zamkniety pas, 8 zamknieta droga, 9 roboty
INCIDENT_CATS = {1, 6, 7, 8, 9}
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
    if (OSM_DIR / "buildings_warsaw.parquet").exists():
        pass  # budynki calej Warszawy ida do buildings.json
    elif bpath.exists():
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


BUILDING_TILE = 2000


def export_buildings(out):
    """Budynki calej Warszawy: kafelki 2 x 2 km (osobna siatka na kafelek - Unity pomija niewidoczne).
    Kafelek: h = wysokosci, n = liczba wierzcholkow obrysu, p = wspolrzedne [x, z, ...] wszystkich obrysow."""
    import shapely
    from shapely import wkb

    path = OSM_DIR / "buildings_warsaw.parquet"
    if not path.exists():
        log("  brak buildings_warsaw.parquet - budynki tylko w Srodmiesciu (uruchom fetch_static --only osm)")
        write_json(out / "buildings.json", {"tile": BUILDING_TILE, "tiles": []})
        return
    b = pd.read_parquet(path)
    tiles = {}
    count = 0
    for g, h in zip(b["geometry"], b["height_m"]):
        for poly in shapely.get_parts(_to_metric(wkb.loads(g))):
            if poly.geom_type != "Polygon" or poly.area < 30:
                continue
            cc = np.asarray(poly.exterior.simplify(0.8).coords)[:-1]
            if len(cc) < 3:
                continue
            c = poly.centroid
            key = (int(c.x // BUILDING_TILE), int(c.y // BUILDING_TILE))
            t = tiles.setdefault(key, {"h": [], "n": [], "p": []})
            t["h"].append(round(float(h), 1))
            t["n"].append(len(cc))
            t["p"].extend(flat_ints(cc[:, 0], cc[:, 1]))
            count += 1
    log(f"  budynki: {count} w {len(tiles)} kafelkach")
    write_json(out / "buildings.json", {"tile": BUILDING_TILE, "tiles": list(tiles.values())})


# gestosc drzew [m2 na drzewo] wg klasy zieleni z osm.py: 0 las, 1 park, 2 cmentarz, 3 trawa (bez drzew)
TREE_M2 = {0: 160.0, 1: 450.0, 2: 260.0}
MAX_TREES = 90000


def _trees(polys_by_cls, rng):
    """Losowe polozenia drzew w lasach, parkach i na cmentarzach (staly seed - za kazdym razem te same)."""
    import shapely

    pts = []
    total_area = sum(p.area / TREE_M2[c] for c, ps in polys_by_cls.items() if c in TREE_M2 for p in ps)
    scale = min(1.0, MAX_TREES / max(total_area, 1))
    for cls, polys in polys_by_cls.items():
        if cls not in TREE_M2:
            continue
        for poly in polys:
            n = int(poly.area / TREE_M2[cls] * scale)
            if n <= 0:
                continue
            minx, miny, maxx, maxy = poly.bounds
            k = 0
            while k < n:
                xs = rng.uniform(minx, maxx, n * 2)
                zs = rng.uniform(miny, maxy, n * 2)
                inside = shapely.contains_xy(poly, xs, zs)
                for x, z in zip(xs[inside], zs[inside]):
                    if k >= n:
                        break
                    pts.extend((int(x), int(z)))
                    k += 1
                if not inside.any():
                    break
    return pts


def _to_metric(geom):
    import shapely

    return shapely.transform(geom, lambda c: np.column_stack(to_xz(c[:, 1], c[:, 0])))


def _mesh(polys, tol):
    """Wielokaty (metry) -> jedna siatka trojkatow {v: [x,z,...], t: [i,...]} (triangulacja z ograniczeniami)."""
    import shapely

    verts, tris, index = [], [], {}
    for poly in polys:
        poly = poly.simplify(tol)
        if poly.is_empty:
            continue
        for tri in shapely.get_parts(shapely.constrained_delaunay_triangles(poly)):
            ids = []
            for x, z in list(tri.exterior.coords)[:3]:
                key = (int(round(x)), int(round(z)))
                if key not in index:
                    index[key] = len(index)
                    verts.extend(key)
                ids.append(index[key])
            if len(set(ids)) == 3:
                tris.extend(ids)
    return {"v": verts, "t": tris}


def export_basemap(out):
    """Podklad mapy: granica Warszawy, woda, zielen, glowne ulice, tory, mieszkancy w heksagonach H3."""
    import shapely
    from shapely import wkb

    bm = {"boundary": [], "water": {"v": [], "t": []}, "green": {"v": [], "t": []}, "forest": {"v": [], "t": []},
          "roads": [], "rail": [], "metro": [], "trees": [], "population": []}

    bpath = OSM_DIR / "boundary.geojson"
    if bpath.exists():
        import geopandas as gpd

        geom = _to_metric(gpd.read_file(bpath).geometry.iloc[0])
        for p in shapely.get_parts(geom):
            cc = np.asarray(p.exterior.simplify(15).coords)
            bm["boundary"].append({"p": flat_ints(cc[:, 0], cc[:, 1])})

    path = OSM_DIR / "basemap.parquet"
    if path.exists():
        b = pd.read_parquet(path)
        geoms = [_to_metric(wkb.loads(g)) for g in b["geometry"]]
        bridge = b["bridge"] if "bridge" in b else pd.Series(0, index=b.index)
        polys = {}
        for g, k, c in zip(geoms, b["kind"], b["cls"]):
            if k in ("water", "green"):
                key = "water" if k == "water" else ("forest" if c == 0 else "green")
                polys.setdefault(key, []).extend(p for p in shapely.get_parts(g) if p.geom_type == "Polygon")
        for key, ps in polys.items():
            bm[key] = _mesh(ps, 3.0)
        by_cls = {}
        for g, k, c in zip(geoms, b["kind"], b["cls"]):
            if k == "green":
                by_cls.setdefault(int(c), []).extend(p for p in shapely.get_parts(g) if p.geom_type == "Polygon")
        bm["trees"] = _trees(by_cls, np.random.default_rng(1918))
        for g, kind, cls, br in zip(geoms, b["kind"], b["cls"], bridge):
            if kind not in ("road", "rail", "metro"):
                continue
            for line in shapely.get_parts(g):
                cc = np.asarray(line.simplify(4.0).coords)
                if len(cc) >= 2:
                    item = {"p": flat_ints(cc[:, 0], cc[:, 1])}
                    if kind in ("road", "metro"):
                        item["k"] = int(cls)
                    if kind == "road":
                        item["b"] = int(br)
                    bm["roads" if kind == "road" else kind].append(item)
    else:
        log("  brak basemap.parquet - bez Wisly, zieleni i ulic (uruchom fetch_static --only osm)")

    ppath = STATIC / "population_h3.parquet"
    if ppath.exists():
        p = pd.read_parquet(ppath)
        x, z = to_xz(p["lat"], p["lon"])
        bm["population"] = [{"x": int(round(xi)), "z": int(round(zi)), "pop": int(v)}
                            for xi, zi, v in zip(x, z, p["population"].fillna(0))]

    log(f"  podklad: woda {len(bm['water']['t']) // 3} trojkatow, zielen {len(bm['green']['t']) // 3}, "
        f"las {len(bm['forest']['t']) // 3}, {len(bm['trees']) // 2} drzew, {len(bm['roads'])} odcinkow ulic, "
        f"{len(bm['rail'])} torow, {len(bm['metro'])} odcinkow metra, {len(bm['population'])} heksagonow")
    write_json(out / "basemap.json", bm)


# ---------------------------------------------------------------------------
# Kontekst dnia: korki TomTom, utrudnienia, wydarzenia, rowery poza stacjami
# ---------------------------------------------------------------------------


def _day_records(folder, a, b):
    """Rekordy z plikow dziennych (UTC) obejmujacych przedzial [a, b)."""
    rows = []
    for d in pd.date_range(a.floor("D"), b.floor("D"), freq="D"):
        path = DATA / folder / f"{d.date().isoformat()}.jsonl.gz"
        if path.exists():
            rows.extend(iter_jsonl(path))
    df = pd.DataFrame(rows)
    if df.empty or "fetched_at" not in df:
        return pd.DataFrame()
    df["time"] = pd.to_datetime(df["fetched_at"], utc=True)
    return df[(df["time"] >= a) & (df["time"] < b)]


def in_bbox(lat, lon):
    return ((lat >= BBOX["lat_min"]) & (lat <= BBOX["lat_max"]) & (lon >= BBOX["lon_min"])
            & (lon <= BBOX["lon_max"]))


def day_traffic(a, b, n_steps):
    """Korytarze TomTom: polozenie odcinka i wskaznik korkow (1 - predkosc/swobodna) co 30 min; -1 = brak."""
    flow = _day_records("traffic_flow", a, b)
    if flow.empty:
        return {"stepSec": STEP_SEC, "corridors": []}
    flow = flow[flow["free_flow_speed"] > 0].copy()
    flow["corridor"] = flow["point"].map(TOMTOM_CORRIDORS).fillna(flow["point"])
    flow["congestion"] = (1 - flow["current_speed"] / flow["free_flow_speed"]).clip(lower=0)
    flow["step"] = ((flow["time"] - a).dt.total_seconds() // STEP_SEC).astype(int)
    corridors = []
    for corr, g in flow.groupby("corridor"):
        last = g.sort_values("time").iloc[-1]  # aktualny punkt pomiaru (po przeniesieniu 26.10)
        lat = (last["seg_start"][0] + last["seg_end"][0]) / 2
        lon = (last["seg_start"][1] + last["seg_end"][1]) / 2
        x, z = to_xz([lat], [lon])
        cong = g.groupby("step")["congestion"].mean().reindex(range(n_steps))
        corridors.append({
            "name": corr, "label": CORRIDOR_LABELS.get(corr, corr),
            "x": round(float(x[0]), 1), "z": round(float(z[0]), 1),
            "cong": [round(float(v), 3) if pd.notna(v) else -1 for v in cong],
        })
    return {"stepSec": STEP_SEC, "corridors": corridors}


def day_incidents(a, b):
    """Utrudnienia TomTom: jeden pomiar na kazde 30 min (krok), tylko wybrane kategorie."""
    inc = _day_records("incidents", a, b)
    out = {"stepSec": STEP_SEC, "step": [], "x": [], "z": [], "cat": [], "mag": []}
    if inc.empty or "incident_id" not in inc:
        return out
    inc = inc[inc["incident_id"].notna() & inc["icon_category"].isin(INCIDENT_CATS) & inc["lat"].notna()]
    inc = inc[in_bbox(inc["lat"], inc["lon"])].copy()
    inc["step"] = ((inc["time"] - a).dt.total_seconds() // STEP_SEC).astype(int)
    # pierwszy pomiar w kazdym kroku
    first = inc.groupby("step")["time"].transform("min")
    inc = inc[inc["time"] == first].drop_duplicates(["step", "incident_id"])
    x, z = to_xz(inc["lat"], inc["lon"])
    out.update(step=inc["step"].astype(int).tolist(), x=np.round(x).astype(int).tolist(),
               z=np.round(z).astype(int).tolist(), cat=inc["icon_category"].astype(int).tolist(),
               mag=inc["magnitude"].fillna(0).astype(int).tolist())
    return out


def day_loose(a, b):
    """Rowery zostawione poza stacjami w Warszawie: numer pomiaru (5 min), pozycja, czy e-rower."""
    lo = _day_records("loose", a, b)
    out = {"slot": [], "x": [], "z": [], "e": []}
    if lo.empty or "bike_number" not in lo:
        return out
    lo = lo[lo["bike_number"].notna() & lo["lat"].notna()]
    lo = lo[in_bbox(lo["lat"], lo["lon"])]
    slot = ((lo["time"] - a).dt.total_seconds() / SLOT_SEC).round().astype(int)
    x, z = to_xz(lo["lat"], lo["lon"])
    battery = lo["battery"] if "battery" in lo else pd.Series(np.nan, index=lo.index)
    out.update(slot=slot.tolist(), x=np.round(x).astype(int).tolist(), z=np.round(z).astype(int).tolist(),
               e=battery.notna().astype(int).tolist())
    return out


def demand_rates(sh, cx):
    """Popyt stacji [wypozyczenia / h, gdy rowery sa dostepne] wg godziny lokalnej i typu dnia (roboczy / wolny).

    Szacunek z godzin, w ktorych stacja miala rowery (popyt na pustej stacji jest niewidoczny).
    Malo obserwacji -> sciagniecie do profilu calego systemu przeskalowanego wielkoscia stacji."""
    sh = sh.copy()
    loc = sh["hour"].dt.tz_convert(TZ)
    sh["lh"] = loc.dt.hour
    work = cx.drop_duplicates("local_date").set_index("local_date")["day_type"].eq("workday")
    sh["wk"] = loc.dt.date.map(work).fillna(True).astype(bool)
    sh["avail_h"] = sh["minutes_available"] / 60.0
    g = sh.groupby(["station_id", "lh", "wk"])[["departures", "avail_h"]].sum()
    sys_prof = sh.groupby(["lh", "wk"])[["departures", "avail_h"]].sum()
    sys_rate = sys_prof["departures"] / sys_prof["avail_h"].clip(lower=1e-6)
    st_tot = sh.groupby("station_id")[["departures", "avail_h"]].sum()
    st_scale = (st_tot["departures"] / st_tot["avail_h"].clip(lower=1e-6)) / (
        sh["departures"].sum() / max(sh["avail_h"].sum(), 1e-6))
    prior = sys_rate.reindex(pd.MultiIndex.from_tuples([(lh, wk) for _, lh, wk in g.index])).to_numpy() \
        * st_scale.reindex(g.index.get_level_values(0)).fillna(1.0).to_numpy()
    k = 2.0  # sila sciagania: ok. 2 h obserwacji
    rate = (g["departures"].to_numpy() + k * prior) / (g["avail_h"].to_numpy() + k)
    return pd.Series(rate, index=g.index)


def day_lost(day, a, slots, bikes, order, rates, workday):
    """Szacowany utracony popyt: na kazdy pomiar (5 min), w ktorym stacja jest pusta, popyt tej stacji
    o tej godzinie / 12. Wynik: suma narastajaco co 30 min dla kazdej stacji + popyt stacji co godzine."""
    steps = math.ceil(len(slots) * SLOT_SEC / STEP_SEC)
    lh = slots.tz_convert(TZ).hour.to_numpy()
    lost = np.zeros((len(order), steps))
    rate_h = np.zeros((len(order), 24))
    bv = bikes.to_numpy()  # sloty x stacje
    for i, sid in enumerate(order):
        for h in range(24):
            rate_h[i, h] = rates.get((sid, h, workday), 0.0)
        empty = bv[:, i] == 0
        per_slot = np.where(empty, rate_h[i, lh] / 12.0, 0.0)
        step = (np.arange(len(slots)) * SLOT_SEC) // STEP_SEC
        lost[i] = np.cumsum(np.bincount(step, weights=per_slot, minlength=steps)[:steps])
    return {
        "stepSec": STEP_SEC, "steps": steps,
        "cum": np.round(lost, 2).ravel().tolist(),
        "rate": np.round(rate_h, 2).ravel().tolist(),
        "total": round(float(lost[:, -1].sum()), 1),
    }


def day_events(a, b):
    """Wydarzenia z events.csv trwajace w tym dniu (czas w sekundach od lokalnej polnocy)."""
    path = STATIC / "events.csv"
    if not path.exists():
        return []
    ev = pd.read_csv(path)
    ev["start"] = pd.to_datetime(ev["start_utc"], utc=True)
    ev["end"] = pd.to_datetime(ev["end_utc"], utc=True)
    ev = ev[(ev["end"] > a) & (ev["start"] < b) & ev["lat"].notna()]
    x, z = to_xz(ev["lat"], ev["lon"])
    return [{
        "name": str(r["name"]), "venue": str(r["venue"]), "category": str(r["category"]),
        "x": round(float(xi), 1), "z": round(float(zi), 1),
        "start": int((r["start"] - a).total_seconds()), "end": int((r["end"] - a).total_seconds()),
        "large": int(r["scale"] == "large"),
    } for (_, r), xi, zi in zip(ev.iterrows(), x, z)]


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


def commute_keys():
    """(rower, t_departure) przejazdow na trasach dojazdowych (z src.data.agents)."""
    path = PROCESSED / "trip_features.parquet"
    if not path.exists():
        return set()
    tf = pd.read_parquet(path, columns=["bike", "t_departure", "is_commute"])
    tf = tf[tf["is_commute"]]
    return set(zip(tf["bike"].astype(str), tf["t_departure"]))


def day_cascades():
    """Fale pustek (>= 3 stacje) ze wszystkich dni - src.metrics, siatka 5 min."""
    try:
        from src.metrics.emergence import cascades
        from src.metrics.io import load_run

        return cascades(load_run(PROCESSED))["members"]
    except Exception as e:  # metryki sa dodatkiem - eksport dziala bez nich
        log(f"  fale pustek pominiete: {e}")
        return []


def export(out, days_wanted=None, source="observed"):
    log(f"Eksport do {out}")
    st = pd.read_parquet(PROCESSED / "stations.parquet")
    ot = pd.read_parquet(PROCESSED / "observed_timeseries.parquet")
    ot = ot[~ot["is_spike"]]
    trips = pd.read_parquet(PROCESSED / "trips.parquet")
    reb = pd.read_parquet(PROCESSED / "rebalancing_observed.parquet")
    cx = pd.read_parquet(PROCESSED / "context_hourly.parquet")
    fleet = pd.read_parquet(PROCESSED / "fleet_timeseries.parquet")
    rates = demand_rates(pd.read_parquet(PROCESSED / "station_hourly.parquet"), cx)
    commute = commute_keys()
    members = day_cascades()

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
            "nBars": int(col("n_bar_300m")[i]),
            "nCafes": int(col("n_cafe_300m")[i]),
            "nOffices": int(col("n_office_300m")[i]),
            "nUniversities": int(col("n_university_300m")[i]),
            "nSchools": int(col("n_school_300m")[i]),
            "distMetro": int(col("dist_metro_m", -1)[i]),
            "distCenter": int(col("dist_center_m", -1)[i]),
            "population": int(col("population_500m")[i]),
            "transitDepartures": int(col("departures_total_300m")[i]),
            "cyclewayM": int(col("cycleway_m_300m")[i]),
            "elevation": round(float(col("elevation_m")[i]), 1),
        })
    write_json(out / "stations.json", {"stations": stations})

    export_city(out)
    export_buildings(out)
    export_basemap(out)

    # --- dni
    days = local_days(ot["time"])
    if days_wanted:
        days = [d for d in days if d.isoformat() in days_wanted]

    trips_u = trips[
        (trips["type"] == "user") & ~trips["is_flicker"] & ~trips["too_fast"] & ~trips["is_long"]
        & ~trips["same_station"]
        # stacja bez polozenia w danych (np. nowa, jeszcze bez wpisu w info) - nie da sie narysowac
        & trips[["from_lat", "from_lon", "to_lat", "to_lon"]].notna().all(axis=1)
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

    old_index = out / "index.json"
    sims = json.loads(old_index.read_text(encoding="utf-8")).get("sims", []) if old_index.exists() else []
    sims = [s_ for s_ in sims if (out / s_["file"]).exists()]
    index = {
        "source": source,
        "generated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "originLat": CENTER_LAT,
        "originLon": CENTER_LON,
        "slotSec": SLOT_SEC,
        "days": [],
        "sims": sims,
    }
    from .export_sim import flat_cascades

    sidx_str = {str(k): v for k, v in sidx.items()}
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
        fleet_slots = fleet.drop_duplicates("time").set_index("time")
        fleet_slots = fleet_slots.reindex(fleet_slots.index.union(slots)).sort_index().ffill(limit=2).reindex(slots)
        fl = fleet_slots["in_use"]

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
            "source": "observed",
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
                "awayLong": fleet_slots["away_long"].fillna(-1).astype(int).tolist(),
                "looseWarsaw": fleet_slots["loose_warsaw"].fillna(-1).astype(int).tolist(),
                "fleetTarget": int(fleet["set_point_bikes"].dropna().iloc[-1]) if fleet["set_point_bikes"].notna().any() else 0,
                "known": kpi_known.astype(int).tolist(),
                "tripsPerHour": trips_per_hour.astype(int).tolist(),
            },
            "eventList": day_events(a, b),
            "traffic": day_traffic(a, b, math.ceil(length / STEP_SEC)),
            "incidents": day_incidents(a, b),
            "loose": day_loose(a, b),
            "lost": day_lost(day, a, slots, bikes, order, rates, day_type == "workday"),
            "trips": {
                "dep": dep.tolist(), "arr": arr.tolist(), "route": rix,
                "ebike": t["is_ebike"].fillna(False).astype(int).tolist(),
                "bike": pd.to_numeric(t["bike"], errors="coerce").fillna(0).astype(np.int64).tolist(),
                "km": t["network_km"].fillna(t["distance_km"]).fillna(0).round(1).tolist(),
                "fromSt": from_i, "toSt": to_i,
                "fx": fx, "fz": fz, "tx": tx, "tz": tz,
                # 1 = przejazd na trasie dojazdowej (processed/trip_features.parquet)
                "kind": [int((str(bk), td) in commute) for bk, td in zip(t["bike"], t["t_departure"])],
            },
            "cascades": flat_cascades([m for m in members if m["date"] == day], sidx_str,
                                      pd.Timestamp(day).tz_localize(TZ)),
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
                "apparentTemp": carr("apparent_temperature", 10.0, 1),
                "humidity": carr("relative_humidity_2m", 70.0, 0),
                "sunElevation": carr("sun_elevation", 0.0, 1),
                "weatherCode": [int(v) for v in carr("weather_code", 0, 0)],
                "congestion": carr("congestion", 0.0, 3),
                "aqi": carr("european_aqi", 0.0, 0),
            },
        }
        fname = f"day_{day.isoformat()}.json"
        log(f"Dzien {day} ({doc['label']}): pokrycie {coverage:.0%}, {len(dep)} przejazdow, "
            f"{len(r_dep)} relokacji, utracony popyt ok. {doc['lost']['total']:.0f}")
        write_json(out / fname, doc)
        index["days"].append({
            "date": day.isoformat(), "label": doc["label"], "file": fname,
            "trips": int(len(dep)), "coverage": round(coverage, 3), "dayType": day_type,
            "lost": doc["lost"]["total"],
        })
    write_json(out / "index.json", index)
    log("Gotowe.")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--days", nargs="*", help="daty RRRR-MM-DD (domyslnie wszystkie)")
    ap.add_argument("--source", default="observed", help="observed | sim (sim = przebiegi symulacji z --runs)")
    ap.add_argument("--runs", nargs="*", default=[], help="--source sim: katalogi przebiegow symulacji")
    args = ap.parse_args()
    if args.source == "sim":
        # to samo co python -m src.viz.export_sim <katalogi>
        from .export_sim import export as export_sim

        if not args.runs:
            ap.error("--source sim wymaga --runs <katalogi przebiegow>")
        export_sim([Path(r) for r in args.runs], args.out)
        return
    export(args.out, set(args.days) if args.days else None, args.source)


if __name__ == "__main__":
    main()
