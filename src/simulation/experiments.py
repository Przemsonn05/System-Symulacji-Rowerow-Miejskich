from dataclasses import replace
from itertools import combinations
from pathlib import Path
import hashlib
import json
import platform
import sys

from joblib import Parallel, delayed
import numpy as np
import pandas as pd
from scipy import stats

from .engine import run_simulation


METRICS = ["lost_demand", "lost_share", "empty_station_share", "extra_user_minutes", "extra_minutes_per_request", "truck_km"]
STRATEGIES = ("none", "operator", "threshold")


def confidence_interval(values):
    values = np.asarray(values, dtype=float)
    if len(values) < 2 or not np.isfinite(values).all():
        raise ValueError("CI requires at least two finite replications")
    mean = float(values.mean())
    half = float(stats.t.ppf(0.975, len(values) - 1) * stats.sem(values))
    return mean, mean - half, mean + half


def summarize(runs):
    rows = []
    for (strategy, trucks), group in runs.groupby(["scenario", "n_trucks"], sort=True):
        for metric in METRICS:
            mean, low, high = confidence_interval(group[metric])
            rows.append({"scenario": strategy, "n_trucks": trucks, "metric": metric,
                         "n": len(group), "mean": mean, "ci95_low": low, "ci95_high": high})
    return pd.DataFrame(rows)


def paired_comparisons(runs):
    rows = []
    for trucks, group in runs.groupby("n_trucks"):
        pivot = group.pivot(index="seed", columns="scenario", values="lost_demand")
        for a, b in combinations(STRATEGIES, 2):
            if a not in pivot or b not in pivot or pivot[[a, b]].isna().any().any():
                raise ValueError("Paired comparison has missing replications")
            difference = pivot[a].to_numpy() - pivot[b].to_numpy()
            pvalue = float(stats.wilcoxon(difference, zero_method="pratt", alternative="two-sided", method="auto").pvalue) if np.any(difference) else 1.0
            mean, low, high = confidence_interval(difference)
            rows.append({"strategy_a": a, "strategy_b": b, "n_trucks": trucks, "n_pairs": len(difference),
                         "mean_lost_a_minus_b": mean, "ci95_low": low, "ci95_high": high, "p_wilcoxon": pvalue})
    result = pd.DataFrame(rows)
    order = np.argsort(result.p_wilcoxon.to_numpy(), kind="stable")
    corrected = np.maximum.accumulate(result.p_wilcoxon.to_numpy()[order] * np.arange(len(result), 0, -1))
    result["p_holm"] = 1.0
    result.loc[order, "p_holm"] = np.minimum(corrected, 1.0)
    return result


def pareto_front(summary):
    frame = summary.pivot(index=["scenario", "n_trucks"], columns="metric", values="mean").reset_index()
    xy = frame[["truck_km", "lost_demand"]].to_numpy()
    frame["pareto"] = [not any(np.all(other <= point) and np.any(other < point) for other in xy) for point in xy]
    return frame


def request_digest(requests):
    payload = requests.to_csv(index=False, float_format="%.12g").encode()
    return hashlib.sha256(payload).hexdigest()


def run_one(params, strategy, trucks, seed, directory):
    target = Path(directory) / "runs" / f"{strategy}_{trucks}" / f"seed_{seed}"
    result = run_simulation(replace(params, n_trucks=int(trucks), output_dir=target), strategy, int(seed))
    return {**result.kpis, "requests_sha256": request_digest(result.requests)}


def run_experiments(params, output_dir, replications=30, n_jobs=2, seed_start=1000, truck_counts=(1, 2, 3, 4)):
    if replications < 2:
        raise ValueError("At least two replications required")
    if not truck_counts or any(int(n) != n or n < 1 for n in truck_counts) or len(set(truck_counts)) != len(truck_counts):
        raise ValueError("Invalid truck counts")
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    seeds = list(range(seed_start, seed_start + replications))
    tasks = [(strategy, trucks, seed) for strategy in STRATEGIES for trucks in truck_counts for seed in seeds]
    rows = Parallel(n_jobs=n_jobs, backend="loky", verbose=10)(
        delayed(run_one)(params, strategy, trucks, seed, output_dir) for strategy, trucks, seed in tasks)
    runs = pd.DataFrame(rows)
    if (runs.groupby("seed").requests_sha256.nunique() != 1).any():
        raise AssertionError("Common random numbers were not preserved")
    runs.to_csv(output_dir / "replications.csv", index=False)
    runs.to_parquet(output_dir / "replications.parquet", index=False)
    summary = summarize(runs)
    paired = paired_comparisons(runs)
    pareto = pareto_front(summary)
    summary.to_csv(output_dir / "summary.csv", index=False)
    paired.to_csv(output_dir / "paired_wilcoxon.csv", index=False)
    pareto.to_csv(output_dir / "pareto.csv", index=False)
    import importlib.metadata
    manifest = {"replications": replications, "seeds": seeds, "strategies": list(STRATEGIES),
                "truck_counts": list(truck_counts), "duration_min": params.duration_min,
                "start_time": params.start_time.isoformat(), "n_stations": len(params.stations),
                "n_jobs": n_jobs, "python": sys.version, "platform": platform.platform(),
                "network": params.network.source, "ci": "Student t, two-sided 95%, across independent seeds",
                "input_provenance": params.provenance,
                "paired_tests": "Wilcoxon signed ranks, two-sided, Pratt zeros; Holm correction across all comparisons",
                "packages": {name: importlib.metadata.version(name) for name in ["numpy", "pandas", "simpy", "scipy", "joblib", "pyarrow", "networkx"]},
                "parameters": {key: getattr(params, key) for key in ["truck_capacity", "handling_min_per_bike", "dispatch_interval_min",
                    "lower_threshold", "upper_threshold", "target_fill", "bike_speed_kmh", "walk_speed_kmh", "max_walk_km",
                    "empty_retry_probability", "full_redirect_probability", "ride_sigma", "snapshot_interval_min", "congestion_multiplier"]}}
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    make_plots(summary, paired, pareto, output_dir)
    write_report(runs, summary, paired, pareto, manifest, output_dir)
    return runs, summary, paired


def make_plots(summary, paired, pareto, output_dir):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update({"font.size": 11, "figure.dpi": 150, "axes.spines.top": False, "axes.spines.right": False})
    labels = {"none": "Brak relokacji", "operator": "Odtworzenie operatora", "threshold": "Strategia progowa"}
    colors = {"none": "#7b8794", "operator": "#e29539", "threshold": "#148a8b"}
    fig, ax = plt.subplots(figsize=(10, 6))
    for strategy in STRATEGIES:
        loss = summary[(summary.scenario == strategy) & (summary.metric == "lost_demand")].sort_values("n_trucks")
        distance = summary[(summary.scenario == strategy) & (summary.metric == "truck_km")].sort_values("n_trucks")
        if strategy == "none":
            loss = loss.iloc[:1]
            distance = distance.iloc[:1]
        ax.errorbar(distance["mean"], loss["mean"], xerr=np.maximum(0, [distance["mean"] - distance.ci95_low, distance.ci95_high - distance["mean"]]),
                    yerr=np.maximum(0, [loss["mean"] - loss.ci95_low, loss.ci95_high - loss["mean"]]),
                    fmt="o-", capsize=3, label=labels[strategy], color=colors[strategy], alpha=0.9)
        for x, y, trucks in zip(distance["mean"], loss["mean"], loss.n_trucks):
            label = "1–4" if strategy == "none" else str(trucks)
            offset = (12, -18) if strategy == "operator" and trucks == 3 else (6, 7)
            ax.annotate(label, (x, y), xytext=offset, textcoords="offset points")
    front = pareto[pareto.pareto].sort_values("truck_km").drop_duplicates(["truck_km", "lost_demand"])
    ax.plot(front.truck_km, front.lost_demand, "k--", alpha=0.4, label="Front Pareto (średnie)")
    ax.set(xlabel="Kilometry ciężarówek / dobę", ylabel="Utracony popyt / dobę", title="H3: wstępne porównanie strategii, 95% CI")
    ax.legend()
    ax.grid(alpha=0.15)
    fig.tight_layout()
    fig.savefig(Path(output_dir) / "h3_pareto.png")
    plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    for strategy in STRATEGIES:
        for ax, metric, ylabel in zip(axes, ["lost_demand", "empty_station_share"], ["Utracony popyt / dobę", "Udział czasu pustych stacji"]):
            subset = summary[(summary.scenario == strategy) & (summary.metric == metric)].sort_values("n_trucks")
            ax.errorbar(subset.n_trucks, subset["mean"], yerr=np.maximum(0, [subset["mean"] - subset.ci95_low, subset.ci95_high - subset["mean"]]),
                        fmt="o-", capsize=3, color=colors[strategy], label=labels[strategy])
            ax.set(xlabel="Liczba ciężarówek", ylabel=ylabel, xticks=sorted(subset.n_trucks.unique()))
            ax.grid(alpha=0.15)
    axes[0].legend(fontsize=9)
    fig.suptitle("Wyniki wstępne; modele wymagają kalibracji")
    fig.tight_layout()
    fig.savefig(Path(output_dir) / "h3_kpis.png")
    plt.close(fig)


def write_report(runs, summary, paired, pareto, manifest, output_dir):
    loss = summary[summary.metric == "lost_demand"].set_index(["scenario", "n_trucks"])
    km = summary[summary.metric == "truck_km"].set_index(["scenario", "n_trucks"])
    mode = manifest.get("input_provenance", {}).get("mode", "unspecified")
    if mode == "preliminary_empirical":
        origin = "Dane stacji, początkowych stanów, kontekstu i przewozów operatora są rzeczywiste (pięć stanów początkowych uzupełniono przykładowo). Popyt i OD są estymatami roboczymi z wcześniejszych dni; czasy jazdy i zachowania użytkowników mają parametry przykładowe. Wyniki nie rozstrzygają jeszcze H3 dla rzeczywistego systemu."
    elif mode == "synthetic_example":
        origin = "Dane i parametry są syntetyczne. W tym przykładzie strategia operatora odtwarza przykładowy harmonogram. Wyniki służą weryfikacji działania silnika, a nie rozstrzygnięciu H3 dla rzeczywistego systemu."
    else:
        origin = "Pochodzenie danych nie zostało określone w manifeście. Przed interpretacją H3 należy sprawdzić wejścia i kalibrację parametrów."
    lines = ["# H3 — wyniki wstępne na 5 listopada 2026", "",
             f"Wykonano {len(runs)} przebiegów: 3 strategie × {len(manifest['truck_counts'])} warianty floty × {manifest['replications']} replikacji.",
             f"Każdy przebieg: {manifest['n_stations']} stacji, {manifest['duration_min'] / 60:g} h od {manifest['start_time']}.", "",
             origin, "",
             "## Średnie i 95% przedziały ufności", "",
             "| Strategia | Ciężarówki | Utracony popyt [95% CI] | Km ciężarówek [95% CI] |", "|---|---:|---:|---:|"]
    for index, row in loss.iterrows():
        distance = km.loc[index]
        lines.append(f"| {index[0]} | {index[1]} | {row['mean']:.1f} [{row.ci95_low:.1f}; {row.ci95_high:.1f}] | {distance['mean']:.1f} [{distance.ci95_low:.1f}; {distance.ci95_high:.1f}] |")
    lines += ["", "![Pareto](h3_pareto.png)", "", "![KPI](h3_kpis.png)", "", "## Porównania parowane", "",
              "Dodatnia różnica A − B oznacza mniej utraconego popytu w strategii B. Przedział t dotyczy średniej różnicy; test Wilcoxona dotyczy rang różnic przy założeniu ich symetrii. Skorygowane p obejmuje całą rodzinę porównań (Holm).", "",
              "| A | B | Ciężarówki | Średnia A − B [95% CI] | p Wilcoxona | p Holm |", "|---|---|---:|---:|---:|---:|"]
    for row in paired.itertuples():
        lines.append(f"| {row.strategy_a} | {row.strategy_b} | {row.n_trucks} | {row.mean_lost_a_minus_b:.1f} [{row.ci95_low:.1f}; {row.ci95_high:.1f}] | {row.p_wilcoxon:.4g} | {row.p_holm:.4g} |")
    best = loss.sort_values("mean").iloc[0]
    best_key = loss.sort_values("mean").index[0]
    baseline = float(loss.loc[("none", best_key[1]), "mean"])
    reduction = (baseline - best["mean"]) / baseline if baseline else 0.0
    lines += ["", "## Odczyt wyniku", "",
              f"Najmniejszy średni utracony popyt: {best_key[0]}, {best_key[1]} ciężarówki; {best['mean']:.1f} wobec {baseline:.1f} bez relokacji ({reduction:.1%} mniej). To wynik warunkowy dla przyjętych danych i parametrów.", "",
              "Front Pareto dotyczy średnich i dwóch celów: utraconego popytu i kilometrów. Nie uwzględnia stałego kosztu utrzymania floty. W strategii none liczba dostępnych ciężarówek nie zmienia przebiegu; cztery warianty to ten sam punkt odniesienia.", "",
              "## Metoda i ograniczenia", "",
              f"- {manifest['replications']} niezależnych ziaren {manifest['seeds'][0]}–{manifest['seeds'][-1]}; identyczne potencjalne przyjścia, cele, czasy i decyzje tych samych klientów we wszystkich wariantach danego ziarna. Zgodność potwierdzona SHA-256 tabel requests.",
              "- Przedziały t-Studenta liczone między replikacjami; nie opisują błędu estymacji modeli wejściowych. Brak okresu rozgrzewki: skończony eksperyment dobowy z obserwowanym stanem początkowym.",
              "- Popyt: niejednorodny Poisson, intensywność stała wewnątrz godziny, thinning Lewis–Shedler. OD estymowane z wcześniejszych dni, z wygładzaniem odległościowym.",
              "- Progowa: interwencja poniżej 20% lub powyżej 80%, cel 50%, rezerwacja stacji podczas zlecenia. Operator: kolejka rzeczywistych zleceń z dnia eksperymentu, bez teleportacji rowerów i bez przekraczania pojemności pojazdu.",
              "- Operator jest odtworzeniem ex post: godziny i kierunki są znane z danych. Nie zakładamy znajomości faktycznych tras ani identyfikatorów ciężarówek. Różna liczba pojazdów oznacza różne opóźnienia wykonania tych samych zleceń.",
              "- Miękka pojemność: zwrot ponad liczbę stojaków jest dozwolony. Domyślnie brak przekierowania z przepełnionej stacji. Alternatywne reguły są parametryzowane.",
              "- Utracony popyt to klienci, którzy zakończyli próbę bez roweru. Pending users, rowery w drodze i na ciężarówkach na końcu doby są raportowane osobno; nie wymuszamy zwrotów po horyzoncie.",
              "- Czas pustych stacji jest całkowany dokładnie pomiędzy zmianami stanu. Dodatkowy czas obejmuje chodzenie i przekierowanie zrealizowane do horyzontu; kilometry obejmują pusty przejazd i załadowaną jazdę, także część odcinka do końca doby.",
              "- Nocna, predykcyjna, H5b, scenariusze co-jeśli oraz Morris/tornado są poza jutrzejszym kamieniem milowym.", "",
              "## Pliki do przekazania", "",
              "`replications.csv`, `summary.csv`, `paired_wilcoxon.csv`, `pareto.csv`, `manifest.json`, wykresy oraz `runs/<strategia>_<flota>/seed_<ziarno>/`: events, station_timeseries, trips, requests, fleet_timeseries, station_kpis, stations, context i kpis.json.", "",
              "Pełne założenia danych: `../inputs/metadata.json`. Opis modelu i instrukcja: `../../docs/simulation.md`.", ""]
    (Path(output_dir) / "REPORT.md").write_text("\n".join(lines), encoding="utf-8")
