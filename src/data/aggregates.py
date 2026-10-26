"""Tabele pochodne dla modelu: okresy pustych stacji, stacja x godzina, flota, bilans."""

import gzip
import json

import numpy as np
import pandas as pd

from .config import DATA

STEP_MIN = 5  # odstep pomiarow
BREAK_GAP_MIN = 15  # dluzsza luka przerywa okres (nie wiadomo, co dzialo sie w srodku)


def empty_periods(obs):
    """Okresy, w ktorych stacja byla pusta - popyt w nich jest ocenzurowany.

    start = pierwszy pomiar z bikes == 0, end = pierwszy pomiar z rowerami
    (albo ostatni pomiar + 5 min, gdy okres trwa do konca danych / do luki).
    """
    o = obs[["station_id", "time", "is_empty"]].sort_values(["station_id", "time"])
    gap = o.groupby("station_id")["time"].diff().dt.total_seconds() / 60
    new_run = (o["is_empty"] != o.groupby("station_id")["is_empty"].shift()) | (gap > BREAK_GAP_MIN)
    o["run"] = new_run.cumsum()
    runs = o[o["is_empty"]].groupby("run").agg(station_id=("station_id", "first"), start=("time", "min"),
                                              last=("time", "max"), n_obs=("time", "size"))
    # koniec = nastepny pomiar tej stacji, jesli nastepuje bez luki
    nxt = o.groupby("station_id")["time"].shift(-1)
    nxt_gap = (nxt - o["time"]).dt.total_seconds() / 60
    end_of_run = o.assign(nxt=nxt, nxt_gap=nxt_gap).groupby("run").last()
    runs = runs.join(end_of_run[["nxt", "nxt_gap"]])
    closed = runs["nxt"].notna() & (runs["nxt_gap"] <= BREAK_GAP_MIN)
    runs["end"] = runs["nxt"].where(closed, runs["last"] + pd.Timedelta(minutes=STEP_MIN))
    runs["censored_end"] = ~closed  # nie wiemy, kiedy naprawde sie skonczyl
    runs["duration_min"] = (runs["end"] - runs["start"]).dt.total_seconds() / 60
    return runs[["station_id", "start", "end", "duration_min", "n_obs", "censored_end"]].reset_index(drop=True)


def _clean_user(trips):
    """Przejazdy uzytkownikow bez artefaktow feedu i wycofan do serwisu."""
    return trips[(trips["type"] == "user") & ~trips["is_flicker"] & ~trips["too_fast"] & ~trips["is_long"]]


def station_hourly(obs, trips):
    """Stacja x godzina (UTC): wypozyczenia, zwroty i czas dostepnosci do kalibracji popytu.

    Zdarzenie przypisujemy do srodka odstepu pomiarow, w ktorym nastapilo
    (odjazd: t_departure + 2,5 min, przyjazd: t_arrival - 2,5 min).
    """
    half = pd.Timedelta(minutes=STEP_MIN / 2)
    o = obs.assign(hour=obs["time"].dt.floor("h"))
    base = o.groupby(["station_id", "hour"]).agg(
        n_obs=("bikes", "size"),
        mean_bikes=("bikes", "mean"),
        min_bikes=("bikes", "min"),
        n_empty=("is_empty", "sum"),
        n_overfull=("is_overfull", "sum"),
        mean_ebikes=("ebikes", "mean"),
    )
    base["minutes_observed"] = base.pop("n_obs") * STEP_MIN
    base["minutes_empty"] = base.pop("n_empty") * STEP_MIN
    base["minutes_overfull"] = base.pop("n_overfull") * STEP_MIN
    base["minutes_available"] = base["minutes_observed"] - base["minutes_empty"]

    def count(df, side, t_col, shift, name):
        """side = "from" (odjazdy) albo "to" (przyjazdy)."""
        s = df[df[f"{side}_type"] == "station"]
        h = (s[t_col] + shift).dt.floor("h")
        return s.groupby([s[f"{side}_station"].rename("station_id"), h.rename("hour")]).size().rename(name)

    user = _clean_user(trips)
    service = trips[trips["type"] == "service"]
    parts = [
        count(user, "from", "t_departure", half, "departures"),
        count(user, "to", "t_arrival", -half, "arrivals"),
        count(user[user["bike"].isin(_ebikes(trips))], "from", "t_departure", half, "departures_ebike"),
        count(service, "from", "t_departure", half, "service_out"),
        count(service, "to", "t_arrival", -half, "service_in"),
    ]
    out = base.join(pd.concat(parts, axis=1), how="left")
    cnt = ["departures", "arrivals", "departures_ebike", "service_out", "service_in"]
    out[cnt] = out[cnt].fillna(0).astype(int)
    # wypozyczenia na godzine dostepnosci roweru = estymator intensywnosci z korekta na pusta stacje
    out["departure_rate_per_h"] = (out["departures"] / (out["minutes_available"] / 60)).where(
        out["minutes_available"] > 0)
    out["mean_bikes"] = out["mean_bikes"].round(2)
    out["mean_ebikes"] = out["mean_ebikes"].astype(float).round(2)
    out["departure_rate_per_h"] = out["departure_rate_per_h"].round(3)
    return out.reset_index()


def _ebikes(trips):
    return set(trips.loc[trips["is_ebike"], "bike"]) if "is_ebike" in trips else set()


def read_system():
    """Dzienne pliki data/system: docelowa i dostepna flota wg operatora."""
    rows = []
    for path in sorted((DATA / "system").glob("*.json.gz")):
        with gzip.open(path, "rt", encoding="utf-8") as f:
            s = json.load(f)
        city = (s.get("live_city") or [{}])[0]
        rows.append({"day": path.name[:10], "set_point_bikes": city.get("set_point_bikes"),
                     "operator_available_bikes": city.get("available_bikes")})
    return pd.DataFrame(rows)


def fleet_timeseries(fleet):
    """Flota w kazdym pomiarze + docelowa wielkosc floty operatora (set_point_bikes)."""
    f = fleet.copy()
    f["seen_total"] = f[["at_stations", "loose_warsaw", "loose_outside", "in_use"]].sum(axis=1, min_count=4)
    sysd = read_system()
    if not sysd.empty:
        f["day"] = f["time"].dt.strftime("%Y-%m-%d")
        f = f.merge(sysd, on="day", how="left").drop(columns="day")
    return f


def flow_balance(obs, trips):
    """Kontrola jakosci przejazdow: czy zmiana liczby rowerow na stacji miedzy pomiarami
    = przyjazdy - odjazdy (wszystkie odtworzone, takze serwis i artefakty).

    Zwraca (udzial odstepow z dokladnym bilansem, udzial zmian liczby rowerow
    niewyjasnionych przez przejazdy)."""
    o = obs[["station_id", "time", "bikes"]].sort_values(["station_id", "time"]).copy()
    o["t0"] = o.groupby("station_id")["time"].shift()
    o["delta"] = o.groupby("station_id")["bikes"].diff()
    o = o.dropna(subset=["delta"])
    st = trips
    dep = st[st["from_type"] == "station"].groupby(["from_station", "t_departure"]).size().rename("dep")
    arr = st[st["to_type"] == "station"].groupby(["to_station", "t_arrival"]).size().rename("arr")
    o = o.merge(dep, left_on=["station_id", "t0"], right_index=True, how="left")
    o = o.merge(arr, left_on=["station_id", "time"], right_index=True, how="left")
    # odstepy po pomiarach w starym formacie (bez numerow rowerow) nie maja przejazdow
    o = o[o["time"] > trips["t_departure"].min()] if len(trips) else o.iloc[0:0]
    err = o["delta"] - (o["arr"].fillna(0) - o["dep"].fillna(0))
    exact = float((err == 0).mean()) if len(o) else np.nan
    unexplained = float(err.abs().sum() / o["delta"].abs().sum()) if len(o) else np.nan
    return exact, unexplained
