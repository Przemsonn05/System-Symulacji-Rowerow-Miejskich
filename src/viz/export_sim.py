"""Eksport wyniku symulacji DES do wizualizacji 3D (ten sam format dnia co dane rzeczywiste + agenci).

    python -m src.viz.export_sim results/sim/threshold_2/seed_1000 results/sim/none_1/seed_1000 ...
    python -m src.viz.export_sim --runs results/h3/runs --seed 1000      # wszystkie strategie dla ziarna 1000

Najpierw python -m src.viz.export (dane rzeczywiste: stations.json, dni, pogoda). Kazde wywolanie zastepuje
liste symulacji w index.json ("sims"), wiec podaj od razu wszystkie przebiegi, ktore maja byc w wizualizacji.

Na przebieg powstaje sim_<strategia>_<ciezarowki>_s<ziarno>_<data>.json:
  states, kpi, trips, trucks       jak w day_*.json (stacje w kolejnosci stations.json)
  lost                             prawdziwy utracony popyt z symulacji (zdarzenia lost_demand), nie szacunek
  agents                           klienci przy pustej stacji (rezygnacja, przejscie do sasiedniej stacji),
                                   zadania dyspozytora (ktora ciezarowka jedzie skad dokad), sygnaly stacji
  cascades                         fale pustek (src.metrics, siatka 5 min - jak dla danych)
  hours, traffic, eventList        z dnia rzeczywistego o tej samej dacie (ten sam kontekst co w symulacji)

Obsluguje zdarzenia obecnego silnika (user_arrival, walk_to_alternative, lost_demand, rental, return,
truck_departure, truck_arrival, truck_load, truck_unload) i - jesli sie pojawia - nowe zdarzenia agentow
z kontraktu (user_wait_start / user_wait_end / user_leave / user_walk, task_announced / task_awarded,
signal_on / signal_off, kolumna pressure w station_timeseries, user_type w zdarzeniach).
"""

import argparse
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from src.data.config import TZ
from .export import DEFAULT_OUT, SLOT_SEC, STEP_SEC, WEEKDAYS_PL, Router, log, to_xz, write_json

USER_TYPES = {"": 0, "inny": 0, "commuter": 1, "dojezdzajacy": 1, "student": 2, "leisure": 3, "rekreacyjny": 3,
              "ebike": 4, "e-rowerzysta": 4}
STRATEGY_PL = {"none": "bez relokacji", "operator": "operator (odtworzenie)", "threshold": "progowa",
               "night": "nocna", "predictive": "predykcyjna", "operator_rule": "reguła operatora",
               "auction": "aukcja / dyspozytor"}


def _read(run, name):
    p = Path(run) / f"{name}.parquet"
    return pd.read_parquet(p) if p.exists() else None


def _sec(times, start):
    return np.round((pd.to_datetime(times, utc=True) - start).dt.total_seconds()).astype(int).to_numpy()


def load_viz_stations(out):
    st = json.loads((Path(out) / "stations.json").read_text(encoding="utf-8"))["stations"]
    return [s["id"] for s in st]


def run_key(kpis, date):
    return f"{kpis.get('scenario', 'sim')}_{kpis.get('n_trucks', 0)}_s{kpis.get('seed', 0)}_{date}"


def cascades_of(run_dir, order):
    """Fale pustek z siatki 5 min (src.metrics) -> plaskie tablice dla JsonUtility."""
    from src.metrics.emergence import cascades
    from src.metrics.io import load_run

    try:
        run = load_run(run_dir)
    except Exception as e:  # brak tabel - bez fal
        log(f"  fale pustek: pominiete ({e})")
        return {"start": [], "len": [], "st": [], "t": []}
    res = cascades(run)
    sidx = {s: i for i, s in enumerate(order)}
    start0 = run.bikes.index[0].tz_convert(TZ).normalize()
    return flat_cascades(res["members"], sidx, start0)


def flat_cascades(members, sidx, day_start_local, min_size=3):
    out = {"start": [], "len": [], "st": [], "t": []}
    for m in members:
        ids = m.get("station_ids", [])
        if len(ids) < min_size:
            continue
        day0 = pd.Timestamp(m["date"]).tz_localize(TZ)
        base = int((day0 - day_start_local).total_seconds())
        pts = [(sidx[s], int(base + mi * 60)) for s, mi in zip(ids, m["minutes"]) if s in sidx]
        if len(pts) < min_size:
            continue
        out["start"].append(len(out["st"]))
        out["len"].append(len(pts))
        out["st"].extend(p[0] for p in pts)
        out["t"].extend(p[1] for p in pts)
    return out


def truck_legs(ev, start, sidx):
    """Odcinki jazdy ciezarowek: truck_departure -> truck_arrival tej samej ciezarowki."""
    legs = []
    tr = ev[ev["event"].isin(["truck_departure", "truck_arrival"])].sort_values(["truck_id", "minute"], kind="stable")
    for tid, g in tr.groupby("truck_id"):
        pending = None
        for r in g.itertuples():
            if r.event == "truck_departure":
                pending = r
            elif pending is not None:
                legs.append({"truck": int(tid), "dep": pending.minute, "arr": r.minute,
                             "from": pending.station_id, "to": r.station_id, "n": int(getattr(pending, "load", 0) or 0)})
                pending = None
    out = pd.DataFrame(legs, columns=["truck", "dep", "arr", "from", "to", "n"])
    out = out[out["from"].isin(sidx) & out["to"].isin(sidx)].sort_values("dep", kind="stable")
    return out


def dispatcher_tasks(ev, sidx):
    """Zadania: przydzial (wyjazd po rowery) -> rozladunek. Z kolejnosci zdarzen kazdej ciezarowki."""
    tasks = []
    if "task_awarded" in set(ev["event"]):
        aw = ev[ev["event"] == "task_awarded"]
        for r in aw.itertuples():
            tasks.append({"t0": r.minute, "t1": r.minute + 30, "truck": int(r.truck_id),
                          "pick": r.station_id, "drop": getattr(r, "to_station", r.station_id), "n": 0})
        return tasks
    t = ev[ev["event"].isin(["truck_departure", "truck_arrival", "truck_load", "truck_unload"])]
    for tid, g in t.sort_values(["truck_id", "minute"], kind="stable").groupby("truck_id"):
        cur = None
        for r in g.itertuples():
            if r.event == "truck_departure" and (getattr(r, "load", 0) or 0) == 0:
                if cur is not None:
                    tasks.append(cur)
                cur = {"t0": r.minute, "t1": r.minute, "truck": int(tid), "pick": r.to_station, "drop": None, "n": 0}
            elif cur is None:
                continue
            elif r.event == "truck_load":
                cur["n"] += 1
            elif r.event == "truck_departure":
                cur["drop"] = r.to_station
            elif r.event in ("truck_unload", "truck_arrival"):
                cur["t1"] = r.minute
        if cur is not None:
            tasks.append(cur)
    return [x for x in tasks if x["drop"] is not None and x["pick"] in sidx and x["drop"] in sidx]


def agents_block(ev, start_min_to_sec, sidx, net=None, walk_kmh=4.5):
    """Agenci widoczni w 3D. Czasy w sekundach od lokalnej polnocy."""
    sec = start_min_to_sec
    a = {"lostT": [], "lostSt": [], "lostType": [],
         "walkT": [], "walkEnd": [], "walkFrom": [], "walkTo": [], "walkType": [],
         "waitT": [], "waitEnd": [], "waitSt": [], "waitType": [],
         "taskT0": [], "taskT1": [], "taskTruck": [], "taskPick": [], "taskDrop": [], "taskN": [],
         "sigT": [], "sigSt": [], "sigOn": [],
         "arrT": [], "arrSt": []}
    if ev is None or ev.empty:
        return a
    utype = (lambda r: USER_TYPES.get(str(getattr(r, "user_type", "") or ""), 0)) if "user_type" in ev else (lambda r: 0)
    by_req = {}
    for r in ev[ev["request_id"].notna()].itertuples():
        by_req.setdefault(r.request_id, []).append(r)
    for r in ev[ev["event"] == "lost_demand"].itertuples():
        if r.station_id in sidx:
            a["lostT"].append(sec(r.minute)); a["lostSt"].append(sidx[r.station_id]); a["lostType"].append(utype(r))
    for kind in ("walk_to_alternative", "user_walk"):
        for r in ev[ev["event"] == kind].itertuples():
            to = getattr(r, "to_station", None)
            if r.station_id not in sidx or to not in sidx:
                continue
            nxt = [x for x in by_req.get(r.request_id, []) if x.minute > r.minute]
            if nxt:
                end = nxt[0].minute
            elif net is not None:
                end = r.minute + net.get((r.station_id, to), 0.4) * 60 / walk_kmh
            else:
                end = r.minute + 5
            a["walkT"].append(sec(r.minute)); a["walkEnd"].append(sec(end))
            a["walkFrom"].append(sidx[r.station_id]); a["walkTo"].append(sidx[to]); a["walkType"].append(utype(r))
    # przyjscia na pusta stacje (do pokazania czekajacych przed decyzja)
    starts = ev[ev["event"] == "user_wait_start"]
    if len(starts):
        ends = {r.request_id: r.minute for r in ev[ev["event"].isin(["user_wait_end", "user_leave"])].itertuples()}
        for r in starts.itertuples():
            if r.station_id in sidx:
                a["waitT"].append(sec(r.minute)); a["waitEnd"].append(sec(ends.get(r.request_id, r.minute + 5)))
                a["waitSt"].append(sidx[r.station_id]); a["waitType"].append(utype(r))
    for kind, on in (("signal_on", 1), ("signal_off", 0)):
        for r in ev[ev["event"] == kind].itertuples():
            if r.station_id in sidx:
                a["sigT"].append(sec(r.minute)); a["sigSt"].append(sidx[r.station_id]); a["sigOn"].append(on)
    order = np.argsort(a["sigT"], kind="stable")
    for k in ("sigT", "sigSt", "sigOn"):
        a[k] = [a[k][i] for i in order]
    for t in dispatcher_tasks(ev, sidx):
        a["taskT0"].append(sec(t["t0"])); a["taskT1"].append(sec(t["t1"])); a["taskTruck"].append(t["truck"])
        a["taskPick"].append(sidx[t["pick"]]); a["taskDrop"].append(sidx[t["drop"]]); a["taskN"].append(t["n"])
    return a


def export_run(run_dir, out, order, real_days, bike_router_pairs, truck_router_pairs):
    run_dir = Path(run_dir)
    kpis = json.loads((run_dir / "kpis.json").read_text(encoding="utf-8"))
    ts = _read(run_dir, "station_timeseries")
    if ts is None:
        ts = _read(run_dir, "observed_timeseries")
    ev = _read(run_dir, "events")
    trips = _read(run_dir, "trips")
    fleet = _read(run_dir, "fleet_timeseries")
    st_sim = _read(run_dir, "stations")
    ts["station_id"] = ts["station_id"].astype(str)
    ts["time"] = pd.to_datetime(ts["time"], utc=True)
    t_first = ts["time"].min()
    start = t_first.tz_convert(TZ).normalize().tz_convert("UTC")
    date = start.tz_convert(TZ).date()
    end = ts["time"].max()
    length = int(round((end - start).total_seconds() / SLOT_SEC)) * SLOT_SEC
    n_slots = length // SLOT_SEC
    slots = pd.date_range(start, periods=n_slots, freq=f"{SLOT_SEC}s")
    sidx = {s: i for i, s in enumerate(order)}

    wide = ts.pivot_table(index="time", columns="station_id", values="bikes", aggfunc="last")
    wide = wide.reindex(columns=order).reindex(wide.index.union(slots)).sort_index().ffill(limit=2).reindex(slots)
    bikes = wide.fillna(-1).astype(int)
    pressure = None
    if "pressure" in ts:
        pw = ts.pivot_table(index="time", columns="station_id", values="pressure", aggfunc="last")
        pressure = pw.reindex(columns=order).reindex(slots).ffill(limit=2).fillna(0).clip(-1, 1)
    cap = st_sim.assign(station_id=st_sim["station_id"].astype(str)).set_index("station_id")["capacity"]
    capv = cap.reindex(order).fillna(10).to_numpy()
    bv = bikes.to_numpy()
    known = bv >= 0

    minute0 = (t_first - start).total_seconds() / 60  # minuta symulacji 0 = t_first
    to_sec = lambda m: int(round((float(m) + minute0) * 60))

    # przejazdy uzytkownikow
    u = trips[(trips["type"] == "user") & trips["from_station"].astype(str).isin(sidx)
              & trips["to_station"].astype(str).isin(sidx)].copy() if trips is not None else pd.DataFrame()
    u["from_station"] = u["from_station"].astype(str)
    u["to_station"] = u["to_station"].astype(str)
    u = u.sort_values("t_departure", kind="stable")
    bike_router_pairs.update(zip(u["from_station"], u["to_station"]))
    dep = _sec(u["t_departure"], start)
    arr = _sec(u["t_arrival"], start)
    bike_ids = {b: i + 1 for i, b in enumerate(pd.unique(u["bike"]))}
    utype = np.zeros(len(u), int)
    if ev is not None and "user_type" in ev and "request_id" in u:
        types = ev.dropna(subset=["request_id"]).drop_duplicates("request_id").set_index("request_id")["user_type"]
        utype = u["request_id"].map(types).fillna("").map(lambda v: USER_TYPES.get(str(v), 0)).to_numpy()

    legs = truck_legs(ev, start, sidx) if ev is not None and len(ev) else pd.DataFrame(columns=["truck", "dep", "arr", "from", "to", "n"])
    truck_router_pairs.update(zip(legs["from"], legs["to"]))

    lost_ev = ev[ev["event"] == "lost_demand"] if ev is not None else pd.DataFrame(columns=["minute", "station_id"])
    steps = math.ceil(length / STEP_SEC)
    lost = np.zeros((len(order), steps))
    for r in lost_ev.itertuples():
        if r.station_id in sidx:
            k = min(to_sec(r.minute) // STEP_SEC, steps - 1)
            lost[sidx[r.station_id], k] += 1
    lost = np.cumsum(lost, axis=1)

    real = real_days.get(date.isoformat(), {})
    fl = fleet.set_index(pd.to_datetime(fleet["time"], utc=True)) if fleet is not None else None
    in_use = fl["in_use"].reindex(slots, method="ffill").fillna(0).astype(int).tolist() if fl is not None else [0] * n_slots
    hours_sec = np.clip(dep // 3600, 0, 24)
    doc = {
        "date": date.isoformat(),
        "label": f"{WEEKDAYS_PL[date.weekday()]} {date.day:02d}.{date.month:02d}",
        "dayType": real.get("dayType", ""), "uniClasses": real.get("uniClasses", 0), "events": real.get("events", []),
        "startEpoch": int(start.timestamp()), "tzOffsetSec": int(start.tz_convert(TZ).utcoffset().total_seconds()),
        "lengthSec": length, "slotSec": SLOT_SEC, "coverage": 1.0,
        "source": "sim", "scenario": kpis.get("scenario", ""), "scenarioLabel": STRATEGY_PL.get(kpis.get("scenario", ""), kpis.get("scenario", "")),
        "nTrucks": int(kpis.get("n_trucks", 0)), "seed": int(kpis.get("seed", 0)),
        "simKpi": {k: float(kpis[k]) for k in ("requests", "rentals", "lost_demand", "lost_share", "truck_km",
                                               "relocated_bikes", "empty_station_share") if k in kpis},
        "routesFile": "sim_routes.json", "truckRoutesFile": "sim_truck_routes.json",
        "states": [{"b": bikes[s].tolist(), "e": [-1] * n_slots,
                    **({"p": np.round(pressure[s].to_numpy() * 100).astype(int).tolist()} if pressure is not None else {})}
                   for s in order],
        "kpi": {
            "empty": ((bv == 0) & known).sum(axis=1).astype(int).tolist(),
            "overfull": ((bv > capv) & known).sum(axis=1).astype(int).tolist(),
            "atStations": np.where(known, bv, 0).sum(axis=1).astype(int).tolist(),
            "inUse": in_use, "awayLong": [-1] * n_slots, "looseWarsaw": [-1] * n_slots,
            "fleetTarget": 0, "known": known.any(axis=1).astype(int).tolist(),
            "tripsPerHour": np.bincount(hours_sec, minlength=25)[: math.ceil(length / 3600)].astype(int).tolist(),
        },
        "eventList": real.get("eventList", []),
        "traffic": real.get("traffic", {"stepSec": STEP_SEC, "corridors": []}),
        "incidents": {"stepSec": STEP_SEC, "step": [], "x": [], "z": [], "cat": [], "mag": []},
        "loose": {"slot": [], "x": [], "z": [], "e": []},
        "lost": {"stepSec": STEP_SEC, "steps": steps, "cum": np.round(lost, 2).ravel().tolist(),
                 "rate": real.get("lost", {}).get("rate", []), "total": float(len(lost_ev)), "exact": 1},
        "trips": {
            "dep": dep.tolist(), "arr": arr.tolist(), "route": [],  # indeksy tras uzupelnia finalize()
            "ebike": [0] * len(u), "bike": [bike_ids[b] for b in u["bike"]],
            "km": u["network_km"].fillna(u["distance_km"]).fillna(0).round(1).tolist(),
            "fromSt": [sidx[s] for s in u["from_station"]], "toSt": [sidx[s] for s in u["to_station"]],
            "fx": [0] * len(u), "fz": [0] * len(u), "tx": [0] * len(u), "tz": [0] * len(u),
            "kind": utype.astype(int).tolist(),
            "_pairs": list(zip(u["from_station"], u["to_station"])),
        },
        "trucks": {
            "dep": [to_sec(m) for m in legs["dep"]], "arr": [max(to_sec(b), to_sec(a) + 60) for a, b in zip(legs["dep"], legs["arr"])],
            "route": [], "n": legs["n"].astype(int).tolist(),
            "fromSt": [sidx[s] for s in legs["from"]], "toSt": [sidx[s] for s in legs["to"]],
            "truck": legs["truck"].astype(int).tolist(),
            "_pairs": list(zip(legs["from"], legs["to"])),
        },
        "agents": agents_block(ev, to_sec, sidx),
        "cascades": cascades_of(run_dir, order),
        "hours": real.get("hours") or {"localHour": list(range(24)), "temp": [10.0] * 24, "precip": [0.0] * 24,
                                       "cloud": [50.0] * 24, "wind": [0.0] * 24, "apparentTemp": [10.0] * 24,
                                       "humidity": [70.0] * 24, "sunElevation": [0.0] * 24, "weatherCode": [0] * 24,
                                       "congestion": [0.0] * 24, "aqi": [0.0] * 24},
    }
    key = run_key(kpis, date.isoformat())
    return key, doc, kpis


def finalize(doc, bike_idx, truck_idx):
    doc["trips"]["route"] = [bike_idx.get(p, -1) for p in doc["trips"].pop("_pairs")]
    doc["trucks"]["route"] = [truck_idx.get(p, -1) for p in doc["trucks"].pop("_pairs")]


def export(run_dirs, out=DEFAULT_OUT):
    out = Path(out)
    if not (out / "index.json").exists() or not (out / "stations.json").exists():
        raise SystemExit("Najpierw python -m src.viz.export (dane rzeczywiste)")
    index = json.loads((out / "index.json").read_text(encoding="utf-8"))
    order = load_viz_stations(out)
    real_days = {}
    for d in index["days"]:
        p = out / d["file"]
        if p.exists():
            real_days[d["date"]] = json.loads(p.read_text(encoding="utf-8"))
    bike_pairs, truck_pairs, docs = set(), set(), []
    for rd in run_dirs:
        log(f"Przebieg {rd}")
        docs.append(export_run(rd, out, order, real_days, bike_pairs, truck_pairs))
    from src.data.config import PROCESSED

    st = pd.read_parquet(PROCESSED / "stations.parquet")
    st["station_id"] = st["station_id"].astype(str)
    st = st[st["station_id"].isin(order)]
    bike = Router("bike", st).routes(sorted(bike_pairs))
    truck = Router("drive", st).routes(sorted(truck_pairs))
    bkeys, tkeys = sorted(bike), sorted(truck)
    write_json(out / "sim_routes.json", {"routes": [{"p": bike[k]} for k in bkeys]})
    write_json(out / "sim_truck_routes.json", {"routes": [{"p": truck[k]} for k in tkeys]})
    bidx = {k: i for i, k in enumerate(bkeys)}
    tidx = {k: i for i, k in enumerate(tkeys)}
    for old in out.glob("sim_*_s*.json"):
        old.unlink()
    sims = []
    for key, doc, kpis in docs:
        finalize(doc, bidx, tidx)
        fname = f"sim_{key}.json"
        write_json(out / fname, doc)
        label = f"{doc['scenarioLabel']}" + (f", {doc['nTrucks']} ciężar." if doc["scenario"] != "none" else "")
        sims.append({"key": key, "date": doc["date"], "label": label, "file": fname, "scenario": doc["scenario"],
                     "trucks": doc["nTrucks"], "seed": doc["seed"], "trips": len(doc["trips"]["dep"]),
                     "lost": doc["lost"]["total"], "coverage": 1.0, "dayType": doc["dayType"]})
        log(f"  {fname}: {len(doc['trips']['dep'])} przejazdow, utracony popyt {doc['lost']['total']:.0f}, "
            f"{len(doc['agents']['lostT'])} rezygnacji, {len(doc['agents']['walkT'])} przejsc, "
            f"{len(doc['agents']['taskT0'])} zadan, {len(doc['cascades']['len'])} fal >= 3")
    index["sims"] = sims
    write_json(out / "index.json", index)
    return sims


def main():
    import sys

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("runs", nargs="*", help="katalogi przebiegow (z kpis.json i station_timeseries.parquet)")
    ap.add_argument("--runs-root", help="katalog runs/ z eksperymentu (strategia_flota/seed_N)")
    ap.add_argument("--seed", type=int, default=1000)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()
    dirs = [Path(r) for r in args.runs]
    if args.runs_root:
        dirs += sorted(Path(args.runs_root).glob(f"*/seed_{args.seed}"))
    if not dirs:
        ap.error("podaj katalogi przebiegow albo --runs-root")
    export(dirs, args.out)


if __name__ == "__main__":
    main()
