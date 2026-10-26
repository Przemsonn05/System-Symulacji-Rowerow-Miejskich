"""Odczyt surowych danych zbieranych przez collect.py (data/*/RRRR-MM-DD.json[l].gz)."""

import gzip
import json
import math
from pathlib import Path

import pandas as pd

from .config import DATA


def day_files(folder, pattern="*.jsonl.gz"):
    return sorted((DATA / folder).glob(pattern))


def iter_jsonl(path):
    """Linie pliku jsonl.gz (takze wieloczlonowego); uszkodzone linie sa pomijane."""
    with gzip.open(path, "rt", encoding="utf-8") as f:
        for line in f:
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def iter_snapshots():
    """Kolejne pomiary stanu stacji: (fetched_at, [rekordy stacji]).

    collect.py zapisuje rekordy jednego pomiaru jeden po drugim, wiec wystarczy
    grupowac kolejne linie o tym samym fetched_at - bez wczytywania wszystkiego.
    """
    current, rows = None, []
    for path in day_files("status"):
        for rec in iter_jsonl(path):
            ts = rec.get("fetched_at")
            if ts != current:
                if rows:
                    yield current, rows
                current, rows = ts, []
            rows.append(rec)
    if rows:
        yield current, rows


def read_jsonl_folder(folder):
    """Caly folder jsonl.gz jako DataFrame (dla malych zbiorow: loose, traffic, incidents)."""
    rows = [rec for path in day_files(folder) for rec in iter_jsonl(path)]
    df = pd.DataFrame(rows)
    if "fetched_at" in df:
        df["time"] = pd.to_datetime(df["fetched_at"], utc=True)
    return df


def read_info():
    """Wszystkie dzienne pliki info jako jeden DataFrame z kolumna day."""
    frames = []
    for path in sorted((DATA / "info").glob("*.json.gz")):
        with gzip.open(path, "rt", encoding="utf-8") as f:
            info = json.load(f)
        st = pd.DataFrame(info.get("data", {}).get("stations", []))
        if st.empty:
            continue
        st["day"] = Path(path.stem).stem  # RRRR-MM-DD
        frames.append(st)
    df = pd.concat(frames, ignore_index=True)
    df["station_id"] = df["station_id"].astype(str)
    return df


def haversine_km(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = (
        math.sin((p2 - p1) / 2) ** 2
        + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    )
    return 6371 * 2 * math.asin(math.sqrt(a))
