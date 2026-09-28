"""Night-time lights per seat from NASA Black Marble (VNP46A4, yearly, 15 arc-second ≈ 500 m), for the Power sector
and Seat Rank. Brighter nights over years mean more electrified homes, streets and business; a dimmer seat is a flag.
It cannot see a single outage or a single street.

Telangana sits on two Black Marble tiles, h25v07 (70-80°E) and h26v07 (80-90°E), each about 130 MB a year. Downloads
need a free NASA Earthdata token: put EARTHDATA_TOKEN in .streamlit/secrets.toml (or the environment).

Run: .venv/bin/python pipeline/night_lights.py 2014 2018 2023 2024
Writes data/night_lights.csv (seat, year, mean radiance, lit share) and keeps the downloads in pipeline/cache/.
"""

import os
import sys
import tomllib

import numpy as np
import pandas as pd
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import geo   # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "pipeline", "cache", "blackmarble")
OUT = os.path.join(ROOT, "data", "night_lights.csv")
LAADS = "https://ladsweb.modaps.eosdis.nasa.gov"
PRODUCT = "VNP46A4"
TILES = {"h25v07": (70.0, 10.0, 80.0, 20.0), "h26v07": (80.0, 10.0, 90.0, 20.0)}     # lon0, lat0, lon1, lat1
SIZE = 2400
FIELD = "HDFEOS/GRIDS/VIIRS_Grid_DNB_2d/Data Fields/AllAngle_Composite_Snow_Free"
LIT = 1.0      # nW/cm²/sr above which a pixel counts as lit


def token():
    t = os.environ.get("EARTHDATA_TOKEN")
    if t:
        return t
    try:
        with open(os.path.join(ROOT, ".streamlit", "secrets.toml"), "rb") as fh:
            return tomllib.load(fh).get("EARTHDATA_TOKEN")
    except Exception:
        return None


def file_for(year, tile):
    """The archive name of one tile-year, from the public catalogue (no login needed to list)."""
    url = f"{LAADS}/api/v2/content/details/allData/5200/{PRODUCT}/{year}/001?limit=600"
    names = [c["name"] for c in requests.get(url, timeout=60).json()["content"]]
    hits = [n for n in names if f".{tile}." in n]
    return hits[0] if hits else None


HDF5_SIGNATURE = b"\x89HDF\r\n\x1a\n"


def download(year, tile, tok):
    os.makedirs(CACHE, exist_ok=True)
    name = file_for(year, tile)
    if not name:
        raise RuntimeError(f"no {PRODUCT} file for {year} {tile}")
    path = os.path.join(CACHE, name)
    if os.path.exists(path) and os.path.getsize(path) > 1_000_000:
        with open(path, "rb") as fh:
            if fh.read(8) == HDF5_SIGNATURE:
                return path
        os.remove(path)  # a previous run cached something that wasn't really the file; get it again
    # NASA's own file listing gives the real download prefix as .../api/v2/content/archives/..., not .../archive/...;
    # the shorter path looks like a normal URL but actually serves an Earthdata Login HTML page, not the data
    url = f"{LAADS}/api/v2/content/archives/allData/5200/{PRODUCT}/{year}/001/{name}"
    with requests.get(url, headers={"Authorization": f"Bearer {tok}"}, stream=True, timeout=600) as r:
        if r.status_code in (401, 403):
            raise RuntimeError("NASA refused the token (check EARTHDATA_TOKEN, and that it has not expired: tokens last 60 days)")
        r.raise_for_status()
        with open(path + ".part", "wb") as fh:
            for chunk in r.iter_content(1 << 20):
                fh.write(chunk)
    with open(path + ".part", "rb") as fh:
        head = fh.read(512)
    if not head.startswith(HDF5_SIGNATURE):
        os.remove(path + ".part")
        hint = head[:200].decode("utf-8", "replace")
        raise RuntimeError(f"downloaded {name} but it isn't a real data file — NASA sent this instead: {hint!r}")
    os.replace(path + ".part", path)
    return path


def radiance(path):
    """The tile's snow-free all-angle composite radiance, nW/cm²/sr, NaN where missing. Row 0 is the tile's north edge."""
    import h5py

    with h5py.File(path, "r") as f:
        ds = f[FIELD]
        raw = ds[()].astype("float64")
        fill = ds.attrs.get("_FillValue", 65535)
        scale = ds.attrs.get("scale_factor", 0.1)
        offset = ds.attrs.get("add_offset", 0.0)
    fill = float(np.ravel(fill)[0])
    raw[raw == fill] = np.nan
    return raw * float(np.ravel(scale)[0]) + float(np.ravel(offset)[0])


def seat_values(year, tok):
    grids = {t: radiance(download(year, t, tok)) for t in TILES}
    rows = []
    for seat in geo.seats():
        feat = geo.area(seat, use_wards=False)
        total, lit, n = 0.0, 0, 0
        for t, (lon0, lat0, lon1, lat1) in TILES.items():
            minx, miny, maxx, maxy = geo.bbox(feat)
            if maxx < lon0 or minx > lon1:
                continue
            # the tile's pixel window covering the seat, then the seat's mask inside it
            c0 = max(0, int((minx - lon0) / (lon1 - lon0) * SIZE)); c1 = min(SIZE, int((maxx - lon0) / (lon1 - lon0) * SIZE) + 1)
            r0 = max(0, int((lat1 - maxy) / (lat1 - lat0) * SIZE)); r1 = min(SIZE, int((lat1 - miny) / (lat1 - lat0) * SIZE) + 1)
            box = (lon0 + c0 / SIZE * (lon1 - lon0), lat1 - r1 / SIZE * (lat1 - lat0), lon0 + c1 / SIZE * (lon1 - lon0), lat1 - r0 / SIZE * (lat1 - lat0))
            m = geo.mask(feat, box, c1 - c0, r1 - r0)
            vals = grids[t][r0:r1, c0:c1][m]
            vals = vals[~np.isnan(vals)]
            total += vals.sum(); lit += int((vals > LIT).sum()); n += len(vals)
        rows.append({"seat": seat, "year": year, "mean_radiance": round(total / n, 3) if n else None, "lit_share": round(lit / n, 4) if n else None, "pixels": n})
    return rows


def main(years):
    tok = token()
    if not tok:
        raise SystemExit("EARTHDATA_TOKEN is not set (see the guide on the Proof page).")
    old = pd.read_csv(OUT) if os.path.exists(OUT) else pd.DataFrame()
    rows = [r for r in old.to_dict("records") if r["year"] not in years] if not old.empty else []
    for y in years:
        print(f"{y}: downloading and reading", flush=True)
        rows += seat_values(y, tok)
        pd.DataFrame(rows).to_csv(OUT, index=False)
    print("written", OUT)


if __name__ == "__main__":
    main([int(a) for a in sys.argv[1:]] or [2014, 2018, 2023, 2024])
