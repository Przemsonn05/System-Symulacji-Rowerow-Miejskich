"""Wczytanie danych rzeczywistych albo wyniku symulacji do wspolnej postaci (siatka 5 min).

Metryki emergencji licza sie z tabel stanow co 5 min - tak samo dla danych (observed_timeseries)
i symulacji (station_timeseries). Dzieki temu symulacja nie "widzi" krotkich pustek, ktorych w danych
nie widac.

Obslugiwane katalogi:
  processed/                         observed_timeseries.parquet, stations.parquet, trips.parquet
  results/.../seed_1000/ (DES)       station_timeseries.parquet (albo observed_timeseries), stations.parquet,
                                     trips.parquet, events.parquet (opcjonalnie)
"""

import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

TZ = "Europe/Warsaw"
SLOT = "5min"


@dataclass
class RunData:
    """Stan systemu na siatce 5 min.

    bikes     DataFrame czas (UTC, co 5 min) x station_id, NaN = brak pomiaru
    stations  station_id, lat, lon, capacity (kolejnosc = kolumny bikes)
    trips     przejazdy uzytkownikow (t_departure, t_arrival, from/to lat/lon, from/to station)
    day_type  local_date -> typ dnia (workday, saturday, ...)
    """
    source: str
    bikes: pd.DataFrame
    stations: pd.DataFrame
    trips: pd.DataFrame
    day_type: dict = field(default_factory=dict)
    path: Path = None

    @property
    def xy(self):
        """Wspolrzedne stacji w metrach (rzut lokalny)."""
        lat = self.stations["lat"].to_numpy(float)
        lon = self.stations["lon"].to_numpy(float)
        lat0 = np.nanmean(lat)
        return np.column_stack([(lon - np.nanmean(lon)) * 111_320.0 * np.cos(np.radians(lat0)),
                                (lat - lat0) * 110_574.0])

    @property
    def local_dates(self):
        return self.bikes.index.tz_convert(TZ).date

    def empty(self):
        """1 = pusta, 0 = ma rowery, NaN = brak danych."""
        b = self.bikes.to_numpy(float)
        return np.where(np.isnan(b), np.nan, (b == 0).astype(float))


def _grid(ts, value="bikes"):
    t = ts.copy()
    t["slot"] = t["time"].dt.floor(SLOT)
    wide = t.pivot_table(index="slot", columns="station_id", values=value, aggfunc="last")
    full = pd.date_range(wide.index.min(), wide.index.max(), freq=SLOT)
    return wide.reindex(full)


def _clean_user(trips):
    if trips is None or trips.empty:
        return pd.DataFrame(columns=["t_departure", "t_arrival", "from_lat", "from_lon", "to_lat", "to_lon"])
    t = trips[trips["type"] == "user"] if "type" in trips else trips
    for flag in ("is_flicker", "too_fast", "is_long"):
        if flag in t:
            t = t[~t[flag].fillna(False).astype(bool)]
    return t.copy()


def load_run(path, day_type=None):
    """Katalog processed/ albo katalog przebiegu symulacji -> RunData."""
    path = Path(path)
    if (path / "station_timeseries.parquet").exists():
        source, ts = "sim", pd.read_parquet(path / "station_timeseries.parquet")
    elif (path / "observed_timeseries.parquet").exists():
        ts = pd.read_parquet(path / "observed_timeseries.parquet")
        source = "sim" if (path / "events.parquet").exists() else "observed"
    else:
        raise FileNotFoundError(f"{path}: brak station_timeseries.parquet / observed_timeseries.parquet")
    if "is_spike" in ts:
        ts = ts[~ts["is_spike"].fillna(False).astype(bool)]
    ts["station_id"] = ts["station_id"].astype(str)
    ts["time"] = pd.to_datetime(ts["time"], utc=True)
    bikes = _grid(ts)
    st = pd.read_parquet(path / "stations.parquet")
    st["station_id"] = st["station_id"].astype(str)
    st = st.set_index("station_id").reindex(bikes.columns).reset_index()
    if "capacity" not in st:
        st["capacity"] = np.nan
    keep = st["lat"].notna().to_numpy()
    bikes, st = bikes.loc[:, keep], st[keep].reset_index(drop=True)
    trips = pd.read_parquet(path / "trips.parquet") if (path / "trips.parquet").exists() else None
    if day_type is None:
        day_type = _day_types(path, bikes.index)
    return RunData(source, bikes, st[["station_id", "lat", "lon", "capacity"]], _clean_user(trips), day_type, path)


def _day_types(path, index):
    for p in (path / "context_hourly.parquet", Path(__file__).resolve().parents[2] / "processed" / "context_hourly.parquet"):
        if p.exists():
            c = pd.read_parquet(p)
            if "day_type" in c and "time" in c:
                c["time"] = pd.to_datetime(c["time"], utc=True)
                c["local_date"] = c["time"].dt.tz_convert(TZ).dt.date
                m = c.dropna(subset=["day_type"]).drop_duplicates("local_date").set_index("local_date")["day_type"]
                found = {d: m[d] for d in set(index.tz_convert(TZ).date) if d in m.index}
                if found:
                    return found
    # bez kalendarza: sobota / niedziela z dnia tygodnia
    return {d: ("saturday" if d.weekday() == 5 else "sunday" if d.weekday() == 6 else "workday")
            for d in set(index.tz_convert(TZ).date)}


def day_kind(day_type):
    return "roboczy" if day_type == "workday" else "wolny"


def full_days(run, min_coverage=0.9):
    """Lokalne daty z pokryciem siatki >= min_coverage (dzien niepelny psuje rytm i fale)."""
    known = ~run.bikes.isna().all(axis=1)
    loc = run.bikes.index.tz_convert(TZ)
    cov = pd.Series(known.to_numpy(), index=loc.date).groupby(level=0).agg(lambda s: s.sum())
    out = []
    for d, n in cov.items():
        start = pd.Timestamp(d).tz_localize(TZ)
        expected = (pd.Timestamp(d + dt.timedelta(days=1)).tz_localize(TZ) - start).total_seconds() / 300
        if n / expected >= min_coverage:
            out.append(d)
    return out
