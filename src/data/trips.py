"""Odtwarzanie przejazdow z numerow rowerow (bike_numbers) w kolejnych pomiarach.

Przejazd: rower znika z miejsca A (stacji albo punktu poza stacja) i pojawia sie
w miejscu B. Czas zdarzenia jest znany z dokladnoscia do odstepu pomiarow:
t_departure = ostatni pomiar z rowerem w A, t_arrival = pierwszy pomiar z rowerem w B,
wiec duration_min zawyza czas jazdy srednio o ok. jeden odstep (5 min).

Przeskok GPS: rower zmienia miejsce bez znikniecia, a odleglosc < 0,5 km - to
dryf pozycji albo przypisanie do sasiedniej stacji, nie przejazd (odrzucany).
Przy luce w danych > MAX_GAP_MIN przejazdy nie sa laczone przez luke.
"""

import pandas as pd

from .raw import haversine_km

MAX_GAP_MIN = 15
GPS_JUMP_KM = 0.5
SERVICE_MIN_BIKES = 4
LONG_TRIP_MIN = 240
FLICKER_MAX_MIN = 10  # dwa odstepy pomiarow
MAX_SPEED_KMH = 30


class Location:
    __slots__ = ("kind", "id", "lat", "lon")

    def __init__(self, kind, id_, lat, lon):
        self.kind, self.id, self.lat, self.lon = kind, id_, lat, lon

    @property
    def label(self):
        return self.id if self.kind == "station" else f"loose:{self.id}"

    def dist(self, other):
        if None in (self.lat, self.lon, other.lat, other.lon):
            return float("nan")
        return haversine_km(self.lat, self.lon, other.lat, other.lon)


class TripBuilder:
    def __init__(self):
        self.prev_t = None
        self.prev = {}  # rower -> Location w poprzednim pomiarze
        self.prev_battery = {}  # rower -> % baterii w poprzednim pomiarze (e-rowery)
        self.open = {}  # rower -> (Location, czas ostatniego widzenia, bateria) - rower w drodze
        self.trips = []
        self.stats = {"gps_jumps": 0, "appeared_unmatched": 0, "resets": 0}

    def reset(self):
        self.prev_t, self.prev, self.open = None, {}, {}
        self.stats["resets"] += 1

    def step(self, t, locs, battery=None):
        """t: czas pomiaru; locs: {rower: Location} albo None (pomiar bez numerow rowerow);
        battery: {rower: % baterii} dla e-rowerow w tym pomiarze."""
        battery = battery or {}
        if locs is None:
            self.reset()
            return
        if self.prev_t is None or (t - self.prev_t).total_seconds() / 60 > MAX_GAP_MIN:
            if self.prev_t is not None:
                self.stats["resets"] += 1
            self.prev_t, self.prev, self.prev_battery, self.open = t, locs, battery, {}
            return

        for bike, a in self.prev.items():
            b = locs.get(bike)
            if b is None:
                self.open[bike] = (a, self.prev_t, self.prev_battery.get(bike))
            elif a.kind != b.kind or a.id != b.id:
                d = a.dist(b)
                if d < GPS_JUMP_KM:
                    self.stats["gps_jumps"] += 1
                    key = f"gps_jumps_{a.kind}_{b.kind}"
                    self.stats[key] = self.stats.get(key, 0) + 1
                else:
                    self._add(bike, a, b, self.prev_t, t, d, self.prev_battery.get(bike))
        for bike, b in locs.items():
            if bike in self.prev:
                continue
            if bike in self.open:
                a, t0, bat = self.open.pop(bike)
                self._add(bike, a, b, t0, t, a.dist(b), bat)
            else:
                self.stats["appeared_unmatched"] += 1  # z serwisu albo pierwszy raz po luce
        self.prev_t, self.prev, self.prev_battery = t, locs, battery

    def in_transit(self, t):
        """Rowery w drodze w chwili t: (do 4 h, dluzej - zwykle serwis)."""
        long_ = sum((t - t0).total_seconds() / 60 > LONG_TRIP_MIN for _, t0, _ in self.open.values())
        return len(self.open) - long_, long_

    def _add(self, bike, a, b, t0, t1, d, battery):
        self.trips.append(
            (bike, a.label, b.label, a.kind, b.kind, a.lat, a.lon, b.lat, b.lon, t0, t1, d, battery)
        )

    def to_frame(self):
        cols = ["bike", "from_station", "to_station", "from_type", "to_type", "from_lat", "from_lon",
                "to_lat", "to_lon", "t_departure", "t_arrival", "distance_km", "battery_start"]
        df = pd.DataFrame(self.trips, columns=cols)
        # jawne typy - przy braku przejazdow pusta ramka mialaby kolumny object
        for c in ["t_departure", "t_arrival"]:
            df[c] = pd.to_datetime(df[c], utc=True)
        df["distance_km"] = df["distance_km"].astype(float)
        df["battery_start"] = df["battery_start"].astype(float)
        df["duration_min"] = (df["t_arrival"] - df["t_departure"]).dt.total_seconds() / 60
        df["distance_km"] = df["distance_km"].round(3)
        df["same_station"] = (df["from_type"] == "station") & (df["from_station"] == df["to_station"])
        # rower "znika" na jeden pomiar i wraca na te sama stacje - zwykle artefakt feedu
        df["is_flicker"] = df["same_station"] & (df["duration_min"] <= FLICKER_MAX_MIN)
        df["from_loose"] = df["from_type"] == "loose"
        df["to_loose"] = df["to_type"] == "loose"
        df["is_long"] = df["duration_min"] > LONG_TRIP_MIN
        # duration_min to gorna granica czasu jazdy, wiec ta predkosc to dolna granica:
        # > 30 km/h oznacza bledna pozycje w feedzie (zwykle chwilowy punkt poza stacja)
        df["too_fast"] = df["distance_km"] / (df["duration_min"] / 60) > MAX_SPEED_KMH
        df["type"] = "user"
        self.stats["open_at_end"] = len(self.open)
        return df


def mark_service(trips):
    """Relokacje: >= SERVICE_MIN_BIKES rowerow przeniesionych razem miedzy ta sama
    para stacji w tym samym odstepie pomiarow. Zwraca (trips z type, rebalancing)."""
    key = ["from_station", "to_station", "t_departure", "t_arrival"]
    st = trips[(trips["from_type"] == "station") & (trips["to_type"] == "station") & ~trips["same_station"]]
    size = st.groupby(key)["bike"].transform("size")
    service_idx = st.index[size >= SERVICE_MIN_BIKES]
    trips = trips.copy()
    trips.loc[service_idx, "type"] = "service"
    reb = (
        trips.loc[service_idx]
        .groupby(key)
        .agg(n_bikes=("bike", "size"), bikes=("bike", list), distance_km=("distance_km", "first"),
             duration_min=("duration_min", "first"))
        .reset_index()
        .sort_values("t_departure")
        .reset_index(drop=True)
    )
    return trips, reb
