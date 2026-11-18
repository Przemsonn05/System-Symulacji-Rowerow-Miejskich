from typing import Any, List, Optional, Tuple
import numpy as np
from .base import Agent, TruckView

class TruckAgent(Agent):
    def __init__(
        self,
        truck_id: int,
        capacity: int = 20,
        initial_position: int = 0,
        shift_hours: Optional[Tuple[int, int]] = None,
        env: Optional[Any] = None
    ):
        super().__init__(agent_id=f"truck_{truck_id}", env=env)
        self.truck_id = truck_id
        self.capacity = capacity
        self.position = initial_position
        self.cargo: List[Any] = []
        self.shift_hours = shift_hours
        self.busy = False
        self.current_task: Optional[Any] = None
        self.total_km = 0.0
        self.working_minutes = 0.0

    def is_on_shift(self, minute: float) -> bool:
        if self.shift_hours is None:
            return True
        start_h, end_h = self.shift_hours
        hour = int(minute // 60) % 24
        if start_h <= end_h:
            return start_h <= hour < end_h
        return hour >= start_h or hour < end_h

    def estimate_cost(
        self,
        from_station: int,
        to_station: int,
        n_bikes: int,
        truck_minutes: np.ndarray,
        handling_min_per_bike: float
    ) -> float:
        leg1 = float(truck_minutes[self.position, from_station])
        load_time = float(n_bikes * handling_min_per_bike)
        leg2 = float(truck_minutes[from_station, to_station])
        unload_time = float(n_bikes * handling_min_per_bike)
        return leg1 + load_time + leg2 + unload_time

    def view(self, minute: float) -> TruckView:
        return TruckView(
            truck_id=self.truck_id,
            capacity=self.capacity,
            load=len(self.cargo),
            position=self.position,
            busy=self.busy,
            shift_active=self.is_on_shift(minute)
        )
