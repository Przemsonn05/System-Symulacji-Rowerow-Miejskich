"""Testy metryk emergencji i danych dla agentow na malych, recznie ulozonych przykladach."""

import datetime as dt

import numpy as np
import pandas as pd
import pytest

from src.data.agents import commute_pairs, land_use, regular_days
from src.metrics.emergence import (cascade_stats, cascades, empty_concentration, empty_durations, empty_onsets,
                                   hourly_rhythm, lorenz_gini, morans_i, null_test)
from src.metrics.io import RunData, full_days

LAT0, LON0 = 52.23, 21.0
M_LAT = 110_574.0
M_LON = 111_320.0 * np.cos(np.radians(LAT0))


def make_run(bikes_by_station, xs_m, start="2026-11-02T23:00:00Z", trips=None, day_type=None):
    """bikes_by_station: lista list (liczba rowerow co 5 min), xs_m: polozenie stacji na osi wschod [m]."""
    n = len(bikes_by_station[0])
    idx = pd.date_range(start, periods=n, freq="5min")
    ids = [f"s{i}" for i in range(len(bikes_by_station))]
    bikes = pd.DataFrame(np.array(bikes_by_station, dtype=float).T, index=idx, columns=ids)
    st = pd.DataFrame({"station_id": ids, "lat": LAT0, "lon": LON0 + np.asarray(xs_m, float) / M_LON,
                       "capacity": 10})
    trips = trips if trips is not None else pd.DataFrame(columns=["t_departure", "t_arrival", "from_lat",
                                                                    "from_lon", "to_lat", "to_lon"])
    dates = set(idx.tz_convert("Europe/Warsaw").date)
    return RunData("test", bikes, st, trips, day_type or {d: "workday" for d in dates})


# ---------------------------------------------------------------------------- Gini, Lorenz


def test_gini_equal_and_concentrated():
    assert lorenz_gini([1, 1, 1, 1])[2] == pytest.approx(0.0, abs=1e-12)
    # cala "pustka" na jednej z 4 stacji: Gini = (n - 1) / n
    assert lorenz_gini([0, 0, 0, 5])[2] == pytest.approx(0.75)


def test_empty_concentration_top_shares():
    # 10 stacji, pusta tylko pierwsza (polowa czasu) -> 10% stacji = 100% pustek, 90% nigdy pustych
    rows = [[0, 1] * 6] + [[3] * 12 for _ in range(9)]
    r = make_run(rows, np.arange(10) * 2000)
    c = empty_concentration(r)
    assert c["top10_share"] == pytest.approx(1.0)
    assert c["never_empty_share"] == pytest.approx(0.9)


# ---------------------------------------------------------------------------- dlugosc pustek


def test_empty_durations_runs_and_censoring():
    r = make_run([[2, 0, 0, 0, 1, 0, np.nan, 0, 0]], [0])
    d = empty_durations(r)
    assert d["minutes"].tolist() == [15, 5, 10]
    # drugi okres konczy sie brakiem danych, trzeci dotyka konca -> ocenzurowane
    assert d["censored"].tolist() == [False, True, True]


# ---------------------------------------------------------------------------- Moran


def test_moran_cluster_positive_alternating_negative():
    xy = np.column_stack([np.arange(10) * 500.0, np.zeros(10)])
    clustered = morans_i([1, 1, 1, 1, 1, 0, 0, 0, 0, 0], xy, radius_m=600, permutations=499, seed=1)
    assert clustered["I"] > 0.5 and clustered["p"] < 0.05
    alternating = morans_i([1, 0] * 5, xy, radius_m=600, permutations=0)
    assert alternating["I"] < -0.5
    assert clustered["expected"] == pytest.approx(-1 / 9)


# ---------------------------------------------------------------------------- fale pustek


def test_cascade_chain_of_three_neighbours():
    # stacje A, B, C co 500 m pustoszeja w 5., 15. i 25. minucie, stacja D 5 km dalej - w 10. minucie
    a = [1, 0, 0, 0, 0, 0, 0, 0]
    b = [1, 1, 1, 0, 0, 0, 0, 0]
    c = [1, 1, 1, 1, 1, 0, 0, 0]
    d = [1, 1, 0, 0, 0, 0, 0, 0]
    r = make_run([a, b, c, d], [0, 500, 1000, 6000])
    on = empty_onsets(r)
    assert sorted(on["station"]) == [0, 1, 2, 3]
    res = cascades(r, radius_m=800, window=20)
    assert res["size_counts"] == {1: 1, 3: 1}
    assert res["n_cascades_ge3"] == 1 and res["max_size"] == 3
    assert res["linked_share"] == pytest.approx(0.75)
    assert res["members"][0]["station_ids"] == ["s0", "s1", "s2"]


def test_cascade_window_breaks_chain():
    # B pustoszeje 25 min po A - poza oknem 20 min
    a = [1, 0, 0, 0, 0, 0, 0, 0]
    b = [1, 1, 1, 1, 1, 1, 0, 0]
    res = cascades(make_run([a, b], [0, 300]), radius_m=800, window=20)
    assert res["size_counts"] == {1: 2}


def test_null_test_runs_on_two_days():
    # dwa dni robocze po 288 slotow; w obu stacje 0-2 pustoszeja razem rano
    day = np.full((3, 288), 2.0)
    day[:, 96:110] = 0
    rows = np.hstack([day, day])
    r = make_run(rows.tolist(), [0, 400, 800], start="2026-11-02T23:00:00Z")
    assert len(full_days(r)) == 2
    res = null_test(r, n_perm=20, seed=3)
    assert res["observed"]["linked_share"] == pytest.approx(1.0)
    for model in ("inny_dzien", "zamiana_miejsc"):
        p = res[model]["linked_share"]["p"]
        assert 0 < p <= 1


def test_cascade_stats_accepts_null_events():
    near = np.ones((2, 2), bool)
    ev = pd.DataFrame({"station": [0, 1], "date": [dt.date(2026, 11, 3)] * 2, "minute": [60.0, 70.0]})
    assert cascade_stats(ev, near, 20)["n_cascades_ge2"] == 1


# ---------------------------------------------------------------------------- rytm


def test_hourly_rhythm_counts_per_day():
    t0 = pd.Timestamp("2026-11-03T07:10:00", tz="Europe/Warsaw").tz_convert("UTC")
    trips = pd.DataFrame({"t_departure": [t0, t0 + pd.Timedelta(minutes=5), t0 + pd.Timedelta(hours=2)],
                          "t_arrival": [t0] * 3, "from_lat": LAT0, "from_lon": LON0, "to_lat": LAT0, "to_lon": LON0})
    r = make_run([[1] * 288], [0], trips=trips)
    rh = hourly_rhythm(r)
    w = rh[rh["day_kind"] == "roboczy"].set_index("hour")["trips_per_day"]
    assert w[7] == 2 and w[9] == 1 and w.sum() == 3


# ---------------------------------------------------------------------------- dane dla agentow


def test_regular_days_tolerance():
    dates = ["d1", "d2", "d3", "d4"]
    minutes = [480, 490, 470, 540]  # 8:00, 8:10, 7:50, 9:00; 7:50 i 8:10 dziela 20 min > 15
    assert regular_days(dates, minutes, tol=15).tolist() == [3, 2, 2, 1]


def _trip(day, hm, a, b):
    t = pd.Timestamp(f"{day} {hm}", tz="Europe/Warsaw")
    return {"from_station": a, "to_station": b, "from_type": "station", "to_type": "station", "local_date": t.date(),
            "dep_min": t.hour * 60 + t.minute, "is_workday": True, "km": 2.0, "is_ebike": False}


def test_commute_pair_rule_needs_three_days_both_ways():
    rows = []
    for day in ["2026-11-02", "2026-11-03", "2026-11-04"]:
        rows += [_trip(day, "07:50", "A", "B"), _trip(day, "16:30", "B", "A")]
        rows += [_trip(day, "08:00", "C", "D")]                   # tylko rano - nie jest dojazdowa
    rows += [_trip("2026-11-02", "17:00", "D", "C"), _trip("2026-11-03", "17:00", "D", "C")]  # 2 dni - za malo
    pairs = commute_pairs(pd.DataFrame(rows))
    assert list(zip(pairs["home_station"], pairs["work_station"])) == [("A", "B")]
    assert pairs.loc[0, "regular_days_morning"] == 3 and pairs.loc[0, "median_time_morning"] == "07:50"


def test_land_use_priority():
    st = pd.DataFrame({"n_university_300m": [1, 0, 0, 0, 0], "n_office_300m": [50, 50, 0, 0, 0],
                       "n_park_300m": [1, 1, 1, 0, 0], "population_500m": [0, 0, 0, 20000, 0]})
    label, _ = land_use(st)
    assert label.tolist() == ["uczelnia", "biura", "park", "osiedle", "mieszane"]
