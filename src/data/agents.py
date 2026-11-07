"""Dane dla agentow (Osoba 1, zadanie 1): typy podrozy, trasy dojazdowe, zmiany operatora, bilans dzielnic.

    python -m src.data.agents        # po python -m src.data.build (uruchamiane tez automatycznie na koncu build)

Wynik (processed/):
  trip_features.parquet    kazdy przejazd uzytkownika: pora, typ dnia, dzien zajec, czas, km, e-rower, bateria,
                           otoczenie startu i celu (uczelnia / biura / park / osiedle), dzielnica, trasa dojazdowa
  commute_pairs.parquet    pary stacji dojazdowych (A -> B rano, B -> A po poludniu) z regularnoscia
  operator_shifts.parquet  w ktorych godzinach pracuja ciezarowki operatora (dni robocze / wolne)
  district_flows.parquet   dzielnica x godzina: przyjazdy, wyjazdy, bilans ("oddychanie miasta")
  daily_check.parquet      kontrola kazdego dnia: pokrycie, aktywne stacje, flota, relokacje, zwijanie sezonu
  stations.parquet         + kolumny district i land_use

Reguly (do raportu):
  * przejazd uzytkownika = type user, bez is_flicker, too_fast, is_long (jak w calym projekcie);
  * para (A, B) jest dojazdowa, jesli w co najmniej 3 rozne dni robocze jest przejazd A -> B w 6:30-9:30
    i w co najmniej 3 rozne dni robocze przejazd B -> A w 15:00-19:00 (czas lokalny);
  * regularnosc: dla przejazdu o godzinie g liczymy dni robocze, w ktorych na tej samej parze byl przejazd
    o godzinie g +- 15 min; maksimum po przejazdach pary = regular_days. To dolne oszacowanie liczby
    "stalych bywalcow" (tozsamosci klientow nie znamy, wiec dwie osoby o tej samej porze licza sie jak jedna);
  * otoczenie stacji: uczelnia (uczelnia w 300 m), biura (liczba biur w 300 m >= 3. kwartyl
    stacji), park (park w 300 m), osiedle (mieszkancy w 500 m >= 2/3 kwantyl); pierwsza pasujaca etykieta,
    inaczej "mieszane". Bulwarow nie rozpoznajemy osobno (OSM nie ma dla nich jednolitego tagu);
  * zmiany operatora: relokacje wykrywamy tylko przy >= 4 rowerach przewiezionych naraz, a liczby aut nie
    znamy - tabela mowi, KIEDY operator pracuje, a nie ILE ma ciezarowek. Godzina zmiany = srednio co najmniej
    50% przewozow najbardziej pracowitej godziny. Dni niepelne (< 95% pomiarow) i dni zwijania sezonu pominiete;
  * zwijanie sezonu (koniec sezonu Veturilo 30.11): dzien, w ktorym aktywnych stacji jest < 85% albo rowerow na
    stacjach (mediana dnia) < 75% mediany wczesniejszych pelnych dni (co najmniej 7).
"""

import argparse
import datetime as dt

import numpy as np
import pandas as pd

from .config import OSM_DIR, PROCESSED, TZ

MORNING = (6 * 60 + 30, 9 * 60 + 30)
AFTERNOON = (15 * 60, 19 * 60)
COMMUTE_MIN_DAYS = 3
REGULAR_TOL_MIN = 15
FULL_DAY_COVERAGE = 0.95
WIND_DOWN_STATIONS = 0.85
WIND_DOWN_FLEET = 0.75
SHIFT_SHARE = 0.5
LAND_USE_ORDER = ["uczelnia", "biura", "park", "osiedle", "mieszane"]


def log(msg):
    print(msg, flush=True)


def clean_user_trips(trips):
    return trips[(trips["type"] == "user") & ~trips["is_flicker"] & ~trips["too_fast"] & ~trips["is_long"]].copy()


# ---------------------------------------------------------------------------
# Stacje: dzielnica i otoczenie
# ---------------------------------------------------------------------------


def load_districts():
    path = OSM_DIR / "districts.geojson"
    if not path.exists():
        return None
    import geopandas as gpd

    return gpd.read_file(path).to_crs("EPSG:4326")[["name", "geometry"]]


def district_of(lat, lon, districts):
    """Dzielnica dla punktow (lat, lon); NaN poza Warszawa albo bez pliku granic."""
    lat = np.asarray(lat, dtype=float)
    lon = np.asarray(lon, dtype=float)
    out = np.full(len(lat), None, dtype=object)
    if districts is None or len(lat) == 0:
        return out
    import shapely

    ok = np.isfinite(lat) & np.isfinite(lon)
    pts = shapely.points(lon[ok], lat[ok])
    idx = np.flatnonzero(ok)
    for name, geom in zip(districts["name"], districts.geometry):
        shapely.prepare(geom)
        inside = shapely.contains(geom, pts)
        out[idx[inside]] = name
    return out


def land_use(st):
    """Etykieta otoczenia stacji (patrz docstring modulu)."""
    def col(name, default=0.0):
        return st[name].fillna(default) if name in st else pd.Series(default, index=st.index)

    office_q = col("n_office_300m").quantile(0.75)
    pop_q = col("population_500m").quantile(2 / 3)
    flags = pd.DataFrame({
        "uczelnia": col("n_university_300m") > 0,
        "biura": col("n_office_300m") >= max(office_q, 1),
        "park": col("n_park_300m") > 0,
        "osiedle": col("population_500m") >= max(pop_q, 1),
    })
    label = pd.Series("mieszane", index=st.index)
    for name in reversed(LAND_USE_ORDER[:-1]):
        label[flags[name]] = name
    return label, flags


def station_table(st, districts):
    st = st.copy()
    st["district"] = district_of(st["lat"], st["lon"], districts)
    st["land_use"], _ = land_use(st)
    return st


# ---------------------------------------------------------------------------
# Kalendarz dni
# ---------------------------------------------------------------------------


def day_info(ctx):
    d = ctx.drop_duplicates("local_date").set_index("local_date")
    cols = [c for c in ["day_type", "is_holiday", "n_uni_classes", "school_classes_day"] if c in d]
    out = d[cols].copy()
    out.index = pd.to_datetime(out.index).date
    return out


def daily_check(obs, fleet, reb, days):
    """Kontrola dni: pokrycie, aktywne stacje, flota, relokacje i flaga zwijania sezonu."""
    loc = obs["time"].dt.tz_convert(TZ)
    o = obs.assign(local_date=loc.dt.date)
    snaps = o.drop_duplicates("time").groupby("local_date").size()
    stations = o.groupby("local_date")["station_id"].nunique()
    f = fleet.assign(local_date=fleet["time"].dt.tz_convert(TZ).dt.date)
    at_st = f.groupby("local_date")["at_stations"].median()
    r = reb.assign(local_date=reb["t_departure"].dt.tz_convert(TZ).dt.date)
    n_reb = r.groupby("local_date").size()
    bikes_reb = r.groupby("local_date")["n_bikes"].sum()
    out = pd.DataFrame({"snapshots": snaps}).sort_index()
    # dzien zmiany czasu ma 25 h (300 pomiarow)
    expected = pd.Series({d: (pd.Timestamp(d + dt.timedelta(days=1)).tz_localize(TZ)
                              - pd.Timestamp(d).tz_localize(TZ)).total_seconds() / 300 for d in out.index})
    out["coverage"] = (out["snapshots"] / expected).clip(upper=1).round(3)
    out["active_stations"] = stations
    out["bikes_at_stations_median"] = at_st
    out["relocations"] = n_reb.reindex(out.index).fillna(0).astype(int)
    out["relocated_bikes"] = bikes_reb.reindex(out.index).fillna(0).astype(int)
    out["day_type"] = [days["day_type"].get(d, "") if "day_type" in days else "" for d in out.index]
    out["full_day"] = out["coverage"] >= FULL_DAY_COVERAGE
    wind = []
    for i, d in enumerate(out.index):
        prev = out.iloc[:i]
        prev = prev[prev["full_day"]]
        if len(prev) < 7:
            wind.append(False)
            continue
        ref_st = prev["active_stations"].median()
        ref_fleet = prev["bikes_at_stations_median"].median()
        row = out.loc[d]
        wind.append(bool(row["active_stations"] < WIND_DOWN_STATIONS * ref_st
                         or row["bikes_at_stations_median"] < WIND_DOWN_FLEET * ref_fleet))
    out["wind_down"] = wind
    out.index.name = "local_date"
    return out.reset_index()


# ---------------------------------------------------------------------------
# Przejazdy: opis i trasy dojazdowe
# ---------------------------------------------------------------------------


def regular_days(dates, minutes, tol=REGULAR_TOL_MIN):
    """Dla kazdego przejazdu: w ilu roznych dniach byl przejazd o tej samej porze (+- tol min)."""
    dates = np.asarray(dates)
    minutes = np.asarray(minutes, dtype=float)
    out = np.zeros(len(minutes), dtype=int)
    for i in range(len(minutes)):
        close = np.abs(minutes - minutes[i]) <= tol
        out[i] = len(set(dates[close]))
    return out


def commute_pairs(tf):
    """Pary dojazdowe i regularnosc (patrz docstring modulu). tf - przejazdy z kolumnami z trip_features."""
    st = tf[(tf["from_type"] == "station") & (tf["to_type"] == "station") & tf["is_workday"]
            & (tf["from_station"] != tf["to_station"])]
    mor = st[st["dep_min"].between(*MORNING)]
    aft = st[st["dep_min"].between(*AFTERNOON)]
    m_days = mor.groupby(["from_station", "to_station"])["local_date"].nunique()
    a_days = aft.groupby(["from_station", "to_station"])["local_date"].nunique()
    rows = []
    for (a, b), nd in m_days[m_days >= COMMUTE_MIN_DAYS].items():
        back = a_days.get((b, a), 0)
        if back < COMMUTE_MIN_DAYS:
            continue
        m = mor[(mor["from_station"] == a) & (mor["to_station"] == b)]
        f = aft[(aft["from_station"] == b) & (aft["to_station"] == a)]
        rm = regular_days(m["local_date"], m["dep_min"])
        ra = regular_days(f["local_date"], f["dep_min"])
        rows.append({
            "home_station": a, "work_station": b,
            "days_morning": int(nd), "days_afternoon": int(back),
            "trips_morning": len(m), "trips_afternoon": len(f),
            "median_time_morning": _hhmm(m["dep_min"].median()),
            "median_time_afternoon": _hhmm(f["dep_min"].median()),
            "regular_days_morning": int(rm.max()), "regular_days_afternoon": int(ra.max()),
            "km": float(m["km"].median()),
            "ebike_share": float(pd.concat([m["is_ebike"], f["is_ebike"]]).mean()),
        })
    cols = ["home_station", "work_station", "days_morning", "days_afternoon", "trips_morning", "trips_afternoon",
            "median_time_morning", "median_time_afternoon", "regular_days_morning", "regular_days_afternoon",
            "km", "ebike_share"]
    out = pd.DataFrame(rows, columns=cols)
    return out.sort_values(["regular_days_morning", "days_morning"], ascending=False).reset_index(drop=True)


def _hhmm(minutes):
    if pd.isna(minutes):
        return ""
    m = int(round(minutes))
    return f"{m // 60:02d}:{m % 60:02d}"


def trip_features(trips, st, days, districts):
    u = clean_user_trips(trips)
    loc = u["t_departure"].dt.tz_convert(TZ)
    u["local_date"] = loc.dt.date
    u["local_hour"] = loc.dt.hour
    u["dep_min"] = loc.dt.hour * 60 + loc.dt.minute + loc.dt.second / 60
    u["dow"] = loc.dt.dayofweek
    dtype = u["local_date"].map(days["day_type"]) if "day_type" in days else pd.Series("", index=u.index)
    u["day_type"] = dtype.fillna("")
    u["is_workday"] = u["day_type"] == "workday"
    u["is_weekend"] = u["day_type"].isin(["saturday", "sunday", "sunday_holiday", "weekend"])
    u["is_holiday"] = u["local_date"].map(days["is_holiday"]).fillna(False).astype(bool) if "is_holiday" in days else False
    uni = u["local_date"].map(days["n_uni_classes"]) if "n_uni_classes" in days else pd.Series(0, index=u.index)
    u["is_class_day"] = uni.fillna(0) > 0
    u["km"] = u["network_km"].fillna(u["distance_km"])
    u["is_ebike"] = u["is_ebike"].fillna(False).astype(bool)
    s = st.set_index("station_id")
    for side in ("from", "to"):
        sid = u[f"{side}_station"].where(u[f"{side}_type"] == "station")
        u[f"{side}_land_use"] = sid.map(s["land_use"])
        d = district_of(u[f"{side}_lat"], u[f"{side}_lon"], districts)
        u[f"{side}_district"] = d
    pairs = commute_pairs(u)
    key_m = set(zip(pairs["home_station"], pairs["work_station"]))
    key_a = set(zip(pairs["work_station"], pairs["home_station"]))
    fs, ts = u["from_station"].to_numpy(), u["to_station"].to_numpy()
    dm = u["dep_min"].to_numpy()
    wk = u["is_workday"].to_numpy()
    in_m = (dm >= MORNING[0]) & (dm <= MORNING[1])
    in_a = (dm >= AFTERNOON[0]) & (dm <= AFTERNOON[1])
    is_m = np.array([(a, b) in key_m for a, b in zip(fs, ts)]) & in_m & wk
    is_a = np.array([(a, b) in key_a for a, b in zip(fs, ts)]) & in_a & wk
    u["is_commute"] = is_m | is_a
    u["commute_leg"] = np.where(is_m, "rano", np.where(is_a, "popoludnie", ""))
    # regularnosc kazdego przejazdu dojazdowego (+- 15 min w innych dniach roboczych)
    u["regular_days"] = 0
    com = u[u["is_commute"]]
    for (a, b, leg), g in com.groupby(["from_station", "to_station", "commute_leg"]):
        u.loc[g.index, "regular_days"] = regular_days(g["local_date"], g["dep_min"])
    cols = ["bike", "from_station", "to_station", "from_type", "to_type", "t_departure", "t_arrival", "local_date",
            "local_hour", "dep_min", "dow", "day_type", "is_workday", "is_weekend", "is_holiday", "is_class_day",
            "duration_min", "km", "is_ebike", "battery_start", "elev_diff_m",
            "from_land_use", "to_land_use", "from_district", "to_district",
            "is_commute", "commute_leg", "regular_days"]
    return u[cols].reset_index(drop=True), pairs


# ---------------------------------------------------------------------------
# Operator i dzielnice
# ---------------------------------------------------------------------------


def operator_shifts(reb, check):
    good = set(check.loc[check["full_day"] & ~check["wind_down"], "local_date"])
    work = set(check.loc[check["day_type"] == "workday", "local_date"])
    r = reb.assign(local_date=reb["t_departure"].dt.tz_convert(TZ).dt.date,
                   hour=reb["t_departure"].dt.tz_convert(TZ).dt.hour)
    r = r[r["local_date"].isin(good)]
    rows = []
    for kind, dates in (("roboczy", good & work), ("wolny", good - work)):
        n_days = len(dates)
        g = r[r["local_date"].isin(dates)]
        cnt = g.groupby("hour").size().reindex(range(24), fill_value=0)
        bikes = g.groupby("hour")["n_bikes"].sum().reindex(range(24), fill_value=0)
        mean = cnt / max(n_days, 1)
        peak = mean.max()
        for h in range(24):
            rows.append({"day_kind": kind, "hour": h, "n_days": n_days,
                         "relocations_per_day": round(float(mean[h]), 3),
                         "bikes_per_day": round(float(bikes[h] / max(n_days, 1)), 2),
                         "share_of_day": round(float(cnt[h] / max(cnt.sum(), 1)), 4),
                         "is_shift": bool(peak > 0 and mean[h] >= SHIFT_SHARE * peak)})
    return pd.DataFrame(rows)


def district_flows(trips, districts, days, t0, t1):
    """Dzielnica x godzina (UTC): wyjazdy i przyjazdy uzytkownikow, przewozy operatora, bilans."""
    names = sorted(districts["name"]) if districts is not None else []
    hours = pd.date_range(t0.floor("h"), t1.floor("h"), freq="h")
    grid = pd.MultiIndex.from_product([names, hours], names=["district", "hour"])
    half = pd.to_timedelta(150, unit="s")
    parts = {}
    u = clean_user_trips(trips)
    s = trips[trips["type"] == "service"]
    for name, df, side, tcol, shift in (("departures", u, "from", "t_departure", half),
                                        ("arrivals", u, "to", "t_arrival", -half),
                                        ("service_out", s, "from", "t_departure", half),
                                        ("service_in", s, "to", "t_arrival", -half)):
        d = district_of(df[f"{side}_lat"], df[f"{side}_lon"], districts)
        h = (df[tcol] + shift).dt.floor("h")
        parts[name] = pd.DataFrame({"district": d, "hour": h}).dropna().groupby(["district", "hour"]).size()
    out = pd.DataFrame(parts).reindex(grid).fillna(0).astype(int).reset_index()
    out["net"] = out["arrivals"] - out["departures"]
    loc = out["hour"].dt.tz_convert(TZ)
    out["local_date"] = loc.dt.date
    out["local_hour"] = loc.dt.hour
    out["day_type"] = out["local_date"].map(days["day_type"]).fillna("") if "day_type" in days else ""
    return out


# ---------------------------------------------------------------------------


def build_agent_tables(log=log):
    st = pd.read_parquet(PROCESSED / "stations.parquet")
    trips = pd.read_parquet(PROCESSED / "trips.parquet")
    reb = pd.read_parquet(PROCESSED / "rebalancing_observed.parquet")
    obs = pd.read_parquet(PROCESSED / "observed_timeseries.parquet", columns=["time", "station_id", "is_spike"])
    obs = obs[~obs["is_spike"]]
    fleet = pd.read_parquet(PROCESSED / "fleet_timeseries.parquet")
    ctx = pd.read_parquet(PROCESSED / "context_hourly.parquet")
    days = day_info(ctx)
    districts = load_districts()
    if districts is None:
        log("  brak data/static/osm/districts.geojson - dzielnice puste")

    st = station_table(st.drop(columns=[c for c in ("district", "land_use") if c in st]), districts)
    st.to_parquet(PROCESSED / "stations.parquet", index=False)

    check = daily_check(obs, fleet, reb, days)
    check.to_parquet(PROCESSED / "daily_check.parquet", index=False)
    log(f"  daily_check: {len(check)} dni, pelne {int(check['full_day'].sum())}, "
        f"zwijanie sezonu: {int(check['wind_down'].sum())}")

    tf, pairs = trip_features(trips, st, days, districts)
    tf.to_parquet(PROCESSED / "trip_features.parquet", index=False)
    pairs.to_parquet(PROCESSED / "commute_pairs.parquet", index=False)
    log(f"  trip_features: {len(tf)} przejazdow, dojazdowe {int(tf['is_commute'].sum())} "
        f"({tf['is_commute'].mean():.1%}); commute_pairs: {len(pairs)} par")

    shifts = operator_shifts(reb, check)
    shifts.to_parquet(PROCESSED / "operator_shifts.parquet", index=False)
    on = shifts[shifts["is_shift"]].groupby("day_kind")["hour"].agg(lambda h: ",".join(map(str, h)))
    log(f"  operator_shifts: godziny pracy {on.to_dict()} (kiedy, nie ile ciezarowek)")

    flows = district_flows(trips, districts, days, obs["time"].min(), obs["time"].max())
    flows.to_parquet(PROCESSED / "district_flows.parquet", index=False)
    log(f"  district_flows: {len(flows)} wierszy ({flows['district'].nunique()} dzielnic)")
    return check, tf, pairs, shifts, flows


def report_section(check, pairs, shifts):
    """Dopisek do quality_report.md."""
    lines = ["", "## Dni i koniec sezonu", "",
             "| dzień | typ | pokrycie | aktywne stacje | rowery na stacjach (mediana) | relokacje | zwijanie sezonu |",
             "|---|---|---|---|---|---|---|"]
    for r in check.itertuples():
        lines.append(f"| {r.local_date} | {r.day_type} | {r.coverage:.0%} | {r.active_stations} | "
                     f"{r.bikes_at_stations_median:.0f} | {r.relocations} | {'**TAK**' if r.wind_down else ''} |")
    lines += ["", f"Zwijanie sezonu: aktywnych stacji < {WIND_DOWN_STATIONS:.0%} albo rowerów na stacjach "
              f"< {WIND_DOWN_FLEET:.0%} mediany wcześniejszych pełnych dni. Takie dni nie wchodzą do "
              "operator_shifts i trzeba je wykluczyć z kalibracji.", "",
              "## Dane dla agentów", "",
              f"- Pary dojazdowe (≥ {COMMUTE_MIN_DAYS} dni robocze A→B 6:30–9:30 i B→A 15:00–19:00): {len(pairs)}"]
    if len(pairs):
        lines.append(f"- Regularność rano (dni z przejazdem ±{REGULAR_TOL_MIN} min): mediana "
                     f"{pairs['regular_days_morning'].median():.0f}, max {pairs['regular_days_morning'].max()}")
    for kind, g in shifts.groupby("day_kind"):
        h = g.loc[g["is_shift"], "hour"].tolist()
        lines.append(f"- Operator ({kind}, {g['n_days'].iloc[0]} dni): godziny pracy "
                     f"{', '.join(f'{x}:00' for x in h) if h else 'brak'}")
    return "\n".join(lines) + "\n"


def main(argv=None):
    import sys

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter).parse_args(argv)
    check, _, pairs, shifts, _ = build_agent_tables()
    path = PROCESSED / "quality_report.md"
    if path.exists():
        text = path.read_text(encoding="utf-8").split("\n## Dni i koniec sezonu")[0].rstrip("\n") + "\n"
        path.write_text(text + report_section(check, pairs, shifts), encoding="utf-8")


if __name__ == "__main__":
    main()
