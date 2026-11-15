"""Przykladowy przebieg symulacji zgodny z kontraktem (docs/kontrakty.md, sekcje 2 i 3).

Bierze prawdziwy przebieg silnika (dzis bez agentow) i dopisuje do niego **nowe** typy zdarzen agentow
oraz kolumne `pressure`, tak jak bedzie je zapisywal silnik agentowy Osoby 3:

    user_wait_start / user_wait_end / user_walk / user_leave  (z user_id, user_type, has_app)
    signal_on / signal_off                                   (sygnal stacji "brakuje rowerow")
    task_announced / bid / task_awarded                      (przetarg dyspozytora, Contract Net)

Wartosci nowych zdarzen sa umowne (losowane), plik sluzy do sprawdzenia formatu: czy silnik zapisuje
to samo, czy metryki (python -m src.metrics) i 3D (python -m src.viz.export_sim) go wczytuja.

    python tools/przyklad_przebiegu.py results/sim/operator_2/seed_1000 --out docs/przyklad_przebiegu
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.viz.export_sim import dispatcher_tasks  # noqa: E402

USER_TYPES = ["commuter", "student", "leisure", "ebike", None]
TYPE_P = [0.35, 0.2, 0.2, 0.15, 0.1]
COPY = ["stations", "trips", "fleet_timeseries", "context_hourly"]
EVENT_COLUMNS = ["time", "minute", "event", "station_id", "to_station", "request_id", "user_id", "user_type",
                 "has_app", "truck_id", "bike", "n_bikes", "load"]


def pressure(ts, low=0.2, high=0.8):
    """Sygnal stacji w [-1, 1]: -1 = pusta, 0 = zapelnienie miedzy progami, +1 = pelna (liniowo za progami)."""
    occ = (ts["bikes"] / ts["capacity"].where(ts["capacity"] > 0)).fillna(0.5)
    p = np.where(occ < low, -(low - occ) / low, np.where(occ > high, (occ - high) / (1 - high), 0.0))
    return np.clip(p, -1, 1).round(3)


def signals(ts, on=-0.5, off=-0.2):
    """signal_on, gdy cisnienie spada ponizej `on`; signal_off, gdy wraca powyzej `off` (histereza)."""
    rows = []
    for sid, g in ts.sort_values("time").groupby("station_id"):
        active = False
        for t, p in zip(g["time"], g["pressure"]):
            if not active and p <= on:
                rows.append((t, "signal_on", sid)); active = True
            elif active and p >= off:
                rows.append((t, "signal_off", sid)); active = False
    return pd.DataFrame(rows, columns=["time", "event", "station_id"])


def user_events(ev, rng):
    """Nowe zdarzenia klientow z obecnych lost_demand / walk_to_alternative (te zostaja dla zgodnosci)."""
    req = ev[ev["request_id"].notna()].drop_duplicates("request_id")[["request_id"]].copy()
    req["user_type"] = rng.choice(np.array(USER_TYPES, dtype=object), size=len(req), p=TYPE_P)
    req["has_app"] = rng.random(len(req)) < 0.5
    req["user_id"] = np.arange(len(req))
    commuters = req["user_type"] == "commuter"   # stali bywalcy: wspolne user_id dla czesci dojezdzajacych
    req.loc[commuters, "user_id"] = rng.integers(0, max(1, commuters.sum() // 3), commuters.sum()) + 10**6
    out = []
    for kind in ("lost_demand", "walk_to_alternative"):
        for r in ev[ev["event"] == kind].itertuples():
            wait = float(rng.uniform(1, 8))
            out.append(dict(minute=r.minute - wait, event="user_wait_start", station_id=r.station_id, request_id=r.request_id))
            out.append(dict(minute=r.minute, event="user_wait_end", station_id=r.station_id, request_id=r.request_id))
            if kind == "lost_demand":
                out.append(dict(minute=r.minute, event="user_leave", station_id=r.station_id, request_id=r.request_id))
            else:
                out.append(dict(minute=r.minute, event="user_walk", station_id=r.station_id, request_id=r.request_id,
                                to_station=r.to_station))
    return pd.DataFrame(out), req


def dispatcher_events(ev, n_trucks, rng):
    """Przetarg przed kazdym kursem (pusta jazda po rowery -> dowoz): ogloszenie, oferty aut, przydzial.

    task_awarded: station_id = skad zabrac rowery, to_station = dokad dowiezc, n_bikes = ile.
    """
    every = {s: 0 for s in pd.concat([ev["station_id"], ev["to_station"]]).dropna().unique()}
    out = []
    for task_id, t in enumerate(sorted(dispatcher_tasks(ev, every), key=lambda x: x["t0"])):
        t0 = t["t0"] - 0.5
        out.append(dict(minute=t0, event="task_announced", station_id=t["drop"], n_bikes=t["n"], task_id=task_id))
        for k in range(n_trucks):
            out.append(dict(minute=t0 + 0.1, event="bid", station_id=t["drop"], truck_id=k, task_id=task_id,
                            cost_min=round(float(rng.uniform(5, 40)), 1)))
        out.append(dict(minute=t["t0"], event="task_awarded", station_id=t["pick"], to_station=t["drop"],
                        truck_id=t["truck"], n_bikes=t["n"], task_id=task_id))
    return pd.DataFrame(out)


def build(run, out, hours=None, seed=0):
    run, out = Path(run), Path(out)
    rng = np.random.default_rng(seed)
    kpis = json.loads((run / "kpis.json").read_text(encoding="utf-8"))
    ts = pd.read_parquet(run / "station_timeseries.parquet")
    ev = pd.read_parquet(run / "events.parquet")
    t0 = ts["time"].min()
    if hours:
        ts = ts[ts["time"] < t0 + pd.Timedelta(minutes=int(hours * 60))]
        ev = ev[ev["minute"] < hours * 60]
    ev = ev[ev["event"] != "hour_change"].copy()
    ev["truck_id"] = ev["truck_id"].astype("Int64")

    ts = ts.copy()
    ts["pressure"] = pressure(ts)
    sig = signals(ts)
    sig["minute"] = (sig["time"] - t0).dt.total_seconds() / 60

    users, req = user_events(ev, rng)
    disp = dispatcher_events(ev, int(kpis.get("n_trucks", 2)), rng)
    # user_walk zastepuje walk_to_alternative (silnik agentowy zapisuje jedno albo drugie, nie oba);
    # lost_demand zostaje obok user_leave, bo z niego liczy sie licznik utraconych klientow
    ev = ev[ev["event"] != "walk_to_alternative"]
    allev = pd.concat([ev, users, sig.drop(columns="time"), disp], ignore_index=True)
    allev = allev.merge(req, on="request_id", how="left")
    allev["time"] = t0 + pd.to_timedelta(allev["minute"], unit="min")
    load = allev["event"].isin(["truck_load", "truck_unload"])
    allev.loc[load, "n_bikes"] = 1  # jeden wiersz = jeden rower
    for c in EVENT_COLUMNS:
        if c not in allev:
            allev[c] = None
    allev = allev[EVENT_COLUMNS + [c for c in ("task_id", "cost_min") if c in allev]]
    allev = allev.sort_values(["minute", "event"], kind="stable").reset_index(drop=True)
    allev["truck_id"] = allev["truck_id"].astype("Int64")
    for c in ("n_bikes", "task_id"):
        allev[c] = pd.to_numeric(allev[c]).astype("Int64")
    allev["user_id"] = pd.to_numeric(allev["user_id"]).astype("Int64")
    allev["has_app"] = allev["has_app"].astype("boolean")
    for c in ("station_id", "to_station", "request_id", "user_type", "bike"):
        allev[c] = allev[c].astype("string")

    out.mkdir(parents=True, exist_ok=True)  # nadpisuje pliki danych, README zostaje
    allev.to_parquet(out / "events.parquet", index=False)
    ts.to_parquet(out / "station_timeseries.parquet", index=False)
    end = ts["time"].max()
    for name in COPY:
        p = run / f"{name}.parquet"
        if not p.exists():
            continue
        df = pd.read_parquet(p)
        if hours and name == "trips":
            df = df[df["t_departure"] <= end]
        elif hours and "time" in df:
            df = df[df["time"] <= end]
        df.to_parquet(out / f"{name}.parquet", index=False)
    kpis = kpis | {"example": True, "source_run": str(run).replace("\\", "/"), "hours": hours}
    (out / "kpis.json").write_text(json.dumps(kpis, indent=2, ensure_ascii=False), encoding="utf-8")
    return allev, ts


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run", help="katalog przebiegu silnika (kpis.json, events.parquet, station_timeseries.parquet)")
    ap.add_argument("--out", default="docs/przyklad_przebiegu")
    ap.add_argument("--hours", type=float, default=12, help="ile pierwszych godzin doby zapisac (mniejszy plik)")
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    ev, ts = build(a.run, a.out, a.hours, a.seed)
    print(f"{a.out}: {len(ev)} zdarzen, {len(ts)} wierszy station_timeseries")
    print(ev["event"].value_counts().to_string())


if __name__ == "__main__":
    main()
