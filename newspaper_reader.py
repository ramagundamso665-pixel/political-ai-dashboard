"""Civic complaints from a photo of a local newspaper page.

Local editions of Telugu and English dailies print reader complaints and area reports (water, roads, drains, power).
A vision model reads the page image, Telugu included, and lists each complaint in one short line of its own words.
Only that short summary, the area it names, and the paper and date are kept. The article text is not stored, so the
page stays the newspaper's. Staff review every line before it goes into the Local Issues register.
"""

import base64
import io
import json

import registers

MODEL = "gpt-4.1-mini"
MAX_SIDE = 2200
PROMPT = """This is a photo or scan of a page from a local newspaper edition (Telugu, English or both).
Find every item on it that reports a local civic problem or a resident's complaint: water supply, roads, drainage or flooding, garbage,
street lights, power cuts, parks, traffic, encroachment, health, schools, safety, or a welfare scheme not reaching people.
Ignore adverts, sport, national politics, crime reports and obituaries.
For each item return:
- title: one plain English sentence, in your own words, saying what the problem is (do not copy the article).
- category: exactly one of {categories}.
- area: the locality, colony, division or mandal the item names, in English letters ("" if none).
- severity: Low, Medium or High, by how many people are affected and for how long.
- language: the language the item is printed in.
Return ONLY JSON: {{"items": [{{"title": "...", "category": "...", "area": "...", "severity": "...", "language": "..."}}]}}. If the page has no such item, return {{"items": []}}."""


def _prepare(data):
    """JPEG bytes no larger than MAX_SIDE on the long side."""
    from PIL import Image

    img = Image.open(io.BytesIO(data)).convert("RGB")
    scale = MAX_SIDE / max(img.size)
    if scale < 1:
        img = img.resize((int(img.width * scale), int(img.height * scale)))
    out = io.BytesIO()
    img.save(out, "JPEG", quality=90)
    return out.getvalue()


def read_page(image_bytes, api_key, model=MODEL):
    """{'ok', 'error', 'items': [{'title','category','area','severity','language'}]} for one page image."""
    from openai import OpenAI

    try:
        jpeg = _prepare(image_bytes)
    except Exception:
        return {"ok": False, "error": "the file is not a readable image", "items": []}
    try:
        resp = OpenAI(api_key=api_key, timeout=90).chat.completions.create(
            model=model, temperature=0, response_format={"type": "json_object"},
            messages=[{"role": "user", "content": [
                {"type": "text", "text": PROMPT.format(categories=", ".join(registers.CATEGORIES))},
                {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(jpeg).decode(), "detail": "high"}},
            ]}],
        )
        raw = json.loads(resp.choices[0].message.content).get("items", [])
    except Exception as exc:
        import live_pulse
        return {"ok": False, "error": live_pulse._openai_reason(exc), "items": []}

    items = []
    for it in raw if isinstance(raw, list) else []:
        title = str(it.get("title", "")).strip()
        if not title:
            continue
        category = str(it.get("category", "")).strip()
        severity = str(it.get("severity", "")).strip().capitalize()
        items.append({
            "title": title[:240],
            "category": category if category in registers.CATEGORIES else "Other",
            "area": str(it.get("area", "")).strip()[:80],
            "severity": severity if severity in registers.SEVERITIES else "Medium",
            "language": str(it.get("language", "")).strip()[:20],
        })
    return {"ok": True, "error": None, "items": items}
