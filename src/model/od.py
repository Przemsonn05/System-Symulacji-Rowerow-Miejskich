"""Model celu podrozy: empiryczna macierz OD + model grawitacyjny.

Grawitacja: P(j | i, s) ~ A_{j,s} * exp(-beta * d_ij), dla j = i: A_{i,s} * exp(delta)
  s = przedzial czasu (blok pory dnia x dzien roboczy/weekend), A_{j,s} = udzial przyjazdow na j,
  d_ij = odleglosc po drogach rowerowych [km], delta = osobna waga powrotow na te sama stacje.
beta, delta z najwiekszej wiarygodnosci na rzeczywistych przejazdach.

Do symulacji: macierz empiryczna wygladzona grawitacja (P = (C + k G) / (n + k)), wiec rzadkie
relacje dostaja prawdopodobienstwo z modelu, a czeste zostaja jak w danych. Dla nowej stacji
wystarczy jej A_j i odleglosci.
"""

import numpy as np
import pandas as pd
from scipy import optimize
from scipy.spatial import cKDTree

from .data import BLOCKS, distance_matrix, load, time_block

BLOCK_NAMES = [b for b, _, _ in BLOCKS]
N_SLOTS = 2 * len(BLOCK_NAMES)
SMOOTH_K = 10.0


def slot_index(local_hour, weekend):
    b = pd.Series(time_block(local_hour)).map({n: k for k, n in enumerate(BLOCK_NAMES)}).to_numpy()
    return b + len(BLOCK_NAMES) * np.asarray(weekend, dtype=int)


def count_matrix(trips, station_ids, stations):
    """Liczba przejazdow [sloty x skad x dokad]. Przejazdy konczace sie poza stacja -> najblizsza
    stacja; zaczynajace sie poza stacja sa pomijane (nie sa popytem stacji)."""
    idx = {s: k for k, s in enumerate(station_ids)}
    t = trips[~trips["from_loose"]].copy()
    t["i"] = t["from_station"].map(idx)
    t["j"] = t["to_station"].map(idx)
    st = stations.set_index("station_id").reindex(station_ids)
    scale = np.cos(np.radians(52.2))
    miss = t["j"].isna() & t["to_lat"].notna()
    _, nn = cKDTree(np.c_[st["lat"], st["lon"] * scale]).query(np.c_[t.loc[miss, "to_lat"], t.loc[miss, "to_lon"] * scale])
    t.loc[miss, "j"] = nn
    t = t.dropna(subset=["i", "j"])
    ctx = load("context_hourly")
    weekend = t["local_date"].isin(set(ctx.loc[ctx["day_type"] != "workday", "local_date"]))
    C = np.zeros((N_SLOTS, len(station_ids), len(station_ids)))
    np.add.at(C, (slot_index(t["local_hour"], weekend), t["i"].astype(int), t["j"].astype(int)), 1.0)
    return C


def gravity(A, D, beta, delta):
    """A: [sloty x stacje] atrakcyjnosc, D: [stacje x stacje] km. Zwraca P [sloty x i x j]."""
    K = np.exp(-beta * D)
    np.fill_diagonal(K, np.exp(delta))
    W = A[:, None, :] * K[None, :, :]
    return W / W.sum(axis=2, keepdims=True)


def loglik(C, P):
    m = C > 0
    return float(np.sum(C[m] * np.log(np.clip(P[m], 1e-12, None))))


class OdModel:
    def fit(self, trips, station_ids, stations):
        self.station_ids = list(station_ids)
        self.D = distance_matrix(self.station_ids, stations)
        C = count_matrix(trips, self.station_ids, stations)
        arr = C.sum(axis=1) + 0.5
        self.A = arr / arr.sum(axis=1, keepdims=True)
        res = optimize.minimize(lambda x: -loglik(C, gravity(self.A, self.D, *x)), x0=[0.8, 0.0], method="Nelder-Mead")
        self.beta, self.delta = map(float, res.x)
        self.n_trips = int(C.sum())
        self.P = (C + SMOOTH_K * self.gravity()) / (C.sum(axis=2, keepdims=True) + SMOOTH_K)
        # empiryczna z minimalnym wygladzeniem (bez zer), tylko do porownania w evaluate()
        self.E = (C + 0.01) / (C.sum(axis=2, keepdims=True) + 0.01 * C.shape[2])
        return self

    def gravity(self):
        return gravity(self.A, self.D, self.beta, self.delta)

    def probs(self, slot):
        return self.P[slot]

    def evaluate(self, trips, stations):
        """Porownanie na innych przejazdach: log-wiarygodnosc na przejazd (wyzej = lepiej) i CPC
        przeplywow (1 = identyczne macierze)."""
        C = count_matrix(trips, self.station_ids, stations)
        n = C.sum(axis=2, keepdims=True)
        rows = []
        for name, P in [("empiryczna", self.E), ("grawitacyjna", self.gravity()),
                        ("empiryczna + grawitacja (symulacja)", self.P)]:
            cpc = 2 * np.minimum(n * P, C).sum() / (2 * C.sum())
            rows.append({"model": name, "loglik_na_przejazd": loglik(C, P) / C.sum(), "CPC": cpc})
        return pd.DataFrame(rows).set_index("model")

    def __getstate__(self):
        d = self.__dict__.copy()
        d.pop("E", None)
        return d
