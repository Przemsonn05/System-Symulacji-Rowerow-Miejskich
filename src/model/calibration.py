"""Kalibracja (Optuna) i walidacja symulacji wzgledem rzeczywistosci.

Kazda doba lokalna startuje ze stanu zaobserwowanego o polnocy (pierwszy pomiar po 00:00), wiec blad
nie kumuluje sie przez caly tydzien; relokacje operatora sa odtwarzane z danych.
"""

import datetime as dt
from dataclasses import dataclass

import numpy as np
import optuna
import pandas as pd

from ..data.config import TZ
from .data import load
from .od import count_matrix
from .simulation import AgentParams, run_simulation

SPACE = {"p_walk": (0.0, 1.0), "radius_m": (100.0, 800.0), "overflow_k": (0.0, 5.0)}


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


def simulate(models, params, days, obs, n_reps, seed0=0):
    """Symulacja dzien po dniu (n_reps replikacji). Zwraca tablice symulacji i rzeczywistosci:
    occ_* [replikacje x chwile x stacje], dep_* [replikacje x godziny x stacje], lost, od."""
    parts = []
    for d_i, day in enumerate(days):
        start, end = (pd.Timestamp(dt.datetime.combine(d, dt.time()), tz=TZ).tz_convert("UTC")
                      for d in (day, day + dt.timedelta(days=1)))
        times = obs.bikes.index[(obs.bikes.index >= start) & (obs.bikes.index < end)]
        if len(times) < 12:
            continue
        start, end = times[0], min(end, times[-1] + pd.Timedelta(minutes=1))
        init = obs.bikes.loc[start].to_numpy()
        runs = [run_simulation(models, params, start, end, init, obs.ctx, obs.rebalancing, times[1:],
                               seed=seed0 + 1000 * d_i + r) for r in range(n_reps)]
        parts.append(runs)
    times = parts[0][0].times.append([p[0].times for p in parts[1:]])
    hours = parts[0][0].hours.append([p[0].hours for p in parts[1:]])
    return {
        "times": times, "hours": hours,
        "occ_sim": np.concatenate([np.stack([r.bikes for r in p]) for p in parts], axis=1),
        "dep_sim": np.concatenate([np.stack([r.departures for r in p]) for p in parts], axis=1),
        "lost": np.concatenate([np.stack([r.lost for r in p]) for p in parts], axis=1),
        "od_sim": sum(r.od for p in parts for r in p) / n_reps,
        "occ_obs": obs.bikes.loc[times].to_numpy(),
        "dep_obs": obs.departures.reindex(hours).fillna(0).to_numpy(),
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


def calibrate(models, days, obs, n_trials=60, n_reps=3, log=print):
    """Optuna (TPE). Wszystkie proby maja te same ziarna, wiec roznice wynikaja z parametrow."""
    def run(trial):
        p = AgentParams(**{k: trial.suggest_float(k, a, b) for k, (a, b) in SPACE.items()})
        s = simulate(models, p, days, obs, n_reps)
        m = metrics(s)
        for k, v in m.items():
            trial.set_user_attr(k, v)
        return objective(m, s)

    optuna.logging.set_verbosity(optuna.logging.WARNING)
    study = optuna.create_study(direction="minimize", sampler=optuna.samplers.TPESampler(seed=42))
    study.enqueue_trial(AgentParams().as_dict())
    study.optimize(run, n_trials=n_trials, callbacks=[
        lambda st, t: log(f"  proba {t.number:3d}: cel {t.value:.4f} (najlepszy {st.best_value:.4f})") if t.number % 10 == 0 else None])
    return AgentParams(**study.best_params), study


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


def od_cpc(s, trips, models, stations):
    """Zgodnosc macierzy OD symulacji z rzeczywista (CPC: 1 = identyczne przeplywy)."""
    days = set(s["times"].tz_convert(TZ).date)
    real = count_matrix(trips[trips["local_date"].isin(days)], models.station_ids, stations).sum(axis=0)
    sim = s["od_sim"] * real.sum() / s["od_sim"].sum()
    return float(np.minimum(sim, real).sum() / real.sum())
