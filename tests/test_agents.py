from dataclasses import replace
import math
import numpy as np
import pandas as pd
from pandas.testing import assert_frame_equal
import pytest

from src.agents.base import Agent, AgentMessage, StationView, AppView, TruckView, DispatcherView
from src.agents.dispatcher import DispatcherAgent, RebalanceTask
from src.agents.field import PressureField
from src.agents.station import StationAgent, WaitingUser
from src.agents.truck import TruckAgent
from src.simulation.agent_experiments import (
    run_h3_suite,
    run_h5b_suite,
    run_phase_transition_suite,
    run_herd_effect_suite,
    run_pressure_radius_suite,
    run_what_if_suite,
    run_tornado_analysis,
    run_morris_analysis,
    generate_experiments_summary_report
)
from src.simulation.demand import HourlyDemand
from src.simulation.engine import Simulation, SimulationParams, run_simulation
from src.simulation.network import build_network

@pytest.fixture
def agent_params():
    stations = pd.DataFrame({
        "station_id": ["S1", "S2", "S3", "S4"],
        "capacity": [20, 20, 20, 20],
        "initial_bikes": [18, 2, 10, 10],
        "lat": [52.20, 52.21, 52.22, 52.23],
        "lon": [21.00, 21.01, 21.02, 21.03]
    })
    network = build_network(stations)
    schedule = pd.DataFrame([{"minute": 10.0, "from_station": "S1", "to_station": "S2", "n_bikes": 4}])
    return SimulationParams(
        stations=stations,
        network=network,
        demand_model=HourlyDemand(np.array([15., 15., 15., 15.])),
        rebalancing_observed=schedule,
        duration_min=180,
        n_trucks=2,
        dispatch_interval_min=5.0
    )

def test_conservation_multi_day(agent_params):
    p = replace(agent_params, days=2, duration_min=2880)
    sim = Simulation(p, "threshold", 101)
    res = sim.run()
    total = sum(agent_params.stations.initial_bikes)
    fleet = res.fleet_timeseries
    assert ((fleet.at_stations + fleet.in_use + fleet.on_trucks) == total).all()
    assert res.kpis["final_bikes"] == total
    assert res.kpis["initial_bikes"] == total

def test_contract_net_auction():
    disp = DispatcherAgent(
        strategy="threshold",
        n_stations=3,
        capacity=np.array([20, 20, 20])
    )
    t0 = TruckAgent(truck_id=0, capacity=20, initial_position=0)
    t1 = TruckAgent(truck_id=1, capacity=20, initial_position=2)
    matrix = np.array([
        [0.0, 10.0, 20.0],
        [10.0, 0.0, 10.0],
        [20.0, 10.0, 0.0]
    ])
    task = RebalanceTask(task_id=1, origin=0, destination=1, n_bikes=5, minute=0.0)
    res = disp.contract_net_auction(task, [t0, t1], matrix, handling_min=0.25, minute=0.0)
    assert res is not None
    winner, cost, bids = res
    assert winner.truck_id == 0
    assert len(bids) == 2
    assert bids[0]["truck_id"] == 0

def test_contract_net_tie_breaking():
    disp = DispatcherAgent(
        strategy="threshold",
        n_stations=2,
        capacity=np.array([10, 10])
    )
    t0 = TruckAgent(truck_id=0, capacity=10, initial_position=0)
    t1 = TruckAgent(truck_id=1, capacity=10, initial_position=0)
    matrix = np.zeros((2, 2))
    task = RebalanceTask(task_id=1, origin=0, destination=1, n_bikes=2, minute=0.0)
    winner, cost, bids = disp.contract_net_auction(task, [t1, t0], matrix, handling_min=0.1, minute=0.0)
    assert winner.truck_id == 0

def test_truck_shifts():
    t = TruckAgent(truck_id=0, shift_hours=(8, 16))
    assert not t.is_on_shift(7 * 60)
    assert t.is_on_shift(8 * 60)
    assert t.is_on_shift(12 * 60)
    assert not t.is_on_shift(16 * 60)

def test_station_waiting_queue_fifo():
    st = StationAgent(station_id="TEST", index=0, capacity=10, initial_bikes=0)
    u1 = st.add_waiting_user("req-1", current_minute=1.0, patience_min=10.0)
    u2 = st.add_waiting_user("req-2", current_minute=2.0, patience_min=10.0)
    assert len(st.waiting_queue) == 2
    popped = st.pop_waiting_user()
    assert popped.request_id == "req-1"
    assert len(st.waiting_queue) == 1

def test_station_waiting_queue_patience_removal():
    st = StationAgent(station_id="TEST", index=0, capacity=10, initial_bikes=0)
    st.add_waiting_user("req-1", current_minute=1.0, patience_min=5.0)
    st.add_waiting_user("req-2", current_minute=2.0, patience_min=5.0)
    removed = st.remove_waiting_user("req-1")
    assert removed is True
    assert len(st.waiting_queue) == 1
    assert st.waiting_queue[0].request_id == "req-2"

def test_pressure_field_diffusion():
    dist = np.array([
        [0.0, 0.5, 5.0],
        [0.5, 0.0, 5.0],
        [5.0, 5.0, 0.0]
    ])
    field_zero = PressureField(dist, radius_km=1.5, length_scale=1.0, alpha=0.0)
    signals = np.array([1.0, -0.5, 0.0])
    p_zero = field_zero.compute_pressure(signals)
    np.testing.assert_allclose(p_zero, signals)

    field_diff = PressureField(dist, radius_km=1.5, length_scale=1.0, alpha=0.5, iterations=3)
    p_diff = field_diff.compute_pressure(signals)
    assert p_diff[0] < 1.0
    assert p_diff[1] > -0.5
    assert p_diff[2] == 0.0

def test_hysteresis_no_flicker():
    st = StationAgent(
        station_id="HYS",
        index=0,
        capacity=100,
        initial_bikes=15,
        lower_threshold=0.10,
        reset_lower=0.25,
        upper_threshold=0.90,
        reset_upper=0.75
    )
    sig, state, changed = st.update_signal(15)
    assert state == "normal"
    assert changed is False

    sig, state, changed = st.update_signal(8)
    assert state == "deficit"
    assert changed is True

    sig, state, changed = st.update_signal(15)
    assert state == "deficit"
    assert changed is False

    sig, state, changed = st.update_signal(24)
    assert state == "deficit"
    assert changed is False

    sig, state, changed = st.update_signal(26)
    assert state == "normal"
    assert changed is True

def test_predictive_no_peeking(agent_params):
    p = replace(agent_params, duration_min=60)
    sim1 = Simulation(p, "predictive", 42)
    res1 = sim1.run()
    reqs = sim1.requests.copy()
    reqs.loc[reqs.minute > 30, "destination"] = 3
    sim2 = Simulation(p, "predictive", 42, requests=reqs)
    res2 = sim2.run()
    events1 = res1.events[res1.events.minute <= 30]
    events2 = res2.events[res2.events.minute <= 30]
    ev_types1 = events1[events1.event.isin(["task_announced", "task_awarded"])].event.tolist()
    ev_types2 = events2[events2.event.isin(["task_announced", "task_awarded"])].event.tolist()
    assert ev_types1 == ev_types2

def test_extreme_conditions(agent_params):
    zero_bikes_stations = agent_params.stations.copy()
    zero_bikes_stations["initial_bikes"] = 0
    p_zero = replace(agent_params, stations=zero_bikes_stations, duration_min=30)
    res_zero = run_simulation(p_zero, "none", 1)
    assert res_zero.kpis["lost_demand"] == res_zero.kpis["requests"]

    zero_demand_p = replace(agent_params, demand_model=HourlyDemand(np.zeros(4)), duration_min=30)
    res_no_req = run_simulation(zero_demand_p, "none", 1)
    assert res_no_req.kpis["requests"] == 0
    assert res_no_req.kpis["lost_demand"] == 0

@pytest.mark.parametrize("strat", ["none", "operator", "threshold", "night", "predictive", "pressure", "operator_rule"])
def test_all_strategies_run(agent_params, strat):
    p = replace(agent_params, duration_min=30)
    res = run_simulation(p, strat, 123)
    assert res.kpis["initial_bikes"] == res.kpis["final_bikes"]
    assert "pressure" in res.station_timeseries.columns

def test_user_outcomes_dataframe(agent_params):
    p = replace(agent_params, duration_min=30, app_share=0.5, user_patience_min=2.0)
    res = run_simulation(p, "threshold", 55)
    assert res.user_outcomes is not None
    assert "decision" in res.user_outcomes.columns
    assert "has_app" in res.user_outcomes.columns
    assert "wait_time" in res.user_outcomes.columns

def test_agent_experiments_suites_smoke(agent_params, tmp_path):
    p = replace(agent_params, duration_min=15)
    h3_res = run_h3_suite(p, tmp_path / "h3", replications=2, strategies=["none", "threshold"], truck_counts=(1,))
    assert len(h3_res) == 4
    h5b_res = run_h5b_suite(p, tmp_path / "h5b", congestion_multipliers=(0.0, 1.0), strategies=("threshold",), replications=2)
    assert len(h5b_res) == 4
    rep = generate_experiments_summary_report(tmp_path)
    assert rep.exists()

def test_tornado_and_morris_smoke(agent_params, tmp_path):
    p = replace(agent_params, duration_min=15)
    tornado_df = run_tornado_analysis(p, tmp_path / "tornado", param_names=["truck_capacity"], delta=0.2, replications=2)
    assert len(tornado_df) == 1
    morris_df = run_morris_analysis(p, tmp_path / "morris", num_trajectories=2, num_levels=4)
    assert len(morris_df) == 4
