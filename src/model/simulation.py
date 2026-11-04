"""Referencyjna, minimalna symulacja zdarzen dyskretnych na poziomie stacji.

Sluzy do kalibracji i walidacji modeli zachowan, dopoki nie ma pelnej run_simulation() Osoby 3.

Zdarzenia:
  klient przychodzi na stacje i (niejednorodny proces Poissona: lambda z modelu popytu, stala
    w obrebie godziny, z mnoznikiem gamma o wariancji alpha jak w regresji NB),
  - jest rower -> jedzie; cel z modelu OD, czas z modelu czasu jazdy,
  - pusto -> z p_walk idzie do najblizszej stacji z rowerem w promieniu radius_m, inaczej rezygnuje
    (utracony popyt),
  zwrot na stacji: pojemnosc miekka - przy nadmiarze n = rowery - stojaki >= 0 z prawdopodobienstwem
    1 - exp(-overflow_k * (n + 1) / stojaki) jedzie do najblizszej niepelnej stacji w promieniu
    radius_m, inaczej zostawia rower mimo przepelnienia,
  relokacje operatora odtwarzane z rebalancing_observed (zabiera tyle, ile stoi, nie wiecej).
"""

import heapq
from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from .data import walk_matrix_m
from .od import slot_index


@dataclass
class AgentParams:
    p_walk: float = 0.5
    radius_m: float = 400.0
    overflow_k: float = 1.0

    def as_dict(self):
        return asdict(self)


class Models:
    """Modele zachowan + dane stacji potrzebne w symulacji."""

    def __init__(self, demand, od, duration, stations):
        self.demand, self.od, self.duration = demand, od, duration
        self.station_ids = od.station_ids
        st = stations.set_index("station_id").reindex(self.station_ids)
        self.capacity = st["capacity"].fillna(10).astype(int).to_numpy()
        walk = walk_matrix_m(self.station_ids, stations)
        # sasiedzi kazdej stacji od najblizszego: [(stacja, metry), ...]
        self.neighbors = [[(int(j), walk[i, j]) for j in np.argsort(walk[i]) if j != i and walk[i, j] <= 1000]
                          for i in range(len(self.station_ids))]
        self.cum_od = np.cumsum(od.P, axis=2)


@dataclass
class SimResult:
    times: pd.DatetimeIndex  # chwile zapisu stanu stacji
    bikes: np.ndarray        # [chwile x stacje]
    hours: pd.DatetimeIndex
    departures: np.ndarray   # [godziny x stacje]
    lost: np.ndarray         # [godziny x stacje] klienci, ktorzy zrezygnowali
    od: np.ndarray           # [stacje x stacje] liczba przejazdow


ARRIVE, RETURN, REB_OUT, REB_IN, SNAP = range(5)


def _nearest(neighbors, radius, ok):
    for j, dist in neighbors:
        if dist > radius:
            return -1
        if ok(j):
            return j
    return -1


def run_simulation(models, params, start, end, initial_bikes, ctx, rebalancing, times, seed=0):
    """Symulacja od start do end (pd.Timestamp UTC) ze stanu initial_bikes [stacje].

    ctx: context_hourly (godziny [start, end) wybierane tutaj), rebalancing: rebalancing_observed,
    times: chwile, w ktorych zapisujemy stan stacji."""
    rng = np.random.default_rng(seed)
    m = models
    n = len(m.station_ids)
    idx = {s: k for k, s in enumerate(m.station_ids)}

    def minutes(ts):
        return (ts - start).total_seconds() / 60.0

    horizon = minutes(end)
    c = ctx[(ctx["time"] >= start.floor("h")) & (ctx["time"] < end)].reset_index(drop=True)
    hours = pd.DatetimeIndex(c["time"])
    lam = m.demand.rate(m.station_ids, c) * rng.gamma(1.0 / m.demand.alpha, m.demand.alpha, size=(len(c), n))
    slots = slot_index(c["local_hour"], c["day_type"] != "workday")
    first_hour = minutes(hours[0])

    ev = []
    counts = rng.poisson(lam)
    for h, i in zip(*np.nonzero(counts)):
        a = minutes(hours[h])
        ev += [(u, ARRIVE, int(i), 0) for u in rng.uniform(a, a + 60.0, counts[h, i]) if 0 <= u < horizon]
    reb = rebalancing[(rebalancing["t_arrival"] >= start) & (rebalancing["t_departure"] < end)]
    for k, r in enumerate(reb.itertuples()):
        ev.append((max(minutes(r.t_departure), 0.0), REB_OUT, idx.get(r.from_station, -1), k))
        ev.append((max(minutes(r.t_arrival), 0.0), REB_IN, idx.get(r.to_station, -1), k))
    ev += [(minutes(ts), SNAP, k, 0) for k, ts in enumerate(times)]
    heapq.heapify(ev)

    bikes = np.asarray(initial_bikes, dtype=int).copy()
    cap = m.capacity
    reb_want, reb_taken = reb["n_bikes"].astype(int).to_numpy(), {}
    dep = np.zeros((len(c), n), dtype=int)
    lost = np.zeros((len(c), n), dtype=int)
    od = np.zeros((n, n), dtype=int)
    snaps = np.zeros((len(times), n), dtype=int)

    while ev:
        u, kind, i, k = heapq.heappop(ev)
        h = min(max(int((u - first_hour) // 60), 0), len(c) - 1)
        if kind == ARRIVE:
            o = i
            if bikes[i] == 0:
                o = _nearest(m.neighbors[i], params.radius_m, lambda j: bikes[j] > 0) if rng.random() < params.p_walk else -1
                if o < 0:
                    lost[h, i] += 1
                    continue
            bikes[o] -= 1
            dep[h, o] += 1
            dest = min(int(np.searchsorted(m.cum_od[slots[h], i], rng.random())), n - 1)
            od[o, dest] += 1
            t_ret = u + m.duration.sample(np.array([m.od.D[o, dest]]), rng)[0]
            if t_ret < horizon:
                heapq.heappush(ev, (t_ret, RETURN, dest, 0))
        elif kind == RETURN:
            excess = bikes[i] - cap[i]
            if excess >= 0 and rng.random() < 1.0 - np.exp(-params.overflow_k * (excess + 1) / max(cap[i], 1)):
                j = _nearest(m.neighbors[i], params.radius_m, lambda j: bikes[j] < cap[j])
                i = j if j >= 0 else i
            bikes[i] += 1
        elif kind == REB_OUT:
            take = reb_want[k] if i < 0 else min(reb_want[k], bikes[i])  # i < 0: z magazynu
            if i >= 0:
                bikes[i] -= take
            reb_taken[k] = take
        elif kind == REB_IN and i >= 0:
            bikes[i] += reb_taken.get(k, 0)
        elif kind == SNAP:
            snaps[i] = bikes

    return SimResult(pd.DatetimeIndex(times), snaps, hours, dep, lost, od)
