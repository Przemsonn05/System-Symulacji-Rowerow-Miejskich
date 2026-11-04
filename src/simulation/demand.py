from dataclasses import dataclass
import hashlib
import math
import pickle
from pathlib import Path

import numpy as np
import pandas as pd


def random_stream(seed, *key):
    digest = hashlib.sha256("/".join(map(str, key)).encode()).digest()
    words = np.frombuffer(digest[:16], dtype="<u4").tolist()
    return np.random.default_rng(np.random.SeedSequence([int(seed), *words]))


@dataclass
class HourlyDemand:
    rates_per_hour: np.ndarray

    def rates(self, stations, context):
        rates = np.asarray(self.rates_per_hour, dtype=float)
        if rates.shape != (len(stations),):
            raise ValueError("Demand model must return one rate per station")
        return rates


@dataclass
class ExampleDemand:
    base_rates: np.ndarray

    def rates(self, stations, context):
        hour = int(context.get("local_hour", 12))
        profile = 0.12 + 0.9 * np.exp(-((hour - 8) / 2) ** 2)
        profile += 1.35 * np.exp(-((hour - 17) / 3) ** 2)
        return np.asarray(self.base_rates) * profile


@dataclass
class EmpiricalDemand:
    rates_by_hour: np.ndarray

    def rates(self, stations, context):
        return self.rates_by_hour[:, int(context["local_hour"])]


def load_demand(path):
    with Path(path).open("rb") as handle:
        model = pickle.load(handle)
    if not hasattr(model, "rates"):
        raise TypeError("demand_model.pkl must implement rates(stations, context) in arrivals/hour")
    return model


def thinning(rate, upper_bound, horizon, rng):
    if not np.isfinite(upper_bound) or upper_bound < 0 or horizon < 0:
        raise ValueError("Invalid thinning bound or horizon")
    if upper_bound == 0:
        return
    time = 0.0
    while True:
        time += float(rng.exponential(60.0 / upper_bound))
        if time >= horizon:
            return
        intensity = float(rate(time))
        if not np.isfinite(intensity) or intensity < 0 or intensity > upper_bound * (1 + 1e-12):
            raise ValueError("Intensity outside thinning bound")
        if rng.random() < intensity / upper_bound:
            yield time


def context_at(start, minute, context):
    stamp = start + pd.Timedelta(minutes=float(minute))
    local = stamp.tz_convert("Europe/Warsaw")
    result = {"time": stamp.floor("h"), "local_hour": local.hour,
              "local_date": str(local.date()), "dow": local.dayofweek,
              "congestion": 0.0, "temperature_2m": 12.0, "precipitation": 0.0}
    if context is not None and not context.empty:
        key = stamp.floor("h")
        if key in context.index:
            result.update(context.loc[key].dropna().to_dict())
    return result


def next_hour_minute(start, minute):
    offset = (start - start.floor("h")).total_seconds() / 60
    return (math.floor((minute + offset) / 60 + 1e-10) + 1) * 60 - offset


def generate_requests(stations, network, params, demand, od, context, seed):
    ids = stations.station_id.tolist()
    n = len(ids)
    if od is None:
        weights = np.exp(-network.bike_km / 3.0)
        np.fill_diagonal(weights, 0.05)
        od = weights / weights.sum(axis=1, keepdims=True)
    od = np.asarray(od, dtype=float)
    if od.shape != (n, n) or not np.isfinite(od).all() or (od < 0).any() or (od.sum(axis=1) <= 0).any():
        raise ValueError("OD must be a finite nonnegative station-by-station matrix")
    od = od / od.sum(axis=1, keepdims=True)
    cumulative = od.cumsum(axis=1)
    cumulative[:, -1] = 1.0
    rows = []
    minute = 0.0
    counters = np.zeros(n, dtype=int)
    arrival_rngs = [random_stream(seed, "arrivals", sid) for sid in ids]
    while minute < params.duration_min:
        ctx = context_at(params.start_time, minute, context)
        span = min(params.duration_min - minute, next_hour_minute(params.start_time, minute) - minute)
        rates = np.asarray(demand.rates(stations.copy(), ctx), dtype=float)
        if rates.shape != (n,) or not np.isfinite(rates).all() or (rates < 0).any():
            raise ValueError("Demand rates must be finite, nonnegative and match stations")
        for i, rate in enumerate(rates):
            for offset in thinning(lambda t, r=rate: r, float(rate), span, arrival_rngs[i]):
                k = int(counters[i])
                rng = random_stream(seed, "customer", ids[i], k)
                destination = min(int(np.searchsorted(cumulative[i], rng.random())), n - 1)
                rows.append({"request_id": f"{ids[i]}:{k}", "minute": minute + offset,
                             "origin": i, "destination": destination,
                             "ride_factor": float(rng.lognormal(-params.ride_sigma ** 2 / 2, params.ride_sigma)),
                             "try_alternative": bool(rng.random() < params.empty_retry_probability),
                             "redirect_full": bool(rng.random() < params.full_redirect_probability)})
                counters[i] += 1
        minute += span
    columns = ["request_id", "minute", "origin", "destination", "ride_factor", "try_alternative", "redirect_full"]
    return pd.DataFrame(rows, columns=columns).sort_values(["minute", "request_id"]).reset_index(drop=True)
