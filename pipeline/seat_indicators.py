"""Satellite indicators for all 119 Telangana seats, for the Seat Rank view.

For each seat outline (OpenCity 2018 map), at about 60 m per pixel:
- land cover 2017 and 2023 (Esri/Impact Observatory): hectares built, trees, crops, water
- Sentinel-2 dry season (Feb-Mar) 2019 and the latest year: hectares green (irrigated rabi) and open water

Writes data/seat_indicators.csv. Resumable: seats already in the file are skipped.
Run: .venv/bin/python pipeline/seat_indicators.py
"""

import os
import sys
import time

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import geo      # noqa: E402
import orbit    # noqa: E402
import proof    # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "seat_indicators.csv")
LC_YEARS = (2017, orbit.LULC_YEARS[-1])
DRY_YEARS = (2019, 2026)
METRES = 60


def one(seat):
    feat = geo.area(seat, use_wards=False)
    fr = proof.Frame(feat, METRES, cap=400, pad=0.002)
    row = {"seat": seat, "area_km2": round(geo.km2(feat), 1)}
    for y in LC_YEARS:
        lc = orbit.landcover(fr.box, fr.w, fr.h, y)
        if not lc["ok"]:
            raise RuntimeError(f"land cover {y}: {lc['error']}")
        c = lc["classes"]
        for code, name in ((7, "built"), (2, "trees"), (5, "crops"), (1, "water")):
            row[f"{name}_{y}_ha"] = round(float((fr.inside & (c == code)).sum()) * fr.px_ha, 1)
    for y in DRY_YEARS:
        s = orbit.sentinel(fr.box, fr.w, fr.h, *orbit.season(y, "dry"), max_cloud=20)
        if not s["ok"]:
            row[f"dry_green_{y}_ha"] = row[f"dry_water_{y}_ha"] = None
            continue
        seen = fr.inside & ~(s["ndvi"] != s["ndvi"])
        row[f"dry_green_{y}_ha"] = round(float((s["ndvi"][seen] > proof.GREEN).sum()) * fr.px_ha, 1)
        row[f"dry_water_{y}_ha"] = round(float((s["mndwi"][seen] > proof.WATER).sum()) * fr.px_ha, 1)
        row[f"dry_cover_{y}"] = round(float(seen.sum() / max(1, fr.inside.sum())), 3)
    return row


def main():
    done = pd.read_csv(OUT) if os.path.exists(OUT) else pd.DataFrame()
    have = set(done["seat"]) if not done.empty else set()
    rows = done.to_dict("records") if not done.empty else []
    for seat in geo.seats():
        if seat in have:
            continue
        for attempt in range(3):
            try:
                t = time.time()
                rows.append(one(seat))
                print(f"{seat}: ok ({time.time() - t:.0f}s)", flush=True)
                break
            except Exception as exc:
                print(f"{seat}: attempt {attempt + 1} failed: {exc}", flush=True)
                time.sleep(5)
        pd.DataFrame(rows).to_csv(OUT, index=False)
    print("done", len(rows))


if __name__ == "__main__":
    main()
