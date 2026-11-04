from dataclasses import dataclass
from pathlib import Path
import json

import networkx as nx
import numpy as np
import pandas as pd


@dataclass
class StationNetwork:
    ids: list
    bike_km: np.ndarray
    truck_km: np.ndarray
    truck_minutes: np.ndarray
    source: dict

    def validate(self):
        n = len(self.ids)
        if len(set(self.ids)) != n:
            raise ValueError("Duplicate station IDs")
        for matrix in (self.bike_km, self.truck_km, self.truck_minutes):
            if matrix.shape != (n, n) or not np.isfinite(matrix).all() or (matrix < 0).any():
                raise ValueError("Invalid network matrix")
        return self

    def save(self, directory, stations):
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(directory / "matrices.npz", ids=np.array(self.ids, dtype=str),
                            bike_km=self.bike_km, truck_km=self.truck_km, truck_minutes=self.truck_minutes)
        (directory / "network_source.json").write_text(json.dumps(self.source, indent=2), encoding="utf-8")
        graph = nx.DiGraph()
        for row in stations.itertuples():
            graph.add_node(str(row.station_id), capacity=int(row.capacity), bikes=int(row.initial_bikes),
                           lat=float(row.lat), lon=float(row.lon))
        for i, origin in enumerate(self.ids):
            for j, destination in enumerate(self.ids):
                if i != j:
                    graph.add_edge(origin, destination, bike_km=float(self.bike_km[i, j]),
                                   truck_km=float(self.truck_km[i, j]), truck_minutes=float(self.truck_minutes[i, j]))
        nx.write_graphml(graph, directory / "stations.graphml")

    @classmethod
    def load(cls, directory):
        directory = Path(directory)
        with np.load(directory / "matrices.npz", allow_pickle=False) as data:
            result = cls(data["ids"].tolist(), data["bike_km"], data["truck_km"], data["truck_minutes"],
                         json.loads((directory / "network_source.json").read_text(encoding="utf-8")))
        return result.validate()


def geometric_distances(stations):
    lat = np.radians(stations.lat.to_numpy(float))
    lon = np.radians(stations.lon.to_numpy(float))
    a = np.sin((lat[:, None] - lat) / 2) ** 2
    a += np.cos(lat[:, None]) * np.cos(lat) * np.sin((lon[:, None] - lon) / 2) ** 2
    return 12742 * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def road_matrices(stations, graph_path, speed_kmh=25.0):
    import osmnx as ox
    from scipy.sparse import csr_matrix
    from scipy.sparse.csgraph import dijkstra

    graph = ox.load_graphml(graph_path)
    graph = ox.truncate.largest_component(graph, strongly=True)
    nearest, snap = ox.distance.nearest_nodes(graph, stations.lon.to_numpy(), stations.lat.to_numpy(), return_dist=True)
    nodes = list(graph.nodes)
    index = {node: i for i, node in enumerate(nodes)}
    edges = {}
    for u, v, data in graph.edges(data=True):
        key = (index[u], index[v])
        edges[key] = min(edges.get(key, np.inf), float(data["length"]))
    keys = list(edges)
    matrix = csr_matrix((list(edges.values()), ([k[0] for k in keys], [k[1] for k in keys])), shape=(len(nodes), len(nodes)))
    sources = [index[node] for node in nearest]
    km = np.concatenate([dijkstra(matrix, directed=True, indices=sources[k:k + 20])[:, sources]
                         for k in range(0, len(sources), 20)]) / 1000
    km += (snap[:, None] + snap[None, :]) / 1000
    np.fill_diagonal(km, 0)
    return km, km * 60 / speed_kmh


def build_network(stations, bike_path=None, drive_graph=None, speed_kmh=25.0):
    ids = stations.station_id.astype(str).tolist()
    straight = geometric_distances(stations)
    bike = straight * 1.3
    source = {"bike": "example_haversine_x1.3", "truck": "example_haversine_x1.4", "truck_speed_kmh": speed_kmh}
    if bike_path and Path(bike_path).exists():
        table = pd.read_parquet(bike_path).rename(columns={"from": "from_station", "to": "to_station"})
        table["from_station"] = table.from_station.astype(str)
        table["to_station"] = table.to_station.astype(str)
        candidate = table.pivot(index="from_station", columns="to_station", values="network_km").reindex(index=ids, columns=ids).to_numpy(float)
        missing = ~np.isfinite(candidate)
        bike = np.where(missing, bike, candidate)
        source["bike"] = "cached_osm_network"
        source["bike_fallback_pairs"] = int(missing.sum())
    truck = straight * 1.4
    truck_time = truck * 60 / speed_kmh
    if drive_graph and Path(drive_graph).exists():
        truck, truck_time = road_matrices(stations, drive_graph, speed_kmh)
        source["truck"] = "osm_drive_shortest_paths"
    np.fill_diagonal(bike, 0)
    return StationNetwork(ids, bike, truck, truck_time, source).validate()
