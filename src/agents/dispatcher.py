from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple
import math
import numpy as np
from .base import Agent, DispatcherView
from .truck import TruckAgent

@dataclass
class RebalanceTask:
    task_id: int
    origin: int
    destination: int
    n_bikes: int
    minute: float
    reason: str = "general"

class DispatcherAgent(Agent):
    def __init__(
        self,
        strategy: str,
        n_stations: int,
        capacity: np.ndarray,
        truck_capacity: int = 20,
        lower_threshold: float = 0.2,
        upper_threshold: float = 0.8,
        target_fill: float = 0.5,
        dispatch_interval_min: float = 5.0,
        env: Optional[Any] = None
    ):
        super().__init__(agent_id="dispatcher", env=env)
        self.strategy = strategy
        self.n_stations = n_stations
        self.capacity = np.asarray(capacity, dtype=int)
        self.truck_capacity = truck_capacity
        self.lower_threshold = lower_threshold
        self.upper_threshold = upper_threshold
        self.target_fill = target_fill
        self.dispatch_interval_min = dispatch_interval_min
        self.reserved_stations: Set[int] = set()
        self.task_counter = 0

    def contract_net_auction(
        self,
        task: RebalanceTask,
        trucks: List[TruckAgent],
        truck_minutes: np.ndarray,
        handling_min: float,
        minute: float
    ) -> Optional[Tuple[TruckAgent, float, List[Dict[str, Any]]]]:
        eligible_trucks = [t for t in trucks if not t.busy and t.is_on_shift(minute)]
        if not eligible_trucks:
            return None
        bids = []
        for t in eligible_trucks:
            cost = t.estimate_cost(task.origin, task.destination, task.n_bikes, truck_minutes, handling_min)
            bids.append((cost, t.truck_id, t))
        bids.sort(key=lambda x: (x[0], x[1]))
        winner_cost, winner_id, winner_truck = bids[0]
        bid_records = [
            {
                "minute": minute,
                "event": "bid",
                "station_id": task.destination,
                "truck_id": t.truck_id,
                "task_id": task.task_id,
                "cost_min": round(cost, 2)
            }
            for cost, tid, t in bids
        ]
        return winner_truck, winner_cost, bid_records

    def find_threshold_pair(
        self,
        inventory_counts: np.ndarray,
        truck_minutes: np.ndarray
    ) -> Optional[Tuple[int, int, int]]:
        ratio = inventory_counts / np.maximum(1, self.capacity)
        donors = [i for i in range(self.n_stations)
                  if i not in self.reserved_stations and inventory_counts[i] > self.capacity[i] * self.target_fill]
        targets = [i for i in range(self.n_stations)
                   if i not in self.reserved_stations and inventory_counts[i] < self.capacity[i] * self.target_fill]
        pairs = [(a, b) for a in donors for b in targets
                 if ratio[a] > self.upper_threshold or ratio[b] < self.lower_threshold]
        if not pairs:
            return None
        origin, destination = min(pairs, key=lambda pair: (ratio[pair[1]] - ratio[pair[0]], truck_minutes[pair], pair))
        count = min(
            self.truck_capacity,
            max(1, int(inventory_counts[origin] - self.capacity[origin] * self.target_fill)),
            max(1, int(math.ceil(self.capacity[destination] * self.target_fill - inventory_counts[destination])))
        )
        return origin, destination, count

    def find_pressure_pair(
        self,
        pressures: np.ndarray,
        inventory_counts: np.ndarray,
        truck_minutes: np.ndarray
    ) -> Optional[Tuple[int, int, int]]:
        donors = [i for i in range(self.n_stations)
                  if i not in self.reserved_stations and pressures[i] > 0.05 and inventory_counts[i] > 2]
        targets = [i for i in range(self.n_stations)
                   if i not in self.reserved_stations and pressures[i] < -0.05]
        if not donors or not targets:
            return None
        pairs = [(a, b) for a in donors for b in targets]
        origin, destination = min(pairs, key=lambda p: (pressures[p[1]] - pressures[p[0]], truck_minutes[p], p))
        needed = max(1, int(math.ceil(self.capacity[destination] * self.target_fill - inventory_counts[destination])))
        available = max(1, int(inventory_counts[origin] - self.capacity[origin] * self.target_fill))
        count = min(self.truck_capacity, available, needed)
        return origin, destination, count

    def find_predictive_pair(
        self,
        forecasts: np.ndarray,
        inventory_counts: np.ndarray,
        truck_minutes: np.ndarray
    ) -> Optional[Tuple[int, int, int]]:
        forecast_ratio = forecasts / np.maximum(1, self.capacity)
        donors = [i for i in range(self.n_stations)
                  if i not in self.reserved_stations and forecast_ratio[i] > self.upper_threshold and inventory_counts[i] > 2]
        targets = [i for i in range(self.n_stations)
                   if i not in self.reserved_stations and forecast_ratio[i] < self.lower_threshold]
        if not donors or not targets:
            return None
        pairs = [(a, b) for a in donors for b in targets]
        origin, destination = min(pairs, key=lambda p: (forecast_ratio[p[1]] - forecast_ratio[p[0]], truck_minutes[p], p))
        count = min(
            self.truck_capacity,
            max(1, int(inventory_counts[origin] - self.capacity[origin] * self.target_fill)),
            max(1, int(math.ceil(self.capacity[destination] * self.target_fill - inventory_counts[destination])))
        )
        return origin, destination, count

    def find_night_pair(
        self,
        morning_net_outflow: np.ndarray,
        inventory_counts: np.ndarray,
        truck_minutes: np.ndarray
    ) -> Optional[Tuple[int, int, int]]:
        morning_target = np.clip(
            np.round(self.capacity * self.target_fill + morning_net_outflow),
            1,
            self.capacity
        )
        diff = inventory_counts - morning_target
        donors = [i for i in range(self.n_stations)
                  if i not in self.reserved_stations and diff[i] > 2 and inventory_counts[i] > 2]
        targets = [i for i in range(self.n_stations)
                   if i not in self.reserved_stations and diff[i] < -2]
        if not donors or not targets:
            return None
        pairs = [(a, b) for a in donors for b in targets]
        origin, destination = min(pairs, key=lambda p: (diff[p[1]] - diff[p[0]], truck_minutes[p], p))
        count = min(
            self.truck_capacity,
            max(1, int(diff[origin])),
            max(1, int(-diff[destination]))
        )
        return origin, destination, count

    def find_operator_rule_pair(
        self,
        inventory_counts: np.ndarray,
        truck_minutes: np.ndarray,
        minute: float
    ) -> Optional[Tuple[int, int, int]]:
        hour = int(minute // 60) % 24
        if not (6 <= hour < 22):
            return None
        ratio = inventory_counts / np.maximum(1, self.capacity)
        donors = [i for i in range(self.n_stations)
                  if i not in self.reserved_stations and ratio[i] > 0.75 and inventory_counts[i] > 3]
        targets = [i for i in range(self.n_stations)
                   if i not in self.reserved_stations and ratio[i] < 0.25]
        if not donors or not targets:
            return None
        pairs = [(a, b) for a in donors for b in targets]
        origin, destination = min(pairs, key=lambda p: (ratio[p[1]] - ratio[p[0]], truck_minutes[p], p))
        count = min(
            self.truck_capacity,
            max(1, int(inventory_counts[origin] - self.capacity[origin] * self.target_fill)),
            max(1, int(math.ceil(self.capacity[destination] * self.target_fill - inventory_counts[destination])))
        )
        return origin, destination, count

    def next_task_id(self) -> int:
        self.task_counter += 1
        return self.task_counter
