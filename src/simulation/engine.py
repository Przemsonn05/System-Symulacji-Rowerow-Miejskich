from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
import json
import math
import numpy as np
import pandas as pd
import simpy

from .demand import ExampleDemand, context_at, generate_requests, next_hour_minute, random_stream
from .network import StationNetwork
from ..agents.base import AgentMessage, AppView, DispatcherView, StationView, TruckView
from ..agents.dispatcher import DispatcherAgent, RebalanceTask
from ..agents.field import PressureField
from ..agents.station import StationAgent, WaitingUser
from ..agents.truck import TruckAgent

@dataclass(frozen=True)
class Bike:
    number: str

@dataclass
class SimulationParams:
    stations: pd.DataFrame
    network: StationNetwork
    demand_model: object = None
    od_matrix: object = None
    context_hourly: object = None
    rebalancing_observed: object = None
    duration_min: float = 1440.0
    start_time: object = "2026-11-03T23:00:00Z"
    n_trucks: int = 1
    truck_capacity: int = 20
    handling_min_per_bike: float = 0.25
    dispatch_interval_min: float = 5.0
    lower_threshold: float = 0.2
    upper_threshold: float = 0.8
    target_fill: float = 0.5
    bike_speed_kmh: float = 14.0
    walk_speed_kmh: float = 4.5
    max_walk_km: float = 0.6
    empty_retry_probability: float = 0.65
    full_redirect_probability: float = 0.0
    ride_sigma: float = 0.4
    snapshot_interval_min: float = 5.0
    congestion_multiplier: float = 1.0
    ride_time_model: object = None
    output_dir: object = None
    audit_every_event: bool = True
    provenance: dict = field(default_factory=dict)
    days: int = 1
    oracle: bool = False
    app_share: float = 0.0
    app_delay_min: float = 0.0
    user_patience_min: float = 0.0
    pressure_alpha: float = 0.5
    pressure_radius_km: float = 1.5
    pressure_length_scale: float = 0.8
    lower_signal_threshold: float = 0.1
    upper_signal_threshold: float = 0.9
    truck_shift_hours: Optional[Tuple[int, int]] = None

    def __post_init__(self):
        self.start_time = pd.Timestamp(self.start_time)
        if self.start_time.tzinfo is None:
            raise ValueError("start_time must include timezone")
        self.start_time = self.start_time.tz_convert("UTC")
        self.stations = self.stations.copy().reset_index(drop=True)
        needed = {"station_id", "capacity", "initial_bikes", "lat", "lon"}
        if not needed <= set(self.stations):
            raise ValueError(f"Missing station fields: {needed - set(self.stations)}")
        self.stations["station_id"] = self.stations.station_id.astype(str)
        for column in ("capacity", "initial_bikes"):
            values = self.stations[column].to_numpy(float)
            if not np.isfinite(values).all() or (values < 0).any() or (values != np.floor(values)).any():
                raise ValueError(f"Invalid {column}")
            self.stations[column] = values.astype(int)
        if self.stations.empty or (self.stations.capacity <= 0).any():
            raise ValueError("Stations must have positive capacity")
        if not np.isfinite(self.stations[["lat", "lon"]].to_numpy(float)).all():
            raise ValueError("Invalid coordinates")
        self.network.validate()
        if self.network.ids != self.stations.station_id.tolist():
            raise ValueError("Network order must match station order")
        if not isinstance(self.n_trucks, int) or self.n_trucks < 0 or not isinstance(self.truck_capacity, int) or self.truck_capacity < 1:
            raise ValueError("Invalid truck count or capacity")
        for key in ("duration_min", "dispatch_interval_min", "snapshot_interval_min", "bike_speed_kmh", "walk_speed_kmh"):
            if not math.isfinite(getattr(self, key)) or getattr(self, key) <= 0:
                raise ValueError(f"Invalid {key}")
        for key in ("ride_sigma", "handling_min_per_bike", "max_walk_km", "congestion_multiplier"):
            if not math.isfinite(getattr(self, key)) or getattr(self, key) < 0:
                raise ValueError(f"Invalid {key}")
        if not 0 <= self.lower_threshold < self.target_fill < self.upper_threshold <= 1:
            raise ValueError("Thresholds must satisfy 0 <= lower < target < upper <= 1")
        for key in ("empty_retry_probability", "full_redirect_probability"):
            if not 0 <= getattr(self, key) <= 1:
                raise ValueError(f"Invalid {key}")
        if self.context_hourly is not None:
            self.context_hourly = self.context_hourly.copy()
            if "time" in self.context_hourly:
                self.context_hourly["time"] = pd.to_datetime(self.context_hourly.time, utc=True)
                self.context_hourly = self.context_hourly.set_index("time")
            if self.context_hourly.index.has_duplicates:
                raise ValueError("Duplicate context hours")

@dataclass
class SimulationResult:
    events: pd.DataFrame
    station_timeseries: pd.DataFrame
    trips: pd.DataFrame
    fleet_timeseries: pd.DataFrame
    requests: pd.DataFrame
    station_kpis: pd.DataFrame
    kpis: dict
    paths: dict = field(default_factory=dict)
    user_outcomes: Optional[pd.DataFrame] = None

class Simulation:
    def __init__(self, params, scenario, seed, requests=None):
        valid_scenarios = {"none", "operator", "threshold", "night", "predictive", "pressure", "operator_rule"}
        if scenario not in valid_scenarios:
            raise ValueError(f"scenario must be one of {valid_scenarios}")
        if scenario != "none" and params.n_trucks < 1:
            raise ValueError("Rebalancing requires at least one truck")
        self.p, self.scenario, self.seed = params, scenario, int(seed)
        if params.days > 1 and params.duration_min == 1440.0:
            self.duration = float(1440.0 * params.days)
        else:
            self.duration = float(params.duration_min)
        self.env = simpy.Environment()
        self.ids = params.network.ids
        self.index = {sid: i for i, sid in enumerate(self.ids)}
        self.capacity = params.stations.capacity.to_numpy(int)
        self.inventory = [[Bike(f"sim-{sid}-{k:04d}") for k in range(int(count))]
                          for sid, count in zip(self.ids, params.stations.initial_bikes)]
        self.total = sum(map(len, self.inventory))
        self.initial_ids = {bike.number for station in self.inventory for bike in station}
        self.in_transit: Dict[str, Bike] = {}
        self.in_transit_destinations: Dict[str, int] = {}
        self.cargo = [[] for _ in range(params.n_trucks)]
        self.truck_position = [i % len(self.ids) for i in range(params.n_trucks)]
        self.legs = []
        self.reserved: Set[int] = set()
        self.last_change = np.zeros(len(self.ids))
        self.empty_min = np.zeros(len(self.ids))
        self.overfull_min = np.zeros(len(self.ids))
        self.events, self.trips, self.snapshots, self.fleet = [], [], [], []
        self.lost = self.rentals = self.returned = self.relocated = 0
        self.extra_min = 0.0
        self.extra_activities = []
        self.jobs_started = self.jobs_completed = 0
        self.audit_count = 0
        self.task_counter = 0
        self.station_waiting: List[List[Tuple[str, float, float, Any]]] = [[] for _ in range(len(self.ids))]
        self.user_outcome_records: List[Dict[str, Any]] = []

        demand = params.demand_model
        if demand is None:
            demand = ExampleDemand(np.full(len(self.ids), 1.0))
        # popyt zalezny od ziarna (losowy poziom dnia z modelu Osoby 2): ten sam dla wszystkich strategii
        # z danym ziarnem, wiec wspolne liczby losowe sa zachowane
        if hasattr(demand, "for_seed"):
            demand = demand.for_seed(self.seed)
        self.requests = generate_requests(params.stations, params.network, params, demand, params.od_matrix,
                                          params.context_hourly, seed) if requests is None else requests.copy()
        if scenario == "operator" and params.rebalancing_observed is None:
            raise ValueError("operator requires an observed or explicitly synthetic schedule")
        self.operator_jobs = self.prepare_operator_jobs() if scenario == "operator" else []

        self.field = PressureField(
            bike_km=params.network.bike_km,
            radius_km=params.pressure_radius_km,
            length_scale=params.pressure_length_scale,
            alpha=params.pressure_alpha
        )

        self.station_agents = [
            StationAgent(
                station_id=sid,
                index=i,
                capacity=int(self.capacity[i]),
                initial_bikes=int(params.stations.initial_bikes.iloc[i]),
                env=self.env,
                target_fill=params.target_fill,
                lower_threshold=params.lower_signal_threshold,
                reset_lower=0.25,
                upper_threshold=params.upper_signal_threshold,
                reset_upper=0.75,
                oracle=params.oracle
            )
            for i, sid in enumerate(self.ids)
        ]
        # agent-stacja widzi te same rowery co silnik; z wlasna, nigdy nieaktualizowana lista prognoza zawsze
        # wynosila 0, wiec strategie predictive i pressure nie znajdowaly dawcow i nie robily przewozow
        for agent, bikes in zip(self.station_agents, self.inventory):
            agent.inventory = bikes

        self.truck_agents = [
            TruckAgent(
                truck_id=t,
                capacity=params.truck_capacity,
                initial_position=self.truck_position[t],
                shift_hours=params.truck_shift_hours,
                env=self.env
            )
            for t in range(params.n_trucks)
        ]

        self.dispatcher = DispatcherAgent(
            strategy=scenario,
            n_stations=len(self.ids),
            capacity=self.capacity,
            truck_capacity=params.truck_capacity,
            lower_threshold=params.lower_threshold,
            upper_threshold=params.upper_threshold,
            target_fill=params.target_fill,
            dispatch_interval_min=params.dispatch_interval_min,
            env=self.env
        )

        self.client_rng = random_stream(seed + 999, "client_agent_decisions")
        self.app_history: List[Tuple[float, Dict[str, int]]] = []

    def stamp(self, minute=None):
        return self.p.start_time + pd.Timedelta(minutes=float(self.env.now if minute is None else minute))

    def log(self, kind, station=None, **fields):
        self.events.append({"time": self.stamp(), "minute": float(self.env.now), "event": kind,
                            "station_id": self.ids[station] if station is not None and isinstance(station, int) else (station if station is not None else None), **fields})

    def touch(self, station):
        elapsed = self.env.now - self.last_change[station]
        count = len(self.inventory[station])
        if count == 0:
            self.empty_min[station] += elapsed
        if count > self.capacity[station]:
            self.overfull_min[station] += elapsed
        self.last_change[station] = self.env.now

    def audit(self, identities=False):
        station_count = sum(map(len, self.inventory))
        truck_count = sum(map(len, self.cargo))
        if station_count + truck_count + len(self.in_transit) != self.total:
            raise AssertionError("Bike conservation violated")
        if any(len(load) > self.p.truck_capacity for load in self.cargo):
            raise AssertionError("Truck capacity exceeded")
        if identities:
            numbers = [bike.number for station in self.inventory for bike in station]
            numbers += [bike.number for load in self.cargo for bike in load]
            numbers += list(self.in_transit)
            if len(set(numbers)) != len(numbers) or set(numbers) != self.initial_ids:
                raise AssertionError("Bike identities violated")
        self.audit_count += 1

    def changed(self):
        if self.p.audit_every_event:
            self.audit()

    def alternative(self, origin, want_bike, delayed_app=False):
        distances = self.p.network.bike_km[origin]
        target_inventory = self.inventory
        if delayed_app and self.p.app_delay_min > 0 and self.app_history:
            target_time = max(0.0, self.env.now - self.p.app_delay_min)
            snapshot = min(self.app_history, key=lambda x: abs(x[0] - target_time))
            counts_proxy = [snapshot[1].get(sid, len(self.inventory[idx])) for idx, sid in enumerate(self.ids)]
            for station in np.argsort(distances, kind="stable"):
                if station == origin or distances[station] > self.p.max_walk_km:
                    continue
                available = counts_proxy[station] > 0 if want_bike else counts_proxy[station] < self.capacity[station]
                if available:
                    return int(station)
            return None
        for station in np.argsort(distances, kind="stable"):
            if station == origin or distances[station] > self.p.max_walk_km:
                continue
            available = len(target_inventory[station]) > 0 if want_bike else len(target_inventory[station]) < self.capacity[station]
            if available:
                return int(station)
        return None

    def customer(self, request):
        origin, destination = int(request.origin), int(request.destination)
        yield self.env.timeout(float(request.minute) - self.env.now)
        has_app = bool(self.client_rng.random() < self.p.app_share) if self.p.app_share > 0 else False
        user_id = getattr(request, "user_id", None)
        user_type = getattr(request, "user_type", "commuter" if (request.origin == request.destination) else "standard")
        self.log("user_arrival", origin, request_id=request.request_id, user_id=user_id, user_type=user_type, has_app=has_app)

        pickup = origin
        waited_time = 0.0
        visited_stations = 1
        decision = "rented"

        if not self.inventory[pickup]:
            if self.p.user_patience_min > 0:
                patience = float(self.p.user_patience_min)
                wait_ev = self.env.event()
                self.station_waiting[pickup].append((str(request.request_id), self.env.now, patience, wait_ev))
                self.log("user_wait_start", pickup, request_id=request.request_id, user_id=user_id, user_type=user_type, has_app=has_app)
                t_before = self.env.now
                res = yield wait_ev | self.env.timeout(patience)
                waited_time = self.env.now - t_before
                if wait_ev in res:
                    self.log("user_wait_end", pickup, request_id=request.request_id, user_id=user_id, user_type=user_type, has_app=has_app)
                    decision = "waited"
                else:
                    self.station_waiting[pickup] = [w for w in self.station_waiting[pickup] if w[0] != str(request.request_id)]
                    self.log("user_wait_end", pickup, request_id=request.request_id, user_id=user_id, user_type=user_type, has_app=has_app)
            if not self.inventory[pickup] and bool(request.try_alternative):
                alternative = self.alternative(origin, True, delayed_app=has_app)
                if alternative is not None:
                    walk = self.p.network.bike_km[origin, alternative] * 60 / self.p.walk_speed_kmh
                    self.extra_activities.append((self.env.now, self.env.now + walk))
                    self.log("walk_to_alternative", origin, request_id=request.request_id, to_station=self.ids[alternative], user_id=user_id, user_type=user_type, has_app=has_app)
                    self.log("user_walk", origin, request_id=request.request_id, to_station=self.ids[alternative], user_id=user_id, user_type=user_type, has_app=has_app)
                    yield self.env.timeout(walk)
                    pickup = alternative
                    visited_stations += 1
                    decision = "walked"
        if not self.inventory[pickup]:
            self.lost += 1
            decision = "abandoned"
            self.log("lost_demand", pickup, request_id=request.request_id, user_id=user_id, user_type=user_type, has_app=has_app)
            self.log("user_leave", pickup, request_id=request.request_id, user_id=user_id, user_type=user_type, has_app=has_app)
            self.user_outcome_records.append({
                "request_id": str(request.request_id),
                "user_id": user_id,
                "user_type": user_type,
                "has_app": has_app,
                "decision": decision,
                "wait_time": round(waited_time, 2),
                "stations_visited": visited_stations
            })
            return

        self.touch(pickup)
        bike = self.inventory[pickup].pop()
        departure = self.env.now
        self.in_transit[bike.number] = bike
        self.in_transit_destinations[bike.number] = destination
        self.rentals += 1
        self.log("rental", pickup, request_id=request.request_id, bike=bike.number, to_station=self.ids[destination], user_id=user_id, user_type=user_type, has_app=has_app)
        self.changed()

        km = self.p.network.bike_km[pickup, destination]
        if self.p.ride_time_model is not None:
            ride = float(self.p.ride_time_model.mean_minutes(km)) * float(request.ride_factor)
        else:
            ride = max(0.5, km * 60 / self.p.bike_speed_kmh) * float(request.ride_factor)
        yield self.env.timeout(ride)

        self.log("user_arrival_destination", destination, request_id=request.request_id, bike=bike.number, user_id=user_id, user_type=user_type, has_app=has_app)
        final = destination
        if len(self.inventory[destination]) >= self.capacity[destination] and bool(request.redirect_full):
            alternative = self.alternative(destination, False, delayed_app=has_app)
            if alternative is not None:
                extra = max(0.1, self.p.network.bike_km[destination, alternative] * 60 / self.p.bike_speed_kmh) * float(request.ride_factor)
                self.extra_activities.append((self.env.now, self.env.now + extra))
                self.log("redirect_return", destination, request_id=request.request_id, bike=bike.number, to_station=self.ids[alternative], user_id=user_id, user_type=user_type, has_app=has_app)
                yield self.env.timeout(extra)
                final = alternative
                visited_stations += 1

        self.touch(final)
        self.in_transit_destinations.pop(bike.number, None)
        returned_bike = self.in_transit.pop(bike.number)
        if self.station_waiting[final]:
            w_req_id, w_arr, w_pat, w_ev = self.station_waiting[final].pop(0)
            self.inventory[final].append(returned_bike)
            if not w_ev.triggered:
                w_ev.succeed()
        else:
            self.inventory[final].append(returned_bike)

        self.returned += 1
        self.log("return", final, request_id=request.request_id, bike=bike.number, user_id=user_id, user_type=user_type, has_app=has_app)
        self.add_trip(bike, pickup, final, departure, "user", request.request_id)
        self.changed()

        self.user_outcome_records.append({
            "request_id": str(request.request_id),
            "user_id": user_id,
            "user_type": user_type,
            "has_app": has_app,
            "decision": decision,
            "wait_time": round(waited_time, 2),
            "stations_visited": visited_stations
        })

    def add_trip(self, bike, origin, destination, departure, kind, request_id=None):
        self.trips.append({"bike": bike.number, "from_station": self.ids[origin], "to_station": self.ids[destination],
                           "from_type": "station", "to_type": "station",
                           "from_lat": float(self.p.stations.lat.iloc[origin]), "from_lon": float(self.p.stations.lon.iloc[origin]),
                           "to_lat": float(self.p.stations.lat.iloc[destination]), "to_lon": float(self.p.stations.lon.iloc[destination]),
                           "t_departure": self.stamp(departure), "t_arrival": self.stamp(),
                           "duration_min": self.env.now - departure, "type": kind,
                           "network_km": float((self.p.network.bike_km if kind == "user" else self.p.network.truck_km)[origin, destination]),
                           "distance_km": float((self.p.network.bike_km if kind == "user" else self.p.network.truck_km)[origin, destination]),
                           "is_ebike": False, "battery_start": None, "elev_diff_m": None,
                           "same_station": origin == destination, "is_flicker": False, "from_loose": False,
                           "to_loose": False, "is_long": False, "too_fast": False, "request_id": request_id})

    def travel(self, truck, destination):
        origin = self.truck_position[truck]
        km = float(self.p.network.truck_km[origin, destination])
        remaining = float(self.p.network.truck_minutes[origin, destination])
        total = remaining
        self.log("truck_departure", origin, truck_id=truck, to_station=self.ids[destination], load=len(self.cargo[truck]))
        while remaining > 1e-10:
            ctx = context_at(self.p.start_time, self.env.now, self.p.context_hourly)
            congestion = float(ctx.get("congestion", 0.0))
            if not math.isfinite(congestion) or not 0 <= congestion <= 1:
                raise ValueError("congestion must be in [0,1]")
            slowdown = 1 / max(0.05, 1 - min(0.95, congestion * self.p.congestion_multiplier))
            until_hour = next_hour_minute(self.p.start_time, self.env.now) - self.env.now
            elapsed = min(remaining * slowdown, until_hour)
            covered = elapsed / slowdown
            self.legs.append((self.env.now, self.env.now + elapsed, km * covered / total if total else 0.0))
            yield self.env.timeout(elapsed)
            remaining -= covered
        self.truck_position[truck] = destination
        self.truck_agents[truck].position = destination
        self.log("truck_arrival", destination, truck_id=truck, load=len(self.cargo[truck]))

    def threshold_job(self):
        counts = np.array([len(station) for station in self.inventory])
        ratio = counts / self.capacity
        donors = [i for i in range(len(self.ids)) if i not in self.reserved and counts[i] > self.capacity[i] * self.p.target_fill]
        targets = [i for i in range(len(self.ids)) if i not in self.reserved and counts[i] < self.capacity[i] * self.p.target_fill]
        pairs = [(a, b) for a in donors for b in targets
                 if ratio[a] > self.p.upper_threshold or ratio[b] < self.p.lower_threshold]
        if not pairs:
            return None
        origin, destination = min(pairs, key=lambda pair: (ratio[pair[1]] - ratio[pair[0]], self.p.network.truck_minutes[pair], pair))
        count = min(self.p.truck_capacity, max(1, int(counts[origin] - self.capacity[origin] * self.p.target_fill)),
                    max(1, int(math.ceil(self.capacity[destination] * self.p.target_fill - counts[destination]))))
        self.reserved.update((origin, destination))
        return (origin, destination, count)

    def select_agent_job(self):
        counts = np.array([len(station) for station in self.inventory])
        if self.scenario == "threshold":
            return self.threshold_job()
        if self.scenario == "operator_rule":
            job = self.dispatcher.find_operator_rule_pair(counts, self.p.network.truck_minutes, self.env.now)
            if job:
                self.reserved.update((job[0], job[1]))
            return job
        if self.scenario == "pressure":
            signals = np.array([ag.signal_value for ag in self.station_agents])
            pressures = self.field.compute_pressure(signals)
            job = self.dispatcher.find_pressure_pair(pressures, counts, self.p.network.truck_minutes)
            if job:
                self.reserved.update((job[0], job[1]))
            return job
        if self.scenario == "predictive":
            forecasts = np.zeros(len(self.ids))
            for i, ag in enumerate(self.station_agents):
                in_tr = sum(1 for dest in self.in_transit_destinations.values() if dest == i) if self.p.oracle else 0
                exp_ret = 1.0 if not self.p.oracle else in_tr
                forecasts[i] = ag.forecast_bikes(in_tr, exp_ret, 1.0)
            job = self.dispatcher.find_predictive_pair(forecasts, counts, self.p.network.truck_minutes)
            if job:
                self.reserved.update((job[0], job[1]))
            return job
        if self.scenario == "night":
            hour = int(self.env.now // 60) % 24
            if 0 <= hour < 5:
                morning_outflow = np.zeros(len(self.ids))
                for i in range(len(self.ids)):
                    morning_outflow[i] = max(0, int(self.capacity[i] * 0.3))
                job = self.dispatcher.find_night_pair(morning_outflow, counts, self.p.network.truck_minutes)
                if job:
                    self.reserved.update((job[0], job[1]))
                return job
            return None
        return None

    def prepare_operator_jobs(self):
        table = self.p.rebalancing_observed.copy()
        if table.empty:
            return []
        needed = {"from_station", "to_station", "n_bikes"}
        if not needed <= set(table):
            raise ValueError("Invalid operator schedule columns")
        if "minute" not in table:
            table["minute"] = (pd.to_datetime(table.t_departure, utc=True) - self.p.start_time).dt.total_seconds() / 60
        jobs = []
        for row in table.sort_values("minute", kind="stable").itertuples():
            if str(row.from_station) not in self.index or str(row.to_station) not in self.index:
                raise ValueError("Unknown station in operator schedule")
            if not math.isfinite(row.minute) or not math.isfinite(row.n_bikes) or row.n_bikes < 0 or row.n_bikes != int(row.n_bikes):
                raise ValueError("Invalid operator job")
            if 0 <= row.minute < self.duration:
                remaining = int(row.n_bikes)
                while remaining:
                    amount = min(remaining, self.p.truck_capacity)
                    jobs.append((float(row.minute), self.index[str(row.from_station)], self.index[str(row.to_station)], amount))
                    remaining -= amount
        return jobs

    def truck(self, truck):
        truck_ag = self.truck_agents[truck]
        while self.env.now < self.duration:
            if not truck_ag.is_on_shift(self.env.now):
                yield self.env.timeout(self.p.dispatch_interval_min)
                continue
            if self.scenario == "operator":
                if not self.operator_jobs:
                    return
                ready, origin, destination, requested = self.operator_jobs.pop(0)
                if ready > self.env.now:
                    yield self.env.timeout(ready - self.env.now)
            else:
                job = self.select_agent_job()
                if job is None:
                    yield self.env.timeout(self.p.dispatch_interval_min)
                    continue
                origin, destination, requested = job
                self.task_counter += 1
                t_id = self.task_counter
                self.log("task_announced", destination, n_bikes=requested, task_id=t_id)
                self.log("bid", destination, truck_id=truck, task_id=t_id, cost_min=10.0)
                self.log("task_awarded", origin, to_station=self.ids[destination], truck_id=truck, n_bikes=requested, task_id=t_id)

            self.jobs_started += 1
            truck_ag.busy = True
            yield from self.travel(truck, origin)
            departures = {}
            for _ in range(requested):
                yield self.env.timeout(self.p.handling_min_per_bike)
                if not self.inventory[origin]:
                    break
                self.touch(origin)
                bike = self.inventory[origin].pop()
                self.cargo[truck].append(bike)
                truck_ag.cargo.append(bike)
                departures[bike.number] = self.env.now
                self.log("truck_load", origin, bike=bike.number, truck_id=truck)
                self.changed()
            if self.cargo[truck]:
                yield from self.travel(truck, destination)
                while self.cargo[truck]:
                    yield self.env.timeout(self.p.handling_min_per_bike)
                    self.touch(destination)
                    bike = self.cargo[truck].pop()
                    if truck_ag.cargo:
                        truck_ag.cargo.pop()
                    if self.station_waiting[destination]:
                        w_req_id, w_arr, w_pat, w_ev = self.station_waiting[destination].pop(0)
                        self.inventory[destination].append(bike)
                        if not w_ev.triggered:
                            w_ev.succeed()
                    else:
                        self.inventory[destination].append(bike)
                    self.relocated += 1
                    self.log("truck_unload", destination, bike=bike.number, truck_id=truck)
                    self.add_trip(bike, origin, destination, departures[bike.number], "service")
                    self.changed()
            self.jobs_completed += 1
            truck_ag.busy = False
            if self.scenario != "operator":
                self.reserved.difference_update((origin, destination))
                self.dispatcher.reserved_stations.difference_update((origin, destination))
            yield self.env.timeout(self.p.dispatch_interval_min if self.scenario != "operator" else 0)

    def snapshot(self):
        signals = np.zeros(len(self.ids))
        for i, sid in enumerate(self.ids):
            count = len(self.inventory[i])
            cap = self.capacity[i]
            in_tr = sum(1 for dest in self.in_transit_destinations.values() if dest == i) if self.p.oracle else 0
            exp_ret = 1.0 if not self.p.oracle else in_tr
            fc = self.station_agents[i].forecast_bikes(in_tr, exp_ret, 1.0)
            sig, state, changed = self.station_agents[i].update_signal(fc)
            signals[i] = sig
            if changed:
                event_name = "signal_on" if state != "normal" else "signal_off"
                self.log(event_name, i)

        pressures = self.field.compute_pressure(signals)
        app_state = {}
        for i, sid in enumerate(self.ids):
            count = len(self.inventory[i])
            app_state[sid] = count
            self.snapshots.append({"time": self.stamp(), "station_id": sid, "bikes": count,
                                   "capacity": int(self.capacity[i]), "docks": max(0, int(self.capacity[i]) - count),
                                   "ebikes": 0, "ebikes_low": 0, "is_empty": count == 0,
                                   "is_overfull": count > self.capacity[i], "is_spike": False, "numbers_mismatch": False,
                                   "pressure": float(round(pressures[i], 3))})
        self.app_history.append((float(self.env.now), app_state))
        if len(self.app_history) > 100:
            self.app_history.pop(0)

        self.fleet.append({"time": self.stamp(), "at_stations": sum(map(len, self.inventory)),
                           "in_use": len(self.in_transit), "on_trucks": sum(map(len, self.cargo)), "total": self.total})
        self.audit()

    def clock(self):
        while True:
            ctx = context_at(self.p.start_time, self.env.now, self.p.context_hourly)
            self.log("hour_change", congestion=float(ctx.get("congestion", 0.0)),
                     temperature_2m=float(ctx.get("temperature_2m", 12.0)), local_hour=int(ctx["local_hour"]))
            yield self.env.timeout(next_hour_minute(self.p.start_time, self.env.now) - self.env.now)

    def sampling(self):
        while True:
            self.snapshot()
            yield self.env.timeout(self.p.snapshot_interval_min)

    def run(self):
        for request in self.requests.itertuples():
            if float(request.minute) < self.duration:
                self.env.process(self.customer(request))
        if self.scenario != "none":
            for truck in range(self.p.n_trucks):
                self.env.process(self.truck(truck))
        self.env.process(self.clock())
        self.env.process(self.sampling())
        self.env.run(until=self.duration)
        for station in range(len(self.ids)):
            self.touch(station)
        self.snapshot()
        self.audit(identities=True)
        km = sum(distance * max(0.0, min(1.0, (self.duration - start) / (end - start)))
                 for start, end, distance in self.legs if end > start)
        self.extra_min = sum(max(0.0, min(end, self.duration) - start) for start, end in self.extra_activities)
        arrived = int((self.requests.minute < self.duration).sum())
        pending = arrived - self.lost - self.rentals
        kpis = {"scenario": self.scenario, "seed": self.seed, "n_trucks": self.p.n_trucks,
                "requests": arrived, "rentals": self.rentals, "returns": self.returned,
                "lost_demand": self.lost, "lost_share": self.lost / arrived if arrived else 0.0,
                "pending_users": pending, "empty_station_share": float(self.empty_min.sum() / (len(self.ids) * self.duration)),
                "extra_user_minutes": float(self.extra_min), "extra_minutes_per_request": self.extra_min / arrived if arrived else 0.0,
                "truck_km": float(km), "relocated_bikes": self.relocated, "jobs_started": self.jobs_started,
                "jobs_completed": self.jobs_completed, "operator_jobs_unassigned": len(self.operator_jobs),
                "initial_bikes": self.total, "final_bikes": self.total,
                "bikes_in_transit_at_end": len(self.in_transit), "bikes_on_trucks_at_end": sum(map(len, self.cargo)),
                "conservation_checks": self.audit_count}
        events = pd.DataFrame(self.events)
        for column in ("bike", "request_id", "from_station", "to_station", "truck_id", "user_id", "user_type", "has_app", "task_id", "cost_min", "n_bikes", "load"):
            if column not in events:
                events[column] = pd.Series(dtype="object")
        trip_columns = ["bike", "from_station", "to_station", "from_type", "to_type", "from_lat", "from_lon", "to_lat", "to_lon",
                        "t_departure", "t_arrival", "duration_min", "type", "network_km", "distance_km", "is_ebike", "battery_start",
                        "elev_diff_m", "same_station", "is_flicker", "from_loose", "to_loose", "is_long", "too_fast", "request_id"]
        trips = pd.DataFrame(self.trips, columns=trip_columns)
        station_kpis = pd.DataFrame({"station_id": self.ids, "empty_minutes": self.empty_min,
                                     "overfull_minutes": self.overfull_min, "empty_share": self.empty_min / self.duration})
        user_outcomes = pd.DataFrame(self.user_outcome_records)
        return SimulationResult(events, pd.DataFrame(self.snapshots), trips, pd.DataFrame(self.fleet), self.requests,
                                station_kpis, kpis, user_outcomes=user_outcomes)

def run_simulation(params, scenario, seed):
    if isinstance(params, dict):
        params = SimulationParams(**params)
    result = Simulation(params, scenario, seed).run()
    if params.output_dir is not None:
        directory = Path(params.output_dir)
        directory.mkdir(parents=True, exist_ok=True)
        tables = {"events": result.events, "station_timeseries": result.station_timeseries, "trips": result.trips,
                  "fleet_timeseries": result.fleet_timeseries, "requests": result.requests, "station_kpis": result.station_kpis}
        for name, table in tables.items():
            path = directory / f"{name}.parquet"
            table.to_parquet(path, index=False)
            result.paths[name] = path
        result.station_timeseries.to_parquet(directory / "observed_timeseries.parquet", index=False)
        params.stations.to_parquet(directory / "stations.parquet", index=False)
        if params.context_hourly is not None:
            params.context_hourly.reset_index().to_parquet(directory / "context_hourly.parquet", index=False)
        if result.user_outcomes is not None and not result.user_outcomes.empty:
            result.user_outcomes.to_parquet(directory / "user_outcomes.parquet", index=False)
        service = result.trips[result.trips.type == "service"]
        if service.empty:
            reb = pd.DataFrame(columns=["from_station", "to_station", "t_departure", "t_arrival", "n_bikes", "bikes", "distance_km", "network_km", "duration_min"])
        else:
            reb = service.groupby(["from_station", "to_station", "t_departure", "t_arrival"], as_index=False).agg(
                n_bikes=("bike", "size"), bikes=("bike", list), distance_km=("distance_km", "first"),
                network_km=("network_km", "first"), duration_min=("duration_min", "first"))
        reb.to_parquet(directory / "rebalancing_observed.parquet", index=False)
        (directory / "kpis.json").write_text(json.dumps(result.kpis, indent=2), encoding="utf-8")
    return result
