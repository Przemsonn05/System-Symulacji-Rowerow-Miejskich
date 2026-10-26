"""Dane OpenStreetMap dla Warszawy (OSMnx) -> data/static/osm/.

Pliki:
  boundary.geojson                granica Warszawy
  pois.parquet                    punkty POI: category, name, osmid, lat, lon
  cycleways.parquet               drogi rowerowe (GeoParquet, EPSG:4326)
  buildings_srodmiescie.parquet   budynki Srodmiescia z wysokoscia (GeoParquet)
  graph_bike.graphml, graph_drive.graphml   grafy drog (z wycinka BBBike, nie z Overpass)
Odpowiedzi Overpass sa cache'owane w osm/cache (OSMnx), wiec ponowne
uruchomienie nie pobiera ich drugi raz.
"""

import pandas as pd

from .config import OSM_DIR, PLACE, PLACE_SRODMIESCIE

# Kategorie POI: tagi OSM i opcjonalny filtr wierszy (np. metro vs kolej).
POI_TAGS = {
    "restaurant": {"amenity": ["restaurant", "fast_food", "food_court"]},
    "bar": {"amenity": ["bar", "pub", "biergarten", "nightclub"]},
    "cafe": {"amenity": ["cafe"]},
    "office": {"office": True},
    "university": {"amenity": ["university", "college"]},
    "school": {"amenity": ["school"]},
    "mall": {"shop": ["mall"]},
    "attraction": {"tourism": ["attraction", "museum", "gallery", "zoo", "theme_park", "viewpoint"]},
    "park": {"leisure": ["park"]},
    "metro": {"railway": ["station"], "station": ["subway"]},
    "train_station": {"railway": ["station", "halt"]},
    "tram_stop": {"railway": ["tram_stop"]},
    # przystanki autobusowe: z GTFS (transit_stops.parquet), razem z liczba odjazdow
}


def _filter(category, gdf):
    """Doprecyzowanie kategorii, ktorych nie da sie wyrazic samymi tagami."""
    col = gdf.get("station")
    if category == "metro":
        # tagi sa laczone przez OR, wiec trzeba wymagac obu
        gdf = gdf[(col == "subway") & (gdf.get("railway") == "station")] if col is not None else gdf.iloc[0:0]
    elif category == "train_station":
        # dworce/przystanki kolejowe = stacje kolejowe, ktore nie sa stacjami metra
        gdf = gdf[col != "subway"] if col is not None else gdf
    if category in ("metro", "train_station") and "name" in gdf:
        # ta sama stacja bywa zmapowana jako punkt i jako obszar
        named = gdf[gdf["name"].notna()].drop_duplicates("name")
        gdf = pd.concat([named, gdf[gdf["name"].isna()]])
    return gdf


OVERPASS_URLS = [
    "https://overpass-api.de/api",
    "https://overpass.private.coffee/api",
    "https://overpass.kumi.systems/api",
]


def _retry(ox, fn, log, what, attempts=6):
    """Publiczne serwery Overpass bywaja przeciazone (502/504) - ponawiamy
    z rosnacym odstepem, przelaczajac sie miedzy serwerami."""
    import time

    wait = 20
    for i in range(attempts):
        ox.settings.overpass_url = OVERPASS_URLS[i % len(OVERPASS_URLS)]
        try:
            return fn()
        except Exception as e:
            if i == attempts - 1:
                raise
            msg = str(e).splitlines()[0][:120]
            log(f"  {what}: {ox.settings.overpass_url} nie odpowiada ({msg}), ponawiam za {wait} s")
            time.sleep(wait)
            wait = min(wait * 2, 300)


def _setup():
    import osmnx as ox

    OSM_DIR.mkdir(parents=True, exist_ok=True)
    ox.settings.use_cache = True
    ox.settings.cache_folder = str(OSM_DIR / "cache")
    ox.settings.requests_timeout = 600
    # serwery zapasowe nie maja endpointu /status - bez tego OSMnx czeka w nieskonczonosc
    ox.settings.overpass_rate_limit = False
    ox.settings.log_console = False
    ox.settings.log_file = True
    ox.settings.logs_folder = str(OSM_DIR / "logs")
    return ox


def boundary(ox):
    path = OSM_DIR / "boundary.geojson"
    if path.exists():
        import geopandas as gpd

        return gpd.read_file(path)
    gdf = ox.geocode_to_gdf(PLACE)
    gdf[["geometry"]].to_file(path, driver="GeoJSON")
    return gdf


def fetch_pois(ox, polygon, log):
    path = OSM_DIR / "pois.parquet"
    old = pd.read_parquet(path) if path.exists() else None
    # Przyrostowo: pobieramy tylko kategorie, ktorych jeszcze nie ma w pliku.
    todo = {c: t for c, t in POI_TAGS.items() if old is None or c not in set(old["category"])}
    if not todo:
        log(f"  OSM POI: juz sa ({path.name})")
        return
    # Jedno zapytanie Overpass na wszystkie kategorie (OSMnx laczy tagi przez OR),
    # podzial na kategorie lokalnie - kilkanascie osobnych zapytan trwa bardzo dlugo.
    union = {}
    for tags in todo.values():
        for key, val in tags.items():
            if key == "station":
                continue  # doprecyzowanie metra, filtrowane lokalnie
            if val is True or union.get(key) is True:
                union[key] = True
            else:
                union[key] = sorted(set(union.get(key, [])) | set(val))
    log(f"  OSM POI: jedno zapytanie dla kategorii: {', '.join(todo)}...")
    allf = _retry(ox, lambda: ox.features_from_polygon(polygon, union), log, "OSM POI")
    frames = [old] if old is not None else []
    for category, tags in todo.items():
        mask = pd.Series(True, index=allf.index)
        for key, val in tags.items():
            col = allf.get(key)
            if col is None:
                mask &= False
            elif val is True:
                mask &= col.notna()
            else:
                mask &= col.isin(val)
        gdf = _filter(category, allf[mask])
        if gdf.empty:
            log(f"  OSM {category}: 0")
            continue
        # Punkt reprezentatywny lezy wewnatrz poligonu (np. kampus, park).
        pts = gdf.geometry.representative_point()
        idx = gdf.index.to_frame(index=False)
        frames.append(
            pd.DataFrame(
                {
                    "category": category,
                    "name": gdf.get("name", pd.Series(index=gdf.index, dtype=object)).values,
                    "element": idx.iloc[:, 0].values,
                    "osmid": idx.iloc[:, 1].values,
                    "lat": pts.y.values,
                    "lon": pts.x.values,
                    "area_m2": gdf.geometry.to_crs("EPSG:2180").area.round(0).values,
                }
            )
        )
        log(f"  OSM {category}: {len(gdf)}")
    pd.concat(frames, ignore_index=True).to_parquet(path, index=False)


def fetch_cycleways(ox, polygon, log):
    path = OSM_DIR / "cycleways.parquet"
    if path.exists():
        log(f"  OSM drogi rowerowe: juz sa ({path.name})")
        return
    # droga rowerowa = highway=cycleway albo inna droga z bicycle=designated (np. ciag pieszo-rowerowy)
    tags = {"highway": ["cycleway"], "bicycle": ["designated"]}
    gdf = _retry(ox, lambda: ox.features_from_polygon(polygon, tags), log, "OSM drogi rowerowe")
    gdf = gdf[gdf.geom_type.isin(["LineString", "MultiLineString"]) & gdf.get("highway").notna()]
    cols = [c for c in ["highway", "bicycle", "surface", "segregated", "name"] if c in gdf]
    out = gdf[cols + ["geometry"]].reset_index()
    out["length_m"] = out.to_crs("EPSG:2180").length.round(1)
    out.to_parquet(path, index=False)
    log(f"  OSM drogi rowerowe: {len(out)} odcinkow, {out['length_m'].sum() / 1000:.0f} km")


def fetch_buildings(ox, log):
    path = OSM_DIR / "buildings_srodmiescie.parquet"
    if path.exists():
        log(f"  OSM budynki Srodmiescia: juz sa ({path.name})")
        return
    gdf = _retry(ox, lambda: ox.features_from_place(PLACE_SRODMIESCIE, {"building": True}), log, "OSM budynki")
    gdf = gdf[gdf.geom_type.isin(["Polygon", "MultiPolygon"])]
    height = pd.to_numeric(gdf.get("height"), errors="coerce") if "height" in gdf else None
    levels = pd.to_numeric(gdf.get("building:levels"), errors="coerce") if "building:levels" in gdf else None
    out = gdf[[c for c in ["building", "name"] if c in gdf] + ["geometry"]].reset_index()
    out["height_osm"] = height.values if height is not None else None
    out["levels"] = levels.values if levels is not None else None
    # wysokosc: tag height, a gdy go brak - liczba kondygnacji x 3 m
    out["height_m"] = out["height_osm"].fillna(out["levels"] * 3.0)
    out["height_source"] = "height"
    out.loc[out["height_osm"].isna() & out["levels"].notna(), "height_source"] = "levels*3"
    out.loc[out["height_m"].isna(), "height_source"] = None
    out.to_parquet(path, index=False)
    known = out["height_m"].notna().mean()
    log(f"  OSM budynki Srodmiescia: {len(out)}, z wysokoscia {known:.0%}")


# Grafy budujemy z gotowego wycinka OSM (BBBike, aktualizowany codziennie) zamiast
# z Overpass - zapytanie o graf calej Warszawy jest za duze dla przeciazonych serwerow.
BBBIKE_PBF = "https://download.bbbike.org/osm/bbbike/Warsaw/Warsaw.osm.pbf"
DRIVE_HIGHWAYS = {
    "motorway", "trunk", "primary", "secondary", "tertiary", "unclassified", "residential",
    "motorway_link", "trunk_link", "primary_link", "secondary_link", "tertiary_link",
    "living_street", "road", "service",
}
# jak filtr "bike" w OSMnx; dodatkowo chodniki/deptaki z bicycle=yes/designated
# (ciagi pieszo-rowerowe sa w Warszawie czeste)
BIKE_EXCLUDED = {
    "abandoned", "bridleway", "bus_guideway", "construction", "corridor", "elevator", "escalator",
    "motor", "motorway", "motorway_link", "no", "planned", "platform", "proposed", "raceway",
    "razed", "steps", "trunk", "trunk_link",
}
BIKE_OK = {"yes", "designated", "permissive"}


def _keep_way(tags, kind):
    hw = tags.get("highway")
    if hw is None or tags.get("area") == "yes":
        return False
    access = tags.get("access")
    if kind == "drive":
        return (
            hw in DRIVE_HIGHWAYS
            and access not in ("no", "private")
            and tags.get("motor_vehicle") not in ("no", "private")
            and tags.get("service") not in ("parking", "parking_aisle", "driveway", "private", "emergency_access")
        )
    bicycle = tags.get("bicycle")
    if bicycle in ("no", "dismount") or (access in ("no", "private") and bicycle not in BIKE_OK):
        return False
    if hw in ("footway", "pedestrian"):
        return bicycle in BIKE_OK
    return hw not in BIKE_EXCLUDED


def _download_pbf(log):
    import shutil

    import requests

    from .config import STATIC, USER_AGENT

    pbf = STATIC / "cache" / "Warsaw.osm.pbf"
    if not pbf.exists():
        pbf.parent.mkdir(parents=True, exist_ok=True)
        log(f"  OSM: pobieram wycinek {BBBIKE_PBF} (~120 MB)")
        with requests.get(BBBIKE_PBF, stream=True, timeout=600, headers={"User-Agent": USER_AGENT}) as r:
            r.raise_for_status()
            with open(pbf, "wb") as f:
                shutil.copyfileobj(r.raw, f)
    return pbf


def fetch_graphs(ox, polygon, log):
    import osmium

    todo = [k for k in ["bike", "drive"] if not (OSM_DIR / f"graph_{k}.graphml").exists()]
    if not todo:
        log("  OSM grafy: juz sa")
        return
    import shutil
    import tempfile
    from pathlib import Path

    # libosmium na Windows nie otwiera sciezek z polskimi znakami ("systemów"),
    # wiec przetwarzamy kopie w katalogu tymczasowym
    tmp = Path(tempfile.mkdtemp(prefix="veturilo_osm_"))
    pbf = tmp / "warsaw.osm.pbf"
    shutil.copy(_download_pbf(log), pbf)
    for kind in todo:
        xml = tmp / f"ways_{kind}.osm"
        # drogi danego typu + wezly, do ktorych sie odwoluja
        with osmium.BackReferenceWriter(str(xml), ref_src=str(pbf), overwrite=True) as w:
            for way in osmium.FileProcessor(str(pbf), osmium.osm.WAY).with_filter(osmium.filter.KeyFilter("highway")):
                if _keep_way(way.tags, kind):
                    w.add(way)
        g = ox.graph_from_xml(xml, simplify=False, retain_all=True)
        g = ox.truncate.truncate_graph_polygon(g, polygon)
        g = ox.simplify_graph(g)
        g = ox.truncate.largest_component(g, strongly=False)
        path = OSM_DIR / f"graph_{kind}.graphml"
        ox.save_graphml(g, path)
        log(f"  OSM graf {kind}: {g.number_of_nodes()} wezlow, {g.number_of_edges()} krawedzi -> {path.name}")
    shutil.rmtree(tmp, ignore_errors=True)


def fetch_all(log, force_graphs=False):
    from .config import STATIC

    ox = _setup()
    full = boundary(ox).geometry.iloc[0]
    # Pelna granica ma tysiace wierzcholkow, a Overpass dostaje poligon przy kazdym
    # tagu (blad 413). Lekkie poszerzenie (~100 m) i uproszczenie (~50 m) wystarcza.
    polygon = full.buffer(0.0015).simplify(0.0007)
    log(f"  granica: {len(full.exterior.coords) if full.geom_type == 'Polygon' else '?'} -> "
        f"{len(polygon.exterior.coords)} wierzcholkow")
    fetch_pois(ox, polygon, log)
    fetch_cycleways(ox, polygon, log)
    fetch_buildings(ox, log)
    # Grafy sluza tylko do macierzy odleglosci miedzy stacjami, ktora jest w repo -
    # budujemy je (pobranie ~120 MB) tylko, gdy jej brak albo na zadanie (--force osm).
    if (STATIC / "station_network_distance.parquet").exists() and not force_graphs:
        log("  OSM grafy: pomijam - station_network_distance.parquet jest w repo (--force osm, by zbudowac)")
        return
    fetch_graphs(ox, polygon, log)
