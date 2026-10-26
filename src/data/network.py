"""Odleglosci miedzy stacjami po sieci drog rowerowych (graf OSM, network_type=bike).

Macierz stacja -> stacja liczona algorytmem Dijkstry (scipy) i zapisywana do
data/static/station_network_distance.parquet - mala, wiec trafia do repo i jest
dostepna takze bez pobierania grafu. Przeliczana, gdy pojawia sie nowe stacje.
"""

import numpy as np
import pandas as pd

from .config import OSM_DIR, STATIC

OUT = STATIC / "station_network_distance.parquet"
BATCH = 25  # zrodel naraz - ogranicza pamiec (BATCH x liczba wezlow)


def _compute(stations, log):
    import osmnx as ox
    from scipy.sparse import csr_matrix
    from scipy.sparse.csgraph import dijkstra

    graph_path = OSM_DIR / "graph_bike.graphml"
    log(f"  siec: wczytuje {graph_path.name}...")
    g = ox.load_graphml(graph_path)
    # tylko silnie spojna czesc grafu: inaczej stacja przy slepej drodze jednokierunkowej
    # (np. Eurocentrum) jest osiagalna, ale nie da sie z niej wyjechac
    g = ox.truncate.largest_component(g, strongly=True)
    nodes = list(g.nodes)
    idx = {n: i for i, n in enumerate(nodes)}
    # przy wielu krawedziach miedzy tymi samymi wezlami bierzemy najkrotsza
    edges = {}
    for u, v, d in g.edges(data=True):
        k = (idx[u], idx[v])
        edges[k] = min(edges.get(k, np.inf), float(d.get("length", np.inf)))
    rows, cols = zip(*edges)
    mat = csr_matrix((list(edges.values()), (rows, cols)), shape=(len(nodes), len(nodes)))

    near, snap = ox.distance.nearest_nodes(g, stations["lon"].to_numpy(), stations["lat"].to_numpy(), return_dist=True)
    src = np.array([idx[n] for n in near])
    out = []
    for i in range(0, len(src), BATCH):
        d = dijkstra(mat, directed=True, indices=src[i : i + BATCH])[:, src]
        for k, row in enumerate(d):
            out.append(pd.DataFrame({
                "from": stations["station_id"].iloc[i + k],
                "to": stations["station_id"].to_numpy(),
                "network_km": np.round(row / 1000, 3),
            }))
    res = pd.concat(out, ignore_index=True)
    res.loc[~np.isfinite(res["network_km"]), "network_km"] = np.nan
    snap_m = dict(zip(stations["station_id"], np.round(snap, 1)))
    res["snap_m"] = res["from"].map(snap_m)  # odleglosc stacji od najblizszego wezla grafu
    log(f"  siec: {len(res)} par stacji, brak polaczenia: {res['network_km'].isna().sum()}")
    return res


def network_distances(stations, log):
    """Macierz odleglosci sieciowych (z pliku albo przeliczona, gdy sa nowe stacje)."""
    cached = pd.read_parquet(OUT) if OUT.exists() else None
    ids = set(stations["station_id"])
    if cached is not None and ids <= set(cached["from"]):
        return cached
    if not (OSM_DIR / "graph_bike.graphml").exists():
        log("  siec: brak grafu rowerowego (fetch_static --only osm) - pomijam network_km")
        return cached
    res = _compute(stations, log)
    res.to_parquet(OUT, index=False)
    return res


def add_network_distance(trips, reb, stations, log):
    dist = network_distances(stations, log)
    if dist is None:
        trips["network_km"] = np.nan
        reb["network_km"] = np.nan
        return trips, reb
    lookup = dist.set_index(["from", "to"])["network_km"]
    for df in (trips, reb):
        key = pd.MultiIndex.from_arrays([df["from"], df["to"]])
        df["network_km"] = lookup.reindex(key).to_numpy()
    return trips, reb
