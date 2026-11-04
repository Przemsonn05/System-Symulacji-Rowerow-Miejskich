"""Testy hipotez H1, H4, H5a na modelu popytu (wszystkie dostepne dni, nie tylko kalibracyjne).

Wspolczynniki raportowane jako ilorazy intensywnosci (IRR = exp(b)) z 95% CI. Bledy standardowe sa
odporne i klastrowane po godzinie: pogoda, korki i kalendarz sa wspolne dla wszystkich stacji w danej
godzinie, wiec obserwacje stacja x godzina nie sa niezalezne. Test LR czlonu T^2 (wymagany w planie)
zaklada niezaleznosc i jest przez to zbyt optymistyczny - rozstrzyga p z tabeli wspolczynnikow.
"""

import numpy as np
import pandas as pd
from scipy import stats

from .demand import FORMULA, T_REF, T_SCALE, build_panel, fit_nb

COEFS = ["rain", "temp", "temp2", "dark", "classes_near_uni", "congestion", "saturday"]


def run(days, log=print):
    panel = build_panel(days)
    log("  model pelny (bledy klastrowane po godzinie)...")
    full = fit_nb(panel, FORMULA, cluster_by_time=True)
    b, se = full.params[COEFS], full.bse[COEFS]
    coef = pd.DataFrame({"b": b, "IRR": np.exp(b), "CI_lo": np.exp(b - 1.96 * se), "CI_hi": np.exp(b + 1.96 * se),
                         "p": full.pvalues[COEFS]})
    log("  test LR czlonu T^2...")
    restricted = fit_nb(panel, FORMULA.replace(" + temp2", ""))
    lr = 2 * (full.llf - restricted.llf)
    w = panel.drop_duplicates("time")
    return {
        "n_obs": len(panel), "n_days": len(set(days)), "alpha": full.nb_alpha, "coef": coef,
        "lr_temp2": {"LR": float(lr), "p": float(stats.chi2.sf(lr, 1))},
        "temp_vertex_C": float(T_REF - T_SCALE * b["temp"] / (2 * b["temp2"])),
        "range": {"temp_min": w["temp"].min() * T_SCALE + T_REF, "temp_max": w["temp"].max() * T_SCALE + T_REF,
                  "rain_hours": int((w["rain"] > np.log1p(0.1)).sum()), "hours": len(w),
                  "congestion_min": w["congestion"].min(), "congestion_max": w["congestion"].max()},
    }
