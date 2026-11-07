"""Pomiar emergencji: zjawiska, ktorych nikt nie zaprogramowal, a ktore powstaja z zachowania wielu
klientow naraz. Kazda funkcja dziala tak samo na danych rzeczywistych i na wyniku symulacji (RunData).

  hourly_rhythm        rytm dnia: przejazdy w kazdej godzinie (dni robocze / wolne osobno)
  empty_concentration  skupienie pustek: krzywa Lorenza, Gini, udzial 10% / 20% stacji
  empty_durations      jak dlugo stacje sa puste (okresy z siatki 5 min)
  morans_i             czy podobne wartosci skupiaja sie w przestrzeni (sasiedztwo do 1 km, p z permutacji)
  cascades             fale pustek: stacja pustoszeje, chwile pozniej sasiednia (do 800 m, do 20 min)
  district_balance     przyplyw i odplyw rowerow w dzielnicach rano i po poludniu
  null_test            czy fale to nie przypadek: dane vs model zerowy
                         - "inny dzien": okresy pustki stacji wziete z innego dnia tego samego typu
                           (zachowuje pore dnia i czestosc pustek, zrywa powiazanie z sasiadami),
                         - "zamiana miejsc": stacje o podobnym udziale pustek zamieniaja sie polozeniem.
"""

import datetime as dt

import numpy as np
import pandas as pd
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components

from .io import TZ, day_kind, full_days

SLOT_MIN = 5
MORAN_RADIUS_M = 1000.0
CASCADE_RADIUS_M = 800.0
CASCADE_WINDOW_MIN = 20
MORNING = (7, 10)
AFTERNOON = (16, 19)


def _dist(xy):
    d = xy[:, None, :] - xy[None, :, :]
    return np.sqrt((d ** 2).sum(-1))


# ---------------------------------------------------------------------------
# Rytm, skupienie, dlugosc pustek
# ---------------------------------------------------------------------------


def hourly_rhythm(run, days=None):
    """Srednia liczba przejazdow w kazdej godzinie lokalnej, osobno dni robocze i wolne (tylko pelne dni)."""
    days = set(days if days is not None else full_days(run))
    t = run.trips
    rows = []
    if len(t):
        loc = pd.to_datetime(t["t_departure"], utc=True).dt.tz_convert(TZ)
        df = pd.DataFrame({"date": loc.dt.date, "hour": loc.dt.hour})
        df = df[df["date"].isin(days)]
        df["kind"] = df["date"].map(lambda d: day_kind(run.day_type.get(d, "workday")))
        for kind in ("roboczy", "wolny"):
            n_days = sum(1 for d in days if day_kind(run.day_type.get(d, "workday")) == kind)
            cnt = df[df["kind"] == kind].groupby("hour").size().reindex(range(24), fill_value=0)
            for h in range(24):
                rows.append({"day_kind": kind, "hour": h, "n_days": n_days,
                             "trips_per_day": float(cnt[h] / n_days) if n_days else np.nan})
    return pd.DataFrame(rows, columns=["day_kind", "hour", "n_days", "trips_per_day"])


def empty_share(run):
    e = run.empty()
    with np.errstate(invalid="ignore"):
        return pd.Series(np.nanmean(e, axis=0), index=run.stations["station_id"])


def lorenz_gini(values):
    """Krzywa Lorenza (x, y) i wspolczynnik Giniego dla wartosci nieujemnych."""
    v = np.sort(np.asarray(values, dtype=float)[np.isfinite(values)])
    n = len(v)
    if n == 0 or v.sum() == 0:
        return np.array([0, 1.0]), np.array([0, 1.0]), 0.0
    cum = np.concatenate([[0], np.cumsum(v)]) / v.sum()
    x = np.arange(n + 1) / n
    gini = float(1 - 2 * np.trapezoid(cum, x)) if hasattr(np, "trapezoid") else float(1 - 2 * np.trapz(cum, x))
    return x, cum, gini


def empty_concentration(run):
    s = empty_share(run).dropna()
    x, y, gini = lorenz_gini(s.to_numpy())
    v = np.sort(s.to_numpy())[::-1]
    total = v.sum()

    def top(q):
        return float(v[: int(np.ceil(len(v) * q))].sum() / total) if total > 0 else 0.0

    return {"gini": gini, "top10_share": top(0.1), "top20_share": top(0.2),
            "never_empty_share": float((s <= 0).mean()), "n_stations": int(len(s)),
            "lorenz_x": x.tolist(), "lorenz_y": y.tolist()}


def empty_durations(run):
    """Okresy pustki z siatki 5 min: station_id, start, minutes, censored (dotyka braku danych lub konca)."""
    e = run.empty()
    idx = run.bikes.index
    rows = []
    for j, sid in enumerate(run.stations["station_id"]):
        col = e[:, j]
        k, n = 0, len(col)
        while k < n:
            if col[k] != 1:
                k += 1
                continue
            a = k
            while k < n and col[k] == 1:
                k += 1
            cens = a == 0 or k == n or np.isnan(col[a - 1]) or (k < n and np.isnan(col[k]))
            rows.append((sid, idx[a], (k - a) * SLOT_MIN, bool(cens)))
    return pd.DataFrame(rows, columns=["station_id", "start", "minutes", "censored"])


# ---------------------------------------------------------------------------
# Moran
# ---------------------------------------------------------------------------


def neighbour_weights(xy, radius_m=MORAN_RADIUS_M, row_standardize=True):
    """Sasiad = inna stacja do radius_m. Wiersze standaryzowane (suma wag sasiadow = 1), wiec I jest
    srednia "wartosc u sasiadow" i miesci sie zwykle w [-1, 1]."""
    d = _dist(xy)
    w = ((d > 0) & (d <= radius_m)).astype(float)
    if row_standardize:
        rs = w.sum(axis=1, keepdims=True)
        w = np.divide(w, rs, out=np.zeros_like(w), where=rs > 0)
    return w


def morans_i(values, xy=None, radius_m=MORAN_RADIUS_M, permutations=999, seed=0, weights=None):
    """Indeks Morana (sasiad = stacja do radius_m, wagi standaryzowane wierszami) i p z permutacji (jednostronne,
    "skupienie wieksze niz losowo"). Zwraca dict: I, expected, p, z, n."""
    x = np.asarray(values, dtype=float)
    w = weights if weights is not None else neighbour_weights(xy, radius_m)
    ok = np.isfinite(x)
    x, w = x[ok], w[np.ix_(ok, ok)]
    n, s0 = len(x), w.sum()
    z = x - x.mean()
    denom = (z ** 2).sum()
    if n < 3 or s0 == 0 or denom == 0:
        return {"I": np.nan, "expected": np.nan, "p": np.nan, "z": np.nan, "n": int(n)}
    stat = lambda zz: n / s0 * np.einsum("...i,ij,...j->...", zz, w, zz) / denom
    obs = float(stat(z))
    rng = np.random.default_rng(seed)
    perm = np.stack([rng.permutation(z) for _ in range(permutations)]) if permutations else np.empty((0, n))
    null = stat(perm) if permutations else np.array([])
    p = float((1 + (null >= obs).sum()) / (1 + permutations)) if permutations else np.nan
    zscore = float((obs - null.mean()) / null.std()) if permutations and null.std() > 0 else np.nan
    return {"I": obs, "expected": -1.0 / (n - 1), "p": p, "z": zscore, "n": int(n)}


# ---------------------------------------------------------------------------
# Fale pustek
# ---------------------------------------------------------------------------


def empty_onsets(run):
    """Chwile pustoszenia: slot, w ktorym stacja ma 0 rowerow, a w poprzednim miala > 0 (oba znane).
    Zwraca DataFrame: station (indeks kolumny), time (UTC), date (lokalna), minute (od lokalnej polnocy)."""
    e = run.empty()
    prev = np.vstack([np.full((1, e.shape[1]), np.nan), e[:-1]])
    k, j = np.nonzero((e == 1) & (prev == 0))
    t = run.bikes.index[k]
    loc = t.tz_convert(TZ)
    return pd.DataFrame({"station": j, "time": t, "date": loc.date,
                         "minute": loc.hour * 60 + loc.minute}).sort_values(["time", "station"]).reset_index(drop=True)


def _link_day(station, minute, near, window):
    """Pary (i, j) zdarzen jednego dnia: 0 <= t_j - t_i <= window i stacje sasiednie (rozne)."""
    if len(station) < 2:
        return np.empty(0, int), np.empty(0, int)
    dtm = minute[None, :] - minute[:, None]
    ok = (dtm >= 0) & (dtm <= window) & near[np.ix_(station, station)]
    np.fill_diagonal(ok, False)
    return np.nonzero(ok)


def cascade_stats(events, near, window=CASCADE_WINDOW_MIN, keep_members=False):
    """Fale pustek: spojne skladowe grafu zdarzen polaczonych w czasie (<= window) i przestrzeni (near).

    events: DataFrame ze station, date, minute (jak z empty_onsets)."""
    sizes, linked, members = [], 0, []
    for d, g in events.groupby("date", sort=True):
        st = g["station"].to_numpy()
        mi = g["minute"].to_numpy(float)
        i, j = _link_day(st, mi, near, window)
        n = len(st)
        has = np.zeros(n, bool)
        has[i] = True
        has[j] = True
        linked += int(has.sum())
        graph = coo_matrix((np.ones(len(i)), (i, j)), shape=(n, n))
        nc, lab = connected_components(graph, directed=False)
        cnt = np.bincount(lab, minlength=nc)
        sizes.extend(cnt.tolist())
        if keep_members:
            for c in np.flatnonzero(cnt >= 2):
                sel = np.flatnonzero(lab == c)
                sel = sel[np.argsort(mi[sel], kind="stable")]
                members.append({"date": d, "stations": st[sel].tolist(), "minutes": mi[sel].tolist()})
    sizes = np.asarray(sizes, int)
    n_ev = int(sizes.sum())
    out = {
        "n_onsets": n_ev,
        "linked_share": linked / n_ev if n_ev else 0.0,
        "n_cascades_ge2": int((sizes >= 2).sum()),
        "n_cascades_ge3": int((sizes >= 3).sum()),
        "max_size": int(sizes.max()) if n_ev else 0,
        "mean_size_ge2": float(sizes[sizes >= 2].mean()) if (sizes >= 2).any() else 0.0,
        "size_counts": {int(k): int(v) for k, v in zip(*np.unique(sizes, return_counts=True))} if n_ev else {},
    }
    if keep_members:
        out["members"] = members
    return out


def cascades(run, radius_m=CASCADE_RADIUS_M, window=CASCADE_WINDOW_MIN, keep_members=True):
    near = _dist(run.xy) <= radius_m
    ev = empty_onsets(run)
    res = cascade_stats(ev, near, window, keep_members)
    if keep_members:
        ids = run.stations["station_id"].tolist()
        for m in res["members"]:
            m["station_ids"] = [ids[s] for s in m["stations"]]
    return res


def _day_swap(events, kinds, rng):
    """Model zerowy "inny dzien": dla kazdej stacji i dnia bierzemy jej chwile pustoszenia
    z losowego innego dnia tego samego typu (z zachowaniem pory dnia)."""
    by = {(s, d): g["minute"].to_numpy() for (s, d), g in events.groupby(["station", "date"])}
    stations = events["station"].unique()
    days_by_kind = {}
    for d, k in kinds.items():
        days_by_kind.setdefault(k, []).append(d)
    rows_s, rows_d, rows_m = [], [], []
    for k, ds in days_by_kind.items():
        if len(ds) < 2:
            for d in ds:  # brak innego dnia tego typu - zostawiamy bez zmian
                for s in stations:
                    m = by.get((s, d))
                    if m is not None:
                        rows_s.append(np.full(len(m), s)); rows_d.extend([d] * len(m)); rows_m.append(m)
            continue
        for s in stations:
            for d in ds:
                other = ds[rng.integers(len(ds) - 1)]
                if other == d:
                    other = ds[-1]
                m = by.get((s, other))
                if m is not None and len(m):
                    rows_s.append(np.full(len(m), s)); rows_d.extend([d] * len(m)); rows_m.append(m)
    if not rows_m:
        return events.iloc[0:0]
    return pd.DataFrame({"station": np.concatenate(rows_s), "date": rows_d, "minute": np.concatenate(rows_m)})


def _location_groups(share, n_groups=10):
    """Grupy stacji o podobnym udziale pustek (decyle) - do zamiany miejsc."""
    r = pd.Series(share).rank(method="first")
    return np.minimum((r.to_numpy() - 1) * n_groups // max(len(r), 1), n_groups - 1).astype(int)


def null_test(run, n_perm=1000, radius_m=CASCADE_RADIUS_M, window=CASCADE_WINDOW_MIN, seed=1918,
              days=None, stats=("linked_share", "n_cascades_ge3", "mean_size_ge2")):
    """Fale pustek w danych vs dwa modele zerowe. p = (1 + liczba prob >= dane) / (1 + n_perm)."""
    days = set(days if days is not None else full_days(run))
    ev = empty_onsets(run)
    ev = ev[ev["date"].isin(days)]
    near = _dist(run.xy) <= radius_m
    obs = cascade_stats(ev, near, window)
    rng = np.random.default_rng(seed)
    kinds = {d: day_kind(run.day_type.get(d, "workday")) for d in days}
    groups = _location_groups(empty_share(run).to_numpy())
    out = {"observed": {k: obs[k] for k in stats}, "n_perm": n_perm, "radius_m": radius_m, "window_min": window}
    can_swap_days = any(sum(1 for k in kinds.values() if k == kind) >= 2 for kind in set(kinds.values()))
    for name in ("inny_dzien", "zamiana_miejsc"):
        if name == "inny_dzien" and not can_swap_days:
            out[name] = None  # np. symulacja jednego dnia
            continue
        vals = {k: [] for k in stats}
        for _ in range(n_perm):
            if name == "inny_dzien":
                null_ev, nb = _day_swap(ev, kinds, rng), near
            else:
                perm = np.arange(len(groups))
                for g in np.unique(groups):
                    sel = np.flatnonzero(groups == g)
                    perm[sel] = rng.permutation(sel)
                null_ev, nb = ev, near[np.ix_(perm, perm)]
            res = cascade_stats(null_ev, nb, window)
            for k in stats:
                vals[k].append(res[k])
        out[name] = {k: {"mean": float(np.mean(v)), "q95": float(np.quantile(v, 0.95)),
                         "p": float((1 + np.sum(np.asarray(v) >= obs[k])) / (1 + n_perm)),
                         "ratio": float(obs[k] / np.mean(v)) if np.mean(v) else np.nan}
                     for k, v in vals.items()}
    return out


# ---------------------------------------------------------------------------
# Dzielnice
# ---------------------------------------------------------------------------


def district_balance(run, districts=None, days=None):
    """Srednio na dzien roboczy: przyjazdy - wyjazdy w dzielnicy rano (7-10) i po poludniu (16-19)."""
    from ..data.agents import district_of, load_districts

    districts = districts if districts is not None else load_districts()
    days = set(days if days is not None else full_days(run))
    work = [d for d in days if run.day_type.get(d, "workday") == "workday"]
    t = run.trips
    if districts is None or not len(t) or not work:
        return pd.DataFrame(columns=["district", "morning_net", "afternoon_net"])
    rows = []
    for side, tcol, sign in (("from", "t_departure", -1), ("to", "t_arrival", +1)):
        loc = pd.to_datetime(t[tcol], utc=True).dt.tz_convert(TZ)
        df = pd.DataFrame({"district": district_of(t[f"{side}_lat"], t[f"{side}_lon"], districts),
                           "date": loc.dt.date, "hour": loc.dt.hour, "v": sign})
        rows.append(df[df["date"].isin(work)])
    df = pd.concat(rows).dropna(subset=["district"])
    out = pd.DataFrame({
        "morning_net": df[df["hour"].between(MORNING[0], MORNING[1] - 1)].groupby("district")["v"].sum(),
        "afternoon_net": df[df["hour"].between(AFTERNOON[0], AFTERNOON[1] - 1)].groupby("district")["v"].sum(),
    }).reindex(sorted(districts["name"])).fillna(0) / len(work)
    return out.reset_index().rename(columns={"index": "district"})


# ---------------------------------------------------------------------------
# Raport i porownanie
# ---------------------------------------------------------------------------


def emergence_report(path_or_run, n_perm=1000, seed=1918):
    """Wszystkie metryki dla katalogu (processed/ albo przebieg symulacji). Zwraca slownik."""
    from .io import load_run

    run = path_or_run if hasattr(path_or_run, "bikes") else load_run(path_or_run)
    days = full_days(run)
    share = empty_share(run)
    dur = empty_durations(run)
    unc = dur.loc[~dur["censored"], "minutes"]
    work_morning = _morning_share(run, days)
    return {
        "source": run.source, "path": str(run.path) if run.path else None,
        "days": [d.isoformat() for d in days], "n_stations": int(len(run.stations)),
        "rhythm": hourly_rhythm(run, days),
        "concentration": empty_concentration(run),
        "durations": {"n": int(len(unc)), "median_min": float(unc.median()) if len(unc) else np.nan,
                      "p90_min": float(unc.quantile(0.9)) if len(unc) else np.nan,
                      "mean_min": float(unc.mean()) if len(unc) else np.nan,
                      "minutes": unc.to_numpy()},
        "moran_empty": morans_i(share.to_numpy(), run.xy, seed=seed),
        "moran_morning": morans_i(work_morning, run.xy, seed=seed + 1),
        "cascades": cascades(run),
        "null": null_test(run, n_perm=n_perm, seed=seed, days=days),
        "districts": district_balance(run, days=days),
        "empty_share": share,
    }


def _morning_share(run, days):
    """Udzial pustki stacji w porannym szczycie (7-10) dni roboczych - do Morana."""
    loc = run.bikes.index.tz_convert(TZ)
    sel = np.isin(loc.date, [d for d in days if run.day_type.get(d, "workday") == "workday"]) \
        & (loc.hour >= MORNING[0]) & (loc.hour < MORNING[1])
    e = run.empty()[sel]
    with np.errstate(invalid="ignore"):
        return np.nanmean(e, axis=0) if len(e) else np.full(e.shape[1], np.nan)


def summary_table(reports):
    """Tabela metryk obok siebie: {nazwa: raport} -> DataFrame."""
    rows = {}
    for name, r in reports.items():
        c, m, k, nl = r["concentration"], r["moran_empty"], r["cascades"], r["null"]
        rhythm = r["rhythm"]
        peak = rhythm[rhythm["day_kind"] == "roboczy"].sort_values("trips_per_day").tail(1)
        n_days = max(len(r["days"]), 1)
        rows[name] = {
            "dni": len(r["days"]),
            "przejazdy / dzień roboczy": rhythm.loc[rhythm["day_kind"] == "roboczy", "trips_per_day"].sum(),
            "godzina szczytu": int(peak["hour"].iloc[0]) if len(peak) else np.nan,
            "Gini pustek": c["gini"], "10% stacji = udział pustek": c["top10_share"],
            "nigdy pusta": c["never_empty_share"],
            "pustka: mediana [min]": r["durations"]["median_min"], "pustka: p90 [min]": r["durations"]["p90_min"],
            "Moran I (pustki)": m["I"], "Moran p": m["p"],
            "chwile pustoszenia / dzień": k["n_onsets"] / n_days, "w fali (z sąsiadem)": k["linked_share"],
            "fale ≥ 3 stacje / dzień": k["n_cascades_ge3"] / n_days, "największa fala": k["max_size"],
            "fale vs inny dzień (×)": (nl["inny_dzien"] or {}).get("linked_share", {}).get("ratio", np.nan),
            "p (inny dzień)": (nl["inny_dzien"] or {}).get("linked_share", {}).get("p", np.nan),
            "fale vs zamiana miejsc (×)": nl["zamiana_miejsc"]["linked_share"]["ratio"],
            "p (zamiana miejsc)": nl["zamiana_miejsc"]["linked_share"]["p"],
        }
    return pd.DataFrame(rows)


def compare(a, b, out_png=None, labels=("dane", "symulacja")):
    """Wykresy obok siebie dla dwoch raportow (albo katalogow): rytm, Lorenz, dlugosc pustek, fale, dzielnice."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    ra = a if isinstance(a, dict) else emergence_report(a, n_perm=200)
    rb = b if isinstance(b, dict) else emergence_report(b, n_perm=200)
    colors = ("#2b6cb0", "#dd6b20")
    fig, ax = plt.subplots(2, 3, figsize=(15, 8.5))
    for r, lab, c in zip((ra, rb), labels, colors):
        rh = r["rhythm"]
        w = rh[rh["day_kind"] == "roboczy"]
        ax[0, 0].plot(w["hour"], w["trips_per_day"], "-o", ms=3, color=c, label=lab)
        cc = r["concentration"]
        ax[0, 1].plot(cc["lorenz_x"], cc["lorenz_y"], color=c, label=f"{lab} (Gini {cc['gini']:.2f})")
        m = r["durations"]["minutes"]
        if len(m):
            ax[0, 2].hist(m, bins=np.arange(0, 245, 10), alpha=0.5, color=c, density=True,
                          label=f"{lab} (mediana {np.median(m):.0f} min)")
        sc = r["cascades"]["size_counts"]
        ks = sorted(k for k in sc if k >= 2)
        ax[1, 0].plot(ks, [sc[k] / max(len(r["days"]), 1) for k in ks], "-o", ms=4, color=c, label=lab)
    ax[0, 1].plot([0, 1], [0, 1], "k:", lw=0.8)
    ax[0, 0].set(title="Rytm dnia (dni robocze)", xlabel="godzina", ylabel="przejazdy / dzień")
    ax[0, 1].set(title="Skupienie pustek (krzywa Lorenza)", xlabel="udział stacji", ylabel="udział czasu pustek")
    ax[0, 2].set(title="Jak długo stacje są puste", xlabel="minuty", ylabel="gęstość")
    ax[1, 0].set(title="Fale pustek (sąsiad ≤ 800 m, ≤ 20 min)", xlabel="liczba stacji w fali",
                 ylabel="fale / dzień", yscale="log")
    da, db = ra["districts"], rb["districts"]
    if len(da) and len(db):
        x = np.arange(len(da))
        ax[1, 1].bar(x - 0.2, da["morning_net"], 0.4, color=colors[0], label=labels[0])
        ax[1, 1].bar(x + 0.2, db.set_index("district").reindex(da["district"])["morning_net"].fillna(0), 0.4,
                     color=colors[1], label=labels[1])
        ax[1, 1].set_xticks(x, da["district"], rotation=70, fontsize=8)
        ax[1, 1].axhline(0, color="k", lw=0.6)
    ax[1, 1].set(title="Bilans dzielnic rano 7–10 (przyjazdy − wyjazdy)", ylabel="rowery / dzień")
    tab = summary_table({labels[0]: ra, labels[1]: rb})
    keep = ["Gini pustek", "pustka: mediana [min]", "Moran I (pustki)", "w fali (z sąsiadem)", "fale ≥ 3 stacje / dzień",
            "fale vs zamiana miejsc (×)"]
    ax[1, 2].axis("off")
    cell = [[f"{tab.loc[k, c]:.2f}" if isinstance(tab.loc[k, c], float) else str(tab.loc[k, c]) for c in tab.columns]
            for k in keep]
    t = ax[1, 2].table(cellText=cell, rowLabels=keep, colLabels=list(tab.columns), loc="center")
    t.scale(1, 1.6)
    t.set_fontsize(9)
    for a_ in ax.flat[:5]:
        a_.grid(alpha=0.2)
        if a_.get_legend_handles_labels()[0]:
            a_.legend(fontsize=8)
    fig.tight_layout()
    if out_png:
        fig.savefig(out_png, dpi=130)
    plt.close(fig)
    return tab
