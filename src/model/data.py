"""Wczytanie processed/ i wspolne przygotowanie danych dla modeli."""

import datetime as dt
import pickle

import numpy as np
import pandas as pd

from ..data.config import PROCESSED, STATIC, TZ

OUT = PROCESSED / "model"

# Podzial czasowy (daty lokalne, wlacznie). Kalibracja na wczesniejszych dniach, test na pozniejszych.
CALIB = (dt.date(2026, 10, 23), dt.date(2026, 10, 29))
VALID = (dt.date(2026, 10, 30), dt.date(2026, 11, 4))

# Bloki pory dnia: wlasny poziom popytu stacji w kazdym bloku i osobne macierze OD.
BLOCKS = [("noc", 0, 6), ("rano", 6, 10), ("poludnie", 10, 15), ("popoludnie", 15, 19), ("wieczor", 19, 24)]


def days(first, last):
    return [first + dt.timedelta(days=i) for i in range((last - first).days + 1)]


def time_block(local_hour):
    h = np.asarray(local_hour)
    out = np.empty(h.shape, dtype=object)
    for name, a, b in BLOCKS:
        out[(h >= a) & (h < b)] = name
    return out


def load(name):
    return pd.read_parquet(PROCESSED / f"{name}.parquet")


def user_trips():
    """Przejazdy uzytkownikow bez bledow feedu (jak w README)."""
    t = load("trips")
    t = t[(t["type"] == "user") & ~t["is_flicker"] & ~t["too_fast"] & ~t["is_long"]].copy()
    local = t["t_departure"].dt.tz_convert(TZ)
    t["local_date"] = local.dt.date
    t["local_hour"] = local.dt.hour
    return t


def _straight_km(station_ids, stations):
    s = stations.set_index("station_id").reindex(station_ids)
    lat, lon = np.radians(s["lat"].to_numpy()), np.radians(s["lon"].to_numpy())
    a = (np.sin((lat[:, None] - lat[None, :]) / 2) ** 2
         + np.cos(lat[:, None]) * np.cos(lat[None, :]) * np.sin((lon[:, None] - lon[None, :]) / 2) ** 2)
    return 2 * 6371.0 * np.arcsin(np.sqrt(a))


def distance_matrix(station_ids, stations):
    """Odleglosc [km] po drogach rowerowych miedzy stacjami; brakujace pary: linia prosta x 1.3."""
    d = _straight_km(station_ids, stations) * 1.3
    net = pd.read_parquet(STATIC / "station_network_distance.parquet")
    idx = {sid: k for k, sid in enumerate(station_ids)}
    i, j = net["from_station"].map(idx), net["to_station"].map(idx)
    ok = i.notna() & j.notna() & net["network_km"].notna()
    d[i[ok].astype(int), j[ok].astype(int)] = net.loc[ok, "network_km"].to_numpy()
    np.fill_diagonal(d, 0.0)
    return d


def walk_matrix_m(station_ids, stations):
    """Odleglosc piesza [m] miedzy stacjami (linia prosta x 1.2)."""
    return _straight_km(station_ids, stations) * 1200.0


def context_filled():
    """Kontekst godzinowy z uzupelnionymi brakami pogody i korkow.

    Pogoda z Open-Meteo bywa opozniona o kilkanascie godzin: brakujace godziny dostaja temperature
    z interpolacji i opad 0 (kolumna weather_imputed=True)."""
    c = load("context_hourly").sort_values("time").reset_index(drop=True)
    c["weather_imputed"] = c["temperature_2m"].isna() | c["precipitation"].isna()
    c["temperature_2m"] = c["temperature_2m"].interpolate(limit_direction="both")
    c["precipitation"] = c["precipitation"].fillna(0.0)
    # Korki: brak pomiaru (np. noc 22.10) -> mediana dla tej godziny lokalnej.
    c["congestion"] = c["congestion"].fillna(c.groupby("local_hour")["congestion"].transform("median")).fillna(0.0)
    return c


def sim_station_ids(stations):
    """Stacje symulacji: aktywne w pomiarach i opisane w stations (bez punktow spoza listy stacji)."""
    return sorted(set(load("observed_timeseries")["station_id"]) & set(stations["station_id"]))


def save(obj, name):
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / name, "wb") as fh:
        pickle.dump(obj, fh)
