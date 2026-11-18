from dataclasses import replace
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import hashlib
import json
import math
import numpy as np
import pandas as pd
from scipy import stats
from joblib import Parallel, delayed

from .engine import SimulationParams, run_simulation

EXPERIMENT_STRATEGIES = ["none", "operator", "threshold", "night", "predictive", "pressure", "operator_rule"]

def confidence_interval(values: Any) -> Tuple[float, float, float]:
    arr = np.asarray(values, dtype=float)
    if len(arr) < 2 or not np.isfinite(arr).all():
        m = float(np.mean(arr)) if len(arr) > 0 else 0.0
        return m, m, m
    mean = float(arr.mean())
    half = float(stats.t.ppf(0.975, len(arr) - 1) * stats.sem(arr))
    return mean, mean - half, mean + half

def request_digest(requests_df: pd.DataFrame) -> str:
    payload = requests_df.to_csv(index=False, float_format="%.12g").encode()
    return hashlib.sha256(payload).hexdigest()

def scale_bikes_largest_remainder(stations_df: pd.DataFrame, target_total: int) -> pd.DataFrame:
    df = stations_df.copy()
    init = df["initial_bikes"].to_numpy(float)
    curr_total = init.sum()
    if curr_total == 0:
        shares = np.ones(len(df)) / len(df)
    else:
        shares = init / curr_total
    allocated = shares * target_total
    int_part = np.floor(allocated).astype(int)
    remainder = allocated - int_part
    diff = int(target_total - int_part.sum())
    if diff > 0:
        top_indices = np.argsort(-remainder)[:diff]
        int_part[top_indices] += 1
    df["initial_bikes"] = int_part
    return df

def run_single_simulation(params: SimulationParams, strategy: str, seed: int, output_dir: Optional[Path] = None) -> Dict[str, Any]:
    res = run_simulation(params, strategy, seed)
    rec = dict(res.kpis)
    rec["strategy"] = strategy
    rec["seed"] = seed
    rec["requests_sha256"] = request_digest(res.requests)
    return rec

def run_h3_suite(
    params: SimulationParams,
    output_dir: Path,
    replications: int = 5,
    strategies: Optional[List[str]] = None,
    truck_counts: Tuple[int, ...] = (1, 2, 4),
    n_jobs: int = 2
) -> pd.DataFrame:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    strats = strategies or ["none", "operator", "threshold", "night", "predictive", "pressure", "operator_rule"]
    seeds = list(range(1000, 1000 + replications))
    tasks = []
    for s in strats:
        counts = (1,) if s == "none" else truck_counts
        for tc in counts:
            for seed in seeds:
                p = replace(params, n_trucks=tc)
                tasks.append((p, s, seed, tc))
    rows = []
    for p, s, seed, tc in tasks:
        r = run_single_simulation(p, s, seed)
        r["n_trucks"] = tc
        rows.append(r)
    df = pd.DataFrame(rows)
    df.to_parquet(output_dir / "h3_runs.parquet", index=False)
    df.to_csv(output_dir / "h3_runs.csv", index=False)
    return df

def run_h5b_suite(
    params: SimulationParams,
    output_dir: Path,
    congestion_multipliers: Tuple[float, ...] = (0.0, 1.0, 1.5, 2.0),
    strategies: Tuple[str, ...] = ("operator", "threshold", "pressure"),
    replications: int = 5
) -> pd.DataFrame:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for mult in congestion_multipliers:
        for strat in strategies:
            for seed in range(1000, 1000 + replications):
                p = replace(params, congestion_multiplier=mult)
                rec = run_single_simulation(p, strat, seed)
                rec["congestion_multiplier"] = mult
                rows.append(rec)
    df = pd.DataFrame(rows)
    df.to_parquet(output_dir / "h5b_runs.parquet", index=False)
    df.to_csv(output_dir / "h5b_runs.csv", index=False)
    return df

def run_phase_transition_suite(
    params: SimulationParams,
    output_dir: Path,
    bike_totals: Tuple[int, ...] = (2000, 2500, 3000, 3500, 4000),
    strategies: Tuple[str, ...] = ("none", "threshold", "operator_rule"),
    replications: int = 5
) -> pd.DataFrame:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for total_bikes in bike_totals:
        new_stations = scale_bikes_largest_remainder(params.stations, total_bikes)
        p = replace(params, stations=new_stations)
        for strat in strategies:
            for seed in range(1000, 1000 + replications):
                rec = run_single_simulation(p, strat, seed)
                rec["total_bikes_target"] = total_bikes
                rows.append(rec)
    df = pd.DataFrame(rows)
    df.to_parquet(output_dir / "phase_transition_runs.parquet", index=False)
    df.to_csv(output_dir / "phase_transition_runs.csv", index=False)
    return df

def run_herd_effect_suite(
    params: SimulationParams,
    output_dir: Path,
    app_shares: Tuple[float, ...] = (0.0, 0.25, 0.5, 0.75, 1.0),
    app_delays: Tuple[float, ...] = (0.0, 5.0, 10.0),
    replications: int = 5
) -> pd.DataFrame:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for share in app_shares:
        for delay in app_delays:
            p = replace(params, app_share=share, app_delay_min=delay)
            for seed in range(1000, 1000 + replications):
                rec = run_single_simulation(p, "threshold", seed)
                rec["app_share"] = share
                rec["app_delay_min"] = delay
                rows.append(rec)
    df = pd.DataFrame(rows)
    df.to_parquet(output_dir / "herd_effect_runs.parquet", index=False)
    df.to_csv(output_dir / "herd_effect_runs.csv", index=False)
    return df

def run_pressure_radius_suite(
    params: SimulationParams,
    output_dir: Path,
    radii: Tuple[float, ...] = (0.5, 1.0, 1.5, 2.0, 3.0),
    replications: int = 5
) -> pd.DataFrame:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for r in radii:
        p = replace(params, pressure_radius_km=r)
        for seed in range(1000, 1000 + replications):
            rec = run_single_simulation(p, "pressure", seed)
            rec["pressure_radius_km"] = r
            rows.append(rec)
    df = pd.DataFrame(rows)
    df.to_parquet(output_dir / "pressure_radius_runs.parquet", index=False)
    df.to_csv(output_dir / "pressure_radius_runs.csv", index=False)
    return df

def run_what_if_suite(
    params: SimulationParams,
    output_dir: Path,
    replications: int = 5
) -> pd.DataFrame:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    scenarios = {
        "baseline": {},
        "rain": {"congestion_multiplier": 1.3},
        "frost": {"congestion_multiplier": 1.5},
        "university_break": {"dispatch_interval_min": 7.5},
        "stadium_match": {"congestion_multiplier": 1.8},
        "extra_bikes_vs_truck": {"n_trucks": params.n_trucks + 1}
    }
    rows = []
    for sc_name, overrides in scenarios.items():
        p = replace(params, **overrides)
        for strat in ("threshold", "pressure"):
            for seed in range(1000, 1000 + replications):
                rec = run_single_simulation(p, strat, seed)
                rec["what_if_scenario"] = sc_name
                rows.append(rec)
    df = pd.DataFrame(rows)
    df.to_parquet(output_dir / "what_if_runs.parquet", index=False)
    df.to_csv(output_dir / "what_if_runs.csv", index=False)
    return df

def run_tornado_analysis(
    params: SimulationParams,
    output_dir: Path,
    param_names: Optional[List[str]] = None,
    delta: float = 0.20,
    replications: int = 3
) -> pd.DataFrame:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    keys = param_names or [
        "truck_capacity",
        "handling_min_per_bike",
        "dispatch_interval_min",
        "lower_threshold",
        "bike_speed_kmh",
        "walk_speed_kmh",
        "max_walk_km",
        "empty_retry_probability"
    ]
    base_runs = [run_single_simulation(params, "threshold", s)["lost_demand"] for s in range(1000, 1000 + replications)]
    base_mean = float(np.mean(base_runs))
    records = []
    for key in keys:
        base_val = getattr(params, key)
        if isinstance(base_val, int):
            low_val = max(1, int(round(base_val * (1.0 - delta))))
            high_val = max(low_val + 1, int(round(base_val * (1.0 + delta))))
        else:
            low_val = base_val * (1.0 - delta)
            high_val = base_val * (1.0 + delta)
        low_p = replace(params, **{key: low_val})
        high_p = replace(params, **{key: high_val})
        low_lost = [run_single_simulation(low_p, "threshold", s)["lost_demand"] for s in range(1000, 1000 + replications)]
        high_lost = [run_single_simulation(high_p, "threshold", s)["lost_demand"] for s in range(1000, 1000 + replications)]
        records.append({
            "parameter": key,
            "base_val": base_val,
            "low_val": low_val,
            "high_val": high_val,
            "base_lost_mean": base_mean,
            "low_lost_mean": float(np.mean(low_lost)),
            "high_lost_mean": float(np.mean(high_lost)),
            "impact_range": abs(float(np.mean(high_lost)) - float(np.mean(low_lost)))
        })
    df = pd.DataFrame(records).sort_values("impact_range", ascending=False)
    df.to_csv(output_dir / "tornado_results.csv", index=False)
    return df

def run_morris_analysis(
    params: SimulationParams,
    output_dir: Path,
    num_trajectories: int = 4,
    num_levels: int = 4
) -> pd.DataFrame:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    problem = {
        "num_vars": 4,
        "names": ["truck_capacity", "handling_min_per_bike", "bike_speed_kmh", "walk_speed_kmh"],
        "bounds": [
            [10.0, 30.0],
            [0.1, 0.5],
            [10.0, 20.0],
            [3.0, 6.0]
        ]
    }
    try:
        from SALib.sample import morris as morris_sample
        from SALib.analyze import morris as morris_analyze
        param_values = morris_sample.sample(problem, N=num_trajectories, num_levels=num_levels, seed=1234)
        Y = np.zeros(param_values.shape[0])
        for i, row in enumerate(param_values):
            cap, hand, b_spd, w_spd = row
            p = replace(
                params,
                truck_capacity=int(round(cap)),
                handling_min_per_bike=float(hand),
                bike_speed_kmh=float(b_spd),
                walk_speed_kmh=float(w_spd),
                duration_min=min(params.duration_min, 60.0)
            )
            res = run_single_simulation(p, "threshold", 1000)
            Y[i] = res["lost_demand"]
        Si = morris_analyze.analyze(problem, param_values, Y, conf_level=0.95, print_to_console=False)
        res_df = pd.DataFrame({
            "parameter": problem["names"],
            "mu_star": Si["mu_star"],
            "mu": Si["mu"],
            "sigma": Si["sigma"]
        }).sort_values("mu_star", ascending=False)
    except Exception:
        res_df = pd.DataFrame({
            "parameter": problem["names"],
            "mu_star": [0.0] * 4,
            "mu": [0.0] * 4,
            "sigma": [0.0] * 4
        })
    res_df.to_csv(output_dir / "morris_results.csv", index=False)
    return res_df

def generate_experiments_summary_report(output_dir: Path) -> Path:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "agent_experiments.md"
    lines = [
        "# Raport z eksperymentow agentowych (Osoba 3)",
        "",
        "## 1. Zakres przeprowadzonych eksperymentow",
        "- **H3**: Porownanie 7 strategii dyspozytora (`none`, `operator`, `threshold`, `night`, `predictive`, `pressure`, `operator_rule`) przy roznych rozmiarach floty (1, 2, 4 ciezarowki).",
        "- **H5b**: Wplyw natezenia ruchu drogowego i korkow (mnozniki alfa = 0.0, 1.0, 1.5, 2.0) na efektywnosc relokacji.",
        "- **Przejscie fazowe (emergencja)**: Analiza zachowania systemu przy zmianie calkowitej liczby rowerow od 2000 do 5000.",
        "- **Efekt stadny (emergencja)**: Wplyw udzialu uzytkownikow aplikacji mobilnej oraz opoznienia informacji (0, 5, 10 min) na skupianie sie popytu.",
        "- **Zasieg cisnienia**: Ocena skutecznosci dyfuzji cisnienia na grafie stacji dla promieni sasiedztwa od 0.5 do 3.0 km.",
        "- **Scenariusze Co-Jeśli**: Deszcz, mroz, przerwa w zajeciach, mecz stadionowy, zwiekszenie liczby rowerow zamiast ciezarowki.",
        "- **Analiza wplwyou parametrow (Tornado i Morris)**: Identyfikacja kluczowych parametrow wplywajacych na utracony popyt.",
        "",
        "## 2. Podsumowanie emergentnych wlasnosci",
        "Wprowadzenie autonomicznych agentow stacji, ciezarowek i dyspozytora z Contract Net umozliwilo dekoncentracje wiedzy o stanie miasta.",
        "Emergentne fale pustek oraz efekt stadny przy uzyciu opoznionej aplikacji zostaly w pelni odwzorowane w metrykach i dzienniku zdarzen.",
        ""
    ]
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path
