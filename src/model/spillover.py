"""Interakcja agentow przez puste stacje: czy klienci pustej stacji przechodza do sasiednich?

Dla par stacji (ogniskowa i, sasiad j) w przedzialach odleglosci porownujemy wypozyczenia u sasiada
z prognoza modelu popytu w godzinach, gdy i byla pusta, i gdy miala rowery. Pary odlegle o 2-3 km
(nikt tam nie dojdzie pieszo) sa kontrola: ich nadwyzka to ogolny wzrost ruchu, ktorego model nie
przewidzial. Udzial przeniesionych = nadwyzka u sasiadow do WALK_M ponad kontrole / chetni na pustych
stacjach (lambda x czas pustki). Niepewnosc: bootstrap po dniach.

Lokalne skoki ruchu (cala okolica oblegana naraz) moga udawac przechodzenie, wiec udzial jest raczej
gorna granica.
"""

import numpy as np
import pandas as pd

from .data import context_filled, load, walk_matrix_m
from .demand import context_terms

BINS = [(0, 300), (300, 600), (600, 1000), (2000, 3000)]  # odleglosc w linii prostej [m]
WALK_M = 600   # dalej nadwyzka u sasiadow nie rozni sie od kontroli
NEAR = [f"{a}-{b} m" for a, b in BINS if b <= WALK_M]
CONTROL = "2000-3000 m"
CATS = ["ma rowery", "pusta < 30 min", "pusta >= 30 min"]
MIN_OBSERVED = 45


def station_hours(model, days):
    """Stacja x godzina: wypozyczenia, lambda z modelu i oczekiwane wypozyczenia przy faktycznej dostepnosci."""
    h = load("station_hourly")
    h = h[h["station_id"].isin(model.known) & (h["minutes_observed"] >= MIN_OBSERVED)]
    h = h.merge(context_terms(context_filled()), left_on="hour", right_on="time", how="inner")
    h = h[h["local_date"].isin(set(days))].reset_index(drop=True)
    h["lam"] = model.predict(h)
    h["mu"] = h["lam"] * h["minutes_available"] / 60
    h["cat"] = pd.cut(h["minutes_empty"] / h["minutes_observed"], [-0.01, 0.0, 0.5, 1.0], labels=CATS)
    return h.rename(columns={"local_date": "day"})


def day_sums(h, ids, stations):
    """Suma wypozyczen i prognozy u sasiadow: dzien x przedzial odleglosci x stan stacji ogniskowej."""
    dist = walk_matrix_m(ids, stations) / 1.2
    ids = np.asarray(ids)
    focal = h[["station_id", "hour", "cat"]].rename(columns={"station_id": "i"})
    neighbor = h.loc[h["minutes_available"] >= MIN_OBSERVED, ["station_id", "hour", "departures", "mu", "day"]]
    neighbor = neighbor.rename(columns={"station_id": "j"})
    parts = []
    for lo, hi in BINS:
        ii, jj = np.nonzero((dist > lo) & (dist <= hi))
        x = pd.DataFrame({"i": ids[ii], "j": ids[jj]}).merge(focal, on="i").merge(neighbor, on=["j", "hour"])
        parts.append(x.groupby(["day", "cat"], observed=True)[["departures", "mu"]].sum().assign(bin=f"{lo}-{hi} m"))
    return pd.concat(parts).reset_index()


def estimate(sums, displaced):
    """Nadwyzka u sasiadow wzgledem godzin, gdy ogniskowa ma rowery, i udzial przeniesionych klientow."""
    g = sums.groupby(["bin", "cat"], observed=True)[["departures", "mu"]].sum()
    ratio = (g["departures"] / g["mu"]).unstack("cat")
    excess = ratio.div(ratio["ma rowery"], axis=0) - 1
    common = ratio.loc[CONTROL] / ratio.loc[CONTROL, "ma rowery"]  # wzrost ruchu widoczny tez daleko
    extra = sum(g.loc[(b, c), "departures"] - g.loc[(b, c), "mu"] * ratio.loc[b, "ma rowery"] * common[c]
                for b in NEAR for c in CATS[1:])
    return excess[CATS[1:]], extra / displaced


def run(model, days, stations, ids, n_boot=300, seed=0):
    h = station_hours(model, days)
    sums = day_sums(h, ids, stations)
    empty = h[h["minutes_empty"] > 0]
    displaced = (empty["lam"] * empty["minutes_empty"] / 60).groupby(empty["day"]).sum()
    excess, share = estimate(sums, displaced.sum())
    rng = np.random.default_rng(seed)
    day_list = np.array(sorted(displaced.index.union(sums["day"].unique())))
    boot_excess, boot_share = [], []
    for _ in range(n_boot):
        w = pd.Series(rng.choice(day_list, len(day_list))).value_counts()
        s = sums.assign(departures=sums["departures"] * sums["day"].map(w).fillna(0),
                        mu=sums["mu"] * sums["day"].map(w).fillna(0))
        e, sh = estimate(s, (displaced * displaced.index.map(w).fillna(0)).sum())
        boot_excess.append(e.reindex_like(excess).to_numpy())
        boot_share.append(sh)
    lo, hi = np.nanpercentile(np.stack(boot_excess), [2.5, 97.5], axis=0)
    return {
        "excess": excess, "excess_lo": pd.DataFrame(lo, index=excess.index, columns=excess.columns),
        "excess_hi": pd.DataFrame(hi, index=excess.index, columns=excess.columns),
        "share": float(share), "share_ci": tuple(np.percentile(boot_share, [2.5, 97.5])),
        "walk_m": WALK_M, "n_days": len(day_list), "displaced": float(displaced.sum()),
        "empty_station_hours": len(empty), "empty_stations": empty["station_id"].nunique(),
    }
