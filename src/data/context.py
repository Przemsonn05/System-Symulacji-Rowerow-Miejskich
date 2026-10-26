"""context_hourly: zmienne zewnetrzne co godzine (UTC).

Pogoda, zmrok, typ dnia, kalendarz, wydarzenia i ruch drogowy (TomTom).
Brak danych zostawiany jest jako NaN (np. TomTom przed startem zbierania).
"""

import datetime as dt

import numpy as np
import pandas as pd

from .config import STATIC, TZ, WARSAW_LAT, WARSAW_LON
from .raw import read_jsonl_folder

# Okno wplywu wydarzenia: od 2 h przed startem do 1 h po koncu.
EVENT_BEFORE_H, EVENT_AFTER_H = 2, 1


def hourly_index(t_min, t_max):
    # godziny, w ktorych byl choc jeden pomiar (ceil dodawal godzine po ostatnim pomiarze)
    hours = pd.date_range(t_min.floor("h"), t_max.floor("h"), freq="h", tz="UTC")
    return pd.DataFrame({"time": hours})


def add_time_fields(ctx):
    local = ctx["time"].dt.tz_convert(TZ)
    ctx["local_date"] = local.dt.date
    ctx["local_hour"] = local.dt.hour
    ctx["dow"] = local.dt.dayofweek
    ctx["is_weekend"] = ctx["dow"] >= 5
    return ctx


def add_sun(ctx):
    """Wysokosc slonca w polowie godziny i flaga zmroku (slonce < -6 st. = po zmierzchu cywilnym)."""
    from astral import Observer
    from astral.sun import elevation

    obs = Observer(latitude=WARSAW_LAT, longitude=WARSAW_LON)
    mid = ctx["time"] + pd.Timedelta(minutes=30)
    ctx["sun_elevation"] = [round(elevation(obs, t.to_pydatetime()), 1) for t in mid]
    ctx["is_dark"] = ctx["sun_elevation"] < -6
    ctx["is_daylight"] = ctx["sun_elevation"] > 0
    return ctx


def add_weather(ctx, log):
    path = STATIC / "weather_hourly.parquet"
    if not path.exists():
        log("  context: brak weather_hourly.parquet (uruchom fetch_static)")
        return ctx
    w = pd.read_parquet(path).rename(columns={"source": "weather_source"})
    ctx = ctx.merge(w, on="time", how="left")
    aq_path = STATIC / "air_quality_hourly.parquet"
    if aq_path.exists():
        aq = pd.read_parquet(aq_path).drop(columns="source")
        ctx = ctx.merge(aq, on="time", how="left")
    return ctx


def add_calendar(ctx, log):
    path = STATIC / "calendar.csv"
    if not path.exists():
        log("  context: brak calendar.csv (uruchom fetch_static)")
        ctx["day_type"] = np.where(ctx["dow"] == 5, "saturday", np.where(ctx["dow"] == 6, "sunday_holiday", "workday"))
        return ctx
    cal = pd.read_csv(path, parse_dates=["date"])
    cal["local_date"] = cal["date"].dt.date
    keep = ["local_date", "day_type", "is_holiday", "holiday_name", "is_long_weekend", "is_bridge_day",
            "school_break", "school_classes_day",
            "uw_period", "pw_period", "sgh_period", "wum_period",
            "uw_classes_day", "pw_classes_day", "sgh_classes_day", "wum_classes_day",
            "n_uni_classes", "n_uni_exams", "calendar_certain"]
    return ctx.merge(cal[keep], on="local_date", how="left")


def event_windows(events):
    """Okna aktywnosci wydarzen. Wydarzenia wielodniowe (np. jarmark) rozbijane
    sa na codzienne okna w tych samych godzinach co start i koniec."""
    rows = []
    for e in events.itertuples():
        start, end = e.start_utc, e.end_utc
        if end - start <= pd.Timedelta(days=1):
            rows.append((e.event_id, e.name, e.scale, start, end))
            continue
        s_loc, e_loc = start.tz_convert(TZ), end.tz_convert(TZ)
        for day in pd.date_range(s_loc.normalize(), e_loc.normalize(), freq="D"):
            ds = day.replace(hour=s_loc.hour, minute=s_loc.minute)
            de = day.replace(hour=e_loc.hour, minute=e_loc.minute)
            rows.append((e.event_id, e.name, e.scale, ds.tz_convert("UTC"), de.tz_convert("UTC")))
    w = pd.DataFrame(rows, columns=["event_id", "name", "scale", "start", "end"])
    w["from"] = w["start"] - pd.Timedelta(hours=EVENT_BEFORE_H)
    w["to"] = w["end"] + pd.Timedelta(hours=EVENT_AFTER_H)
    return w


def add_events(ctx, log):
    path = STATIC / "events.csv"
    if not path.exists():
        log("  context: brak events.csv (uruchom fetch_static)")
        return ctx
    ev = pd.read_csv(path, parse_dates=["start_utc", "end_utc"])
    w = event_windows(ev)
    h0, h1 = ctx["time"], ctx["time"] + pd.Timedelta(hours=1)
    n_all, n_large, names = [], [], []
    for a, b in zip(h0, h1):
        act = w[(w["from"] < b) & (w["to"] > a)]
        n_all.append(len(act))
        n_large.append(int((act["scale"] == "large").sum()))
        names.append("; ".join(sorted(set(act["name"]))) or None)
    ctx["n_events"] = n_all
    ctx["n_events_large"] = n_large
    ctx["event_names"] = names
    return ctx


def add_traffic(ctx, log):
    flow = read_jsonl_folder("traffic_flow")
    if not flow.empty:
        flow = flow[flow["free_flow_speed"] > 0]
        # tylko punkty mierzone przez caly okres: po zmianie lokalizacji punktu (nowa nazwa)
        # srednia z innego zestawu punktow dawalaby sztuczny skok wskaznika
        coverage = flow.groupby("point")["time"].nunique() / flow["time"].nunique()
        stable = coverage[coverage >= 0.95].index
        if len(stable) < coverage.size:
            log(f"  context: congestion z {len(stable)}/{coverage.size} punktow TomTom "
                f"(pominiete: {', '.join(sorted(set(coverage.index) - set(stable)))})")
        flow = flow[flow["point"].isin(stable)].copy()
        flow["congestion"] = (1 - flow["current_speed"] / flow["free_flow_speed"]).clip(lower=0)
        flow["hour"] = flow["time"].dt.floor("h")
        # liczba zamknietych odcinkow w pomiarze, srednio w godzinie (1 lub 2-4 pomiary)
        closures = flow.groupby(["hour", "time"])["road_closure"].sum().groupby(level=0).mean()
        agg = flow.groupby("hour").agg(
            congestion=("congestion", "mean"),
            congestion_max=("congestion", "max"),
        )
        agg["n_road_closures"] = closures
        agg = agg.reset_index().rename(columns={"hour": "time"})
        ctx = ctx.merge(agg, on="time", how="left")
    else:
        log("  context: brak data/traffic_flow")
    inc = read_jsonl_folder("incidents")
    if not inc.empty:
        inc["hour"] = inc["time"].dt.floor("h")
        real = inc[inc["incident_id"].notna()]
        per_snap = real.groupby("time").agg(
            n=("incident_id", "nunique"),
            jams=("icon_category", lambda s: int((s == 6).sum())),
            delay=("delay_sec", "sum"),
        )
        # pomiary bez utrudnien (znacznik incident_id = null) licza sie jako zero
        snaps = inc[["time", "hour"]].drop_duplicates().set_index("time")
        per_snap = snaps.join(per_snap).fillna({"n": 0, "jams": 0, "delay": 0})
        agg = per_snap.groupby("hour").agg(
            n_incidents=("n", "mean"), n_jam_incidents=("jams", "mean"), incident_delay_sec=("delay", "mean")
        ).reset_index().rename(columns={"hour": "time"})
        ctx = ctx.merge(agg, on="time", how="left")
    else:
        log("  context: brak data/incidents")
    return ctx


def build_context(t_min, t_max, log):
    ctx = hourly_index(t_min, t_max)
    ctx = add_time_fields(ctx)
    ctx = add_sun(ctx)
    ctx = add_weather(ctx, log)
    ctx = add_calendar(ctx, log)
    ctx = add_events(ctx, log)
    ctx = add_traffic(ctx, log)
    return ctx
