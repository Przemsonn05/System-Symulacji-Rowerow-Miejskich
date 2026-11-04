"""Model popytu: regresja ujemna dwumianowa liczby wypozyczen na stacje x godzine.

log lambda_i(t) = alpha_{i,blok} + s_{h,d} + b_rain R + b_T T + b_T2 T^2 + b_dark dark
                  + b_cal (zajecia x stacja przy uczelni) + b_cong cong

- alpha_{i,blok}: wlasny poziom stacji w kazdym bloku pory dnia (noc, rano, poludnie, popoludnie,
  wieczor), wiec kazda stacja ma wlasny ksztalt doby (np. osiedle rano, centrum po poludniu);
  bloki z < MIN_BLOCK_DEPARTURES wypozyczen (zwykle noc) dziela wspolny poziom "reszta" stacji,
  bo przy zerze wypozyczen poziom bloku nie ma skonczonej wartosci,
- s_{h,d}: wspolny profil godzinowy w dni robocze i weekendy (ksztalt wewnatrz bloku) + sobota,
- offset log(minuty z rowerem / 60): popyt na godzine, w ktorej stacja miala rowery (godziny pustej
  stacji sa ocenzurowane), godziny z < 15 min dostepnosci pominiete,
- "dzien zajec" sam w sobie nie wchodzi do modelu: w zebranych danych pokrywa sie z dniem roboczym
  (dodac, gdy beda dni robocze bez zajec - przerwa swiateczna, sesja).

Wynik: lambda = oczekiwana liczba chetnych do wypozyczenia na godzine.
"""

import numpy as np
import pandas as pd
import patsy
import statsmodels.api as sm
import statsmodels.formula.api as smf
from scipy import optimize

from .data import BLOCKS, context_filled, load, time_block

MIN_AVAILABLE = 15
MIN_BLOCK_DEPARTURES = 10
T_REF, T_SCALE = 10.0, 5.0
# Godziny odniesienia profilu godzinowego: pierwsza godzina kazdego bloku w dzien roboczy. Bez tego
# profil godzinowy dublowalby poziomy stacja x blok (blok = suma swoich godzin).
REF_HOURS = {a for _, a, _ in BLOCKS}

FORMULA = ("departures ~ 0 + C(station_block) + C(hour_type, Treatment('ref')) + saturday"
           " + rain + temp + temp2 + dark + classes_near_uni + congestion")


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


def fit_nb(panel, formula=FORMULA, cluster_by_time=False):
    """GLM NB2. alpha (nadmierna dyspersja) z najwiekszej wiarygodnosci przy srednich z modelu Poissona.

    cluster_by_time: odporne bledy standardowe klastrowane po godzinie (pogoda i korki sa wspolne dla
    wszystkich stacji w danej godzinie, wiec obserwacje stacja x godzina nie sa niezalezne)."""
    offset = np.log(panel["exposure"].to_numpy())
    pois = smf.glm(formula, panel, offset=offset, family=sm.families.Poisson()).fit()
    y, mu = pois.model.endog, pois.fittedvalues
    res = optimize.minimize_scalar(lambda la: -sm.families.NegativeBinomial(alpha=np.exp(la)).loglike(y, mu),
                                   bounds=(-8, 3), method="bounded")
    alpha = float(np.exp(res.x))
    kw = {"cov_type": "cluster", "cov_kwds": {"groups": pd.factorize(panel["time"])[0]}} if cluster_by_time else {}
    fit = smf.glm(formula, panel, offset=offset, family=sm.families.NegativeBinomial(alpha=alpha)).fit(
        start_params=pois.params, **kw)
    fit.nb_alpha = alpha
    return fit


class DemandModel:
    """lambda(stacja, godzina) dla symulacji: rate(station_ids, ctx) -> [godziny x stacje].

    Stacje, ktorych nie bylo w danych do dopasowania, dostaja lambda = 0."""

    def __init__(self, fit, stations):
        self.alpha = fit.nb_alpha
        self.params = fit.params
        self.formula = fit.model.formula
        self.near_uni = near_university(stations)
        frame = fit.model.data.frame
        self.known = set(frame["station_id"])
        self.own = set(frame["station_block"])
        # po jednym wierszu na kazda kategorie: z nimi patsy odtworzy te same kolumny co przy dopasowaniu
        self.template = pd.concat([frame.drop_duplicates("station_block"), frame.drop_duplicates("hour_type")])

    def predict(self, q):
        rhs = self.formula.split("~", 1)[1]
        X = patsy.dmatrix(rhs, pd.concat([self.template, q]), return_type="dataframe").iloc[len(self.template):]
        return np.exp(X[self.params.index].to_numpy() @ self.params.to_numpy())

    def rate(self, station_ids, ctx):
        c = context_terms(ctx.reset_index(drop=True))
        p = c.loc[c.index.repeat(len(station_ids))].reset_index(drop=True)
        p["station_id"] = np.tile(np.asarray(station_ids), len(c))
        known = p["station_id"].isin(self.known).to_numpy()
        out = np.zeros(len(p))
        out[known] = self.predict(add_station_terms(p[known], self.near_uni, self.own))
        return out.reshape(len(c), len(station_ids))


def fit_demand(days):
    return DemandModel(fit_nb(build_panel(days)), load("stations"))
