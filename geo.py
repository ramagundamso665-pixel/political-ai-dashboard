"""Constituency and ward outlines, and the small amount of geometry the satellite features need.

Outlines are public-domain maps from OpenCity (data.opencity.in): the 2018 Telangana assembly
constituency map and the 2022 Greater Hyderabad 150-ward map. Written in plain Python and numpy
because the usual GIS libraries (shapely, pyproj, rasterio) have no builds for this Python.

A spot check against geocoded localities found the constituency outlines right for most of
Hyderabad but misaligned at a few north-western edges (Kukatpalle, Sanathnagar), so for a city
seat the more precise area is its GHMC wards.
"""

import json
import math
import os
from functools import lru_cache

import numpy as np

ROOT = os.path.dirname(os.path.abspath(__file__))
AC_FILE = os.path.join(ROOT, "data", "telangana_ac_boundaries.geojson")
WARD_FILE = os.path.join(ROOT, "data", "ghmc_wards_2022.geojson")

# GHMC wards (2022 numbering) that make up a city seat. Jubilee Hills from the campaign's own division
# list. That list names a "Srinagar Colony" division, which has no ward of that name on the 2022 map;
# without ward 95 (mapped as "Jubilee Hills") the seat splits into two pieces, so ward 95 is taken to be it.
SEAT_WARDS = {
    "Jubilee Hills": [94, 95, 96, 99, 101, 102, 103],
}
WARD_NOTES = {
    "Jubilee Hills": "Ward 95 (mapped as Jubilee Hills) is taken to be the division the campaign calls Srinagar Colony.",
}


@lru_cache(maxsize=1)
def _acs():
    with open(AC_FILE) as fh:
        return {f["properties"]["seat"]: f for f in json.load(fh)["features"]}


@lru_cache(maxsize=1)
def _wards():
    with open(WARD_FILE) as fh:
        return {f["properties"]["ward_no"]: f for f in json.load(fh)["features"] if f["properties"]["ward_no"]}


def seats():
    return sorted(_acs())


def rings(geom):
    """Outer rings of a Polygon or MultiPolygon as lists of (lon, lat)."""
    if geom["type"] == "Polygon":
        return [geom["coordinates"][0]]
    return [poly[0] for poly in geom["coordinates"]]


def feature(rings_list, **props):
    geom = {"type": "Polygon", "coordinates": [rings_list[0]]} if len(rings_list) == 1 else \
        {"type": "MultiPolygon", "coordinates": [[r] for r in rings_list]}
    return {"type": "Feature", "properties": props, "geometry": geom}


def ward(ward_no):
    return _wards().get(ward_no)


def all_wards():
    return list(_wards().values())


def area(seat, use_wards=True):
    """The area to analyse for a seat: its GHMC wards when known (precise for city seats), else its outline.
    Returns a GeoJSON Feature with 'label' and 'basis' properties."""
    if use_wards and seat in SEAT_WARDS:
        ws = [ward(n) for n in SEAT_WARDS[seat] if ward(n)]
        rs = [r for w in ws for r in rings(w["geometry"])]
        names = ", ".join(w["properties"]["ward"] for w in ws)
        note = f" {WARD_NOTES[seat]}" if seat in WARD_NOTES else ""
        return feature(rs, label=seat, basis=f"GHMC wards: {names}.{note}")
    f = _acs()[seat]
    return feature(rings(f["geometry"]), label=seat, basis="Constituency outline (OpenCity 2018 map)")


def wards_in(seat):
    """Ward features for a city seat (for per-ward breakdowns), or [] outside Hyderabad."""
    return [ward(n) for n in SEAT_WARDS.get(seat, []) if ward(n)]


def bbox(feat, pad=0.0):
    pts = [p for r in rings(feat["geometry"]) for p in r]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return (min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad)


def km2(feat):
    """Approximate area in square kilometres (equirectangular, fine at this scale)."""
    total = 0.0
    for r in rings(feat["geometry"]):
        lat0 = math.radians(sum(p[1] for p in r) / len(r))
        kx, ky = 111.32 * math.cos(lat0), 110.57
        pts = [(x * kx, y * ky) for x, y in r]
        total += abs(sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1]))) / 2
    return total


def centroid(feat):
    pts = [p for r in rings(feat["geometry"]) for p in r]
    return sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)


def contains(feat, lon, lat):
    for r in rings(feat["geometry"]):
        inside = False
        for (x1, y1), (x2, y2) in zip(r, r[1:] + r[:1]):
            if (y1 > lat) != (y2 > lat) and lon < (x2 - x1) * (lat - y1) / (y2 - y1) + x1:
                inside = not inside
        if inside:
            return True
    return False


def mask(feat, box, width, height):
    """Boolean (height, width) array: which pixel centres of the box fall inside the feature. Row 0 is north."""
    minx, miny, maxx, maxy = box
    xs = minx + (np.arange(width) + 0.5) * (maxx - minx) / width
    ys = maxy - (np.arange(height) + 0.5) * (maxy - miny) / height
    gx, gy = np.meshgrid(xs, ys)
    out = np.zeros((height, width), dtype=bool)
    for r in rings(feat["geometry"]):
        inside = np.zeros_like(out)
        pts = np.asarray(r)
        x1, y1 = pts[:, 0], pts[:, 1]
        x2, y2 = np.roll(x1, -1), np.roll(y1, -1)
        for a, b, c, d in zip(x1, y1, x2, y2):
            if b == d:
                continue
            crosses = ((b > gy) != (d > gy)) & (gx < (c - a) * (gy - b) / (d - b) + a)
            inside ^= crosses
        out |= inside
    return out


def grid_size(box, metres=10, cap=900):
    """Pixels across and down for a box at roughly `metres` per pixel, capped so big rural seats stay quick."""
    minx, miny, maxx, maxy = box
    lat = math.radians((miny + maxy) / 2)
    w_m = (maxx - minx) * 111_320 * math.cos(lat)
    h_m = (maxy - miny) * 110_570
    scale = max(w_m / metres, h_m / metres) / cap
    scale = max(scale, 1)
    return max(8, int(w_m / metres / scale)), max(8, int(h_m / metres / scale)), max(metres, metres * scale)
