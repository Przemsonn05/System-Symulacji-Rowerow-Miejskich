from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import simpy

@dataclass
class AgentMessage:
    sender: str
    recipient: str
    kind: str
    payload: Any = None
    minute: float = 0.0

@dataclass(frozen=True)
class StationView:
    station_id: str
    bikes: int
    capacity: int
    queue_len: int
    incoming_bikes: int = 0

@dataclass(frozen=True)
class AppView:
    station_bikes: Dict[str, int]
    station_capacities: Dict[str, int]
    timestamp_minute: float

@dataclass(frozen=True)
class TruckView:
    truck_id: int
    capacity: int
    load: int
    position: int
    busy: bool
    shift_active: bool

@dataclass(frozen=True)
class DispatcherView:
    signals: Dict[str, float]
    pressures: Dict[str, float]
    truck_positions: Dict[int, int]
    truck_busy: Dict[int, bool]

class Agent:
    def __init__(self, agent_id: str, env: Optional[simpy.Environment] = None):
        self.agent_id = agent_id
        self.env = env
        self.state: Dict[str, Any] = {}
        self.inbox: List[AgentMessage] = []

    def perceive(self, view: Any) -> Any:
        return view

    def act(self) -> Any:
        return None

    def on_message(self, message: AgentMessage) -> Any:
        self.inbox.append(message)
        return None

    def send(self, recipient: "Agent", kind: str, payload: Any = None, minute: float = 0.0) -> AgentMessage:
        msg = AgentMessage(
            sender=self.agent_id,
            recipient=recipient.agent_id,
            kind=kind,
            payload=payload,
            minute=minute
        )
        recipient.on_message(msg)
        return msg
