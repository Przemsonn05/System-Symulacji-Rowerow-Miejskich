"""Jednorazowe pobranie danych statycznych/historycznych do data/static/.

  python -m src.data.fetch_static                      # wszystko (pomija gotowe pliki)
  python -m src.data.fetch_static --only weather       # tylko wybrane kroki
  python -m src.data.fetch_static --force calendar     # wymus ponowne utworzenie

Kroki: calendar, events, weather, air_quality, elevation, population, gtfs, osm.
Pogoda i jakosc powietrza sa dociagane przyrostowo przy kazdym uruchomieniu
(brakujace dni + ostatni tydzien); elevation dociaga nowe stacje; osm - nowe
kategorie POI. Pozostale kroki pomijaja gotowe pliki (--force wymusza).
"""

import argparse
import datetime as dt
import sys
import time

import pandas as pd
import requests

from . import calendar_data, events_data
from .config import (
    CALENDAR_END,
    CALENDAR_START,
    DATA_START,
    STATIC,
    TZ,
    USER_AGENT,
    WARSAW_LAT,
    WARSAW_LON,
)
from .raw import read_info

STEPS = ["calendar", "events", "weather", "air_quality", "elevation", "population", "gtfs", "osm"]


def log(msg):
    print(msg, flush=True)


def get_json(url, params, retries=3):
    for attempt in range(1, retries + 1):
        try:
            r = requests.get(url, params=params, timeout=60, headers={"User-Agent": USER_AGENT})
            r.raise_for_status()
            return r.json()
        except requests.RequestException as e:
            if attempt == retries:
                raise
            log(f"  ponawiam ({e})")
            time.sleep(5 * attempt)


# ---------------------------------------------------------------------------
# 1. Kalendarz
# ---------------------------------------------------------------------------


def build_calendar(force=False):
    import holidays

    path = STATIC / "calendar.csv"
    if path.exists() and not force:
        log(f"calendar: juz jest ({path.name})")
        return
    days = pd.date_range(CALENDAR_START, CALENDAR_END, freq="D")
    df = pd.DataFrame({"date": days.date})
    df["dow"] = days.dayofweek  # 0 = poniedzialek
    df["is_weekend"] = df["dow"] >= 5

    pl = holidays.Poland(years=sorted({d.year for d in df["date"]}), language="pl")
    df["holiday_name"] = [pl.get(d) for d in df["date"]]
    df["is_holiday"] = df["holiday_name"].notna()
    df["day_type"] = "workday"
    df.loc[df["dow"] == 5, "day_type"] = "saturday"
    df.loc[(df["dow"] == 6) | df["is_holiday"], "day_type"] = "sunday_holiday"

    # Dlugi weekend: >= 3 kolejne dni wolne (weekend/swieto). Dzien pomostowy:
    # pojedynczy dzien roboczy miedzy dniami wolnymi (wiele osob bierze urlop).
    off = (df["is_weekend"] | df["is_holiday"]).to_numpy()
    run_id = (off != pd.Series(off).shift(fill_value=not off[0])).cumsum()
    run_len = pd.Series(off).groupby(run_id).transform("size")
    df["is_long_weekend"] = off & (run_len >= 3).to_numpy()
    prev_off = pd.Series(off).shift(1, fill_value=False).to_numpy()
    next_off = pd.Series(off).shift(-1, fill_value=False).to_numpy()
    df["is_bridge_day"] = ~off & prev_off & next_off

    def apply(calendar, default):
        period = pd.Series(default, index=df.index, dtype=object)
        label = pd.Series(None, index=df.index, dtype=object)
        certain = pd.Series(True, index=df.index)
        for p in calendar_data.PERIODS:
            if p["calendar"] != calendar:
                continue
            m = (df["date"] >= p["start"]) & (df["date"] <= p["end"])
            period[m], label[m], certain[m] = p["kind"], p["label"], p["certain"]
        return period, label, certain

    # Szkoly: zajecia w dni robocze poza przerwami.
    period, label, certain = apply("school", "classes")
    df["school_break"] = period == "break"
    df["school_break_name"] = label
    df["school_classes_day"] = (period == "classes") & (df["day_type"] == "workday")

    for uni in calendar_data.UNIVERSITIES:
        period, label, certain = apply(uni, "break")
        df[f"{uni}_period"] = period
        df[f"{uni}_label"] = label
        df[f"{uni}_certain"] = certain
        # dzien z zajeciami stacjonarnymi: okres zajec, dzien roboczy, nie swieto
        df[f"{uni}_classes_day"] = (period == "classes") & (df["day_type"] == "workday")
    unis = calendar_data.UNIVERSITIES
    df["n_uni_classes"] = df[[f"{u}_classes_day" for u in unis]].sum(axis=1)
    df["n_uni_exams"] = df[[f"{u}_period" for u in unis]].isin(["exams", "resit"]).sum(axis=1)
    df["calendar_certain"] = df[[f"{u}_certain" for u in unis]].all(axis=1)

    STATIC.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    write_calendar_sources()
    log(f"calendar: {len(df)} dni -> {path.name} (+ calendar_sources.md); "
        f"dni z niepewnymi datami: {(~df['calendar_certain']).sum()}")


def write_calendar_sources():
    lines = [
        "# Źródła kalendarza (calendar.csv)",
        "",
        "Wygenerowane przez `python -m src.data.fetch_static --only calendar` z `src/data/calendar_data.py`.",
        "Okresy oznaczone jako **niepewne** nie zostały potwierdzone w dokumencie źródłowym "
        "(w calendar.csv: `{uczelnia}_certain = False`).",
        "",
        "## Źródła",
        "",
    ]
    for key, (title, url) in calendar_data.SOURCES.items():
        lines.append(f"- `{key}` – {title}. <{url}>")
    lines += ["", "## Okresy", "", "| kalendarz | rodzaj | od | do | opis | źródło | pewne |", "|---|---|---|---|---|---|---|"]
    for p in calendar_data.PERIODS:
        lines.append(
            f"| {p['calendar']} | {p['kind']} | {p['start']} | {p['end']} | {p['label']} | "
            f"`{p['source']}` | {'tak' if p['certain'] else '**niepewne**'} |"
        )
    (STATIC / "calendar_sources.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# 2. Wydarzenia
# ---------------------------------------------------------------------------


def build_events(force=False):
    path = STATIC / "events.csv"
    if path.exists() and not force:
        log(f"events: juz jest ({path.name})")
        return
    df = pd.DataFrame(events_data.EVENTS)
    start = pd.to_datetime(df["start_local"]).dt.tz_localize(TZ)
    default_h = df["category"].map(events_data.DEFAULT_HOURS)
    end = pd.to_datetime(df["end_local"]).dt.tz_localize(TZ)
    end = end.fillna(start + pd.to_timedelta(default_h, unit="h"))
    df.insert(0, "event_id", range(1, len(df) + 1))
    df["start_utc"] = start.dt.tz_convert("UTC")
    df["end_utc"] = end.dt.tz_convert("UTC")
    df["end_estimated"] = df["end_local"].isna()
    df = df.drop(columns=["start_local", "end_local"])
    df.to_csv(path, index=False)
    log(f"events: {len(df)} wydarzen -> {path.name} (niepewnych: {(~df['certain']).sum()})")


# ---------------------------------------------------------------------------
# 3. Pogoda (Open-Meteo)
# ---------------------------------------------------------------------------

WEATHER_VARS = [
    "temperature_2m",
    "apparent_temperature",
    "precipitation",
    "rain",
    "snowfall",
    "cloud_cover",
    "wind_speed_10m",
    "wind_gusts_10m",
    "relative_humidity_2m",
    "weather_code",
]
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
HIST_FORECAST_URL = "https://historical-forecast-api.open-meteo.com/v1/forecast"


def _weather(url, start, end, source):
    params = {
        "latitude": WARSAW_LAT,
        "longitude": WARSAW_LON,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "hourly": ",".join(WEATHER_VARS),
        "timezone": "GMT",
        "wind_speed_unit": "kmh",
    }
    h = get_json(url, params)["hourly"]
    df = pd.DataFrame(h)
    df["time"] = pd.to_datetime(df.pop("time"), utc=True)
    df["source"] = source
    return df


def _days_to_fetch(old, today, source="archive"):
    """Dni bez kompletu 24 godzin z danego zrodla + zawsze ostatni tydzien,
    bo archiwa koryguja swieze dni."""
    have = set()
    if old is not None:
        good = old[old["source"] == source]
        counts = good.groupby(good["time"].dt.date).size()
        fresh = today - dt.timedelta(days=7)
        have = {d for d, n in counts.items() if n == 24 and d < fresh}
    return [d.date() for d in pd.date_range(DATA_START, today) if d.date() not in have]


def update_weather(force=False):
    """Archiwum (ERA5, opoznienie ~5 dni) + Historical Forecast na ostatnie dni.

    Godziny z prognozy sa przy kolejnym uruchomieniu zastepowane archiwum,
    gdy tylko bedzie dostepne.
    """
    path = STATIC / "weather_hourly.parquet"
    today = dt.datetime.now(dt.timezone.utc).date()
    old = None if force or not path.exists() else pd.read_parquet(path)
    need = _days_to_fetch(old, today)
    if not need:
        log("weather: aktualna")
        return
    start, end = min(need), max(need)
    log(f"weather: pobieram {start} .. {end}")
    arch = _weather(ARCHIVE_URL, start, end, "archive")
    arch = arch[arch["temperature_2m"].notna()]
    missing = sorted(set(pd.date_range(start, end).date) - set(
        d for d, n in arch.groupby(arch["time"].dt.date).size().items() if n == 24
    ))
    parts = [arch]
    if missing:
        fc = _weather(HIST_FORECAST_URL, missing[0], missing[-1], "forecast")
        fc = fc[fc["time"].dt.date.isin(missing)]
        parts.append(fc)
    new = pd.concat(parts)
    now = pd.Timestamp.now(tz="UTC")
    new = new[new["time"] <= now]
    if old is not None:
        new = pd.concat([old[~old["time"].isin(new["time"])], new])
    new = new.sort_values("time").drop_duplicates("time", keep="last").reset_index(drop=True)
    STATIC.mkdir(parents=True, exist_ok=True)
    new.to_parquet(path, index=False)
    by_src = new["source"].value_counts().to_dict()
    log(f"weather: {len(new)} godzin ({new['time'].min()} .. {new['time'].max()}), zrodla: {by_src}")


AIR_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
AIR_VARS = ["pm2_5", "pm10", "nitrogen_dioxide", "european_aqi"]


def update_air_quality(force=False):
    """Jakosc powietrza co godzine (Open-Meteo Air Quality, model CAMS Europe)."""
    path = STATIC / "air_quality_hourly.parquet"
    today = dt.datetime.now(dt.timezone.utc).date()
    old = None if force or not path.exists() else pd.read_parquet(path)
    need = _days_to_fetch(old, today, source="cams")
    if not need:
        log("air_quality: aktualna")
        return
    params = {
        "latitude": WARSAW_LAT,
        "longitude": WARSAW_LON,
        "start_date": min(need).isoformat(),
        "end_date": max(need).isoformat(),
        "hourly": ",".join(AIR_VARS),
        "timezone": "GMT",
    }
    new = pd.DataFrame(get_json(AIR_URL, params)["hourly"])
    new["time"] = pd.to_datetime(new.pop("time"), utc=True)
    new["source"] = "cams"
    new = new[(new["time"] <= pd.Timestamp.now(tz="UTC")) & new["pm2_5"].notna()]
    if old is not None:
        new = pd.concat([old[~old["time"].isin(new["time"])], new])
    new = new.sort_values("time").reset_index(drop=True)
    new.to_parquet(path, index=False)
    log(f"air_quality: {len(new)} godzin ({new['time'].min()} .. {new['time'].max()}) -> {path.name}")


# ---------------------------------------------------------------------------
# 4. Wysokosc terenu stacji (Open-Meteo Elevation API, model Copernicus 90 m)
# ---------------------------------------------------------------------------


def update_elevation(force=False):
    path = STATIC / "elevation.csv"
    info = read_info().sort_values("day").drop_duplicates("station_id", keep="last")
    old = None if force or not path.exists() else pd.read_csv(path, dtype={"station_id": str})
    todo = info if old is None else info[~info["station_id"].isin(old["station_id"])]
    if todo.empty:
        log("elevation: aktualna")
        return
    rows = []
    for i in range(0, len(todo), 100):  # API przyjmuje do 100 punktow
        chunk = todo.iloc[i : i + 100]
        res = get_json(
            "https://api.open-meteo.com/v1/elevation",
            {
                "latitude": ",".join(f"{v:.6f}" for v in chunk["lat"]),
                "longitude": ",".join(f"{v:.6f}" for v in chunk["lon"]),
            },
        )
        rows.append(pd.DataFrame({
            "station_id": chunk["station_id"].values,
            "lat": chunk["lat"].values,
            "lon": chunk["lon"].values,
            "elevation_m": res["elevation"],
        }))
    new = pd.concat(rows + ([old] if old is not None else []), ignore_index=True)
    STATIC.mkdir(parents=True, exist_ok=True)
    new.to_csv(path, index=False)
    log(f"elevation: {len(todo)} nowych stacji, razem {len(new)} -> {path.name}")


# ---------------------------------------------------------------------------


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", nargs="+", choices=STEPS, help="tylko wybrane kroki")
    ap.add_argument("--force", nargs="*", choices=STEPS, help="utworz ponownie (bez nazw = wszystkie)")
    args = ap.parse_args(argv)
    steps = args.only or STEPS
    forced = set(STEPS if args.force == [] else (args.force or []))

    failed = []
    for step in steps:
        try:
            if step == "calendar":
                build_calendar(step in forced)
            elif step == "events":
                build_events(step in forced)
            elif step == "weather":
                update_weather(step in forced)
            elif step == "air_quality":
                update_air_quality(step in forced)
            elif step == "elevation":
                update_elevation(step in forced)
            elif step == "population":
                from .population import fetch_population

                fetch_population(log, step in forced)
            elif step == "gtfs":
                from .gtfs import fetch_gtfs

                fetch_gtfs(log, step in forced)
            elif step == "osm":
                from . import osm

                log("osm: pobieranie (pierwszy raz kilka-kilkanascie minut)...")
                osm.fetch_all(log)
        except Exception as e:  # jeden krok nie blokuje pozostalych
            failed.append(step)
            log(f"{step}: BLAD {type(e).__name__}: {e}")
    if failed:
        log(f"Nieudane kroki: {', '.join(failed)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
