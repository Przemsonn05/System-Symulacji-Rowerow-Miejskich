"""Kalibracja (Optuna) i walidacja symulacji (src/simulation, Osoba 3) wzgledem rzeczywistosci.

Kazda doba lokalna startuje ze stanu zaobserwowanego o polnocy, wiec blad nie kumuluje sie przez caly
tydzien; przewozy operatora sa odtwarzane z danych (scenariusz "operator").
"""

import datetime as dt
from dataclasses import dataclass

import numpy as np
import optuna
import pandas as pd
from joblib import Parallel, delayed

from ..data.config import ROOT, TZ
from ..simulation.engine import Simulation, SimulationParams
from ..simulation.network import build_network
from .data import load
from .od import count_matrix

# Parametry klienta kalibrowane Optuna (nazwy jak w SimulationParams).
SPACE = {"empty_retry_probability": (0.0, 1.0), "max_walk_km": (0.1, 1.5), "full_redirect_probability": (0.0, 1.0)}
DEFAULT = {"empty_retry_probability": 0.65, "max_walk_km": 0.6, "full_redirect_probability": 0.0}
# Operator ma jednoczesnie w drodze zwykle ok. 10 grup rowerow (max 13), wiec tyle ciezarowek
# wystarcza, zeby odtworzyc jego przewozy bez sztucznych opoznien.
OPERATOR_TRUCKS = 10
# Rownolegle procesy symulacji: nie wszystkie rdzenie, zeby komputer zostal uzywalny i starczylo pamieci.
N_JOBS = 8


@dataclass
class Observed:
    bikes: pd.DataFrame       # [czas x stacja] liczba rowerow (bez skokow is_spike)
    departures: pd.DataFrame  # [godzina UTC x stacja] wypozyczenia uzytkownikow
    ctx: pd.DataFrame
    rebalancing: pd.DataFrame


def load_observed(station_ids, ctx):
    o = load("observed_timeseries")
    o = o[~o["is_spike"] & o["station_id"].isin(station_ids)]
    bikes = o.pivot_table(index="time", columns="station_id", values="bikes", aggfunc="last")
    bikes = bikes.reindex(columns=station_ids).ffill().bfill()
    h = load("station_hourly")
    dep = h.pivot_table(index="hour", columns="station_id", values="departures", aggfunc="sum")
    return Observed(bikes, dep.reindex(columns=station_ids).fillna(0), ctx, load("rebalancing_observed"))


class HourlyRates:
    """Popyt dla silnika symulacji: lambda policzona z gory dla kazdej godziny doby."""

    def __init__(self, hours, lam):
        self.table = dict(zip(hours, lam))

    def rates(self, stations, context):
        return self.table[context["time"]]


@dataclass
class Day:
    start: pd.Timestamp
    minutes: float
    times: pd.DatetimeIndex  # chwile pomiarow, w ktorych porownujemy stan stacji
    hours: pd.DatetimeIndex
    lam: np.ndarray          # [godziny x stacje]
    init: np.ndarray
    ctx: pd.DataFrame
    rebalancing: pd.DataFrame


class Setup:
    """Wszystko, co wspolne dla przebiegow: stacje, siec drog, modele zachowan i dane dni."""

    def __init__(self, demand, od, duration, stations, obs):
        self.ids = od.station_ids
        st = stations.set_index("station_id").reindex(self.ids).reset_index()
        self.stations = st[["station_id", "name", "lat", "lon", "capacity"]].assign(initial_bikes=0)
        self.network = build_network(self.stations, ROOT / "data/static/station_network_distance.parquet",
                                     ROOT / "data/static/osm/graph_drive.graphml")
        self.demand, self.od, self.duration, self.obs = demand, od, duration, obs
        self._days = {}

    def day(self, day):
        if day not in self._days:
            self._days[day] = self._prepare(day)
        return self._days[day]

    def _prepare(self, day):
        b = self.obs.bikes
        start, end = (pd.Timestamp(dt.datetime.combine(d, dt.time()), tz=TZ).tz_convert("UTC")
                      for d in (day, day + dt.timedelta(days=1)))
        times = b.index[(b.index > start) & (b.index < end)]
        if len(times) < 12:
            return None
        end = min(end, times[-1] + pd.Timedelta(minutes=1))
        ctx = self.obs.ctx[(self.obs.ctx["time"] >= start) & (self.obs.ctx["time"] < end)]
        reb = self.obs.rebalancing
        reb = reb[(reb["t_departure"] >= start) & (reb["t_departure"] < end)
                  & reb["from_station"].isin(self.ids) & reb["to_station"].isin(self.ids)]
        return Day(start, (end - start).total_seconds() / 60, times, pd.DatetimeIndex(ctx["time"]),
                   self.demand.rate(self.ids, ctx), b.reindex([start], method="nearest").to_numpy()[0].astype(int),
                   ctx, reb)


def run_day(setup_parts, d, agent, seed):
    """Jedna symulowana doba w silniku Osoby 3; zwraca tablice do porownania z rzeczywistoscia."""
    ids, stations, network, od, duration, alpha = setup_parts
    rng = np.random.default_rng([seed, 1])
    # mnoznik gamma o wariancji alpha: zachowuje nadmierny rozrzut popytu z regresji NB
    lam = d.lam * rng.gamma(1.0 / alpha, alpha, size=d.lam.shape)
    params = SimulationParams(
        stations=stations.assign(initial_bikes=d.init), network=network, demand_model=HourlyRates(d.hours, lam),
        od_matrix=od, context_hourly=d.ctx, rebalancing_observed=d.rebalancing, duration_min=d.minutes,
        start_time=d.start, n_trucks=OPERATOR_TRUCKS, ride_time_model=duration, ride_sigma=duration.sigma,
        audit_every_event=False, **agent)
    res = Simulation(params, "operator", seed).run()
    bikes = res.station_timeseries.pivot_table(index="time", columns="station_id", values="bikes", aggfunc="last")
    bikes = bikes.reindex(columns=ids).reindex(d.times, method="nearest", tolerance=pd.Timedelta(minutes=3)).ffill()
    ev = res.events
    idx = {sid: k for k, sid in enumerate(ids)}

    def per_hour(kind):
        e = ev[ev["event"] == kind]
        out = np.zeros((len(d.hours), len(ids)), dtype=np.int32)
        h = d.hours.get_indexer(pd.to_datetime(e["time"]).dt.floor("h"))
        np.add.at(out, (h, e["station_id"].map(idx).to_numpy()), 1)
        return out

    user = res.trips[res.trips["type"] == "user"]
    od_counts = np.zeros((len(ids), len(ids)), dtype=np.int32)
    np.add.at(od_counts, (user["from_station"].map(idx).to_numpy(), user["to_station"].map(idx).to_numpy()), 1)
    return bikes.to_numpy(np.int16), per_hour("rental"), per_hour("lost_demand"), od_counts


def simulate(setup, agent, days, n_reps, seed0=0, n_jobs=N_JOBS):
    """Symulacja dzien po dniu (n_reps replikacji, rownolegle). Zwraca tablice symulacji i rzeczywistosci:
    occ_* [replikacje x chwile x stacje], dep_* [replikacje x godziny x stacje], lost, od."""
    ds = [setup.day(day) for day in days]
    ds = [d for d in ds if d is not None]
    parts = (setup.ids, setup.stations, setup.network, setup.od, setup.duration, setup.demand.alpha)
    jobs = [(k, r) for k in range(len(ds)) for r in range(n_reps)]
    out = Parallel(n_jobs=n_jobs)(delayed(run_day)(parts, ds[k], agent, seed0 + 1000 * k + r) for k, r in jobs)
    res = {kr: o for kr, o in zip(jobs, out)}

    def cat(i):
        return np.concatenate([np.stack([res[k, r][i] for r in range(n_reps)]) for k in range(len(ds))], axis=1)

    times = ds[0].times.append([d.times for d in ds[1:]])
    hours = ds[0].hours.append([d.hours for d in ds[1:]])
    return {
        "times": times, "hours": hours,
        "occ_sim": cat(0), "dep_sim": cat(1), "lost": cat(2),
        "od_sim": sum(o[3] for o in out) / n_reps,
        "occ_obs": setup.obs.bikes.loc[times].to_numpy(),
        "dep_obs": setup.obs.departures.reindex(hours).fillna(0).to_numpy(),
    }


def metrics(s):
    err = s["occ_sim"].mean(axis=0) - s["occ_obs"]
    sys_sim, sys_obs = s["dep_sim"].sum(axis=2).mean(axis=0), s["dep_obs"].sum(axis=1)
    empty_sim, empty_obs = (s["occ_sim"] == 0).mean(axis=(0, 1)), (s["occ_obs"] == 0).mean(axis=0)
    return {
        "rmse_occ": float(np.sqrt(np.mean(err ** 2))),
        "mae_occ": float(np.mean(np.abs(err))),
        "rmse_trips_per_h": float(np.sqrt(np.mean((sys_sim - sys_obs) ** 2))),
        "trips_per_h_sim": float(sys_sim.mean()),
        "trips_per_h_obs": float(sys_obs.mean()),
        "empty_share_sim": float(empty_sim.mean()),
        "empty_share_obs": float(empty_obs.mean()),
        "empty_share_corr_station": float(np.corrcoef(empty_sim, empty_obs)[0, 1]),
        "lost_per_day": float(s["lost"].sum(axis=(1, 2)).mean() * 24 / len(s["hours"])),
    }


def objective(m, s):
    """Funkcja celu kalibracji: znormalizowany RMSE zapelnienia + blad przejazdow na godzine."""
    return m["rmse_occ"] / s["occ_obs"].std() + 0.5 * m["rmse_trips_per_h"] / s["dep_obs"].sum(axis=1).mean()


def calibrate(setup, days, n_trials=60, n_reps=3, log=print):
    """Optuna (TPE). Wszystkie proby maja te same ziarna, wiec roznice wynikaja z parametrow."""
    def run(trial):
        agent = {k: trial.suggest_float(k, a, b) for k, (a, b) in SPACE.items()}
        s = simulate(setup, agent, days, n_reps)
        m = metrics(s)
        for k, v in m.items():
            trial.set_user_attr(k, v)
        return objective(m, s)

    optuna.logging.set_verbosity(optuna.logging.WARNING)
    study = optuna.create_study(direction="minimize", sampler=optuna.samplers.TPESampler(seed=42))
    study.enqueue_trial(DEFAULT)
    study.optimize(run, n_trials=n_trials, callbacks=[
        lambda st, t: log(f"  proba {t.number:3d}: cel {t.value:.4f} (najlepszy {st.best_value:.4f})") if t.number % 10 == 0 else None])
    return study.best_params, study


def _at(frame, index, shift):
    """Wartosci frame w chwilach index - shift (najblizszy pomiar w promieniu 5 min)."""
    src = frame.copy()
    src.index = src.index + shift
    return src.reindex(index, method="nearest", tolerance=pd.Timedelta(minutes=5)).to_numpy()


def _hist_mean(frame, index, calib_days, weekend_days):
    """Srednia z dni kalibracyjnych dla stacji x godzina lokalna x (roboczy/weekend)."""
    def key(ix):
        loc = ix.tz_convert(TZ)
        return pd.MultiIndex.from_arrays([loc.hour, pd.Index(loc.date).isin(weekend_days)]), pd.Index(loc.date)
    k_src, d_src = key(frame.index)
    cal = d_src.isin(calib_days)
    return frame[cal].groupby(k_src[cal]).mean().reindex(key(index)[0]).to_numpy()


def baselines(s, obs, calib_days):
    """Modele bazowe w tych samych chwilach co symulacja: RMSE zapelnienia i przejazdow na godzine."""
    weekend = set(obs.ctx.loc[obs.ctx["day_type"] != "workday", "local_date"])
    b, d = obs.bikes, obs.departures
    times, hours = s["times"], s["hours"]
    local = times.tz_convert(TZ)
    midnight = pd.DatetimeIndex(pd.Series(times).groupby(local.date).transform("min"))
    occ = {
        "persystencja: dzień wcześniej": _at(b, times, pd.Timedelta(days=1)),
        "średnia historyczna": _hist_mean(b, times, calib_days, weekend),
        "stan z północy przez całą dobę": b.reindex(midnight).to_numpy(),
    }
    dep = {
        "persystencja: dzień wcześniej": _at(d, hours, pd.Timedelta(days=1)),
        "średnia historyczna": _hist_mean(d, hours, calib_days, weekend),
    }
    rows = {}
    for name, pred in occ.items():
        e = (pred - s["occ_obs"])[~np.isnan(pred)]
        rows[name] = {"rmse_occ": np.sqrt(np.mean(e ** 2)), "mae_occ": np.mean(np.abs(e)), "rmse_trips_per_h": np.nan}
    for name, pred in dep.items():
        e = np.nansum(pred, axis=1) - s["dep_obs"].sum(axis=1)
        rows[name]["rmse_trips_per_h"] = np.sqrt(np.mean(e ** 2))
    return pd.DataFrame(rows).T


def od_cpc(s, trips, setup, stations):
    """Zgodnosc macierzy OD symulacji z rzeczywista (CPC: 1 = identyczne przeplywy)."""
    days = set(s["times"].tz_convert(TZ).date)
    real = count_matrix(trips[trips["local_date"].isin(days)], setup.ids, stations).sum(axis=0)
    sim = s["od_sim"] * real.sum() / s["od_sim"].sum()
    return float(np.minimum(sim, real).sum() / real.sum())
