"""Caly lancuch jednym poleceniem: modele -> kalibracja -> walidacja -> hipotezy.

  python -m src.model.pipeline                    # domyslny podzial: kalibracja 23-29.10, walidacja 30.10-4.11
  python -m src.model.pipeline --build            # najpierw przebuduj processed/ (nowe dane)
  python -m src.model.pipeline --quick            # szybki test (malo prob i replikacji)
  python -m src.model.pipeline --calib 2026-10-23 2026-10-29 --valid 2026-10-30 2026-11-04

Wynik (processed/model/):
  demand_model.pkl, od_model.pkl, duration_model.pkl   modele dopasowane na wszystkich dniach (dla Osoby 3)
  sim_params.json                                      skalibrowane parametry klienta (nazwy jak w SimulationParams)
  results.pkl                                          wszystko do notebooka notebooks/modele_walidacja.ipynb
"""

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import time

# Limit watkow obliczen numerycznych (ustawiany przed importem numpy), zeby pipeline nie zajmowal
# calego komputera; mozna nadpisac zmienna srodowiskowa.
for _var in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_var, "4")

import numpy as np  # noqa: E402

from . import hypotheses
from .calibration import OPERATOR_TRUCKS, Setup, baselines, calibrate, load_observed, metrics, od_cpc, simulate
from .data import CALIB, OUT, VALID, context_filled, days, load, save, sim_station_ids, user_trips
from .demand import build_panel, fit_demand
from .duration import DurationModel
from .od import OdModel

T0 = time.time()


def log(msg):
    print(f"[{time.time() - T0:6.0f} s] {msg}", flush=True)


def fit_models(fit_days, trips, stations, ids):
    t = trips[trips["local_date"].isin(set(fit_days))]
    return fit_demand(fit_days), OdModel().fit(t, ids, stations), DurationModel().fit(t)


def demand_check(model, check_days):
    """Prognoza popytu poza proba: rzeczywiste wypozyczenia vs prognoza w godzinach dostepnosci."""
    p = build_panel(check_days)
    mu = model.predict(p) * p["exposure"].to_numpy()
    sys_o = p.groupby("time")["departures"].sum()
    sys_p = p.assign(mu=mu).groupby("time")["mu"].sum()
    return {"suma_rzeczywista": float(sys_o.sum()), "suma_prognoza": float(sys_p.sum()),
            "korelacja_system_h": float(np.corrcoef(sys_o, sys_p)[0, 1])}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", action="store_true", help="najpierw python -m src.data.build")
    ap.add_argument("--quick", action="store_true", help="szybki test lancucha")
    ap.add_argument("--calib", nargs=2, type=dt.date.fromisoformat, default=CALIB)
    ap.add_argument("--valid", nargs=2, type=dt.date.fromisoformat, default=VALID)
    ap.add_argument("--trials", type=int, default=60)
    ap.add_argument("--reps", type=int, default=3, help="replikacje na probe kalibracji")
    ap.add_argument("--valid-reps", type=int, default=20)
    a = ap.parse_args()
    if a.quick:
        a.trials, a.reps, a.valid_reps = 6, 1, 4
    if a.build:
        log("Przebudowa processed/...")
        subprocess.run([sys.executable, "-m", "src.data.build"], check=True)

    calib_days, valid_days = days(*a.calib), days(*a.valid)
    all_days = calib_days + valid_days
    stations = load("stations")
    ids = sim_station_ids(stations)
    ctx = context_filled()
    trips = user_trips()
    R = {"calib_days": calib_days, "valid_days": valid_days, "quick": a.quick,
         "weather_imputed": ctx.loc[ctx["weather_imputed"], "time"].tolist()}

    log(f"1/4 Modele na dniach kalibracyjnych {calib_days[0]} – {calib_days[-1]}...")
    dm, om, du = fit_models(calib_days, trips, stations, ids)
    R["demand"] = {"alpha": dm.alpha, "n_stations": len(dm.known), "check": demand_check(dm, valid_days)}
    R["od"] = {"beta": om.beta, "delta": om.delta, "n_trips": om.n_trips,
               "eval": om.evaluate(trips[trips["local_date"].isin(set(valid_days))], stations)}
    R["duration"] = {"params": du.params(), "check": du.check}
    log(f"   popyt: alpha={dm.alpha:.3f}; OD: beta={om.beta:.3f}/km; czas jazdy sigma={du.sigma:.3f}")

    log("   siec drog i dane dni dla symulacji (src/simulation)...")
    setup = Setup(dm, om, du, stations, load_observed(ids, ctx))
    log(f"2/4 Kalibracja: {a.trials} prob x {a.reps} replikacje x {len(calib_days)} dni...")
    best, study = calibrate(setup, calib_days, n_trials=a.trials, n_reps=a.reps, log=log)
    R["calibration"] = {"params": best, "trials": study.trials_dataframe(), "n_reps": a.reps}
    log(f"   najlepsze: {json.dumps({k: round(v, 3) for k, v in best.items()})}")

    log(f"3/4 Walidacja na {valid_days[0]} – {valid_days[-1]} ({a.valid_reps} replikacji)...")
    s = simulate(setup, best, valid_days, n_reps=a.valid_reps, seed0=10_000)
    R["validation"] = {"metrics": metrics(s) | {"od_cpc": od_cpc(s, trips, setup, stations)},
                       "baselines": baselines(s, setup.obs, calib_days), "station_ids": ids,
                       "sim": s | {"occ_sim": s["occ_sim"].astype(np.int16)}}
    log(f"   RMSE zapelnienia {R['validation']['metrics']['rmse_occ']:.2f} "
        f"(bazowe: {R['validation']['baselines']['rmse_occ'].min():.2f})")

    log("4/4 Hipotezy H1, H4, H5a (wszystkie dni)...")
    R["hypotheses"] = hypotheses.run(all_days, log=log)

    log("Modele koncowe na wszystkich dniach...")
    dmf, omf, duf = fit_models(all_days, trips, stations, ids)
    save(dmf, "demand_model.pkl")
    save(omf, "od_model.pkl")
    save(duf, "duration_model.pkl")
    (OUT / "sim_params.json").write_text(json.dumps({
        "agent": best, "ride_sigma": duf.sigma, "operator_trucks_in_validation": OPERATOR_TRUCKS,
        "calibration_days": [str(d) for d in calib_days],
        "fit_days": [str(d) for d in all_days]}, indent=2))
    save(R, "results.pkl")
    log(f"Gotowe: {OUT}; raport: notebooks/modele_walidacja.ipynb")


if __name__ == "__main__":
    main()
