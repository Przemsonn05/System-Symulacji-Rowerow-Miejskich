import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .experiments import STRATEGIES, request_digest, summarize


def verify_experiment(directory):
    directory = Path(directory)
    runs = pd.read_parquet(directory / "replications.parquet")
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    expected = {(strategy, trucks, seed) for strategy in STRATEGIES
                for trucks in manifest["truck_counts"] for seed in manifest["seeds"]}
    actual = set(zip(runs.scenario, runs.n_trucks, runs.seed))
    if actual != expected or len(runs) != len(expected):
        raise AssertionError("Missing or duplicate experiment runs")
    if (runs.groupby("seed").requests_sha256.nunique() != 1).any():
        raise AssertionError("CRN digests differ")
    verified_rows = 0
    for row in runs.itertuples():
        path = directory / "runs" / f"{row.scenario}_{row.n_trucks}" / f"seed_{row.seed}"
        for name in ["events", "station_timeseries", "trips", "requests", "fleet_timeseries", "station_kpis", "stations", "rebalancing_observed"]:
            if not (path / f"{name}.parquet").exists():
                raise AssertionError(f"Missing output: {path / name}")
        fleet = pd.read_parquet(path / "fleet_timeseries.parquet")
        if not ((fleet.at_stations + fleet.in_use + fleet.on_trucks) == row.initial_bikes).all():
            raise AssertionError(f"Fleet conservation failed in {path}")
        if not (fleet.total == row.initial_bikes).all() or (fleet.on_trucks > row.n_trucks * manifest["parameters"]["truck_capacity"]).any():
            raise AssertionError(f"Invalid fleet state in {path}")
        station = pd.read_parquet(path / "station_timeseries.parquet", columns=["time", "station_id", "bikes"])
        if (station.bikes < 0).any() or station.station_id.nunique() != manifest["n_stations"]:
            raise AssertionError(f"Invalid station state in {path}")
        trips = pd.read_parquet(path / "trips.parquet", columns=["t_departure", "t_arrival", "duration_min", "type"])
        if len(trips) != row.returns + row.relocated_bikes or (trips.duration_min < 0).any() or (trips.t_arrival < trips.t_departure).any():
            raise AssertionError(f"Invalid trips in {path}")
        requests = pd.read_parquet(path / "requests.parquet")
        if request_digest(requests) != row.requests_sha256:
            raise AssertionError(f"Request file digest changed in {path}")
        if row.requests != row.rentals + row.lost_demand + row.pending_users:
            raise AssertionError(f"User accounting failed in {path}")
        verified_rows += len(station)
    expected_summary = summarize(runs).sort_values(["scenario", "n_trucks", "metric"]).reset_index(drop=True)
    actual_summary = pd.read_csv(directory / "summary.csv").sort_values(["scenario", "n_trucks", "metric"]).reset_index(drop=True)
    if not np.allclose(expected_summary[["mean", "ci95_low", "ci95_high"]], actual_summary[["mean", "ci95_low", "ci95_high"]]):
        raise AssertionError("Summary does not match replications")
    result = {"runs_verified": len(runs), "station_rows_verified": verified_rows,
              "seeds": len(manifest["seeds"]), "common_random_numbers": True,
              "conservation": True, "nonnegative_stations": True, "summary_matches_replications": True}
    (directory / "verification.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", default="results/h3")
    args = parser.parse_args()
    print(json.dumps(verify_experiment(args.results), indent=2))


if __name__ == "__main__":
    main()
