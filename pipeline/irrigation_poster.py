"""A before/after irrigation poster for any seat: dry-season green and water from Sentinel-2, plus a natural-colour
zoom on where the most new water appeared. Always prints a third, earlier year so a drought year is never passed
off as the baseline.

Run: .venv/bin/python pipeline/irrigation_poster.py Gajwel 2019 2026 2017 out.png
"""

import os
import sys
import textwrap

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import geo      # noqa: E402
import proof    # noqa: E402

FONTS = ["/System/Library/Fonts/Supplemental/Arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]
BOLD = ["/System/Library/Fonts/Supplemental/Arial Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]


def _font(size, bold=False):
    for p in BOLD if bold else FONTS:
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def _pil(a, w):
    im = Image.fromarray((np.clip(a, 0, 1) * 255).astype("uint8"))
    return im.resize((w, int(im.height * w / im.width)))


def poster(seat, y_before, y_after, y_check, path, width=620, zoom_km=7):
    f = geo.area(seat, use_wards=False)
    maps = {y: proof.irrigation_map(f, y) for y in (y_check, y_before, y_after)}
    for y, m in maps.items():
        if not m["ok"]:
            raise SystemExit(f"{y}: {m['error']}")
    zoom = proof.biggest_new_water(maps[y_before], maps[y_after], maps[y_after]["box"], size_km=zoom_km)
    zm = {y: proof.irrigation_map(f, y, metres=10, cap=700, box=zoom) for y in (y_before, y_after)} if zoom else {}
    gap = 20
    top = [_pil(maps[y]["rgb"], width) for y in (y_before, y_after)]
    bot = [_pil(zm[y]["truecolour"], width) for y in (y_before, y_after)] if zm else []
    h = 130 + top[0].height + (70 + bot[0].height if bot else 0) + 120
    canvas = Image.new("RGB", (width * 2 + gap * 3, h), (250, 249, 245))
    d = ImageDraw.Draw(canvas)
    d.text((gap, 20), f"{seat}: what reached the fields and tanks, seen from space", fill=(20, 20, 20), font=_font(30, True))
    d.text((gap, 62), "February–March (dry season) each year · Sentinel-2 satellite · green = standing crops and vegetation, blue = water",
           fill=(80, 80, 80), font=_font(17))
    y0 = 100
    for i, (yr, im) in enumerate(zip((y_before, y_after), top)):
        x = gap + i * (width + gap)
        m = maps[yr]
        d.text((x, y0), f"{yr}:  water {m['water_ha']:,} ha   ·   green {m['green_ha']:,} ha", fill=(20, 20, 20), font=_font(20, True))
        canvas.paste(im, (x, y0 + 30))
    y1 = y0 + 30 + top[0].height + 30
    if bot:
        d.text((gap, y1), f"Zoom on the biggest new water: the same {zoom_km} km square, natural colour", fill=(20, 20, 20), font=_font(20, True))
        for i, (yr, im) in enumerate(zip((y_before, y_after), bot)):
            x = gap + i * (width + gap)
            canvas.paste(im, (x, y1 + 35))
            d.text((x + 10, y1 + 45), str(yr), fill=(255, 255, 255), font=_font(26, True))
        y1 = y1 + 35 + bot[0].height + 15
    c = maps[y_check]
    note = (f"For fairness: dry-season green depends on that year's rain ({y_check}: {c['green_ha']:,} ha; {y_before}: {maps[y_before]['green_ha']:,} ha; "
            f"{y_after}: {maps[y_after]['green_ha']:,} ha). Water held in March is the steadier signal: {c['water_ha']:,} ha ({y_check}) → "
            f"{maps[y_before]['water_ha']:,} ha ({y_before}) → {maps[y_after]['water_ha']:,} ha ({y_after}).")
    for k, line in enumerate(textwrap.wrap(note, 150)):
        d.text((gap, y1 + k * 24), line, fill=(60, 60, 60), font=_font(16))
    d.text((gap, y1 + 60), "Source: Copernicus Sentinel-2 via Microsoft Planetary Computer · seat outline: OpenCity 2018 map (approximate) · "
           f"coverage {maps[y_before]['coverage']:.0%} / {maps[y_after]['coverage']:.0%} of the seat seen clearly", fill=(120, 120, 120), font=_font(13))
    canvas.save(path)
    return {y: {k: maps[y][k] for k in ("water_ha", "green_ha", "coverage")} for y in maps}


if __name__ == "__main__":
    seat, a, b, c, out = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]), sys.argv[5]
    print(poster(seat, a, b, c, out))
