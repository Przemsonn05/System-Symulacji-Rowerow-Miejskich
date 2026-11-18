from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
from .base import Agent, StationView

@dataclass
class WaitingUser:
    request_id: str
    arrival_minute: float
    patience_minute: float
    event: Any = None

class StationAgent(Agent):
    def __init__(
        self,
        station_id: str,
        index: int,
        capacity: int,
        initial_bikes: int,
        env: Optional[Any] = None,
        target_fill: float = 0.5,
        lower_threshold: float = 0.1,
        reset_lower: float = 0.25,
        upper_threshold: float = 0.9,
        reset_upper: float = 0.75,
        oracle: bool = False
    ):
        super().__init__(agent_id=f"station_{station_id}", env=env)
        self.station_id = station_id
        self.index = index
        self.capacity = capacity
        self.target_fill = target_fill
        self.lower_threshold = lower_threshold
        self.reset_lower = reset_lower
        self.upper_threshold = upper_threshold
        self.reset_upper = reset_upper
        self.oracle = oracle
        self.inventory: List[Any] = []
        self.waiting_queue: List[WaitingUser] = []
        self.incoming_truck_deliveries = 0
        self.signal_value = 0.0
        self.signal_state = "normal"
        self.empty_minutes = 0.0
        self.overfull_minutes = 0.0
        self.last_change_minute = 0.0

    def view(self) -> StationView:
        return StationView(
            station_id=self.station_id,
            bikes=len(self.inventory),
            capacity=self.capacity,
            queue_len=len(self.waiting_queue),
            incoming_bikes=self.incoming_truck_deliveries
        )

    def forecast_bikes(
        self,
        in_transit_actual: int,
        expected_returns: float,
        expected_rentals: float
    ) -> float:
        current = float(len(self.inventory))
        returns = float(in_transit_actual) if self.oracle else float(expected_returns)
        forecast = current + float(self.incoming_truck_deliveries) + returns - float(expected_rentals)
        return max(0.0, forecast)

    def update_signal(
        self,
        forecast: float
    ) -> Tuple[float, str, bool]:
        target = self.capacity * self.target_fill
        cap = max(1, self.capacity)
        s = (forecast - target) / cap
        s = float(np.clip(s, -1.0, 1.0))
        self.signal_value = s
        prev_state = self.signal_state
        fill_ratio = forecast / cap
        if self.signal_state == "deficit":
            if fill_ratio >= self.reset_lower:
                self.signal_state = "normal"
        elif self.signal_state == "surplus":
            if fill_ratio <= self.reset_upper:
                self.signal_state = "normal"
        else:
            if fill_ratio < self.lower_threshold:
                self.signal_state = "deficit"
            elif fill_ratio > self.upper_threshold:
                self.signal_state = "surplus"
        changed = self.signal_state != prev_state
        return self.signal_value, self.signal_state, changed

    def add_waiting_user(self, request_id: str, current_minute: float, patience_min: float, sim_event: Any = None) -> WaitingUser:
        user = WaitingUser(
            request_id=request_id,
            arrival_minute=current_minute,
            patience_minute=patience_min,
            event=sim_event
        )
        self.waiting_queue.append(user)
        return user

    def pop_waiting_user(self) -> Optional[WaitingUser]:
        if self.waiting_queue:
            return self.waiting_queue.pop(0)
        return None

    def remove_waiting_user(self, request_id: str) -> bool:
        for idx, u in enumerate(self.waiting_queue):
            if u.request_id == request_id:
                self.waiting_queue.pop(idx)
                return True
        return False

    def touch(self, current_minute: float) -> None:
        elapsed = current_minute - self.last_change_minute
        if len(self.inventory) == 0:
            self.empty_minutes += elapsed
        if len(self.inventory) > self.capacity:
            self.overfull_minutes += elapsed
        self.last_change_minute = current_minute

    def add_bike(self, bike: Any, current_minute: float) -> None:
        self.touch(current_minute)
        self.inventory.append(bike)

    def pop_bike(self, current_minute: float) -> Any:
        self.touch(current_minute)
        return self.inventory.pop()
