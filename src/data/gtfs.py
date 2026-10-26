"""Komunikacja miejska: liczba odjazdow z przystankow w typowy dzien roboczy (GTFS).

Zrodlo: GTFS Warszawy (ZTM: autobusy, tramwaje, metro, SKM) publikowany przez
mkuran.pl na podstawie danych ZTM (aktualizowany codziennie). Rozklad to stan
z dnia pobrania - zmiany rozkladow w czasie nie sa uwzgledniane.

Wynik: data/static/transit_stops.parquet - przystanek z liczba odjazdow w dniu
referencyjnym (najblizsza sroda w okresie waznosci rozkladu), w podziale na srodek.
"""

import datetime as dt
import io
import zipfile

import pandas as pd
import requests

from .config import STATIC, USER_AGENT

GTFS_URL = "https://mkuran.pl/gtfs/warsaw.zip"
MODES = {0: "tram", 1: "metro", 2: "rail", 3: "bus", 11: "trolleybus"}


def _read(z, name, **kw):
    with z.open(name) as f:
        return pd.read_csv(f, dtype=str, **kw)


def _active_services(z, names, day):
    """service_id kursujace w danym dniu (calendar.txt + wyjatki calendar_dates.txt)."""
    ymd = day.strftime("%Y%m%d")
    active = set()
    if "calendar.txt" in names:
        cal = _read(z, "calendar.txt")
        wd = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"][day.weekday()]
        m = (cal[wd] == "1") & (cal["start_date"] <= ymd) & (cal["end_date"] >= ymd)
        active |= set(cal.loc[m, "service_id"])
    if "calendar_dates.txt" in names:
        cd = _read(z, "calendar_dates.txt")
        cd = cd[cd["date"] == ymd]
        active |= set(cd.loc[cd["exception_type"] == "1", "service_id"])
        active -= set(cd.loc[cd["exception_type"] == "2", "service_id"])
    return active


def _reference_day(z, names):
    """Najblizsza sroda (typowy dzien roboczy), dla ktorej rozklad ma kursy."""
    today = dt.date.today()
    for k in range(0, 28):
        day = today + dt.timedelta(days=k)
        if day.weekday() == 2 and _active_services(z, names, day):
            return day
    raise RuntimeError("GTFS: brak kursow w najblizszych 4 tygodniach")


def fetch_gtfs(log, force=False):
    out = STATIC / "transit_stops.parquet"
    if out.exists() and not force:
        log(f"gtfs: juz jest ({out.name})")
        return
    cache = STATIC / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    zpath = cache / "warsaw_gtfs.zip"
    if force or not zpath.exists():
        log(f"gtfs: pobieram {GTFS_URL} (~100 MB)")
        r = requests.get(GTFS_URL, timeout=600, headers={"User-Agent": USER_AGENT})
        r.raise_for_status()
        zpath.write_bytes(r.content)
    with zipfile.ZipFile(zpath) as z:
        names = set(z.namelist())
        day = _reference_day(z, names)
        services = _active_services(z, names, day)
        routes = _read(z, "routes.txt", usecols=["route_id", "route_type"])
        trips = _read(z, "trips.txt", usecols=["trip_id", "route_id", "service_id"])
        trips = trips[trips["service_id"].isin(services)].merge(routes, on="route_id")
        trips["mode"] = trips["route_type"].astype(int).map(MODES).fillna("other")
        mode_of = trips.set_index("trip_id")["mode"]
        # Metro jest zapisane jako kurs wzorcowy + frequencies.txt (kursy co X s):
        # taki kurs liczymy tyle razy, ile odjazdow wynika z okien i odstepow.
        runs = pd.Series(dtype=float)
        if "frequencies.txt" in names:
            fq = _read(z, "frequencies.txt")
            secs = lambda s: s.str.split(":", expand=True).astype(int).mul([3600, 60, 1]).sum(axis=1)
            fq["n"] = ((secs(fq["end_time"]) - secs(fq["start_time"])) / fq["headway_secs"].astype(int)).round()
            runs = fq.groupby("trip_id")["n"].sum()
        counts = []
        # stop_times.txt ma miliony wierszy - czytamy kawalkami tylko 2 kolumny
        with z.open("stop_times.txt") as f:
            for chunk in pd.read_csv(io.TextIOWrapper(f, "utf-8"), dtype=str, usecols=["trip_id", "stop_id"],
                                     chunksize=2_000_000):
                chunk = chunk[chunk["trip_id"].isin(mode_of.index)]
                chunk["mode"] = chunk["trip_id"].map(mode_of)
                chunk["n"] = chunk["trip_id"].map(runs).fillna(1)
                counts.append(chunk.groupby(["stop_id", "mode"])["n"].sum())
        stops = _read(z, "stops.txt")
    dep = pd.concat(counts).groupby(level=[0, 1]).sum().unstack(fill_value=0).astype(int)
    dep.columns = [f"departures_{m}" for m in dep.columns]
    dep["departures_total"] = dep.sum(axis=1)
    st = stops[["stop_id", "stop_name", "stop_lat", "stop_lon"]].rename(columns={"stop_lat": "lat", "stop_lon": "lon"})
    st[["lat", "lon"]] = st[["lat", "lon"]].astype(float)
    st = st.merge(dep, left_on="stop_id", right_index=True, how="inner")
    st["reference_day"] = day.isoformat()
    st.to_parquet(out, index=False)
    by_mode = {c.removeprefix("departures_"): int(st[c].sum()) for c in st if c.startswith("departures_")}
    log(f"gtfs: {len(st)} przystankow z kursami w dniu {day} (sroda), odjazdy: {by_mode} -> {out.name}")
