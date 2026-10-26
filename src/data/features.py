"""Cechy otoczenia stacji z danych statycznych (OSM, wysokosc terenu)."""

import numpy as np
import pandas as pd

from .config import CENTER_LAT, CENTER_LON, CRS_METRIC, OSM_DIR, STATIC
from .osm import POI_TAGS

RADIUS_M = 300
POP_RADIUS_M = 500  # heksagony populacji sa wieksze niz 300 m
DIST_TARGETS = {"metro": "dist_metro_m", "university": "dist_university_m", "train_station": "dist_train_station_m"}


def _xy(lat, lon):
    from pyproj import Transformer

    tr = Transformer.from_crs("EPSG:4326", CRS_METRIC, always_xy=True)
    x, y = tr.transform(np.asarray(lon, float), np.asarray(lat, float))
    return np.column_stack([x, y])


def add_station_features(stations, log):
    from scipy.spatial import cKDTree

    st = stations.copy()
    xy = _xy(st["lat"], st["lon"])
    st["dist_center_m"] = np.hypot(*(xy - _xy([CENTER_LAT], [CENTER_LON])[0]).T).round(0)

    pois_path = OSM_DIR / "pois.parquet"
    if pois_path.exists():
        pois = pd.read_parquet(pois_path)
        for cat in POI_TAGS:
            p = pois[pois["category"] == cat]
            col = f"n_{cat}_{RADIUS_M}m"
            if p.empty:
                # kategoria jeszcze nie pobrana - brak danych, a nie zero
                st[col] = np.nan
                log(f"  cechy: brak kategorii POI '{cat}' (fetch_static --only osm)")
                continue
            tree = cKDTree(_xy(p["lat"], p["lon"]))
            st[col] = [len(ix) for ix in tree.query_ball_point(xy, RADIUS_M)]
            if cat in DIST_TARGETS:
                d, _ = tree.query(xy)
                st[DIST_TARGETS[cat]] = d.round(0)
    else:
        log("  cechy: brak data/static/osm/pois.parquet (uruchom fetch_static --only osm)")

    cyc_path = OSM_DIR / "cycleways.parquet"
    if cyc_path.exists():
        import geopandas as gpd

        cyc = gpd.read_parquet(cyc_path).to_crs(CRS_METRIC)
        buf = gpd.GeoSeries(gpd.points_from_xy(xy[:, 0], xy[:, 1]), crs=CRS_METRIC).buffer(RADIUS_M)
        sidx = cyc.sindex
        lengths = []
        for g in buf:
            cand = cyc.iloc[sidx.query(g, predicate="intersects")]
            lengths.append(cand.geometry.intersection(g).length.sum())
        st[f"cycleway_m_{RADIUS_M}m"] = np.round(lengths, 0)
    else:
        log("  cechy: brak data/static/osm/cycleways.parquet")

    pop_path = STATIC / "population_h3.parquet"
    if pop_path.exists():
        pop = pd.read_parquet(pop_path)
        tree = cKDTree(_xy(pop["lat"], pop["lon"]))
        w = pop["population"].to_numpy()
        # heksagon H3 ~400 m: liczymy te, ktorych srodek lezy w promieniu
        st[f"population_{POP_RADIUS_M}m"] = [
            round(float(w[ix].sum())) for ix in tree.query_ball_point(xy, POP_RADIUS_M)
        ]
    else:
        log("  cechy: brak data/static/population_h3.parquet")

    tr_path = STATIC / "transit_stops.parquet"
    if tr_path.exists():
        tr = pd.read_parquet(tr_path)
        tree = cKDTree(_xy(tr["lat"], tr["lon"]))
        near = tree.query_ball_point(xy, RADIUS_M)
        st[f"n_transit_stops_{RADIUS_M}m"] = [len(ix) for ix in near]
        for col in [c for c in tr if c.startswith("departures_")]:
            v = tr[col].to_numpy()
            st[f"{col}_{RADIUS_M}m"] = [int(v[ix].sum()) for ix in near]
        st["dist_transit_stop_m"] = tree.query(xy)[0].round(0)
    else:
        log("  cechy: brak data/static/transit_stops.parquet")

    bld_path = OSM_DIR / "buildings_srodmiescie.parquet"
    if bld_path.exists():
        import geopandas as gpd

        bld = gpd.read_parquet(bld_path).to_crs(CRS_METRIC)
        bld = bld[bld["height_m"].notna()]
        c = bld.geometry.centroid
        tree = cKDTree(np.column_stack([c.x, c.y]))
        h = bld["height_m"].to_numpy()
        # tylko Srodmiescie: stacja musi miec caly okrag 300 m w obszarze z danymi,
        # inaczej srednia bylaby z czesci okregu; poza nim NaN (brak danych), a nie zero
        from shapely.geometry import Point

        area = bld.geometry.union_all().convex_hull.buffer(-RADIUS_M)
        covered = [area.contains(Point(x, y)) for x, y in xy]
        st[f"bldg_height_mean_{RADIUS_M}m"] = [
            round(float(h[ix].mean()), 1) if ok and len(ix) else np.nan
            for ok, ix in zip(covered, tree.query_ball_point(xy, RADIUS_M))
        ]

    elev_path = STATIC / "elevation.csv"
    if elev_path.exists():
        el = pd.read_csv(elev_path, dtype={"station_id": str})[["station_id", "elevation_m"]]
        st = st.merge(el, on="station_id", how="left")
    else:
        log("  cechy: brak data/static/elevation.csv")
    return st
