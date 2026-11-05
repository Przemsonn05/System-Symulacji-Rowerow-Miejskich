"""Czas jazdy: rozklad log-normalny zalezny od odleglosci, osobno e-rowery i powroty na te sama stacje.

log T ~ N(a + b log d + c ebike, sigma)     (d = km po drogach rowerowych)

Czas z danych pochodzi z roznicy pomiarow co 5 min, wiec prawdziwy czas lezy w przedziale
(T_obs - 5, T_obs + 5): wiarygodnosc liczona jest jak dla danych przedzialowych (CDF, nie gestosc).
"""

import numpy as np
import pandas as pd
from scipy import optimize, stats

HALF_WIDTH = 5.0


def _interval_nll(x, logd, ebike, lo, hi):
    a, b, c, log_s = x
    mu = a + b * logd + c * ebike
    s = np.exp(log_s)
    p = stats.norm.cdf((np.log(hi) - mu) / s) - stats.norm.cdf((np.log(lo) - mu) / s)
    return -np.sum(np.log(np.clip(p, 1e-12, None)))


def _bounds(dur):
    return np.clip(dur - HALF_WIDTH, 0.5, None), dur + HALF_WIDTH


class DurationModel:
    def fit(self, trips):
        t = trips[~trips["from_loose"] & ~trips["to_loose"]]
        dist = t["network_km"].fillna(t["distance_km"] * 1.3)
        ride = t[~t["same_station"] & (dist > 0.05)]
        d = dist.loc[ride.index]
        lo, hi = _bounds(ride["duration_min"].to_numpy())
        res = optimize.minimize(_interval_nll, x0=[2.0, 0.6, -0.1, np.log(0.4)],
                                args=(np.log(d.to_numpy()), ride["is_ebike"].to_numpy(float), lo, hi),
                                method="Nelder-Mead", options={"maxiter": 4000, "xatol": 1e-4, "fatol": 1e-2})
        self.a, self.b, self.c, log_s = res.x
        self.sigma = float(np.exp(log_s))
        rt = t[t["same_station"]]
        lo, hi = _bounds(rt["duration_min"].to_numpy())
        res = optimize.minimize(lambda x: _interval_nll([x[0], 0, 0, x[1]], 0.0, 0.0, lo, hi),
                                x0=[2.5, np.log(0.8)], method="Nelder-Mead")
        self.round_mu, self.round_sigma = float(res.x[0]), float(np.exp(res.x[1]))
        self.n = len(ride)
        self.check = self._check(ride, d)
        return self

    def mu(self, km, ebike=False):
        return self.a + self.b * np.log(np.maximum(km, 0.05)) + self.c * np.asarray(ebike, float)

    def sample(self, km, rng, ebike=False):
        km = np.asarray(km, float)
        out = np.exp(self.mu(km, ebike) + self.sigma * rng.standard_normal(km.shape))
        rt = km <= 0.05
        if rt.any():
            out[rt] = np.exp(self.round_mu + self.round_sigma * rng.standard_normal(rt.sum()))
        return out

    def mean_minutes(self, km):
        """Sredni czas jazdy (interfejs symulacji src/simulation: mnozony przez losowy czynnik
        log-normalny o sredniej 1 i odchyleniu ride_sigma = self.sigma)."""
        if km <= 0.05:
            return float(np.exp(self.round_mu + self.round_sigma ** 2 / 2))
        return float(np.exp(self.mu(km) + self.sigma ** 2 / 2))

    def _check(self, ride, d):
        """Udzial przejazdow <= 20 min (darmowe) w danych vs w modelu; mediany czasu."""
        rng = np.random.default_rng(0)
        sim = self.sample(d.to_numpy(), rng, ride["is_ebike"].to_numpy())
        # dane maja rozdzielczosc 5 min: porownujemy po zaokragleniu symulacji tak samo
        sim5 = np.round(sim / 5) * 5
        return pd.Series({
            "udzial_do_20_min_dane": float((ride["duration_min"] <= 20).mean()),
            "udzial_do_20_min_model": float((sim5 <= 20).mean()),
            "mediana_dane_min": float(ride["duration_min"].median()),
            "mediana_model_min": float(np.median(sim5)),
            "predkosc_mediana_kmh": float(np.median(d / (np.exp(self.mu(d.to_numpy(), False)) / 60))),
        })

    def params(self):
        return {"a": self.a, "b": self.b, "c_ebike": self.c, "sigma": self.sigma,
                "round_trip_mu": self.round_mu, "round_trip_sigma": self.round_sigma}
