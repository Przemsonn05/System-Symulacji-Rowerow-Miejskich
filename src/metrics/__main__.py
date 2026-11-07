"""Raport emergencji dla danych i/lub symulacji.

    python -m src.metrics processed                                  # tylko dane
    python -m src.metrics processed --sim results/single             # dane vs symulacja (wykres obok siebie)
    python -m src.metrics processed --out docs/wyniki --perm 1000

Wynik w --out: emergencja.md (tabela metryk i testy), emergencja.png (dane vs symulacja), emergence.json.
"""

import argparse
import datetime as dt
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .emergence import compare, emergence_report, summary_table


def _clean(o):
    if isinstance(o, dict):
        return {str(k): _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating, float)):
        return None if not np.isfinite(o) else float(o)
    if isinstance(o, np.ndarray):
        return _clean(o.tolist())
    if isinstance(o, pd.DataFrame):
        return _clean(o.to_dict(orient="records"))
    if isinstance(o, pd.Series):
        return _clean(o.to_dict())
    if isinstance(o, (dt.date, pd.Timestamp)):
        return o.isoformat()
    return o


def markdown(reports, tab, png=None):
    lines = ["# Emergencja: pomiar zjawisk, których nikt nie zaprogramował", "",
             "Wygenerowane przez `python -m src.metrics`. Wszystkie metryki liczone z tabel stanów co 5 min "
             "(dane: `observed_timeseries`, symulacja: `station_timeseries`), tylko pełne dni.", "",
             "| metryka | " + " | ".join(tab.columns) + " |", "|---|" + "---|" * len(tab.columns)]
    for k, row in tab.iterrows():
        cells = [f"{v:.3g}" if isinstance(v, (float, np.floating)) and abs(v) < 1000 else
                 (f"{v:.0f}" if isinstance(v, (float, np.floating)) else str(v)) for v in row]
        lines.append(f"| {k} | " + " | ".join(cells) + " |")
    lines += ["", "## Jak czytać", "",
              "- **Gini pustek / 10% stacji**: skupienie czasu pustek na niewielu stacjach (H2).",
              "- **Moran I**: czy stacje często puste leżą obok siebie (sąsiad ≤ 1 km, wagi standaryzowane "
              "wierszami; 0 = brak wzoru, > 0 = skupiska). p z 999 permutacji.",
              "- **Fale pustek**: stacja pustoszeje, a w ciągu 20 min pustoszeje stacja do 800 m od niej; "
              "fala = spójny ciąg takich zdarzeń. „W fali” = udział chwil pustoszenia, które mają sąsiada w fali.",
              "- **Modele zerowe** (czy fale to nie przypadek): *inny dzień* – dla każdej stacji jej chwile "
              "pustoszenia z losowego innego dnia tego samego typu (zachowuje porę dnia i częstość pustek, zrywa "
              "powiązanie z sąsiadami tego dnia); *zamiana miejsc* – stacje o podobnym udziale pustek (decyle) "
              "zamieniają się położeniem. „×” = dane / średnia modelu zerowego, p = (1 + liczba prób ≥ dane) / "
              "(1 + liczba prób).", ""]
    for name, r in reports.items():
        nl = r["null"]
        lines += [f"## Testy fal: {name}", "", "| model zerowy | statystyka | dane | średnia modelu | 95% modelu | × | p |",
                  "|---|---|---|---|---|---|---|"]
        for model in ("inny_dzien", "zamiana_miejsc"):
            if not nl.get(model):
                lines.append(f"| {model} | – | brak (za mało dni tego samego typu) | | | | |")
                continue
            for stat, v in nl[model].items():
                lines.append(f"| {model} | {stat} | {nl['observed'][stat]:.3g} | {v['mean']:.3g} | {v['q95']:.3g} | "
                             f"{v['ratio']:.2f} | {v['p']:.3f} |")
        lines.append("")
    if png:
        lines += [f"![dane vs symulacja]({Path(png).name})", ""]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("data", nargs="?", default="processed")
    ap.add_argument("--sim", help="katalog przebiegu symulacji (station_timeseries.parquet)")
    ap.add_argument("--out", default="docs/wyniki")
    ap.add_argument("--perm", type=int, default=1000, help="liczba prób modelu zerowego")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    reports = {"dane": emergence_report(args.data, n_perm=args.perm)}
    if args.sim:
        reports["symulacja"] = emergence_report(args.sim, n_perm=args.perm)
    tab = summary_table(reports)
    png = None
    if args.sim:
        png = out / "emergencja.png"
        compare(reports["dane"], reports["symulacja"], png)
    (out / "emergencja.md").write_text(markdown(reports, tab, png), encoding="utf-8")
    slim = {k: {kk: vv for kk, vv in r.items() if kk not in ("durations", "empty_share")} for k, r in reports.items()}
    for k, r in reports.items():
        slim[k]["durations"] = {kk: vv for kk, vv in r["durations"].items() if kk != "minutes"}
    (out / "emergence.json").write_text(json.dumps(_clean(slim), ensure_ascii=False, indent=1), encoding="utf-8")
    print(tab.to_string())
    print(f"Zapisano {out / 'emergencja.md'}")


if __name__ == "__main__":
    main()
