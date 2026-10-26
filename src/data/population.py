"""Gestosc zaludnienia: Kontur Population (heksagony H3 ~400 m, CC BY 4.0).

Zrodlo: https://data.humdata.org/dataset/kontur-population-poland
Surowy plik (cala Polska, ~22 MB) trafia do data/static/cache/, a do
data/static/population_h3.parquet zapisywany jest tylko wycinek Warszawy.
"""

import gzip
import shutil

import pandas as pd
import requests

from .config import BBOX, STATIC, USER_AGENT

HDX_API = "https://data.humdata.org/api/3/action/package_show?id=kontur-population-poland"


def _latest_url():
    res = requests.get(HDX_API, timeout=60, headers={"User-Agent": USER_AGENT}).json()["result"]["resources"]
    res = sorted(res, key=lambda r: r.get("last_modified") or "")
    return res[-1]["url"]


def fetch_population(log, force=False):
    import geopandas as gpd

    out = STATIC / "population_h3.parquet"
    if out.exists() and not force:
        log(f"population: juz jest ({out.name})")
        return
    cache = STATIC / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    url = _latest_url()
    gz = cache / url.rsplit("/", 1)[-1]
    gpkg = gz.with_suffix("")  # bez .gz
    if not gpkg.exists():
        log(f"population: pobieram {url}")
        with requests.get(url, stream=True, timeout=300, headers={"User-Agent": USER_AGENT}) as r:
            r.raise_for_status()
            with open(gz, "wb") as f:
                shutil.copyfileobj(r.raw, f)
        with gzip.open(gz, "rb") as src, open(gpkg, "wb") as dst:
            shutil.copyfileobj(src, dst)
        gz.unlink()
    gdf = gpd.read_file(gpkg)
    # srodek heksagonu liczony w ukladzie metrycznym, potem na stopnie
    c = gdf.geometry.to_crs("EPSG:2180").centroid.to_crs("EPSG:4326")
    inside = c.y.between(BBOX["lat_min"], BBOX["lat_max"]) & c.x.between(BBOX["lon_min"], BBOX["lon_max"])
    gdf, c = gdf[inside], c[inside]
    df = pd.DataFrame({
        "h3": gdf["h3"].values,
        "lat": c.y.round(6).values,
        "lon": c.x.round(6).values,
        "population": gdf["population"].round(1).values,
        "source": gpkg.name,
    })
    df.to_parquet(out, index=False)
    log(f"population: {len(df)} heksagonow, {df['population'].sum():,.0f} mieszkancow w prostokacie Warszawy -> {out.name}")
