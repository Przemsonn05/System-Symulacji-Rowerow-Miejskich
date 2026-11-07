"""Reczny pomiar opoznienia feedu / aplikacji Veturilo (zadanie 1c). Do zrobienia do 30.11 (koniec sezonu).

Z zebranych danych opoznienia nie da sie zmierzyc: feed nie podaje last_reported ani feed_last_updated,
a my pytamy co 5 min. Pomiar reczny:

1. Na laptopie przy stacji (albo z telefonu z hotspotem) uruchom nasluch jednej stacji:

       python tools/app_latency.py watch --station "Plac Politechniki" --out pomiar.csv

   Skrypt co 10 s pyta feed nextbike-live i zapisuje kazda zmiane liczby rowerow / numerow rowerow
   (dokladny czas UTC + ktore rowery przybyly lub ubyly).

2. Druga osoba 5-10 razy wypozycza i oddaje rower na tej stacji, zapisujac DOKLADNY czas
   (zegar telefonu, sekundy) i numer roweru w pliku CSV:

       action,time,bike
       rent,2026-11-12 08:31:05,614338
       return,2026-11-12 08:36:40,614338

   Czas lokalny (Europe/Warsaw) albo z sufiksem +00:00 dla UTC.

3. Wynik:

       python tools/app_latency.py analyze --watch pomiar.csv --manual reczne.csv

   Opoznienie = chwila, w ktorej feed pokazal zmiane, minus czas z notatki. Wynik (mediana, min, max)
   wpisz do sim_params jako opoznienie aplikacji. Jesli pomiar sie nie uda, opoznienie zostaje
   parametrem scenariusza (0, 5, 10 min).

Uwaga: dokladnosc = krok pytania (domyslnie 10 s) + dokladnosc zegara telefonu.
"""

import argparse
import csv
import datetime as dt
import json
import sys
import time
import urllib.request
from pathlib import Path

LIVE_URL = "https://maps2.nextbike.net/maps/nextbike-live.json?city=812"
USER_AGENT = "Mozilla/5.0 (student project; bike-share simulation)"
TZ = "Europe/Warsaw"


def fetch_places():
    req = urllib.request.Request(LIVE_URL, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        raw = json.loads(resp.read().decode("utf-8"))
    for country in raw.get("countries", []):
        for city in country.get("cities", []):
            for p in city.get("places", []):
                if p.get("spot") and not p.get("bike"):
                    yield p


def find_station(query):
    q = query.strip().lower()
    places = list(fetch_places())
    exact = [p for p in places if str(p.get("uid")) == q or str(p.get("number")) == q]
    if exact:
        return exact[0]
    hits = [p for p in places if q in str(p.get("name", "")).lower()]
    if not hits:
        sys.exit(f"Nie znaleziono stacji '{query}'")
    if len(hits) > 1:
        print("Pasuje kilka stacji, biore pierwsza (podaj uid, zeby wybrac inna):")
        for p in hits[:10]:
            print(f"  uid {p.get('uid')}: {p.get('name')}")
    return hits[0]


def watch(args):
    st = find_station(args.station)
    uid = st.get("uid")
    print(f"Stacja: {st.get('name')} (uid {uid}); pytanie co {args.every} s; Ctrl+C konczy.")
    out = Path(args.out)
    new = not out.exists()
    prev = None
    with out.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["time_utc", "bikes", "added", "removed"])
        while True:
            t = dt.datetime.now(dt.timezone.utc)
            try:
                p = next((x for x in fetch_places() if x.get("uid") == uid), None)
            except Exception as e:  # siec
                print(f"{t:%H:%M:%S} blad: {e}")
                time.sleep(args.every)
                continue
            if p is not None:
                nums = set(map(str, p.get("bike_numbers") or []))
                bikes = p.get("bikes_available_to_rent", p.get("bikes"))
                if prev is None or nums != prev[1] or bikes != prev[0]:
                    added = sorted(nums - prev[1]) if prev else []
                    removed = sorted(prev[1] - nums) if prev else []
                    w.writerow([t.isoformat(timespec="seconds"), bikes, " ".join(added), " ".join(removed)])
                    f.flush()
                    print(f"{t:%H:%M:%S} UTC  rowery {bikes}  +{added}  -{removed}")
                    prev = (bikes, nums)
            time.sleep(args.every)


def _parse_time(s):
    import pandas as pd

    t = pd.Timestamp(s)
    return (t.tz_localize(TZ) if t.tzinfo is None else t).tz_convert("UTC")


def analyze(args):
    import pandas as pd

    w = pd.read_csv(args.watch, dtype=str).fillna("")
    w["time"] = pd.to_datetime(w["time_utc"], utc=True)
    m = pd.read_csv(args.manual, dtype=str)
    rows = []
    for r in m.itertuples():
        t0 = _parse_time(r.time)
        col = "removed" if r.action.strip() == "rent" else "added"
        seen = w[(w["time"] >= t0 - pd.Timedelta(minutes=2)) & w[col].str.split().apply(lambda x: str(r.bike) in x)]
        if seen.empty:
            rows.append({"action": r.action, "bike": r.bike, "manual": t0, "feed": None, "delay_s": None})
            continue
        t1 = seen["time"].iloc[0]
        rows.append({"action": r.action, "bike": r.bike, "manual": t0, "feed": t1,
                     "delay_s": (t1 - t0).total_seconds()})
    res = pd.DataFrame(rows)
    print(res.to_string(index=False))
    d = res["delay_s"].dropna()
    if len(d):
        print(f"\nOpoznienie feedu: mediana {d.median():.0f} s, min {d.min():.0f} s, max {d.max():.0f} s "
              f"(n = {len(d)}; dokladnosc +- krok pytania)")
    else:
        print("\nBrak dopasowanych zdarzen - sprawdz numery rowerow i czasy.")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("watch", help="nasluch jednej stacji")
    a.add_argument("--station", required=True, help="fragment nazwy albo uid stacji")
    a.add_argument("--every", type=float, default=10.0, help="krok pytania [s], 10-15 s")
    a.add_argument("--out", default="pomiar_feed.csv")
    b = sub.add_parser("analyze", help="porownanie z reczna notatka")
    b.add_argument("--watch", required=True)
    b.add_argument("--manual", required=True)
    args = ap.parse_args()
    watch(args) if args.cmd == "watch" else analyze(args)


if __name__ == "__main__":
    main()
