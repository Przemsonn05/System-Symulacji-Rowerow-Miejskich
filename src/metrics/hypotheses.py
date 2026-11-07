"""Hipotezy z danych (Osoba 1, zadanie 3): H2, A, B, C + regula operatora dla Osoby 3.

    python -m src.metrics.hypotheses                 # wynik w docs/wyniki/ i processed/operator_rule.json

H2  puste stacje sa skupione: Gini z przedzialem bootstrap po dniach, stabilnosc miedzy dniami (czy co dzien
    te same stacje), lista 10 stacji najczesciej pustych w porannym szczycie (do obserwacji w terenie).
A   prog darmowych 20 min: czasy przejazdow maja dokladnosc +- 5 min (pomiary co 5 min; czas = pierwszy pomiar
    z rowerem w celu - ostatni pomiar w starcie, czyli zawyzony srednio o ok. 5 min), wiec zamiast wykresu
    minuta po minucie liczymy przejazdy w krokach 5 min i sprawdzamy, czy przy progu (kroki 20->25 i 25->30)
    liczba przejazdow spada ostrzej, niz wynika z trendu krokow sasiednich (15->20, 30->35 ... 40->45).
    Proste rozklady (log-normalny, gamma) nie pasuja do calego rozkladu (drugi garb ok. 50-60 min),
    dlatego porownujemy lokalnie. Przedzial 95%: bootstrap po dniach.
B   e-rowery: czy jezdza nimi dalej (Mann-Whitney), czy unikaja rozladowanych (udzial wypozyczen z baterią
    < 20% vs udzial rozladowanych wsrod e-rowerow stojacych na stacjach, test dwumianowy).
C   czy operator nadaza: ile okresow pustej stacji konczy ciezarowka, po jakim czasie przyjezdza, czy jezdzi
    do stacji najczesciej pustych; regula operatora (przy jakim zapelnieniu przywozi i zabiera, ile rowerow).
"""

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

from ..data.config import PROCESSED, ROOT, TZ
from .emergence import lorenz_gini
from .io import full_days, load_run

OUT = ROOT / "docs" / "wyniki"
LOW_BATTERY = 20
MORNING = (7, 10)


def _user_trips():
    t = pd.read_parquet(PROCESSED / "trips.parquet")
    return t[(t["type"] == "user") & ~t["is_flicker"] & ~t["too_fast"] & ~t["is_long"]].copy()


# ---------------------------------------------------------------------------- H2


def daily_empty_share(run, days):
    """Udzial pustki kazdej stacji w kazdym dniu: DataFrame dzien x stacja."""
    e = pd.DataFrame(run.empty(), index=run.bikes.index.tz_convert(TZ).date, columns=run.stations["station_id"])
    return e[e.index.isin(days)].groupby(level=0).mean()


def h2(run, st, n_boot=1000, seed=7):
    days = full_days(run)
    daily = daily_empty_share(run, days)
    share = daily.mean()
    gini = lorenz_gini(share.dropna().to_numpy())[2]
    rng = np.random.default_rng(seed)
    boot = [lorenz_gini(daily.iloc[rng.integers(len(daily), size=len(daily))].mean().dropna().to_numpy())[2]
            for _ in range(n_boot)]
    loo = [lorenz_gini(daily.drop(index=d).mean().dropna().to_numpy())[2] for d in daily.index]
    per_day = [lorenz_gini(daily.loc[d].dropna().to_numpy())[2] for d in daily.index]
    # czy co dzien te same stacje: Jaccard zbiorow 10% najczesciej pustych miedzy parami dni
    k = int(np.ceil(daily.shape[1] * 0.1))
    tops = [set(daily.loc[d].sort_values(ascending=False).index[:k]) for d in daily.index]
    jac = [len(a & b) / len(a | b) for i, a in enumerate(tops) for b in tops[i + 1:]]
    n = daily.shape[1]
    jac_random = k / (2 * n - k)
    # poranny szczyt dni roboczych: 10 stacji najczesciej pustych
    loc = run.bikes.index.tz_convert(TZ)
    work = [d for d in days if run.day_type.get(d) == "workday"]
    sel = np.isin(loc.date, work) & (loc.hour >= MORNING[0]) & (loc.hour < MORNING[1])
    morning = pd.Series(np.nanmean(run.empty()[sel], axis=0), index=run.stations["station_id"])
    s = st.set_index("station_id")
    top = morning.sort_values(ascending=False).head(10).rename("morning_empty_share").reset_index()
    top["name"] = top["station_id"].map(s["name"])
    top["district"] = top["station_id"].map(s["district"]) if "district" in s else ""
    top["minutes_empty_per_morning"] = (top["morning_empty_share"] * (MORNING[1] - MORNING[0]) * 60).round(0)
    top["share_empty_all_day"] = top["station_id"].map(share).round(3)
    top["lat"] = top["station_id"].map(s["lat"])
    top["lon"] = top["station_id"].map(s["lon"])
    return {
        "days": len(days), "gini": gini, "gini_ci95": [float(np.quantile(boot, 0.025) - (np.mean(boot) - gini)),
                      float(np.quantile(boot, 0.975) - (np.mean(boot) - gini))],
        "gini_leave_one_day_out": [float(min(loo)), float(max(loo))],
        "gini_per_day": [float(min(per_day)), float(np.median(per_day)), float(max(per_day))],
        "top10_jaccard_mean": float(np.mean(jac)) if jac else np.nan, "top10_jaccard_random": jac_random,
        "top_morning": top,
    }


# ---------------------------------------------------------------------------- A


STEP_REF = (15, 30, 35, 40)   # kroki odniesienia (przed progiem i po nim)
STEP_TEST = (20, 25)          # kroki przy progu 20 min (czas zawyzony o ok. 5 min)


def _kink(counts):
    """Spadek liczby przejazdow z kroku na krok przy progu vs trend z krokow sasiednich.

    r(x) = log N(x + 5) / N(x). Dla gladkiego rozkladu r zmienia sie lagodnie, wiec r przy progu
    przewidujemy prosta przez kroki odniesienia. Zwraca exp(srednie r przy progu - przewidywane):
    < 1 = przy progu liczba przejazdow spada ostrzej niz obok (ludzie koncza przed koncem darmowego czasu)."""
    n = lambda x: counts.get(x, 0)
    r = {x: np.log(n(x + 5) / n(x)) for x in STEP_REF + STEP_TEST if n(x) > 0 and n(x + 5) > 0}
    if not all(x in r for x in STEP_REF + STEP_TEST):
        return np.nan, r, {}
    b = np.polyfit(STEP_REF, [r[x] for x in STEP_REF], 1)
    pred = {x: float(np.polyval(b, x)) for x in STEP_TEST}
    return float(np.exp(np.mean([r[x] - pred[x] for x in STEP_TEST]))), r, pred


def h_a(trips, n_boot=1000, seed=11):
    t = trips[(trips["from_type"] == "station") & (trips["to_type"] == "station")
              & (trips["from_station"] != trips["to_station"])].copy()
    t["step"] = ((t["duration_min"] / 5).round() * 5).astype(int)
    t["date"] = t["t_departure"].dt.tz_convert(TZ).dt.date
    by_day = t.groupby(["date", "step"]).size().unstack(fill_value=0)
    counts = by_day.sum()
    factor, r, pred = _kink(counts.to_dict())
    rng = np.random.default_rng(seed)
    boot = []
    for _ in range(n_boot):
        sample = by_day.iloc[rng.integers(len(by_day), size=len(by_day))].sum()
        boot.append(_kink(sample.to_dict())[0])
    boot = np.asarray(boot)
    boot = boot[np.isfinite(boot)]
    grid = list(range(5, 65, 5))
    rows = []
    for x in grid:
        rows.append({"minutes": x, "observed": int(counts.get(x, 0)),
                     "step_ratio": float(counts.get(x + 5, 0) / counts.get(x, 1)) if counts.get(x, 0) else np.nan,
                     "expected_ratio": float(np.exp(pred[x])) if x in pred else np.nan})
    return {"n": int(len(t)), "table": pd.DataFrame(rows), "factor": factor,
            "factor_ci95": [float(np.quantile(boot, 0.025)), float(np.quantile(boot, 0.975))] if len(boot) else [np.nan, np.nan],
            "share_le_20": float((t["duration_min"] <= 20).mean()),
            "share_le_25": float((t["duration_min"] <= 25).mean()),
            "n_days": int(len(by_day))}


# ---------------------------------------------------------------------------- B


def h_b(trips):
    t = trips[(trips["from_type"] == "station") & (trips["to_type"] == "station")
              & (trips["from_station"] != trips["to_station"])].copy()
    t["km"] = t["network_km"].fillna(t["distance_km"])
    e, r = t[t["is_ebike"]], t[~t["is_ebike"]]
    mw = stats.mannwhitneyu(e["km"].dropna(), r["km"].dropna(), alternative="greater")
    obs = pd.read_parquet(PROCESSED / "observed_timeseries.parquet", columns=["ebikes", "ebikes_low", "is_spike"])
    obs = obs[~obs["is_spike"]].dropna(subset=["ebikes"])
    parked_low = float(obs["ebikes_low"].astype(float).sum() / max(obs["ebikes"].astype(float).sum(), 1))
    b = e["battery_start"].dropna()
    rented_low = float((b < LOW_BATTERY).mean()) if len(b) else np.nan
    binom = stats.binomtest(int((b < LOW_BATTERY).sum()), len(b), parked_low, alternative="less") if len(b) else None
    bucket = pd.cut(b, [0, 20, 40, 60, 80, 101], right=False)
    km_by_battery = e.loc[b.index].groupby(bucket, observed=True)["km"].median()
    rho = stats.spearmanr(e.loc[b.index, "battery_start"], e.loc[b.index, "km"], nan_policy="omit")
    return {"n_ebike": int(len(e)), "n_regular": int(len(r)), "ebike_share": float(t["is_ebike"].mean()),
            "km_median_ebike": float(e["km"].median()), "km_median_regular": float(r["km"].median()),
            "min_median_ebike": float(e["duration_min"].median()), "min_median_regular": float(r["duration_min"].median()),
            "mannwhitney_p": float(mw.pvalue),
            "battery_median": float(b.median()) if len(b) else np.nan,
            "rented_low_share": rented_low, "parked_low_share": parked_low,
            "binom_p": float(binom.pvalue) if binom else np.nan,
            "km_by_battery": {str(k): float(v) for k, v in km_by_battery.items()},
            "spearman_battery_km": float(rho.statistic), "spearman_p": float(rho.pvalue)}


# ---------------------------------------------------------------------------- C


def h_c(run, st):
    reb = pd.read_parquet(PROCESSED / "rebalancing_observed.parquet")
    emp = pd.read_parquet(PROCESSED / "empty_periods.parquet")
    emp = emp[~emp["censored_end"]].copy()
    loc = emp["start"].dt.tz_convert(TZ)
    emp = emp[(loc.dt.hour >= 6) & (loc.dt.hour < 22)]
    by_station = {s: g["t_arrival"].dt.tz_convert(None).sort_values().to_numpy() for s, g in reb.groupby("to_station")}
    ended, wait = [], []
    for r in emp.itertuples():
        arr = by_station.get(r.station_id)
        if arr is None:
            ended.append(False)
            wait.append(np.nan)
            continue
        start = r.start.tz_convert(None).to_datetime64()
        after = arr[arr >= start]
        first = after[0] if len(after) else None
        ended.append(bool(first is not None and first <= (r.end + pd.Timedelta(minutes=5)).tz_convert(None).to_datetime64()))
        wait.append((pd.Timestamp(first, tz="UTC") - r.start).total_seconds() / 60 if first is not None else np.nan)
    emp["ended_by_truck"] = ended
    emp["truck_wait_min"] = wait
    long = emp[emp["duration_min"] >= 30]
    # czy ciezarowki jezdza do stacji najczesciej pustych
    share = pd.Series(np.nanmean(run.empty(), axis=0), index=run.stations["station_id"])
    n_days = len(full_days(run))
    deliveries = reb.groupby("to_station").size().reindex(share.index, fill_value=0) / max(n_days, 1)
    rho = stats.spearmanr(share, deliveries)
    top20 = set(share.sort_values(ascending=False).index[: int(np.ceil(len(share) * 0.2))])
    to_top = float(reb["to_station"].isin(top20).mean())
    # regula operatora: zapelnienie celu tuz przed dowozem i startu tuz przed zabraniem
    b = run.bikes
    cap = st.set_index("station_id")["capacity"]
    slot_before = (reb["t_arrival"].dt.floor("5min") - pd.Timedelta(minutes=5))
    slot_from = reb["t_departure"].dt.floor("5min")

    def at(slots, sids):
        out = []
        for s_, sid in zip(slots, sids):
            v = b[sid].get(s_, np.nan) if sid in b.columns else np.nan
            out.append(v)
        return np.asarray(out, float)

    to_fill = at(slot_before, reb["to_station"]) / reb["to_station"].map(cap).to_numpy(float)
    from_fill = at(slot_from, reb["from_station"]) / reb["from_station"].map(cap).to_numpy(float)
    shifts = pd.read_parquet(PROCESSED / "operator_shifts.parquet")
    q = lambda v, p: float(np.nanquantile(v, p))
    rule = {
        "description": "Regula operatora z danych (relokacje >= 4 rowery naraz). Zapelnienie = rowery / stojaki "
                       "tuz przed dowozem (cel) i tuz przed zabraniem (start). Godziny = operator_shifts.is_shift.",
        "n_relocations": int(len(reb)),
        "deliver_when_fill_below": {"median": q(to_fill, 0.5), "q25": q(to_fill, 0.25), "q75": q(to_fill, 0.75)},
        "pickup_when_fill_above": {"median": q(from_fill, 0.5), "q25": q(from_fill, 0.25), "q75": q(from_fill, 0.75)},
        "share_deliveries_to_empty": float(np.nanmean(to_fill <= 0)),
        "bikes_per_relocation": {"median": float(reb["n_bikes"].median()), "q25": q(reb["n_bikes"], 0.25),
                                 "q75": q(reb["n_bikes"], 0.75), "max": int(reb["n_bikes"].max())},
        "shift_hours": {k: g.loc[g["is_shift"], "hour"].astype(int).tolist() for k, g in shifts.groupby("day_kind")},
        "relocations_per_day": {k: float(g["relocations_per_day"].sum()) for k, g in shifts.groupby("day_kind")},
        "caveat": "Widzimy tylko przewozy >= 4 rowerow; liczby ciezarowek nie znamy.",
    }
    return {"n_empty_periods": int(len(emp)), "share_ended_by_truck": float(emp["ended_by_truck"].mean()),
            "n_long": int(len(long)), "share_long_ended_by_truck": float(long["ended_by_truck"].mean()) if len(long) else np.nan,
            "truck_wait_median_min": float(np.nanmedian(emp.loc[emp["ended_by_truck"], "truck_wait_min"]))
            if emp["ended_by_truck"].any() else np.nan,
            "spearman_empty_deliveries": float(rho.statistic), "spearman_p": float(rho.pvalue),
            "deliveries_to_top20_share": to_top, "rule": rule}


# ---------------------------------------------------------------------------- raport


def write_report(r2, ra, rb, rc, out):
    out.mkdir(parents=True, exist_ok=True)
    r2["top_morning"].to_csv(out / "top10_puste_rano.csv", index=False, encoding="utf-8")
    ra["table"].to_csv(out / "h_a_czasy_przejazdow.csv", index=False)
    pct = lambda v: f"{v:.0%}" if pd.notna(v) else "–"
    top = "\n".join(f"| {i + 1} | {r.name} | {r.district or ''} | {r.minutes_empty_per_morning:.0f} min | "
                    f"{r.share_empty_all_day:.0%} |" for i, r in enumerate(r2["top_morning"].itertuples()))
    fmt = lambda v: f"{v:.2f}" if pd.notna(v) else ""
    tab_a = "\n".join(f"| {r.minutes} | {r.observed} | {fmt(r.step_ratio)} | {fmt(r.expected_ratio)} |"
                      for r in ra["table"].itertuples())
    c = rc["rule"]
    text = f"""# Hipotezy z danych: H2, A, B, C (Osoba 1)

Wygenerowane przez `python -m src.metrics.hypotheses` na pełnych dniach z `processed/` ({r2['days']} dni).
Wyniki są wstępne do czasu zamrożenia danych (`dane-final`, 1.12).

## H2. Puste stacje są skupione na niewielu stacjach

- Gini czasu pustek: **{r2['gini']:.2f}** (95% przedział bootstrap po dniach z poprawką na obciążenie {r2['gini_ci95'][0]:.2f}–{r2['gini_ci95'][1]:.2f};
  bez jednego dnia {r2['gini_leave_one_day_out'][0]:.2f}–{r2['gini_leave_one_day_out'][1]:.2f}; w pojedynczych dniach
  {r2['gini_per_day'][0]:.2f} / {r2['gini_per_day'][1]:.2f} / {r2['gini_per_day'][2]:.2f} min / mediana / max – w jednym dniu
  więcej stacji nie jest pusta ani razu, więc Gini dnia jest wyższy niż Gini całego okresu).
- Czy co dzień te same stacje: średni Jaccard zbiorów „10% najczęściej pustych” między parami dni
  **{r2['top10_jaccard_mean']:.2f}** (gdyby wybór był losowy: {r2['top10_jaccard_random']:.2f}).
- **Wniosek:** {'potwierdzona – skupienie jest duże i stabilne, a często puste są w większości te same stacje.' if r2['gini'] > 0.5 and r2['top10_jaccard_mean'] > 2 * r2['top10_jaccard_random'] else 'do weryfikacji na pełnych danych.'}

### 10 stacji najczęściej pustych w porannym szczycie (dni robocze 7–10) – do obserwacji w terenie (Osoba 2)

| # | stacja | dzielnica | pusta średnio (7–10) | pusta w ciągu całej doby |
|---|---|---|---|---|
{top}

Plik: `top10_puste_rano.csv` (z współrzędnymi).

## A. Darmowe 20 minut kształtuje długość jazdy

Czasy mają dokładność ±5 min (pomiary co 5 min, czas zawyżony średnio o ok. 5 min), więc liczymy przejazdy
w krokach 5 min. Proste gładkie rozkłady nie pasują do całego rozkładu (drugi garb ok. 50–60 min), dlatego
sprawdzamy lokalnie: czy przy progu (kroki 20→25 i 25→30 min) liczba przejazdów spada ostrzej, niż wynika
z trendu sąsiednich kroków (15→20, 30→35, 35→40, 40→45).

| czas [min] | przejazdy | następny krok / ten krok | oczekiwane z trendu |
|---|---|---|---|
{tab_a}

- Przejazdów ≤ 20 min: {pct(ra['share_le_20'])}, ≤ 25 min: {pct(ra['share_le_25'])} (n = {ra['n']}, {ra['n_days']} dni).
- Przy progu liczba przejazdów maleje z kroku na krok średnio **{ra['factor']:.2f}×** tego, co wynika z trendu
  (95% bootstrap po dniach {ra['factor_ci95'][0]:.2f}–{ra['factor_ci95'][1]:.2f}; 1 = brak efektu, < 1 = ostrzejszy spadek).
- **Wniosek:** {'widoczne – tuż za granicą darmowego czasu przejazdów ubywa wyraźnie szybciej niż obok, czyli ludzie kończą jazdę przed 20. minutą.' if ra['factor_ci95'][1] < 1 else 'efekt progu niewyraźny przy tej dokładności czasu.'}
  W symulacji czas jazdy nie może być losowany z gładkiego rozkładu.

## B. E-rowery to osobna grupa klientów

- Udział e-rowerów w przejazdach stacja→stacja: {pct(rb['ebike_share'])} (n = {rb['n_ebike']}).
- Dystans: mediana **{rb['km_median_ebike']:.2f} km** e-rowerem vs {rb['km_median_regular']:.2f} km zwykłym
  (Mann–Whitney, jednostronnie p = {rb['mannwhitney_p']:.2g}); czas: {rb['min_median_ebike']:.0f} vs {rb['min_median_regular']:.0f} min.
- Bateria: mediana na starcie {rb['battery_median']:.0f}%. Wypożyczeń z baterią < {LOW_BATTERY}%: **{pct(rb['rented_low_share'])}**,
  a wśród e-rowerów stojących na stacjach rozładowanych jest {pct(rb['parked_low_share'])} (test dwumianowy p = {rb['binom_p']:.2g}).
- Dystans wg baterii (mediana km): {', '.join(f'{k}: {v:.2f}' for k, v in rb['km_by_battery'].items())};
  Spearman bateria–km ρ = {rb['spearman_battery_km']:.2f} (p = {rb['spearman_p']:.2g}).
- **Wniosek:** {'potwierdzona – e-rowerem jeździ się dalej, a rozładowane rowery są omijane.' if rb['km_median_ebike'] > rb['km_median_regular'] and rb['rented_low_share'] < rb['parked_low_share'] else 'częściowo – patrz liczby powyżej.'}

## C. Czy operator nadąża

- Okresy pustej stacji w dzień (6–22, znany koniec): {rc['n_empty_periods']}; zakończone dowozem ciężarówki:
  **{pct(rc['share_ended_by_truck'])}**; wśród pustek ≥ 30 min: {pct(rc['share_long_ended_by_truck'])} (n = {rc['n_long']}).
- Gdy ciężarówka kończy pustkę, przyjeżdża po medianie **{rc['truck_wait_median_min']:.0f} min** od opróżnienia.
- Czy jeździ do stacji najczęściej pustych: Spearman (udział pustek vs dowozy na dzień) ρ = {rc['spearman_empty_deliveries']:.2f}
  (p = {rc['spearman_p']:.2g}); do 20% najczęściej pustych trafia {pct(rc['deliveries_to_top20_share'])} dowozów.
- **Wniosek:** {'operator nie nadąża – większość pustek kończą klienci, a nie ciężarówki.' if rc['share_ended_by_truck'] < 0.5 else 'operator kończy większość pustek.'}
  Uwaga: widzimy tylko przewozy ≥ 4 rowerów.

### Reguła operatora (dla strategii `operator_rule`, Osoba 3) → `processed/operator_rule.json`

- Dowóz, gdy cel ma zapełnienie: mediana {c['deliver_when_fill_below']['median']:.0%} (kwartyle {c['deliver_when_fill_below']['q25']:.0%}–{c['deliver_when_fill_below']['q75']:.0%}); do pustej stacji {pct(c['share_deliveries_to_empty'])} dowozów.
- Zabranie, gdy start ma zapełnienie: mediana {c['pickup_when_fill_above']['median']:.0%} (kwartyle {c['pickup_when_fill_above']['q25']:.0%}–{c['pickup_when_fill_above']['q75']:.0%}).
- Rowerów na kurs: mediana {c['bikes_per_relocation']['median']:.0f} (kwartyle {c['bikes_per_relocation']['q25']:.0f}–{c['bikes_per_relocation']['q75']:.0f}, max {c['bikes_per_relocation']['max']}).
- Godziny pracy: dni robocze {', '.join(map(str, c['shift_hours'].get('roboczy', [])))}; wolne {', '.join(map(str, c['shift_hours'].get('wolny', [])))}.
- Kursów na dobę: dni robocze {c['relocations_per_day'].get('roboczy', 0):.0f}, wolne {c['relocations_per_day'].get('wolny', 0):.0f}.
"""
    (out / "hipotezy_osoba1.md").write_text(text, encoding="utf-8")
    return text


def _clean(o):
    from .__main__ import _clean as c
    return c(o)


def main():
    import sys

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--boot", type=int, default=1000)
    args = ap.parse_args()
    run = load_run(PROCESSED)
    st = pd.read_parquet(PROCESSED / "stations.parquet")
    trips = _user_trips()
    r2, ra, rb, rc = h2(run, st, args.boot), h_a(trips), h_b(trips), h_c(run, st)
    (PROCESSED / "operator_rule.json").write_text(json.dumps(_clean(rc["rule"]), ensure_ascii=False, indent=2),
                                                  encoding="utf-8")
    text = write_report(r2, ra, rb, rc, args.out)
    (args.out / "hipotezy_osoba1.json").write_text(json.dumps(_clean({"H2": r2, "A": ra, "B": rb, "C": rc}),
                                                              ensure_ascii=False, indent=1), encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
