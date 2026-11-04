from dataclasses import replace
import json
import math

import numpy as np
import pandas as pd
from pandas.testing import assert_frame_equal
import pytest
from scipy import stats

from src.simulation.demand import HourlyDemand, next_hour_minute, random_stream, thinning
from src.simulation.engine import Simulation, SimulationParams, run_simulation
from src.simulation.experiments import confidence_interval, paired_comparisons, pareto_front, run_experiments, summarize
from src.simulation.inputs import example_inputs, load_inputs, prepare_inputs
from src.simulation.network import StationNetwork, build_network, road_matrices


@pytest.fixture
def params():
    stations = pd.DataFrame({"station_id": ["A", "B", "C"], "capacity": [10, 10, 10],
                             "initial_bikes": [10, 0, 5], "lat": [52.23, 52.231, 52.232],
                             "lon": [21.0, 21.001, 21.002]})
    network = build_network(stations)
    schedule = pd.DataFrame([{"minute": 1.0, "from_station": "A", "to_station": "B", "n_bikes": 4}])
    return SimulationParams(stations=stations, network=network, demand_model=HourlyDemand(np.array([10., 20., 10.])),
                            rebalancing_observed=schedule, duration_min=120, n_trucks=2)


def requests(rows):
    return pd.DataFrame([{"request_id": str(i), "minute": minute, "origin": origin, "destination": destination,
                          "ride_factor": factor, "try_alternative": retry, "redirect_full": redirect}
                         for i, (minute, origin, destination, factor, retry, redirect) in enumerate(rows)])


@pytest.mark.parametrize("strategy", ["none", "operator", "threshold"])
def test_conservation_and_nonnegative_after_every_event(params, strategy):
    sim = Simulation(params, strategy, 17)
    result = sim.run()
    counts = params.stations.set_index("station_id").initial_bikes.to_dict()
    riding, cargo = set(), set()
    total = sum(counts.values())
    for row in result.events.itertuples():
        if row.event == "rental":
            counts[row.station_id] -= 1
            assert row.bike not in riding | cargo
            riding.add(row.bike)
        elif row.event == "return":
            counts[row.station_id] += 1
            riding.remove(row.bike)
        elif row.event == "truck_load":
            counts[row.station_id] -= 1
            assert row.bike not in riding | cargo
            cargo.add(row.bike)
        elif row.event == "truck_unload":
            counts[row.station_id] += 1
            cargo.remove(row.bike)
        assert min(counts.values()) >= 0
        assert sum(counts.values()) + len(riding) + len(cargo) == total
    assert result.kpis["conservation_checks"] > 1
    assert (result.station_timeseries.bikes >= 0).all()
    fleet = result.fleet_timeseries
    assert ((fleet.at_stations + fleet.in_use + fleet.on_trucks) == total).all()


@pytest.mark.parametrize("strategy", ["none", "operator", "threshold"])
def test_seed_reproducibility(params, strategy):
    a, b = run_simulation(params, strategy, 71), run_simulation(params, strategy, 71)
    for field in ("events", "station_timeseries", "trips", "fleet_timeseries", "requests"):
        assert_frame_equal(getattr(a, field), getattr(b, field))
    assert a.kpis == b.kpis


def test_true_common_random_numbers(params):
    outcomes = [run_simulation(replace(params, n_trucks=n), strategy, 83)
                for strategy in ("none", "operator", "threshold") for n in (1, 2, 4)]
    for result in outcomes[1:]:
        assert_frame_equal(outcomes[0].requests, result.requests)
    assert not outcomes[0].requests.equals(run_simulation(params, "none", 84).requests)


def test_none_never_moves_bikes_with_trucks(params):
    result = run_simulation(params, "none", 2)
    assert result.kpis["truck_km"] == 0
    assert result.kpis["relocated_bikes"] == 0


def test_soft_capacity(params):
    req = requests([(0, 2, 0, 1, False, False)])
    result = Simulation(params, "none", 1, req).run()
    assert result.station_timeseries.query("station_id == 'A'").bikes.max() == 11
    assert result.trips.to_station.iloc[0] == "A"


def test_exact_empty_integral_and_horizon_censoring(params):
    p = replace(params, duration_min=10, snapshot_interval_min=7)
    req = requests([(0, 0, 1, 100000, False, False)])
    result = Simulation(p, "none", 1, req).run()
    assert result.station_kpis.set_index("station_id").loc["B", "empty_minutes"] == 10
    assert result.kpis["bikes_in_transit_at_end"] == 1
    assert len(result.trips) == 0
    assert result.events.minute.max() < 10
    assert result.fleet_timeseries.time.iloc[-1] == p.start_time + pd.Timedelta(minutes=10)


def test_walk_to_alternative_and_lost_customer(params):
    req = requests([(0, 1, 2, 1, True, False), (0.01, 1, 2, 1, False, False)])
    result = Simulation(params, "none", 1, req).run()
    assert result.kpis["lost_demand"] == 1
    assert result.kpis["rentals"] == 1
    assert result.kpis["extra_user_minutes"] > 0
    assert "walk_to_alternative" in result.events.event.values


def test_pending_walk_not_counted_as_lost(params):
    p = replace(params, duration_min=0.01)
    result = Simulation(p, "none", 1, requests([(0, 1, 2, 1, True, False)])).run()
    assert result.kpis["pending_users"] == 1
    assert result.kpis["lost_demand"] == 0
    assert result.kpis["extra_user_minutes"] == pytest.approx(0.01)


def test_full_station_redirect(params):
    result = Simulation(params, "none", 1, requests([(0, 2, 0, 1, False, True)])).run()
    assert "redirect_return" in result.events.event.values
    assert result.trips.to_station.iloc[0] != "A"


def test_operator_replay_timing_capacity_and_no_teleportation(params):
    p = replace(params, demand_model=HourlyDemand(np.zeros(3)), n_trucks=1, truck_capacity=2)
    result = run_simulation(p, "operator", 3)
    loads = result.events[result.events.event == "truck_load"]
    assert len(loads) == 4
    assert loads.minute.min() >= 1 + p.handling_min_per_bike
    assert result.kpis["relocated_bikes"] == 4
    assert result.station_timeseries.query("station_id == 'B'").bikes.iloc[-1] == 4
    assert result.events[result.events.event == "truck_arrival"]["load"].max() <= 2


def test_truck_cargo_preserved_at_end(params):
    matrix = params.network.truck_minutes.copy()
    matrix[0, 1] = 1000
    net = replace(params.network, truck_minutes=matrix)
    p = replace(params, network=net, duration_min=10, n_trucks=1, demand_model=HourlyDemand(np.zeros(3)))
    result = run_simulation(p, "operator", 1)
    assert result.kpis["bikes_on_trucks_at_end"] == 4
    assert result.kpis["relocated_bikes"] == 0
    assert result.kpis["truck_km"] > 0
    assert result.kpis["truck_km"] < net.truck_km[0, 1]


def test_threshold_dispatch_and_reservations(params):
    p = replace(params, demand_model=HourlyDemand(np.zeros(3)), n_trucks=4)
    result = run_simulation(p, "threshold", 9)
    assert result.kpis["relocated_bikes"] == 5
    assert result.kpis["jobs_completed"] == 1
    end = result.station_timeseries[result.station_timeseries.time == result.station_timeseries.time.max()]
    assert end.bikes.tolist() == [5, 5, 5]


def test_no_intervention_within_thresholds(params):
    stations = params.stations.copy()
    stations["initial_bikes"] = 5
    p = replace(params, stations=stations, demand_model=HourlyDemand(np.zeros(3)))
    result = run_simulation(p, "threshold", 9)
    assert result.kpis["jobs_started"] == 0


def test_congestion_slows_trucks(params):
    context = pd.DataFrame({"time": [params.start_time], "congestion": [0.5]})
    p = replace(params, demand_model=HourlyDemand(np.zeros(3)), context_hourly=context, n_trucks=1)
    free = run_simulation(replace(p, congestion_multiplier=0), "operator", 2)
    jam = run_simulation(p, "operator", 2)
    free_time = free.events[free.events.event == "truck_unload"].minute.min()
    jam_time = jam.events[jam.events.event == "truck_unload"].minute.min()
    assert jam_time > free_time
    assert jam.kpis["truck_km"] == pytest.approx(free.kpis["truck_km"])


def test_constant_rate_arrival_distribution():
    times = np.array(list(thinning(lambda t: 30, 30, 100000, random_stream(111, "poisson"))))
    gaps = np.diff(np.r_[0, times])
    assert abs(len(times) - 50000) < 5 * np.sqrt(50000)
    assert stats.kstest(gaps, "expon", args=(0, 2)).pvalue > 1e-4
    counts = np.histogram(times, bins=np.arange(0, 100001, 20))[0]
    observed = np.bincount(np.minimum(counts, 18), minlength=19)
    expected = stats.poisson.pmf(np.arange(19), 10)
    expected[-1] = stats.poisson.sf(17, 10)
    observed = np.r_[observed[:4].sum(), observed[4:]]
    expected = np.r_[expected[:4].sum(), expected[4:]] * len(counts)
    assert (expected >= 5).all()
    assert stats.chisquare(observed, expected).pvalue > 1e-4


def test_birth_death_single_station_analytic(params):
    stations = params.stations.iloc[:1].copy()
    stations["initial_bikes"] = 2
    network = build_network(stations)
    horizon = 100000
    p = replace(params, stations=stations, network=network, n_trucks=0, duration_min=horizon,
                snapshot_interval_min=1000, demand_model=HourlyDemand(np.array([30.])), audit_every_event=False)
    rng = random_stream(13, "birth-death")
    times = np.array(list(thinning(lambda t: 30, 30, horizon, rng)))
    req = pd.DataFrame({"request_id": np.arange(len(times)).astype(str), "minute": times, "origin": 0, "destination": 0,
                        "ride_factor": rng.exponential(6, len(times)), "try_alternative": False, "redirect_full": False})
    result = Simulation(p, "none", 13, req).run()
    offered = 0.5 * 3
    expected_empty = (offered ** 2 / math.factorial(2)) / sum(offered ** n / math.factorial(n) for n in range(3))
    assert result.kpis["empty_station_share"] == pytest.approx(expected_empty, abs=0.015)
    assert result.kpis["lost_share"] == pytest.approx(expected_empty, abs=0.015)


def test_thinning_nonhomogeneous_and_invalid_bound():
    rng = random_stream(2, "nhpp")
    times = np.array(list(thinning(lambda t: 12 if t < 50000 else 36, 36, 100000, rng)))
    assert (times < 50000).sum() == pytest.approx(10000, abs=500)
    assert (times >= 50000).sum() == pytest.approx(30000, abs=900)
    with pytest.raises(ValueError):
        list(thinning(lambda t: 61, 60, 100, rng))
    assert list(thinning(lambda t: 0, 0, 100, rng)) == []


@pytest.mark.parametrize("overrides", [{"duration_min": 0}, {"n_trucks": -1}, {"truck_capacity": 0},
                                       {"lower_threshold": 0.7}, {"empty_retry_probability": 2}, {"ride_sigma": -1}])
def test_invalid_parameters(params, overrides):
    with pytest.raises(ValueError):
        replace(params, **overrides)


def test_unknown_scenario_or_schedule(params):
    with pytest.raises(ValueError):
        run_simulation(params, "unknown", 1)
    with pytest.raises(ValueError):
        run_simulation(replace(params, rebalancing_observed=None), "operator", 1)
    schedule = pd.DataFrame([{"minute": 0, "from_station": "missing", "to_station": "B", "n_bikes": 2}])
    with pytest.raises(ValueError):
        run_simulation(replace(params, rebalancing_observed=schedule), "operator", 1)


def test_invalid_demand_od_and_network(params):
    with pytest.raises(ValueError):
        run_simulation(replace(params, demand_model=HourlyDemand(np.array([-1., 0., 1.]))), "none", 1)
    with pytest.raises(ValueError):
        run_simulation(replace(params, od_matrix=np.zeros((3, 3))), "none", 1)
    with pytest.raises(ValueError):
        replace(params, network=replace(params.network, ids=["B", "A", "C"]))


def test_outputs_parquet_and_inventory_identity(params, tmp_path):
    result = run_simulation(replace(params, output_dir=tmp_path), "threshold", 8)
    for name, path in result.paths.items():
        assert path.exists()
        before = getattr(result, name).copy().astype(object)
        before = before.where(before.notna(), np.nan)
        after = pd.read_parquet(path).astype(object)
        after = after.where(after.notna(), np.nan)
        assert_frame_equal(after, before, check_dtype=False)
    assert {"bike", "from_station", "to_station", "t_departure", "t_arrival", "type"} <= set(result.trips)
    assert json.loads((tmp_path / "kpis.json").read_text())["initial_bikes"] == 15
    assert (tmp_path / "observed_timeseries.parquet").exists()
    assert (tmp_path / "rebalancing_observed.parquet").exists()


def test_network_cache_roundtrip(params, tmp_path):
    params.network.save(tmp_path, params.stations)
    restored = StationNetwork.load(tmp_path)
    assert restored.ids == params.network.ids
    np.testing.assert_array_equal(restored.bike_km, params.network.bike_km)
    import networkx as nx
    graph = nx.read_graphml(tmp_path / "stations.graphml")
    assert len(graph) == 3
    assert graph.nodes["A"]["bikes"] == 10


def test_ci_and_paired_statistics():
    mean, low, high = confidence_interval([1, 2, 3])
    assert mean == 2
    assert high - mean == pytest.approx(stats.t.ppf(0.975, 2) / np.sqrt(3))
    frame = pd.DataFrame([{"scenario": scenario, "n_trucks": 1, "seed": seed, "lost_demand": 10 - i}
                          for i, scenario in enumerate(("none", "operator", "threshold")) for seed in range(30)])
    paired = paired_comparisons(frame)
    assert len(paired) == 3
    assert (paired.p_holm >= paired.p_wilcoxon).all()
    assert (paired.mean_lost_a_minus_b > 0).all()


def test_parallel_experiment_smoke(params, tmp_path):
    p = replace(params, duration_min=10)
    serial = run_experiments(p, tmp_path / "serial", replications=2, n_jobs=1, truck_counts=(1,))
    parallel = run_experiments(p, tmp_path / "parallel", replications=2, n_jobs=2, truck_counts=(1,))
    assert_frame_equal(serial[0], parallel[0])
    assert_frame_equal(serial[1], parallel[1])
    assert (tmp_path / "parallel" / "h3_pareto.png").exists()
    assert (tmp_path / "parallel" / "REPORT.md").exists()


def test_example_348_station_inputs():
    params = example_inputs()
    assert len(params.stations) == 348
    assert params.network.truck_minutes.shape == (348, 348)


def test_zero_demand(params):
    result = run_simulation(replace(params, demand_model=HourlyDemand(np.zeros(3))), "none", 1)
    assert result.kpis["requests"] == 0
    assert result.kpis["lost_share"] == 0
    assert result.kpis["empty_station_share"] == pytest.approx(1 / 3)


def test_hour_boundaries_do_not_create_zero_time_loops(params):
    assert next_hour_minute(params.start_time, 59.99999999999999) == 120
    assert next_hour_minute(params.start_time, 60) == 120
    minute = 59.999999991
    assert next_hour_minute(params.start_time, minute) > minute
    matrix = params.network.truck_minutes.copy()
    matrix[0, 1] = 120.123456789123
    p = replace(params, duration_min=180, network=replace(params.network, truck_minutes=matrix),
                demand_model=HourlyDemand(np.zeros(3)), n_trucks=1)
    result = run_simulation(p, "operator", 1)
    assert result.kpis["relocated_bikes"] == 4


def test_osm_directed_road_distances(params, tmp_path):
    import networkx as nx
    import osmnx as ox
    stations = params.stations.iloc[:2].copy()
    graph = nx.MultiDiGraph(crs="EPSG:4326")
    for i, row in enumerate(stations.itertuples()):
        graph.add_node(i, x=float(row.lon), y=float(row.lat))
    graph.add_edge(0, 1, length=1000.0, osmid=10)
    graph.add_edge(1, 0, length=3000.0, osmid=11)
    path = tmp_path / "drive.graphml"
    ox.save_graphml(graph, path)
    km, minutes = road_matrices(stations, path, speed_kmh=30)
    assert km[0, 1] == pytest.approx(1)
    assert km[1, 0] == pytest.approx(3)
    assert minutes[1, 0] == pytest.approx(6)


def test_hour_context_update_during_travel(params):
    matrix = params.network.truck_minutes.copy()
    matrix[0, 1] = 90
    context = pd.DataFrame({"time": [params.start_time, params.start_time + pd.Timedelta(hours=1)], "congestion": [0.0, 0.5]})
    p = replace(params, n_trucks=1, duration_min=180, context_hourly=context,
                demand_model=HourlyDemand(np.zeros(3)), network=replace(params.network, truck_minutes=matrix))
    result = run_simulation(p, "operator", 8)
    depart = result.events[(result.events.event == "truck_departure") & (result.events.to_station == "B")].minute.iloc[0]
    arrival = result.events[(result.events.event == "truck_arrival") & (result.events.station_id == "B")].minute.iloc[0]
    expected = 60 + 2 * (90 - (60 - depart))
    if expected > 120:
        expected = 120 + (90 - (60 - depart) - 30)
    assert arrival == pytest.approx(expected)


def test_input_serialization(tmp_path):
    before = prepare_inputs(tmp_path, example=True)
    after = load_inputs(tmp_path)
    assert_frame_equal(before.stations, after.stations)
    assert after.provenance["mode"] == "synthetic_example"
    a = run_simulation(replace(before, duration_min=2), "none", 1)
    b = run_simulation(replace(after, duration_min=2), "none", 1)
    assert_frame_equal(a.requests, b.requests)
