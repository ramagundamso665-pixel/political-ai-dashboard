"""Proof from orbit: what changed on the ground in a constituency, measured from free satellite data.

Every number here is a measurement a sceptic can repeat: the same public satellite scenes, the same
thresholds. Where satellites cannot see something (welfare payments, teachers in classrooms, a
resurfaced road under 10 m wide), the functions say so rather than guess.
"""

import math
from datetime import date, timedelta

import numpy as np
import pandas as pd

import geo
import orbit
import osm

GREEN = 0.4          # NDVI above this is healthy vegetation or a standing crop
WATER = 0.0          # modified water index (MNDWI) above this is open water, turbid or not
DROP = 0.15          # an NDVI fall this large on cropland is visible crop damage
CELL_KM = 1.0        # crop-loss cells


class Frame:
    """The analysis grid for one area: box, size, pixel size and which pixels are inside."""

    def __init__(self, feat, metres=10, cap=900, pad=0.002):
        self.feat = feat
        self.box = geo.bbox(feat, pad)
        self.w, self.h, _ = geo.grid_size(self.box, metres, cap)
        minx, miny, maxx, maxy = self.box
        lat = math.radians((miny + maxy) / 2)
        self.px_m = ((maxx - minx) * 111_320 * math.cos(lat) / self.w + (maxy - miny) * 110_570 / self.h) / 2
        self.inside = geo.mask(feat, self.box, self.w, self.h)

    @property
    def px_ha(self):
        return self.px_m ** 2 / 10_000

    def lonlat(self, row, col):
        minx, miny, maxx, maxy = self.box
        return minx + (col + 0.5) * (maxx - minx) / self.w, maxy - (row + 0.5) * (maxy - miny) / self.h


# ----------------------------------------------------------------------
# Sectors over time
# ----------------------------------------------------------------------
def landcover_series(feat, years=orbit.LULC_YEARS, metres=20):
    """Hectares of built area, trees, crops, water and bare ground per year (2017-2024 land-cover maps)."""
    fr = Frame(feat, metres, cap=700)
    rows, errors = [], []
    for y in years:
        lc = orbit.landcover(fr.box, fr.w, fr.h, y)
        if not lc["ok"]:
            errors.append(f"{y}: {lc['error']}")
            continue
        c = lc["classes"]
        seen = fr.inside & ~np.isnan(c)
        row = {"Year": y}
        for code, name in ((7, "Built area"), (2, "Trees"), (5, "Crops"), (1, "Water"), (8, "Bare ground"), (11, "Rangeland")):
            row[name] = round(float((c[seen] == code).sum()) * fr.px_ha, 1)
        rows.append(row)
    return pd.DataFrame(rows), errors


def season_series(feat, years, which="dry", metres=20):
    """Per year, from Sentinel-2 in one season: hectares green (NDVI > 0.4) and hectares of open water.
    Green in the dry season (Feb-Mar) outside forests is mostly irrigated rabi crops; water then is what
    the tanks and reservoirs are still holding before summer."""
    fr = Frame(feat, metres, cap=600)
    rows, errors = [], []
    for y in years:
        s = orbit.sentinel(fr.box, fr.w, fr.h, *orbit.season(y, which), max_cloud=15)
        if not s["ok"]:
            errors.append(f"{y}: {s['error']}")
            continue
        seen = fr.inside & ~np.isnan(s["ndvi"])
        coverage = seen.sum() / max(1, fr.inside.sum())
        rows.append({
            "Year": y, "Green (ha)": round(float((s["ndvi"][seen] > GREEN).sum()) * fr.px_ha, 1),
            "Open water (ha)": round(float((s["mndwi"][seen] > WATER).sum()) * fr.px_ha, 1),
            "Clear-sky coverage": f"{coverage * 100:.0f}%", "Scenes": ", ".join(s["dates"]),
        })
    return pd.DataFrame(rows), errors


# what satellites can and cannot settle, per sector, and the official records that fill the gap
SECTORS = [
    ("Agriculture", "Cropped and green area each season; land left fallow", "PM-KISAN beneficiaries by village (pmkisan.gov.in); Rythu Bharosa lists where published", "Farm income, prices farmers got"),
    ("Irrigation", "Water held in tanks and reservoirs; fields green in the dry season (irrigated)", "Irrigation department command-area figures; Mission Kakatiya tank lists", "Whether water reached a particular farm"),
    ("Infrastructure", "New built-up land, new roads on new alignments, flyovers, colonies, lakes built over", "MGNREGA works with geotagged photos (Bhuvan); MPLADS works (eSAKSHI); MLA fund works (RTI)", "Road quality, drains under 10 m wide"),
    ("Power", "Night-time brightness growth (needs NASA Earthdata login, not yet connected)", "TGSPDCL/TGNPDCL consumption on data.telangana.gov.in", "Individual outages"),
    ("Education", "That a school building exists or is new", "UDISE+ school report cards: teachers, toilets, enrolment, classrooms", "Teaching quality"),
    ("Health", "New hospital or health-centre buildings", "HMIS facility reports; NFHS-5 district indicators", "Whether doctors attend"),
    ("Poverty", "Only estimates from roofs and settlement density", "Ration cards per ration shop (NFSA)", "Anything precise"),
    ("Welfare", "Nothing: payments are invisible from space", "Scheme dashboards where published; RTI for the rest", "Unpublished payments"),
]


# ----------------------------------------------------------------------
# Before and after pictures
# ----------------------------------------------------------------------
def picture(feat, year, which="dry", metres=10, cap=900):
    fr = Frame(feat, metres, cap)
    got = orbit.true_colour(fr.box, fr.w, fr.h, *orbit.season(year, which), max_cloud=10)
    if not got["ok"]:
        return got
    rgb = got["rgb"].copy()
    rgb[~fr.inside] *= 0.35          # dim what lies outside the area
    return {"ok": True, "error": None, "rgb": rgb, "dates": got["dates"]}


def new_built(feat, y0, y1, metres=10, cap=900):
    """Land that turned into built area between two land-cover years, drawn in red over the later picture.
    Returns the picture, hectares newly built, hectares of trees and water lost to building."""
    fr = Frame(feat, metres, cap)
    a, b = orbit.landcover(fr.box, fr.w, fr.h, y0), orbit.landcover(fr.box, fr.w, fr.h, y1)
    if not (a["ok"] and b["ok"]):
        return {"ok": False, "error": a.get("error") or b.get("error")}
    ca, cb = a["classes"], b["classes"]
    new = fr.inside & (cb == 7) & (ca != 7) & ~np.isnan(ca)
    pic = orbit.true_colour(fr.box, fr.w, fr.h, *orbit.season(min(y1 + 1, orbit.this_year()), "dry"))
    rgb = pic["rgb"].copy() if pic["ok"] else np.zeros((fr.h, fr.w, 3))
    rgb[~fr.inside] *= 0.35
    rgb[new] = [0.95, 0.15, 0.15]
    return {
        "ok": True, "error": None, "rgb": rgb,
        "new_built_ha": round(float(new.sum()) * fr.px_ha, 1),
        "trees_lost_ha": round(float((new & (ca == 2)).sum()) * fr.px_ha, 1),
        "water_lost_ha": round(float((new & (ca == 1)).sum()) * fr.px_ha, 1),
        "crops_lost_ha": round(float((new & (ca == 5)).sum()) * fr.px_ha, 1),
    }


# ----------------------------------------------------------------------
# Crop-loss radar
# ----------------------------------------------------------------------
def crop_loss(feat, today=None, window=45, metres=20, max_cloud=70):
    """Compare the latest clear scene with the one before it, on cropland only (latest land-cover map).
    Cells of about 1 km where the crop's NDVI fell sharply are flagged with the nearest village."""
    today = today or date.today()
    fr = Frame(feat, metres, cap=700)
    found = orbit.search("sentinel-2-l2a", fr.box, (today - timedelta(days=window * 2)).isoformat(), today.isoformat(), max_cloud=max_cloud, limit=60)
    if not found["ok"] or len(found["items"]) < 2:
        return {"ok": False, "error": found["error"] or "fewer than two clear scenes in the last weeks (clouds)"}
    by_date = {}
    for it in found["items"]:
        by_date.setdefault(it["date"], []).append(it)
    dates = sorted(by_date, reverse=True)
    lc = orbit.landcover(fr.box, fr.w, fr.h, orbit.LULC_YEARS[-1])
    crop = fr.inside & (lc["classes"] == 5) if lc["ok"] else fr.inside

    def ndvi_on(d):
        got = orbit.mosaic("sentinel-2-l2a", by_date[d], fr.box, fr.w, fr.h, assets=["B04", "B08", "SCL"], bad=lambda x: np.isin(x[2], orbit.S2_CLOUD))
        if not got["ok"]:
            return None
        b4, b8, _ = got["data"]
        if np.isnan(b4[crop]).mean() > 0.7:      # mostly cloud over the crops: not a usable reading
            return None
        with np.errstate(divide="ignore", invalid="ignore"):
            return (b8 - b4) / (b8 + b4)

    after, after_date = None, None
    for d in dates:
        after = ndvi_on(d)
        if after is not None:
            after_date = d
            break
    before, before_date = None, None
    for d in dates:
        if after_date and (date.fromisoformat(after_date) - date.fromisoformat(d)).days >= 5:
            before = ndvi_on(d)
            if before is not None:
                before_date = d
                break
    if after is None or before is None:
        return {"ok": False, "error": "could not read two clear scenes far enough apart"}
    drop = before - after
    both = ~np.isnan(before) & ~np.isnan(after)
    damaged = crop & both & (drop > DROP) & (before > 0.3)
    step = max(1, int(CELL_KM * 1000 / fr.px_m))
    pl = osm.places(fr.box, kinds=("village", "hamlet", "town"))
    cells = []
    for r0 in range(0, fr.h, step):
        for c0 in range(0, fr.w, step):
            cropped = crop[r0:r0 + step, c0:c0 + step]
            hit = damaged[r0:r0 + step, c0:c0 + step]
            if cropped.sum() < 20:
                continue
            share = hit.sum() / cropped.sum()
            if share >= 0.3:
                lon, lat = fr.lonlat(r0 + step // 2, c0 + step // 2)
                name, km = osm.nearest(pl["places"], lon, lat) if pl["places"] else (None, None)
                cells.append({"Near": name or "?", "km away": round(km, 1) if km is not None else None, "Damaged crop (acres)": round(hit.sum() * fr.px_ha * 2.471, 0),
                              "Share of crop in cell": f"{share * 100:.0f}%", "lat": round(lat, 5), "lon": round(lon, 5)})
    cells.sort(key=lambda c: -c["Damaged crop (acres)"])
    return {
        "ok": True, "error": None, "before": before_date, "after": after_date,
        "crop_acres": round(float(crop.sum()) * fr.px_ha * 2.471), "compared_acres": round(float((crop & both).sum()) * fr.px_ha * 2.471), "damaged_acres": round(float(damaged.sum()) * fr.px_ha * 2.471),
        "cells": cells, "places_error": pl["error"],
    }


# ----------------------------------------------------------------------
# Heat
# ----------------------------------------------------------------------
def heat(feat, year, metres=30):
    """Ground temperature on the clearest pre-monsoon Landsat day, per ward for city seats, and the hottest spots."""
    fr = Frame(feat, metres, cap=500)
    got = orbit.surface_heat(fr.box, fr.w, fr.h, *orbit.season(year, "premonsoon"))
    if not got["ok"]:
        return got
    c = got["celsius"]
    vals = c[fr.inside & ~np.isnan(c)]
    if not len(vals):
        return {"ok": False, "error": "the clear day did not cover this area"}
    wards = []
    for w in geo.wards_in(feat["properties"]["label"]):
        m = geo.mask(w, fr.box, fr.w, fr.h) & ~np.isnan(c)
        if m.sum():
            wards.append({"Ward": w["properties"]["ward"], "Average °C": round(float(c[m].mean()), 1), "Hottest 10% °C": round(float(np.percentile(c[m], 90)), 1)})
    pl = osm.places(fr.box, kinds=("suburb", "neighbourhood", "quarter", "village", "hamlet"))
    hot_cut = np.percentile(vals, 95)
    rows, cols = np.where(fr.inside & (c >= hot_cut))
    spots = {}
    for r, cc in zip(rows[::max(1, len(rows) // 400)], cols[::max(1, len(cols) // 400)]):
        lon, lat = fr.lonlat(r, cc)
        name, km = osm.nearest(pl["places"], lon, lat) if pl["places"] else (None, None)
        if name and km is not None and km < 1.5:
            s = spots.setdefault(name, [])
            s.append(float(c[r, cc]))
    hottest = sorted(({"Place": k, "Peak °C": round(max(v), 1), "Hot pixels": len(v)} for k, v in spots.items()), key=lambda x: -x["Peak °C"])[:12]
    return {"ok": True, "error": None, "celsius": c, "inside": fr.inside, "date": got["dates"][0],
            "mean": round(float(vals.mean()), 1), "p5": round(float(np.percentile(vals, 5)), 1), "p95": round(float(np.percentile(vals, 95)), 1),
            "wards": sorted(wards, key=lambda x: -x["Average °C"]), "hottest": hottest}


# ----------------------------------------------------------------------
# Lakes
# ----------------------------------------------------------------------
def lake_watch(feat, year_now=orbit.LULC_YEARS[-1], buffer_m=150, metres=10):
    """For each named lake or tank touching the area: its historical water extent (JRC 1984-2020, water at least
    a quarter of the time), how much of that holds water now (dry season), and how much is now built area.
    The seat is read once and each lake is cut out of it, so a seat with many lakes is no slower."""
    found = osm.lakes(geo.bbox(feat, 0.004))
    if not found["ok"] and not found["lakes"]:
        return {"ok": False, "error": f"lake outlines unavailable ({found['error']})"}
    mine = []
    for lake in found["lakes"]:
        lf = geo.feature(lake["rings"], label=lake["name"])
        if any(geo.contains(feat, x, y) for r in lake["rings"] for x, y in r[:: max(1, len(r) // 20)]) or geo.contains(feat, *geo.centroid(lf)):
            mine.append((lake, lf))
    if not mine:
        return {"ok": True, "error": None, "lakes": []}
    fr = Frame(feat, metres, cap=900, pad=0.004)
    hist = orbit.water_history(fr.box, fr.w, fr.h)
    lc = orbit.landcover(fr.box, fr.w, fr.h, year_now)
    now = orbit.sentinel(fr.box, fr.w, fr.h, *orbit.season(orbit.this_year(), "dry"), max_cloud=15)
    if not (hist["ok"] and lc["ok"]):
        return {"ok": False, "error": hist.get("error") or lc.get("error")}
    minx, miny, maxx, maxy = fr.box
    pad = buffer_m / 111_000
    rows = []
    for lake, lf in mine[:20]:
        lx0, ly0, lx1, ly1 = geo.bbox(lf, pad)
        c0 = max(0, int((lx0 - minx) / (maxx - minx) * fr.w)); c1 = min(fr.w, int((lx1 - minx) / (maxx - minx) * fr.w) + 1)
        r0 = max(0, int((maxy - ly1) / (maxy - miny) * fr.h)); r1 = min(fr.h, int((maxy - ly0) / (maxy - miny) * fr.h) + 1)
        win = (slice(r0, r1), slice(c0, c1))
        was_water = hist["occurrence"][win] >= 25
        if not was_water.any():
            continue
        row = {"Lake": lake["name"], "Historical water (ha)": round(float(was_water.sum()) * fr.px_ha, 1),
               f"Built on it by {year_now} (ha)": round(float((was_water & (lc["classes"][win] == 7)).sum()) * fr.px_ha, 1)}
        if now["ok"]:
            wet = was_water & (now["mndwi"][win] > WATER)
            row["Holding water now (ha)"] = round(float(wet.sum()) * fr.px_ha, 1)
            row["Now water, share of historical"] = f"{wet.sum() / max(1, was_water.sum()) * 100:.0f}%"
        row["OSM"] = lake["osm"]
        rows.append(row)
    return {"ok": True, "error": None, "lakes": sorted(rows, key=lambda r: -r[f"Built on it by {year_now} (ha)"])}


# ----------------------------------------------------------------------
# Ghost works
# ----------------------------------------------------------------------
def work_check(lat, lon, done_year, radius_m=120):
    """Before/after pictures around a claimed work and whether the ground visibly changed (built area,
    bare earth, water or green cover). Small works under about 10 m wide cannot be seen at this resolution."""
    d = radius_m / 111_000
    box = (lon - d / math.cos(math.radians(lat)), lat - d, lon + d / math.cos(math.radians(lat)), lat + d)
    w = h = max(24, int(2 * radius_m / 10))
    y0 = max(2017, done_year - 1)
    y1 = min(orbit.this_year(), done_year + 1)
    before = orbit.sentinel(box, w, h, *orbit.season(y0, "dry"), max_cloud=15)
    after = orbit.sentinel(box, w, h, *orbit.season(y1, "dry"), max_cloud=15)
    if not (before["ok"] and after["ok"]):
        return {"ok": False, "error": before.get("error") or after.get("error")}
    change = {}
    for k in ("ndvi", "mndwi", "ndbi"):
        change[k] = float(np.nanmean(np.abs(after[k] - before[k])))
    score = max(change.values())
    verdict = "Visible change" if score > 0.08 else ("Slight change" if score > 0.04 else "No visible change")
    return {"ok": True, "error": None, "before": before["rgb"], "after": after["rgb"], "before_dates": before["dates"],
            "after_dates": after["dates"], "score": round(score, 3), "verdict": verdict}


# ----------------------------------------------------------------------
# Built growth per ward (for Roll vs Roof and Scheme Reach)
# ----------------------------------------------------------------------
def ward_growth(seat, y0=2017, y1=2023, metres=10):
    """Built-area growth per ward between two land-cover years, as hectares and a percentage."""
    rows = []
    for w in geo.wards_in(seat):
        fr = Frame(w, metres, cap=400)
        a, b = orbit.landcover(fr.box, fr.w, fr.h, y0), orbit.landcover(fr.box, fr.w, fr.h, y1)
        if not (a["ok"] and b["ok"]):
            continue
        ba = float((fr.inside & (a["classes"] == 7)).sum()) * fr.px_ha
        bb = float((fr.inside & (b["classes"] == 7)).sum()) * fr.px_ha
        rows.append({"Ward": w["properties"]["ward"], f"Built {y0} (ha)": round(ba, 1), f"Built {y1} (ha)": round(bb, 1),
                     "Built growth": round((bb - ba) / ba * 100, 1) if ba else None, "Area (ha)": round(geo.km2(w) * 100, 1)})
    return pd.DataFrame(rows)


def roll_vs_roof(booths, growth):
    """Booth deletions against built growth in the booth's ward. `booths` needs columns booth, ward,
    electors_before, deleted. Flags booths whose deletion share is far above the seat's while their ward
    kept growing: the places to put a Form 6 help desk first. It points to where to look, not who."""
    b = booths.copy()
    b["Deleted %"] = (b["deleted"] / b["electors_before"] * 100).round(1)
    seat_rate = b["deleted"].sum() / b["electors_before"].sum() * 100
    g = growth.set_index("Ward")["Built growth"].to_dict() if not growth.empty else {}
    b["Ward built growth %"] = b["ward"].map(lambda w: g.get(str(w).title()))
    b["Excess over seat rate"] = (b["Deleted %"] - seat_rate).round(1)
    b["Priority"] = np.where((b["Excess over seat rate"] > 10) & (b["Ward built growth %"].fillna(0) > 0), "High",
                             np.where(b["Excess over seat rate"] > 5, "Medium", "Low"))
    order = {"High": 0, "Medium": 1, "Low": 2}
    return b.sort_values(["Priority", "Deleted %"], key=lambda s: s.map(order) if s.name == "Priority" else -s), round(seat_rate, 1)


def reach_gap(records, households_col="households", beneficiaries_col="beneficiaries", area_col="area"):
    """Beneficiaries against households per area: low coverage is where eligible families are most likely missed."""
    r = records.copy()
    r["Coverage"] = (r[beneficiaries_col] / r[households_col] * 100).round(1)
    median = r["Coverage"].median()
    r["Gap vs typical area"] = ((median - r["Coverage"]) / 100 * r[households_col]).clip(lower=0).round(0)
    return r.sort_values("Gap vs typical area", ascending=False), median
