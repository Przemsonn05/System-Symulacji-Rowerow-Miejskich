"""Przetworzenie danych live z data/ do processed/.

  python -m src.data.build                 # wszystko
  python -m src.data.build --no-features   # bez cech OSM stacji (szybciej)

Wynik (processed/):
  observed_timeseries.parquet   stan stacji w kazdym pomiarze (tylko stacje aktywne)
  stations.parquet              stacje + statystyki + cechy otoczenia
  trips.parquet                 odtworzone przejazdy (user / service)
  rebalancing_observed.parquet  relokacje (>= 4 rowery razem miedzy para stacji)
  empty_periods.parquet         okresy pustych stacji (popyt ocenzurowany)
  station_hourly.parquet        stacja x godzina: wypozyczenia, zwroty, czas dostepnosci
  fleet_timeseries.parquet      flota w kazdym pomiarze (stacje, poza stacjami, w drodze)
  context_hourly.parquet        pogoda, zmrok, kalendarz, wydarzenia, ruch drogowy
  quality_report.md             raport jakosci danych
"""

import argparse
import datetime as dt

import pandas as pd

from .aggregates import empty_periods, fleet_timeseries, flow_balance, station_hourly
from .config import BBOX, PROCESSED
from .context import build_context
from .raw import iter_snapshots, read_info, read_jsonl_folder
from .trips import Location, TripBuilder, mark_service

DEDUP_SEC = 60  # pomiar < 60 s po poprzednim = duplikat (styk runow zbierania)
GAP_REPORT_MIN = 15


def log(msg):
    print(msg, flush=True)


def load_stations():
    info = read_info()
    latest = info.sort_values("day").drop_duplicates("station_id", keep="last")
    cols = ["station_id", "name", "lat", "lon", "capacity", "number",
            "special_racks", "terminal_type", "rack_locks", "place_type"]
    st = latest[[c for c in cols if c in latest]].reset_index(drop=True)
    st["info_first_day"] = info.groupby("station_id")["day"].min().reindex(st["station_id"]).values
    st["info_last_day"] = latest["day"].values
    return st


def load_loose():
    """Rowery poza stacjami: {fetched_at: {rower: Location}} w granicach Warszawy,
    {fetched_at: {rower: bateria}} i {fetched_at: liczba rowerow poza Warszawa}."""
    lo = read_jsonl_folder("loose")
    if lo.empty:
        return {}, {}, {}
    lo = lo[lo["bike_number"].notna()]
    inside = lo["lat"].between(BBOX["lat_min"], BBOX["lat_max"]) & lo["lon"].between(BBOX["lon_min"], BBOX["lon_max"])
    outside = lo[~inside].groupby("fetched_at").size().to_dict()
    lo = lo[inside]
    locs, battery = {}, {}
    for ts, g in lo.groupby("fetched_at"):
        locs[ts] = {
            str(b): Location("loose", str(p), la, lo_)
            for b, p, la, lo_ in zip(g["bike_number"], g["place_id"], g["lat"], g["lon"])
        }
        if "battery" in g:
            battery[ts] = {str(b): v for b, v in zip(g["bike_number"], g["battery"]) if pd.notna(v)}
    return locs, battery, outside


EBIKE_LOW_PCT = 20  # e-rower ponizej tego poziomu baterii traktujemy jako rozladowany


def scan_status(stations, loose):
    """Jedno przejscie po pomiarach: szereg czasowy stacji, flota i przejazdy."""
    loose_locs, loose_battery, loose_outside = loose
    coords = {r.station_id: (r.lat, r.lon) for r in stations.itertuples()}
    builder = TripBuilder()
    rows, snaps, fleet = [], [], []
    ebike_ids = set()
    last_t, n_dup = None, 0
    for ts, recs in iter_snapshots():
        t = pd.Timestamp(ts)
        if last_t is not None and (t - last_t).total_seconds() < DEDUP_SEC:
            n_dup += 1
            continue
        last_t = t
        has_numbers = "bike_numbers" in recs[0]
        snaps.append((t, has_numbers, recs[0].get("source")))
        locs = {} if has_numbers else None
        battery = dict(loose_battery.get(ts, {}))
        for r in recs:
            sid = str(r["station_id"])
            eb = r.get("ebike_battery")
            n_eb = len(eb) if eb else (0 if "ebike_battery" in r else None)
            n_low = sum(v < EBIKE_LOW_PCT for v in eb.values()) if eb else n_eb
            rows.append((t, sid, r.get("bikes"), r.get("docks"), r.get("is_renting"), r.get("active_place"),
                         n_eb, n_low))
            if eb:
                battery.update({str(k): v for k, v in eb.items()})
            if has_numbers:
                lat, lon = coords.get(sid, (None, None))
                loc = Location("station", sid, lat, lon)
                for b in r.get("bike_numbers") or []:
                    locs[str(b)] = loc
        if has_numbers:
            for b, loc in loose_locs.get(ts, {}).items():
                locs.setdefault(b, loc)
        ebike_ids.update(battery)
        builder.step(t, locs, battery)
        in_use, away = builder.in_transit(t) if has_numbers else (None, None)
        fleet.append((
            t, sum(r.get("bikes") or 0 for r in recs), len(loose_locs.get(ts, {})) if has_numbers else None,
            loose_outside.get(ts, 0) if has_numbers else None, in_use, away,
            len(battery) if "ebike_battery" in recs[0] else None,
        ))

    ts_df = pd.DataFrame(rows, columns=["time", "station_id", "bikes", "docks", "is_renting", "active_place",
                                        "ebikes", "ebikes_low"])
    snap_df = pd.DataFrame(snaps, columns=["time", "has_bike_numbers", "source"])
    fleet_df = pd.DataFrame(fleet, columns=["time", "at_stations", "loose_warsaw", "loose_outside",
                                            "in_use", "away_long", "ebikes_parked"])
    return ts_df, snap_df, fleet_df, builder, n_dup, ebike_ids


def clean_timeseries(ts, stations):
    """Usuwa stacje nieaktywne. W starym formacie (przed 23.10.2026 08:00 UTC) nie ma
    active_place, wiec aktywnosc stacji bierzemy z jej pierwszego pomiaru w nowym formacie."""
    act = ts["is_renting"].astype(float).where(ts["active_place"].notna())
    act = act.groupby(ts["station_id"]).transform("bfill")
    active = act.fillna(ts["is_renting"].astype(float)).astype(bool) & ts["is_renting"].astype(bool)
    out = ts.loc[active, ["time", "station_id", "bikes", "docks", "ebikes", "ebikes_low"]].copy()
    out[["ebikes", "ebikes_low"]] = out[["ebikes", "ebikes_low"]].astype("Int64")  # brak w starym formacie
    cap = stations.set_index("station_id")["capacity"]
    out["is_empty"] = out["bikes"] == 0
    # bikes > capacity jest dozwolone (stacje Veturilo 3.0 przyjmuja rowery ponad stojaki)
    out["is_overfull"] = out["bikes"] > out["station_id"].map(cap)
    return out.reset_index(drop=True), active


def station_stats(stations, obs, ts_all, active):
    g = obs.groupby("station_id")
    s = pd.DataFrame({
        "first_seen": g["time"].min(),
        "last_seen": g["time"].max(),
        "n_obs": g.size(),
        "mean_bikes": g["bikes"].mean().round(2),
        "share_empty": g["is_empty"].mean().round(4),
        "share_overfull": g["is_overfull"].mean().round(4),
    })
    inactive = 1 - active.groupby(ts_all["station_id"]).mean()
    out = stations.merge(s, left_on="station_id", right_index=True, how="left")
    out["share_inactive"] = out["station_id"].map(inactive).round(4)
    return out


def add_trip_elevation(trips):
    """Roznica wysokosci terenu stacja docelowa - poczatkowa (podjazd > 0)."""
    from .config import STATIC

    path = STATIC / "elevation.csv"
    trips["elev_diff_m"] = float("nan")
    if path.exists():
        el = pd.read_csv(path, dtype={"station_id": str}).set_index("station_id")["elevation_m"]
        trips["elev_diff_m"] = (trips["to"].map(el) - trips["from"].map(el)).round(1)
    return trips


def quality_report(snaps, n_dup, n_inactive, n_stations, obs, trips, reb, builder):
    t = snaps["time"]
    gaps = t.diff().dt.total_seconds() / 60
    big = snaps.loc[gaps > GAP_REPORT_MIN, "time"]
    expected = (t.max() - t.min()).total_seconds() / 300 + 1
    per_day = t.dt.tz_convert("UTC").dt.date.value_counts().sort_index()
    user = trips[trips["type"] == "user"]
    lines = [
        "# Raport jakości danych",
        "",
        f"Wygenerowano: {dt.datetime.now(dt.timezone.utc):%Y-%m-%d %H:%M} UTC",
        "",
        "## Pomiary stanu stacji",
        "",
        f"- Zakres: {t.min():%Y-%m-%d %H:%M} – {t.max():%Y-%m-%d %H:%M} UTC "
        f"({(t.max() - t.min()).total_seconds() / 86400:.1f} doby)",
        f"- Pomiary: {len(snaps)} (usunięte duplikaty < {DEDUP_SEC} s: {n_dup}); "
        f"pokrycie siatki 5 min: {len(snaps) / expected:.1%}",
        f"- Pomiary w starym formacie (bez `bike_numbers`): {(~snaps['has_bike_numbers']).sum()}",
        f"- Stacje: {n_stations} w `info`, {obs['station_id'].nunique()} aktywnych przynajmniej w jednym pomiarze; "
        f"rekordy stacji nieaktywnych (usunięte): {n_inactive}",
        f"- Luki > {GAP_REPORT_MIN} min: {len(big)}",
    ]
    for end in big:
        start = t[t < end].max()
        lines.append(f"  - {start:%Y-%m-%d %H:%M} → {end:%Y-%m-%d %H:%M} UTC "
                     f"({(end - start).total_seconds() / 60:.0f} min)")
    lines += ["", "Pomiary na dobę (UTC):", "", "| dzień | pomiary |", "|---|---|"]
    lines += [f"| {d} | {n} |" for d, n in per_day.items()]
    lines += [
        "",
        "## Przejazdy",
        "",
        f"- Przejazdy użytkowników: {len(user)}; relokacje (type=service): "
        f"{(trips['type'] == 'service').sum()} rowerów w {len(reb)} grupach",
        f"- Powroty na tę samą stację: {int(user['same_station'].sum())}, w tym prawdopodobne migotanie "
        f"feedu (≤ 10 min, `is_flicker`): {int(user['is_flicker'].sum())}",
        f"- Z/do miejsc poza stacjami: {int((user['from_loose'] | user['to_loose']).sum())}; "
        f"dłuższe niż 4 h: {int(user['is_long'].sum())}; nierealnie szybkie (> 30 km/h, `too_fast`): "
        f"{int(user['too_fast'].sum())}",
        f"- Odrzucone przeskoki GPS (< 0,5 km bez zniknięcia): {builder.stats['gps_jumps']} "
        f"(stacja→stacja {builder.stats.get('gps_jumps_station_station', 0)}, "
        f"poza stacją→poza stacją {builder.stats.get('gps_jumps_loose_loose', 0)}, "
        f"poza stacją→stacja {builder.stats.get('gps_jumps_loose_station', 0)}, "
        f"stacja→poza stacją {builder.stats.get('gps_jumps_station_loose', 0)})",
        f"- Rowery, które pojawiły się bez wcześniejszego zniknięcia (serwis, start po luce): "
        f"{builder.stats['appeared_unmatched']}",
        f"- Rowery w drodze na końcu danych (bez powrotu): {builder.stats.get('open_at_end', 0)}",
        f"- Przerwania ciągłości (luka > 15 min albo stary format): {builder.stats['resets']}",
    ]
    clean = user[~user["is_long"] & ~user["is_flicker"] & ~user["too_fast"]]
    if len(clean):
        q = clean["duration_min"].quantile([0.1, 0.5, 0.9])
        lines.append(f"- Przejazdy po odfiltrowaniu flag (`is_long`, `is_flicker`, `too_fast`): {len(clean)}; "
                     f"czas p10 {q[0.1]:.0f}, mediana {q[0.5]:.0f}, p90 {q[0.9]:.0f} min "
                     "(zawyżony średnio o ok. 5 min – odstęp pomiarów)")
    return "\n".join(lines) + "\n"


def extra_report(balance, empty, fleet, trips):
    exact, unexplained = balance
    user = trips[(trips["type"] == "user") & ~trips["is_flicker"] & ~trips["too_fast"] & ~trips["is_long"]]
    eb = user["is_ebike"]
    f = fleet.dropna(subset=["in_use"])
    lines = [
        "",
        "## Kontrola przejazdów (bilans przepływów)",
        "",
        f"- Odstępy pomiarów, w których zmiana liczby rowerów na stacji = przyjazdy − odjazdy: {exact:.1%}",
        f"- Zmiany liczby rowerów niewyjaśnione przejazdami: {unexplained:.1%} "
        "(odrzucone przeskoki GPS, serwis bez śladu w danych, luki)",
        "",
        "## Puste stacje (popyt ocenzurowany)",
        "",
        f"- Okresy pustej stacji: {len(empty)} na {empty['station_id'].nunique()} stacjach; "
        f"mediana {empty['duration_min'].median():.0f} min, p90 {empty['duration_min'].quantile(0.9):.0f} min; "
        f"z nieznanym końcem (luka/koniec danych): {int(empty['censored_end'].sum())}",
        "",
        "## Flota i e-rowery",
        "",
    ]
    if len(f):
        last = f.iloc[-1]
        lines.append(
            f"- Ostatni pomiar: na stacjach {last['at_stations']:.0f}, poza stacjami w Warszawie "
            f"{last['loose_warsaw']:.0f}, poza Warszawą {last['loose_outside']:.0f}, w drodze {last['in_use']:.0f}, "
            f"poza systemem > 4 h {last['away_long']:.0f}; docelowa flota operatora: {last.get('set_point_bikes', 'b.d.')}"
        )
        lines.append(f"- Rowery w drodze jednocześnie: mediana {f['in_use'].median():.0f}, max {f['in_use'].max():.0f}")
    if len(user):
        lines.append(f"- E-rowery: {eb.mean():.1%} przejazdów użytkowników; mediana baterii na starcie "
                     f"{user.loc[eb, 'battery_start'].median():.0f}%")
    return "\n".join(lines) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--no-features", action="store_true", help="pomin cechy otoczenia stacji (OSM)")
    args = ap.parse_args(argv)
    PROCESSED.mkdir(exist_ok=True)

    log("Stacje i rowery poza stacjami...")
    stations = load_stations()
    loose = load_loose()

    log("Pomiary stanu stacji i przejazdy...")
    ts_all, snaps, fleet, builder, n_dup, ebike_ids = scan_status(stations, loose)
    obs, active = clean_timeseries(ts_all, stations)
    n_inactive = int((~active).sum())
    obs.to_parquet(PROCESSED / "observed_timeseries.parquet", index=False)
    log(f"  observed_timeseries: {len(obs)} wierszy, {len(snaps)} pomiarow (duplikaty: {n_dup})")

    trips, reb = mark_service(builder.to_frame())
    # e-rower = rower, dla ktorego feed kiedykolwiek podal poziom baterii
    trips["is_ebike"] = trips["bike"].isin(ebike_ids)
    trips = add_trip_elevation(trips)
    if not args.no_features:
        from .network import add_network_distance

        trips, reb = add_network_distance(trips, reb, stations, log)
    trips.to_parquet(PROCESSED / "trips.parquet", index=False)
    reb.to_parquet(PROCESSED / "rebalancing_observed.parquet", index=False)
    log(f"  trips: {len(trips)} (service: {(trips['type'] == 'service').sum()}), relokacje: {len(reb)} grup")

    empty = empty_periods(obs)
    empty.to_parquet(PROCESSED / "empty_periods.parquet", index=False)
    hourly = station_hourly(obs, trips)
    hourly.to_parquet(PROCESSED / "station_hourly.parquet", index=False)
    fleet = fleet_timeseries(fleet)
    fleet.to_parquet(PROCESSED / "fleet_timeseries.parquet", index=False)
    balance = flow_balance(obs, trips)
    log(f"  empty_periods: {len(empty)}, station_hourly: {len(hourly)} wierszy, fleet_timeseries: {len(fleet)}")

    log("Kontekst godzinowy...")
    ctx = build_context(snaps["time"].min(), snaps["time"].max(), log)
    ctx.to_parquet(PROCESSED / "context_hourly.parquet", index=False)
    log(f"  context_hourly: {len(ctx)} godzin, {ctx.shape[1]} kolumn")

    log("Stacje...")
    st = station_stats(stations, obs, ts_all, active)
    if not args.no_features:
        from .features import add_station_features

        st = add_station_features(st, log)
    st.to_parquet(PROCESSED / "stations.parquet", index=False)
    log(f"  stations: {len(st)} stacji, {st.shape[1]} kolumn")

    report = quality_report(snaps, n_dup, n_inactive, len(stations), obs, trips, reb, builder)
    report += extra_report(balance, empty, fleet, trips)
    (PROCESSED / "quality_report.md").write_text(report, encoding="utf-8")
    log("")
    log(report)


if __name__ == "__main__":
    main()
