from pathlib import Path
import json
import pickle

import numpy as np
import pandas as pd

from .demand import EmpiricalDemand, ExampleDemand, load_demand, random_stream
from .engine import SimulationParams
from .network import StationNetwork, build_network


ROOT = Path(__file__).resolve().parents[2]


def example_inputs(n_stations=348, seed=2026):
    rng = random_stream(seed, "example-inputs")
    capacity = rng.integers(8, 23, n_stations)
    stations = pd.DataFrame({"station_id": [str(i) for i in range(n_stations)],
                             "name": [f"Example {i}" for i in range(n_stations)],
                             "lat": rng.uniform(52.18, 52.29, n_stations),
                             "lon": rng.uniform(20.94, 21.12, n_stations), "capacity": capacity,
                             "initial_bikes": np.maximum(0, (capacity * rng.uniform(0.0, 0.9, n_stations)).astype(int))})
    network = build_network(stations)
    schedule = []
    for minute in range(60, 1440, 30):
        a, b = rng.choice(n_stations, 2, replace=False) if n_stations > 1 else (0, 0)
        schedule.append({"minute": float(minute), "from_station": str(a), "to_station": str(b), "n_bikes": 4})
    demand = ExampleDemand(rng.uniform(0.4, 2.5, n_stations))
    return SimulationParams(stations=stations, network=network, demand_model=demand,
                            rebalancing_observed=pd.DataFrame(schedule))


def prepare_inputs(output_dir, day="2026-11-03", processed=None, example=False, use_osm=True):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    processed = Path(processed) if processed else ROOT / "processed"
    if example:
        params = example_inputs()
        metadata = {"mode": "synthetic_example", "warning": "All parameters and station data are synthetic."}
    else:
        needed = ["stations", "observed_timeseries", "station_hourly", "trips", "context_hourly", "rebalancing_observed"]
        for name in needed:
            if not (processed / f"{name}.parquet").exists():
                raise FileNotFoundError(f"Missing {name}.parquet; first run python -X utf8 -m src.data.build --no-features")
        stations = pd.read_parquet(processed / "stations.parquet").sort_values("station_id").reset_index(drop=True)
        stations["station_id"] = stations.station_id.astype(str)
        start = pd.Timestamp(day, tz="Europe/Warsaw").tz_convert("UTC")
        stop = start + pd.Timedelta(days=1)
        observed = pd.read_parquet(processed / "observed_timeseries.parquet")
        observed = observed[~observed.is_spike]
        prior = observed[observed.time <= start].sort_values("time").drop_duplicates("station_id", keep="last")
        age = (start - prior.time).dt.total_seconds() / 60
        prior = prior.loc[age <= 15]
        initial = prior.set_index("station_id").bikes
        fallback = stations.mean_bikes.fillna(stations.capacity * 0.5).round()
        stations["initial_bikes"] = stations.station_id.map(initial).fillna(fallback).clip(lower=0).astype(int)
        inactive = stations.station_id[stations["n_obs"].isna()].tolist()
        hourly = pd.read_parquet(processed / "station_hourly.parquet")
        hourly = hourly[hourly.hour < start].copy()
        if hourly.empty:
            raise ValueError("No historical demand observations before the selected day")
        hourly["local_hour"] = hourly.hour.dt.tz_convert("Europe/Warsaw").dt.hour
        hourly["exposure"] = hourly.minutes_available / 60
        grouped = hourly.groupby(["station_id", "local_hour"])[["departures", "exposure"]].sum()
        grouped["rate"] = grouped.departures / grouped.exposure.clip(lower=1.0)
        rates = grouped.rate.unstack("local_hour").reindex(index=stations.station_id, columns=range(24)).fillna(0).to_numpy(float)
        rates[stations.station_id.isin(inactive), :] = 0
        context = pd.read_parquet(processed / "context_hourly.parquet")
        context = context[(context.time >= start) & (context.time < stop)]
        reb = pd.read_parquet(processed / "rebalancing_observed.parquet")
        reb = reb[(reb.t_departure >= start) & (reb.t_departure < stop)].copy()
        trips = pd.read_parquet(processed / "trips.parquet")
        trips = trips[(trips.type == "user") & (trips.t_departure < start) & ~trips.is_flicker & ~trips.too_fast & ~trips.is_long]
        od_counts = pd.crosstab(trips.from_station, trips.to_station).reindex(index=stations.station_id, columns=stations.station_id, fill_value=0).to_numpy(float)
        drive_path = ROOT / "data/static/osm/graph_drive.graphml"
        network = build_network(stations, ROOT / "data/static/station_network_distance.parquet", drive_path if use_osm else None)
        prior_od = np.exp(-network.bike_km / 3)
        prior_od[:, stations.station_id.isin(inactive).to_numpy()] = 0
        prior_od /= prior_od.sum(axis=1, keepdims=True)
        od = od_counts + prior_od
        od /= od.sum(axis=1, keepdims=True)
        params = SimulationParams(stations=stations, network=network, demand_model=EmpiricalDemand(rates),
                                  od_matrix=od, context_hourly=context, rebalancing_observed=reb, start_time=start)
        metadata = {"mode": "preliminary_empirical", "day": day,
                    "warning": "Demand and OD are preliminary estimates from earlier observations; not calibrated or validated models from Person 2.",
                    "n_stations": len(stations), "inactive_historical_stations": inactive,
                    "initial_inventory_imputed_stations": int(stations.station_id.map(initial).isna().sum()),
                    "initialization": "Last non-spike observation at/before start, max age 15 minutes; otherwise historical mean.",
                    "demand": "Historical departures / available exposure, station x local hour, observations strictly before scenario day.",
                    "od": "Historical user OD with one distance-weighted pseudo-observation per origin; inactive destinations excluded.",
                    "ride_time": "Example lognormal multiplier, sigma=0.4, mean=1; base network distance / 14 km/h.",
                    "agent_rules": "Example: 65% try a station within 600m; walk 4.5 km/h; soft capacity, no full-station redirect by default.",
                    "truck_rules": "20 bikes; loading and unloading 15 seconds/bike; 25 km/h free-flow; congestion is 1-current/free-flow.",
                    "operator": "Actual observed transfers on selected day, queued by departure, physically executed by finite fleet; late jobs remain late.",
                    "operator_jobs": len(reb), "network": network.source,
                    "interpretation": "Operator replay uses that day's observations ex post; this is not a deployable online policy or final evidence for H3."}
    params.stations.to_parquet(output_dir / "stations.parquet", index=False)
    params.network.save(output_dir / "network", params.stations)
    with (output_dir / "demand_model.pkl").open("wb") as handle:
        pickle.dump(params.demand_model, handle)
    if params.od_matrix is not None:
        np.save(output_dir / "od_matrix.npy", params.od_matrix)
    if params.context_hourly is not None:
        params.context_hourly.reset_index().to_parquet(output_dir / "context_hourly.parquet", index=False)
    params.rebalancing_observed.to_parquet(output_dir / "rebalancing_observed.parquet", index=False)
    metadata["start_time"] = params.start_time.isoformat()
    params.provenance = metadata
    (output_dir / "metadata.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
    return params


def load_inputs(directory, **overrides):
    directory = Path(directory)
    metadata = json.loads((directory / "metadata.json").read_text(encoding="utf-8"))
    def table(name):
        path = directory / f"{name}.parquet"
        return pd.read_parquet(path) if path.exists() else None
    params = dict(stations=table("stations"), network=StationNetwork.load(directory / "network"),
                  demand_model=load_demand(directory / "demand_model.pkl"),
                  od_matrix=np.load(directory / "od_matrix.npy", allow_pickle=False) if (directory / "od_matrix.npy").exists() else None,
                  context_hourly=table("context_hourly"), rebalancing_observed=table("rebalancing_observed"),
                  start_time=metadata["start_time"], provenance=metadata)
    params.update(overrides)
    return SimulationParams(**params)
