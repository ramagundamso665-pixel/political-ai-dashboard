"""Satellite readings for any area, from Microsoft's Planetary Computer (free, no key, no scraping).

Planetary Computer serves each satellite scene through a tile server that can cut out a box and
return the raw pixel values as a numpy array, so all the arithmetic below runs here in numpy and
nothing heavier (rasterio, GDAL) is needed. Every function returns {"ok", "error", ...} and never
raises, like live_pulse.

What each source can and cannot show:
- Sentinel-2 (10 m, every 5 days since 2017): plant health (NDVI), open water, bare ground and roofs.
  Clouds block it; the monsoon months are often unusable.
- Landsat 8/9 thermal band (100 m, resampled to 30 m, every 8 days): ground surface temperature,
  which is hotter than air temperature on a sunny afternoon.
- Esri/Impact Observatory annual land cover (10 m, 2017-2024): each pixel classed as water, trees,
  crops, built area, bare ground or rangeland, one map a year. Its own accuracy is about 75-85%.
- JRC Global Surface Water (30 m, 1984-2020): how often each pixel held water, which gives a lake's
  historical extent to compare against today.
"""

import io
from datetime import date

import numpy as np
import requests

STAC = "https://planetarycomputer.microsoft.com/api/stac/v1/search"
DATA = "https://planetarycomputer.microsoft.com/api/data/v1/item"
TIMEOUT = 60

LULC_CLASSES = {1: "Water", 2: "Trees", 4: "Flooded vegetation", 5: "Crops", 7: "Built area", 8: "Bare ground",
                9: "Snow/ice", 10: "Clouds", 11: "Rangeland"}
S2_CLOUD = (3, 8, 9, 10)          # scene classification: cloud shadow, medium and high cloud, cirrus


def _reason(exc):
    if isinstance(exc, requests.exceptions.Timeout):
        return "the satellite server timed out"
    if isinstance(exc, requests.exceptions.HTTPError) and exc.response is not None:
        return f"the satellite server returned HTTP {exc.response.status_code}"
    return type(exc).__name__


def search(collection, box, start, end, max_cloud=None, limit=20):
    """Scenes over the box between two dates, least cloudy first."""
    body = {"collections": [collection], "bbox": list(box), "datetime": f"{start}/{end}", "limit": limit}
    if max_cloud is not None:
        body["query"] = {"eo:cloud_cover": {"lt": max_cloud}}
        body["sortby"] = [{"field": "eo:cloud_cover", "direction": "asc"}]
    try:
        resp = requests.post(STAC, json=body, timeout=TIMEOUT)
        resp.raise_for_status()
        feats = resp.json().get("features", [])
    except Exception as exc:
        return {"ok": False, "error": _reason(exc), "items": []}
    items = [{"id": f["id"], "date": (f["properties"].get("datetime") or f["properties"].get("start_datetime") or "")[:10], "cloud": f["properties"].get("eo:cloud_cover"),
              "bbox": f.get("bbox")} for f in feats]
    return {"ok": True, "error": None, "items": items}


def grid(collection, item, box, width, height, assets=None, expression=None):
    """Pixel values for the box: (bands, height, width) float array with NaN where the scene has no data."""
    minx, miny, maxx, maxy = box
    params = {"collection": collection, "item": item}
    if expression:
        params.update(expression=expression, asset_as_band="true")
    else:
        params["assets"] = assets
    url = f"{DATA}/bbox/{minx},{miny},{maxx},{maxy}/{width}x{height}.npy"
    try:
        resp = requests.get(url, params=params, timeout=TIMEOUT)
        resp.raise_for_status()
        arr = np.load(io.BytesIO(resp.content)).astype("float64")
    except Exception as exc:
        return {"ok": False, "error": _reason(exc), "data": None}
    data, valid = arr[:-1], arr[-1] > 0
    data[:, ~valid] = np.nan
    return {"ok": True, "error": None, "data": data}


def mosaic(collection, items, box, width, height, assets=None, expression=None, bad=None, max_items=6):
    """Fill the box from several scenes, least cloudy first, until every pixel has a clear reading.
    `bad` is an optional function (data) -> boolean mask of pixels to reject, such as clouds."""
    out, used, error = None, [], None
    for it in items[:max_items]:
        got = grid(collection, it["id"], box, width, height, assets=assets, expression=expression)
        if not got["ok"]:
            error = got["error"]
            continue
        data = got["data"]
        if bad is not None:
            reject = bad(data)
            data[:, reject] = np.nan
        if out is None:
            out = data
        else:
            hole = np.isnan(out[0])
            out[:, hole] = data[:, hole]
        used.append(it["date"])
        if not np.isnan(out[0]).any():
            break
    if out is None:
        return {"ok": False, "error": error or "no clear scene in that period", "data": None, "dates": []}
    return {"ok": True, "error": None, "data": out, "dates": used}


# ----------------------------------------------------------------------
# Sentinel-2: plants, water, roofs
# ----------------------------------------------------------------------
S2_BANDS = ["B02", "B03", "B04", "B08", "B11", "SCL"]


def sentinel(box, width, height, start, end, max_cloud=20):
    """Clear-sky Sentinel-2 reflectance for the window, cloud pixels removed, plus the indices.
    Returns {'ok', 'error', 'ndvi', 'ndwi', 'ndbi', 'rgb', 'dates'}."""
    found = search("sentinel-2-l2a", box, start, end, max_cloud=max_cloud)
    if not found["ok"] or not found["items"]:
        return {"ok": False, "error": found["error"] or f"no Sentinel-2 scene under {max_cloud}% cloud between {start} and {end}"}
    got = mosaic("sentinel-2-l2a", found["items"], box, width, height, assets=S2_BANDS,
                 bad=lambda d: np.isin(d[5], S2_CLOUD))
    if not got["ok"]:
        return {"ok": False, "error": got["error"]}
    b2, b3, b4, b8, b11, _ = got["data"]
    with np.errstate(divide="ignore", invalid="ignore"):
        ndvi = (b8 - b4) / (b8 + b4)
        ndwi = (b3 - b8) / (b3 + b8)
        ndbi = (b11 - b8) / (b11 + b8)
        # modified water index (green vs short-wave infrared): holds up on the green, turbid water of
        # city lakes, where the plain index reads algae and weed as land
        mndwi = (b3 - b11) / (b3 + b11)
    rgb = np.clip(np.stack([b4, b3, b2], axis=-1) / 3000, 0, 1)
    return {"ok": True, "error": None, "ndvi": ndvi, "ndwi": ndwi, "mndwi": mndwi, "ndbi": ndbi, "rgb": rgb, "dates": got["dates"]}


# ----------------------------------------------------------------------
# Land cover, one map a year
# ----------------------------------------------------------------------
LULC_YEARS = list(range(2017, 2024))   # the collection ends with the 2023 map


def landcover(box, width, height, year):
    """Land-cover class per pixel for one year (Esri/Impact Observatory 10 m)."""
    # mid-year window: each map is dated 1 Jan to 1 Jan, so a full-year window also catches the previous map
    found = search("io-lulc-annual-v02", box, f"{year}-06-01", f"{year}-06-30", limit=10)
    if not found["ok"] or not found["items"]:
        return {"ok": False, "error": found["error"] or f"no land-cover map for {year}"}
    got = mosaic("io-lulc-annual-v02", found["items"], box, width, height, assets=["data"], max_items=4)
    if not got["ok"]:
        return {"ok": False, "error": got["error"]}
    return {"ok": True, "error": None, "classes": got["data"][0]}


def class_shares(classes, inside):
    """Share of the area in each land-cover class, as percentages of the pixels with a reading."""
    vals = classes[inside & ~np.isnan(classes)]
    n = len(vals)
    if not n:
        return {}
    return {name: round(float((vals == code).sum()) / n * 100, 2) for code, name in LULC_CLASSES.items() if (vals == code).any()}


# ----------------------------------------------------------------------
# Landsat: ground heat
# ----------------------------------------------------------------------
def surface_heat(box, width, height, start, end, max_cloud=15):
    """Ground surface temperature in °C from Landsat 8/9 Collection 2 (lwir11 = ST_B10: x 0.00341802 + 149 K)."""
    found = search("landsat-c2-l2", box, start, end, max_cloud=max_cloud)
    items = [i for i in found["items"] if i["id"].startswith(("LC08", "LC09"))] if found["ok"] else []
    if not items:
        return {"ok": False, "error": found["error"] or f"no clear Landsat 8/9 scene between {start} and {end}"}

    def cloudy(d):
        qa = np.nan_to_num(d[1]).astype("uint16")
        return ((qa >> 3) & 1).astype(bool) | ((qa >> 4) & 1).astype(bool)

    # one scene only: ground temperature changes day to day, so stitching days would make false hot spots
    got = mosaic("landsat-c2-l2", items, box, width, height, assets=["lwir11", "qa_pixel"], bad=cloudy, max_items=1)
    if not got["ok"]:
        return {"ok": False, "error": got["error"]}
    celsius = got["data"][0] * 0.00341802 + 149.0 - 273.15
    celsius[(celsius < -20) | (celsius > 80)] = np.nan
    return {"ok": True, "error": None, "celsius": celsius, "dates": got["dates"]}


# ----------------------------------------------------------------------
# Historical water
# ----------------------------------------------------------------------
def water_history(box, width, height):
    """How often each pixel held water in 1984-2020, 0-100% (JRC Global Surface Water occurrence)."""
    found = search("jrc-gsw", box, "1984-01-01", "2021-01-01", limit=10)
    if not found["ok"] or not found["items"]:
        return {"ok": False, "error": found["error"] or "no historical water layer here"}
    got = mosaic("jrc-gsw", found["items"], box, width, height, assets=["occurrence"], max_items=4)
    if not got["ok"]:
        return {"ok": False, "error": got["error"]}
    occ = got["data"][0]
    occ[occ > 100] = np.nan
    return {"ok": True, "error": None, "occurrence": occ}


# ----------------------------------------------------------------------
# Pictures
# ----------------------------------------------------------------------
def true_colour(box, width, height, start, end, max_cloud=10):
    """A natural-colour picture of the box for the window, as an (h, w, 3) float array in 0..1."""
    got = sentinel(box, width, height, start, end, max_cloud=max_cloud)
    if not got["ok"]:
        return got
    rgb = got["rgb"].copy()
    rgb[np.isnan(rgb)] = 0
    return {"ok": True, "error": None, "rgb": rgb, "dates": got["dates"]}


def season(year, which):
    """Standard comparison windows. Dry season (Feb-Mar) shows irrigation and rabi crops; kharif peak
    (Oct-Nov) shows the main crop after the monsoon; pre-monsoon (Apr-May) is the hottest and clearest."""
    return {
        "dry": (f"{year}-02-01", f"{year}-03-31"),
        "kharif": (f"{year}-10-01", f"{year}-11-30"),
        "premonsoon": (f"{year}-04-01", f"{year}-05-31"),
        "year": (f"{year}-01-01", f"{year}-12-31"),
    }[which]


def this_year():
    return date.today().year
