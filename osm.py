"""Place and lake names from OpenStreetMap, through the public Overpass API (meant for this kind of
query; low volume, cached by callers). OpenStreetMap data is © OpenStreetMap contributors, ODbL."""

import math

import requests

OVERPASS = "https://overpass-api.de/api/interpreter"
HEADERS = {"User-Agent": "peoples-mandate-ai/1.0 (constituency maps)"}


def _query(q, timeout=90):
    try:
        resp = requests.post(OVERPASS, data={"data": q}, headers=HEADERS, timeout=timeout)
        resp.raise_for_status()
        return resp.json().get("elements", []), None
    except Exception as exc:
        return [], type(exc).__name__


def places(box, kinds=("village", "hamlet", "town", "suburb", "neighbourhood", "quarter")):
    """Named places in the box: [{'name', 'kind', 'lon', 'lat'}]."""
    minx, miny, maxx, maxy = box
    q = f'[out:json][timeout:60];node["place"~"^({"|".join(kinds)})$"]["name"]({miny},{minx},{maxy},{maxx});out;'
    els, err = _query(q)
    out = [{"name": e["tags"].get("name:en") or e["tags"]["name"], "kind": e["tags"]["place"], "lon": e["lon"], "lat": e["lat"]} for e in els]
    return {"ok": err is None, "error": err, "places": out}


def lakes(box, min_ha=2):
    """Named lakes and tanks in the box with their outlines: [{'name', 'rings', 'ha'}].
    Hyderabad's lakes are mapped as ways or multipolygon relations tagged natural=water."""
    minx, miny, maxx, maxy = box
    q = (f'[out:json][timeout:80];(way["natural"="water"]["name"]({miny},{minx},{maxy},{maxx});'
         f'relation["natural"="water"]["name"]({miny},{minx},{maxy},{maxx}););out geom;')
    els, err = _query(q)
    out = []
    for e in els:
        rings = []
        if e["type"] == "way" and e.get("geometry"):
            rings = [[[p["lon"], p["lat"]] for p in e["geometry"]]]
        elif e["type"] == "relation":
            rings = [[[p["lon"], p["lat"]] for p in m["geometry"]] for m in e.get("members", []) if m.get("role") == "outer" and m.get("geometry")]
        rings = [r for r in rings if len(r) >= 4]
        if not rings:
            continue
        ha = sum(_ring_ha(r) for r in rings)
        if ha >= min_ha:
            name = e["tags"].get("name:en") or e["tags"]["name"]
            out.append({"name": name, "rings": rings, "ha": round(ha, 1), "osm": f"{e['type']}/{e['id']}"})
    return {"ok": err is None, "error": err, "lakes": sorted(out, key=lambda x: -x["ha"])}


def _ring_ha(r):
    lat0 = math.radians(sum(p[1] for p in r) / len(r))
    kx, ky = 111_320 * math.cos(lat0), 110_570
    pts = [(x * kx, y * ky) for x, y in r]
    return abs(sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1]))) / 2 / 10_000


def nearest(places_list, lon, lat):
    """Name of the closest place to a point, with distance in km."""
    best, dist = None, None
    for p in places_list:
        d = math.hypot((p["lon"] - lon) * 111.32 * math.cos(math.radians(lat)), (p["lat"] - lat) * 110.57)
        if dist is None or d < dist:
            best, dist = p["name"], d
    return best, dist
