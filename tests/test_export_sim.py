"""Eksport symulacji do 3D: zadania dyspozytora, odcinki ciezarowek, agenci i fale pustek."""

import datetime as dt

import numpy as np
import pandas as pd
import pytest

from src.viz.export_sim import agents_block, dispatcher_tasks, flat_cascades, truck_legs

SIDX = {"A": 0, "B": 1, "C": 2}


def ev(rows):
    cols = ["minute", "event", "station_id", "to_station", "truck_id", "load", "request_id"]
    return pd.DataFrame([dict(zip(cols, r)) for r in rows], columns=cols)


TRUCK = ev([
    (0.0, "truck_departure", "C", "A", 0, 0, None),   # przydzial: jedzie pusta po rowery do A
    (6.0, "truck_arrival", "A", None, 0, 0, None),
    (6.25, "truck_load", "A", None, 0, None, None),
    (6.5, "truck_load", "A", None, 0, None, None),
    (6.5, "truck_departure", "A", "B", 0, 2, None),  # z 2 rowerami do B
    (14.0, "truck_arrival", "B", None, 0, 2, None),
    (14.25, "truck_unload", "B", None, 0, None, None),
    (14.5, "truck_unload", "B", None, 0, None, None),
])


def test_truck_legs_pair_departures_with_arrivals():
    legs = truck_legs(TRUCK, None, SIDX)
    assert list(zip(legs["from"], legs["to"], legs["n"])) == [("C", "A", 0), ("A", "B", 2)]
    assert legs["arr"].tolist() == [6.0, 14.0]


def test_dispatcher_task_from_event_order():
    tasks = dispatcher_tasks(TRUCK, SIDX)
    assert len(tasks) == 1
    t = tasks[0]
    assert (t["pick"], t["drop"], t["n"], t["truck"]) == ("A", "B", 2, 0)
    assert t["t0"] == 0.0 and t["t1"] == 14.5


def test_agents_block_lost_and_walk_times():
    e = ev([
        (60.0, "user_arrival", "A", None, None, None, 1),
        (60.0, "walk_to_alternative", "A", "B", None, None, 1),
        (66.0, "rental", "B", "C", None, None, 1),
        (70.0, "lost_demand", "C", None, None, None, 2),
    ])
    a = agents_block(e, lambda m: int(m * 60), SIDX)
    assert a["walkT"] == [3600] and a["walkEnd"] == [3960] and (a["walkFrom"], a["walkTo"]) == ([0], [1])
    assert a["lostT"] == [4200] and a["lostSt"] == [2]


def test_flat_cascades_offsets_and_min_size():
    day0 = pd.Timestamp("2026-11-05").tz_localize("Europe/Warsaw")
    members = [
        {"date": dt.date(2026, 11, 5), "station_ids": ["A", "B", "C"], "minutes": [480.0, 485.0, 495.0]},
        {"date": dt.date(2026, 11, 5), "station_ids": ["A", "B"], "minutes": [600.0, 605.0]},  # < 3 stacje
    ]
    c = flat_cascades(members, SIDX, day0)
    assert c["start"] == [0] and c["len"] == [3]
    assert c["st"] == [0, 1, 2] and c["t"] == [28800, 29100, 29700]
