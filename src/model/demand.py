"""Model popytu: regresja ujemna dwumianowa liczby wypozyczen na stacje x godzine.

Model do symulacji (TERMS):
  log lambda_i(t) = alpha_{i,blok} + gamma_{h,d} + b_T T + b_T2 T^2 + b_cong cong

Te 3 czynniki zewnetrzne wybrane na danych: najlepiej przewidywaly tydzien walidacji (lepiej niz
wszystkie 7). Pelny model do testow hipotez (TERMS_FULL) ma dodatkowo opad, zmrok,
zajecia x stacja przy uczelni i sobote.

Dopasowanie na macierzy rzadkiej (wlasne IRLS): ok. 1500 kolumn poziomow stacja x pora dnia i godzin
to prawie same zera, a gesta macierz w statsmodels zajmowala > 12 GB pamieci juz dla tygodnia danych.

- alpha_{i,blok}: wlasny poziom stacji w kazdym bloku pory dnia (noc, rano, poludnie, popoludnie,
  wieczor), wiec kazda stacja ma wlasny ksztalt doby (np. osiedle rano, centrum po poludniu);
  bloki z < MIN_BLOCK_DEPARTURES wypozyczen (zwykle noc) dziela wspolny poziom "reszta" stacji,
  bo przy zerze wypozyczen poziom bloku nie ma skonczonej wartosci,
- gamma_{h,d}: wspolny profil godzinowy w dni robocze i weekendy (ksztalt wewnatrz bloku),
- temperatura w prognozie jest przycinana do zakresu z danych do dopasowania: parabola oszacowana
  na 1-14 st. C poza tym zakresem rosnie bez sensu (25 st. C dawaloby x21),
- offset log(minuty z rowerem / 60): popyt na godzine, w ktorej stacja miala rowery (godziny pustej
  stacji sa ocenzurowane), godziny z < 15 min dostepnosci pominiete,
- "dzien zajec" sam w sobie nie wchodzi do modelu: w zebranych danych pokrywa sie z dniem roboczym
  (dodac, gdy beda dni robocze bez zajec - przerwa swiateczna, sesja).

Wynik: lambda = oczekiwana liczba chetnych do wypozyczenia na godzine.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd
import scipy.sparse as sp
import statsmodels.api as sm
from scipy import optimize, stats

from .data import BLOCKS, context_filled, load, time_block

MIN_AVAILABLE = 15
MIN_BLOCK_DEPARTURES = 10
T_REF, T_SCALE = 10.0, 5.0
# Godziny odniesienia profilu godzinowego: pierwsza godzina kazdego bloku w dzien roboczy. Bez tego
# profil godzinowy dublowalby poziomy stacja x blok (blok = suma swoich godzin).
REF_HOURS = {a for _, a, _ in BLOCKS}

# Czynniki zewnetrzne (obok poziomow stacja x pora dnia i godzin, ktore sa zawsze).
TERMS = ["temp", "temp2", "congestion"]
TERMS_FULL = TERMS + ["rain", "dark", "classes_near_uni", "saturday"]


def context_terms(ctx):
    """Zmienne zalezne tylko od czasu (wspolne dla wszystkich stacji)."""
    c = pd.DataFrame({"time": ctx["time"].to_numpy(), "local_date": ctx["local_date"].to_numpy()})
    hour = ctx["local_hour"].astype(int).to_numpy()
    weekend = (ctx["day_type"] != "workday").to_numpy()
    c["block"] = time_block(hour)
    c["hour_type"] = [("we" if w else "wd") + f"{h:02d}" for h, w in zip(hour, weekend)]
    c.loc[~weekend & np.isin(hour, list(REF_HOURS)), "hour_type"] = "ref"
    c["saturday"] = (ctx["day_type"] == "saturday").astype(float).to_numpy()
    c["rain"] = np.log1p(ctx["precipitation"].clip(lower=0)).to_numpy()
    c["temp"] = (ctx["temperature_2m"].to_numpy() - T_REF) / T_SCALE
    c["temp2"] = c["temp"] ** 2
    c["dark"] = ctx["is_dark"].astype(float).to_numpy()
    uni = ctx[["uw_classes_day", "pw_classes_day", "sgh_classes_day", "wum_classes_day"]].astype(bool).any(axis=1)
    c["uni_classes"] = uni.astype(float).to_numpy()
    c["congestion"] = ctx["congestion"].to_numpy()
    return c


def near_university(stations):
    """Stacje z uczelnia w promieniu 300 m (do H4)."""
    return set(stations.loc[stations["n_university_300m"] > 0, "station_id"])


def own_blocks(panel):
    """Pary stacja|blok z wlasnym poziomem: >= MIN_BLOCK_DEPARTURES wypozyczen w bloku i tyle samo
    w pozostalych ("reszta") blokach stacji, jesli jakies zostaja."""
    dep = panel.groupby(["station_id", "block"])["departures"].sum()
    own = dep[dep >= MIN_BLOCK_DEPARTURES]
    for sid, total in panel.groupby("station_id")["departures"].sum().items():
        mine = own[own.index.get_level_values(0) == sid].sort_values()
        while len(mine) and len(mine) < 5 and total - mine.sum() < MIN_BLOCK_DEPARTURES:
            mine = mine.iloc[1:]  # najmniejszy blok wraca do "reszty"
        own = own.drop(own.index[(own.index.get_level_values(0) == sid) & ~own.index.isin(mine.index)])
    return {f"{sid}|{b}" for sid, b in own.index}


def add_station_terms(p, near_uni, own):
    p = p.copy()
    key = p["station_id"] + "|" + p["block"]
    p["station_block"] = key.where(key.isin(own), p["station_id"] + "|reszta")
    p["classes_near_uni"] = p["uni_classes"] * p["station_id"].isin(near_uni)
    return p


def build_panel(days):
    """station_hourly + kontekst, tylko godziny z wystarczajaca dostepnoscia."""
    h = load("station_hourly")
    stations = load("stations")
    c = context_terms(context_filled())
    p = h.merge(c, left_on="hour", right_on="time", how="inner")
    p = p[p["local_date"].isin(set(days)) & (p["minutes_available"] >= MIN_AVAILABLE)
          & p["station_id"].isin(set(stations["station_id"]))]
    p = add_station_terms(p.reset_index(drop=True), near_university(stations), own_blocks(p))
    p["exposure"] = p["minutes_available"] / 60.0
    return p


def design(p, levels, terms):
    """Macierz rzadka [stacja x pora dnia | godzina (bez "ref") | czynniki]; levels z dopasowania."""
    rows = np.arange(len(p))

    def dummies(values, categories):
        code = pd.Categorical(values, categories=categories).codes
        ok = code >= 0
        return sp.csr_matrix((np.ones(ok.sum()), (rows[ok], code[ok])), shape=(len(p), len(categories)))

    return sp.hstack([dummies(p["station_block"], levels[0]), dummies(p["hour_type"], levels[1]),
                      sp.csr_matrix(p[terms].to_numpy(float))], format="csr")


def _irls(X, y, offset, alpha, beta, max_iter=100, tol=1e-9):
    """IRLS dla regresji ujemnej dwumianowej z log-linkiem (alpha = 0: Poisson).
    Zwraca wspolczynniki i macierz informacji X'WX (mala, gesta: kolumny x kolumny)."""
    family = sm.families.NegativeBinomial(alpha=alpha) if alpha > 0 else sm.families.Poisson()
    ll_old = -np.inf
    for _ in range(max_iter):
        mu = np.exp(X @ beta + offset)
        w = mu / (1 + alpha * mu)
        XtW = X.T.multiply(w).tocsr()
        info = (XtW @ X).toarray()
        beta = np.linalg.solve(info, XtW @ (X @ beta + (y - mu) / mu))
        ll = family.loglike(y, np.exp(X @ beta + offset))
        if abs(ll - ll_old) < tol * (abs(ll) + 1):
            break
        ll_old = ll
    mu = np.exp(X @ beta + offset)
    return beta, (X.T.multiply(mu / (1 + alpha * mu)).tocsr() @ X).toarray()


@dataclass
class NBFit:
    params: pd.Series
    bse: pd.Series
    pvalues: pd.Series
    llf: float
    nb_alpha: float
    levels: tuple
    terms: list
    temp_range: tuple


def fit_nb(panel, terms=TERMS, cluster_by_time=False):
    """Regresja NB2. alpha (nadmierna dyspersja) z najwiekszej wiarygodnosci przy srednich z modelu Poissona.

    cluster_by_time: odporne bledy standardowe klastrowane po godzinie (pogoda i korki sa wspolne dla
    wszystkich stacji w danej godzinie, wiec obserwacje stacja x godzina nie sa niezalezne)."""
    levels = (sorted(panel["station_block"].unique()), sorted(set(panel["hour_type"]) - {"ref"}))
    X = design(panel, levels, terms)
    y = panel["departures"].to_numpy(float)
    offset = np.log(panel["exposure"].to_numpy())
    # start: poziom stacja x pora dnia = log(wypozyczenia / godziny dostepnosci)
    level = panel.groupby("station_block")[["departures", "exposure"]].sum().reindex(levels[0])
    beta = np.zeros(X.shape[1])
    beta[:len(levels[0])] = np.log((level["departures"] + 0.5) / level["exposure"]).to_numpy()
    beta, _ = _irls(X, y, offset, 0.0, beta)
    mu = np.exp(X @ beta + offset)
    res = optimize.minimize_scalar(lambda la: -sm.families.NegativeBinomial(alpha=np.exp(la)).loglike(y, mu),
                                   bounds=(-8, 3), method="bounded")
    alpha = float(np.exp(res.x))
    beta, info = _irls(X, y, offset, alpha, beta)
    mu = np.exp(X @ beta + offset)
    cov = np.linalg.inv(info)
    if cluster_by_time:
        # sandwich: suma wkladow do pochodnej wiarygodnosci w kazdej godzinie
        g = pd.factorize(panel["time"])[0]
        G = sp.csr_matrix((np.ones(len(g)), (g, np.arange(len(g)))))
        S = (G @ X.multiply(((y - mu) / (1 + alpha * mu))[:, None]).tocsr()).toarray()
        n, k, ng = X.shape[0], X.shape[1], G.shape[0]
        cov = ng / (ng - 1) * (n - 1) / (n - k) * cov @ (S.T @ S) @ cov
    names = [f"st:{b}" for b in levels[0]] + [f"h:{h}" for h in levels[1]] + list(terms)
    params = pd.Series(beta, index=names)
    bse = pd.Series(np.sqrt(np.diag(cov)), index=names)
    return NBFit(params, bse, pd.Series(2 * stats.norm.sf(np.abs(params / bse)), index=names),
                 float(sm.families.NegativeBinomial(alpha=alpha).loglike(y, mu)), alpha, levels, list(terms),
                 (panel["temp"].min(), panel["temp"].max()))


class DemandModel:
    """lambda(stacja, godzina) dla symulacji: rate(station_ids, ctx) -> [godziny x stacje].

    Stacje, ktorych nie bylo w danych do dopasowania, dostaja lambda = 0."""

    def __init__(self, fit, stations):
        self.alpha = fit.nb_alpha
        self.params = fit.params
        self.levels, self.terms, self.temp_range = fit.levels, fit.terms, fit.temp_range
        self.own = set(fit.levels[0])
        self.known = {b.split("|")[0] for b in self.own}
        self.near_uni = near_university(stations)

    def predict(self, q):
        """Oczekiwane wypozyczenia na godzine pelnej dostepnosci dla wierszy z context_terms + station_id."""
        temp = q["temp"].clip(*self.temp_range)
        q = add_station_terms(q.assign(temp=temp, temp2=temp ** 2), self.near_uni, self.own)
        return np.exp(design(q, self.levels, self.terms) @ self.params.to_numpy())

    def rate(self, station_ids, ctx):
        c = context_terms(ctx.reset_index(drop=True))
        p = c.loc[c.index.repeat(len(station_ids))].reset_index(drop=True)
        p["station_id"] = np.tile(np.asarray(station_ids), len(c))
        known = p["station_id"].isin(self.known).to_numpy()
        out = np.zeros(len(p))
        out[known] = self.predict(p[known])
        return out.reshape(len(c), len(station_ids))


def fit_demand(days):
    return DemandModel(fit_nb(build_panel(days)), load("stations"))
