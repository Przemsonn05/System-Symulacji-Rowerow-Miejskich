"""Wspolne sciezki i stale."""

import datetime as dt
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
STATIC = DATA / "static"
OSM_DIR = STATIC / "osm"
PROCESSED = ROOT / "processed"

# Czas wszedzie w UTC; strefa lokalna tylko do godziny i typu dnia.
TZ = "Europe/Warsaw"

# Poczatek zbierania danych live.
DATA_START = dt.date(2026, 10, 22)
# Zakres kalendarza (rok akademicki 2026/2027 do konca czerwca).
CALENDAR_START = dt.date(2026, 10, 1)
CALENDAR_END = dt.date(2027, 6, 30)

WARSAW_LAT, WARSAW_LON = 52.2297, 21.0122
# Centrum miasta = Palac Kultury i Nauki.
CENTER_LAT, CENTER_LON = 52.2318, 21.0060
# Prostokat obejmujacy Warszawe (rowery z data/loose spoza niego sa odrzucane).
BBOX = {"lat_min": 52.09, "lat_max": 52.37, "lon_min": 20.85, "lon_max": 21.28}

PLACE = "Warszawa, Polska"
PLACE_SRODMIESCIE = "Śródmieście, Warszawa, Polska"
# Uklad metryczny dla Polski (PUWG 1992) - do odleglosci i buforow.
CRS_METRIC = "EPSG:2180"

USER_AGENT = "Mozilla/5.0 (student project; bike-share simulation)"
