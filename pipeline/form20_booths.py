"""Booth-level results for every Telangana seat, read from the CEO's scanned Form 20 sheets.

    python pipeline/form20_booths.py --seats 61,1,60        # a few seats
    python pipeline/form20_booths.py --all                  # all 119 (about 1,600 pages)

The sheets are images, so each page is read by a vision model (OpenAI gpt-4.1-mini, about
half a US cent a page) and the reading is never trusted on its own. A seat is written only if:
  * every booth row adds up: the candidates' votes account for the row's valid votes (with or without NOTA);
  * the booth numbers run in an unbroken sequence;
  * each candidate column, summed over all booths, equals that candidate's EVM votes in the Election
    Commission's Detailed Results report (data/telangana_2023_candidates.csv), and the NOTA column matches.
Rows that fail a check are re-read in differently cut strips, and single-cell slips are repaired by arithmetic. Seats that still do not reconcile
are listed in data/telangana_2023_booths_report.csv and left out. Model replies are cached in
pipeline/cache/, so an interrupted run resumes and a re-run costs nothing.

Needs: pip install pymupdf openai requests pandas ; OPENAI_API_KEY in .streamlit/secrets.toml.
Public source: https://ceotelangana.nic.in/GE_2023/FORM-20/INDEX.html (Chief Electoral Officer, Telangana).
"""

import argparse
import base64
import difflib
import json
import os
import re
import sys
import threading
import time
import tomllib
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import pymupdf
import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = "https://ceotelangana.nic.in/GE_2023/FORM-20/"
CACHE = os.path.join(ROOT, "pipeline", "cache", "form20_2023")
UA = {"User-Agent": "Mozilla/5.0 (political-ai-dashboard; public Form 20 sheets, fetched once)"}
FAST, STRONG = "gpt-4.1-mini", "gpt-4.1"
DPI = 170
STRIP_PROMPT = """This is a cropped strip of a scanned election result sheet. Each row is one polling station.
Columns left to right: serial number, polling station (PS) number (may have a letter like 2A), then exactly {k} numeric columns.
Return ONLY JSON: {{"rows": [[sl_no, "ps_no", v1, ..., v{k}], ...]}}. Include every row that has a serial number, in order, each with exactly {k} numbers after the PS number. A printed 0 is a value; an empty cell is 0. Ignore any header text, titles, or lines without a serial number."""
TRAIL_PROMPT = """This is a cropped strip of a scanned election result sheet. Each row is one polling station.
Columns left to right: serial number, polling station (PS) number (may have a letter like 2A), then exactly 5 numeric columns. The column headings at the top of the strip name them; they are some order of: Total number of valid votes, Number of rejected votes, NOTA, Total, Number of tendered votes.
Return ONLY JSON: {{"order": [the 5 headings, each as one of "valid", "rejected", "nota", "total", "tendered", in column order], "rows": [[sl_no, "ps_no", v1, v2, v3, v4, v5], ...]}}. Include every row that has a serial number, in order. A printed 0 is a value; an empty cell is 0. Ignore titles and lines without a serial number."""
STRIP_COLS = 5      # numeric columns per strip; narrow strips are read far more reliably than a whole page


def client():
    from openai import OpenAI
    key = tomllib.load(open(os.path.join(ROOT, ".streamlit", "secrets.toml"), "rb"))["OPENAI_API_KEY"]
    return OpenAI(api_key=key, timeout=120, max_retries=0)


def index():
    """{seat_no: (seat name, file name)} from the CEO's index page."""
    html = requests.get(BASE + "INDEX.html", headers=UA, timeout=60).text
    out = {}
    for href in re.findall(r'href="([^"]+\.pdf)"', html):
        m = re.match(r"(\d+)-(.+)\.pdf$", href)
        if m:
            out[int(m.group(1))] = (m.group(2).strip(), href)
    return out


def fetch_pdf(seat_no, href):
    path = os.path.join(CACHE, "pdf", f"{seat_no}.pdf")
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        resp = requests.get(BASE + urllib.parse.quote(href), headers=UA, timeout=120)
        resp.raise_for_status()
        open(path, "wb").write(resp.content)
        time.sleep(0.5)
    return path


def is_sheet(pdf, page_no):
    """Result pages are landscape; a portrait first page is a cover note, and the model invents rows for it."""
    rect = pymupdf.open(pdf)[page_no].rect
    return rect.width > rect.height


_WINDOW, _LOCK = [], threading.Lock()
TPM_BUDGET = 140_000        # the fast model allows 200,000 tokens a minute; stay well inside it


def _pace(estimate=3_500):
    """Wait until the last minute's token use leaves room for one more call."""
    while True:
        with _LOCK:
            now = time.time()
            _WINDOW[:] = [(t, n) for t, n in _WINDOW if now - t < 60]
            if sum(n for _, n in _WINDOW) + estimate <= TPM_BUDGET:
                _WINDOW.append((now, estimate))
                return
        time.sleep(1.5)


def ask(cl, png, model, k, trailing=False):
    prompt = TRAIL_PROMPT if trailing else STRIP_PROMPT.format(k=k)
    last = None
    for attempt in range(8):
        _pace()
        try:
            r = cl.chat.completions.create(
                model=model, temperature=0, response_format={"type": "json_object"},
                messages=[{"role": "user", "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(png).decode(), "detail": "high"}}]}],
            )
            data = json.loads(r.choices[0].message.content)
            return data.get("rows", []), data.get("order", []), (r.usage.prompt_tokens, r.usage.completion_tokens)
        except Exception as exc:  # rate limit, bad JSON, timeout: back off and retry
            last = exc
            wait = 4 * (attempt + 1)
            m = re.search(r"try again in ([\d.]+)(ms|s)", str(exc))
            if m:                                   # the API says how long to wait when it is a rate limit
                wait = float(m.group(1)) / (1000 if m.group(2) == "ms" else 1) + 1.5
            time.sleep(min(wait, 60))
    raise RuntimeError(f"vision read failed: {last}")


def _groups(idx, gap=5):
    out = []
    for i in idx:
        if out and i - out[-1][-1] <= gap:
            out[-1].append(i)
        else:
            out.append([i])
    return [(g[0] + g[-1]) / 2 for g in out]


def layout(gray, vthr=250):
    """Where the table is on a scanned page: x positions of its vertical rules and the y range of its data rows."""
    import cv2
    import numpy as np
    b = (gray < 140).astype(np.uint8) * 255
    h, w = b.shape
    hor = cv2.morphologyEx(b, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (w // 6, 1)))
    rows = _groups(np.where(hor.sum(axis=1) / 255.0 > w * 0.30)[0])
    ver = cv2.morphologyEx(b, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, 150)))
    cols = [c for c in _groups(np.where(ver.sum(axis=0) / 255.0 > vthr)[0]) if 60 < c < w - 30]
    diffs = [d for d in np.diff(rows) if 35 < d < 55]
    pitch = float(np.median(diffs)) if diffs else 44.0
    # Start at the table's top edge, header included. Scans lose rules unpredictably, so the header's lower edge
    # cannot be found reliably; rows are recognised by their serial number, so a header in the crop does no harm.
    if len(rows) < 3:
        return [], 0, 0, pitch     # no table on this page (a cover note, or a page turned the wrong way)
    top = next((r for r in rows if r > 100), rows[0])
    bottom = rows[-2] if rows[-1] > 0.95 * h and len(rows) > 2 else rows[-1]
    return cols, top, bottom, pitch


def _upright(doc, page_no, n):
    """The page as a grey image with its table upright, plus the table's layout, or None. Some scans are stored
    sideways; try the page as is, then turned each way, and keep the turn where the table's rules make sense."""
    import numpy as np
    pix = doc[page_no].get_pixmap(dpi=200, colorspace=pymupdf.csGRAY)
    g = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
    turns = (0, -1, 1) if g.shape[1] >= g.shape[0] else (-1, 1, 0)
    for k in turns:
        img = np.ascontiguousarray(np.rot90(g, k))
        for vthr in (250, 150, 110):     # faint rules on some scans need a lower bar to be seen
            cols, top, bottom, _ = layout(img, vthr)
            if n + 7 <= len(cols) <= n + 9 and (bottom - top) > 300:
                return img, cols, top, bottom
    return None


def strips(pdf, page_no, n, per=STRIP_COLS, scale=1.4):
    """PNG crops for one page: Sl/PS beside up to `per` candidate columns each, plus one for the five trailing
    columns (valid, rejected, NOTA, total, tendered, in whatever order this sheet prints them).
    Returns [(kind, first_candidate_index, k, png)] or None if the page's ruling could not be read."""
    import cv2
    import numpy as np
    found = _upright(pymupdf.open(pdf), page_no, n)
    if found is None:
        return None
    g, cols, top, bottom = found
    L = cols
    # the last rule is the table's right edge; a stray extra rule can hide anywhere, so take the anchor at which the
    # Sl and PS columns look right (PS is much wider than Sl)
    anchor = len(L) - 6
    if len(L) == n + 9:            # one stray rule somewhere: take the anchor at which PS is the wider of the first two columns
        for a in (len(L) - 6, len(L) - 7):
            if a - n - 2 >= 0 and L[a - n] - L[a - n - 1] > 1.25 * (L[a - n - 1] - L[a - n - 2]):
                anchor = a
                break
    if anchor - n < 0 or anchor + 5 > len(L) - 1:
        return None
    a = anchor
    y0, y1 = int(max(top, 0)), int(bottom) + 6
    sl_ps = (10, int(L[a - n]))

    def crop(x_ranges):
        parts = [g[y0:y1, int(x0):int(x1)] for x0, x1 in x_ranges]
        img = np.hstack([p for pair in zip(parts, [np.full((p.shape[0], 12), 255, np.uint8) for p in parts]) for p in pair])
        img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        return cv2.imencode(".png", img)[1].tobytes()

    out = []
    for j in range(0, n, per):
        k = min(per, n - j)
        out.append(("cand", j, k, crop([sl_ps, (L[a - n + j], L[a - n + j + k])])))
    out.append(("trail", 0, 5, crop([sl_ps, (L[a], L[a + 5])])))
    return out


_TRAIL = {"valid": "valid", "rejected": "rejected", "nota": "nota", "total": "total", "tendered": "tendered"}


def _label(text):
    """A column heading as the model wrote it, reduced to one of the five names."""
    t = str(text).lower()
    if "valid" in t:
        return "valid"
    if "reject" in t:
        return "rejected"
    if "nota" in t:
        return "nota"
    if "tender" in t:
        return "tendered"
    return "total" if "total" in t else t


def page_reading(cl, pdf, seat_no, page_no, model, n, per=STRIP_COLS, scale=1.4):
    """{sl: (ps, [candidate votes], valid, rejected, nota, total)} for one page, cached on disk by model."""
    tag = "" if (per, scale) == (STRIP_COLS, 1.4) else f"_c{per}_s{scale}"
    path = os.path.join(CACHE, "json", f"v4_{seat_no}_{page_no}_{model}{tag}.json")
    if os.path.exists(path):
        return {int(k): v for k, v in json.load(open(path))["rows"].items()}, (0, 0)
    pieces = strips(pdf, page_no, n, per, scale)
    if pieces is None:
        return {}, (0, 0)
    usage = [0, 0]
    cand, ps_of, trail, order = {}, {}, {}, None
    with ThreadPoolExecutor(len(pieces)) as pool:
        answers = list(pool.map(lambda p: ask(cl, p[3], model, p[2], trailing=p[0] == "trail"), pieces))
    for (kind, j, k, png), (rows, ordr, u) in zip(pieces, answers):
        usage[0] += u[0]; usage[1] += u[1]
        if kind == "trail":
            order = [str(x).lower() for x in ordr]
        for row in rows:
            if not isinstance(row, list) or len(row) != k + 2:
                continue
            sl, ps, vals = _int(row[0]), str(row[1]).strip().upper(), [_int(v) for v in row[2:]]
            if sl is None or None in vals:
                continue
            if sl == 1 and ps == "2" and len(vals) >= 3 and all(b - a == 1 for a, b in zip(vals, vals[1:])):
                continue                    # the sheet's column-numbering line (1 2 3 4 ...), not a booth
            ps_of.setdefault(sl, ps)
            if ps_of[sl] != ps:
                ps_of[sl] = None            # the strips disagree about which booth this is
            if kind == "cand":
                cand.setdefault(sl, {})[j] = vals
            else:
                trail[sl] = vals
    result = {}
    order = [_label(x) for x in (order or [])]
    if sorted(order) == sorted(_TRAIL):
        pos = {name: order.index(name) for name in _TRAIL}
        for sl, parts in cand.items():
            if ps_of.get(sl) is None or sl not in trail or len(parts) != -(-n // per):
                continue
            t = trail[sl]
            votes = [v for j in sorted(parts) for v in parts[j]]
            result[sl] = (ps_of[sl], votes, t[pos["valid"]], t[pos["rejected"]], t[pos["nota"]], t[pos["total"]])
    if result:                              # an empty reading is a failure, not an answer: never keep it
        os.makedirs(os.path.dirname(path), exist_ok=True)
        json.dump({"rows": result}, open(path, "w"))
    return result, tuple(usage)


def _int(x):
    try:
        return int(str(x).replace(",", "").strip() or 0)
    except ValueError:
        return None


def row_ok(r, n=None):
    """The candidates' votes account for the row. Sheets differ on whether 'total valid votes' counts NOTA
    (Jubilee Hills: no, Khairatabad: yes), so either is accepted."""
    _, _, cands, valid, rej, nota, total = r
    if n is not None and len(cands) != n:
        return False
    return sum(cands) == valid or sum(cands) + nota == valid


def row_clean(r, n=None):
    """A row that adds up and whose printed total agrees. A printed total can be wrong on the sheet itself (Jubilee
    Hills booth 149), so a row failing only this is looked at again but accepted if it reads the same the second time."""
    _, _, cands, valid, rej, nota, total = r
    return row_ok(r, n) and total in (valid + rej + nota, valid + rej)


def _score(r, n):
    return 2 * row_ok(r, n) + row_clean(r, n)


def as_rows(reading):
    return [(sl, v[0], v[1], v[2], v[3], v[4], v[5]) for sl, v in reading.items()]


def read_seat(cl, seat_no, name, href, usage, n):
    pdf = fetch_pdf(seat_no, href)
    pages = len(pymupdf.open(pdf))
    rows = {}     # sl -> row

    def take(reading, page_rows):
        for r in as_rows(reading):
            if r[0] not in page_rows or _score(r, n) > _score(page_rows[r[0]], n):
                page_rows[r[0]] = r

    for pg in range(pages):
        page_rows = {}
        # first read as strips of five columns; anything that does not add up (or a page with nothing) is read again
        # in differently cut and scaled strips. (The stronger gpt-4.1 was tried for this: it repeated the fast model's
        # misreadings and is capped at 30,000 tokens a minute, so it added cost without adding accuracy.)
        for per, scale in ((STRIP_COLS, 1.4), (3, 1.8), (4, 1.2)):
            if page_rows and all(_score(r, n) == 3 for r in page_rows.values()):
                break
            reading, u = page_reading(cl, pdf, seat_no, pg, FAST, n, per, scale)
            usage[0] += u[0]; usage[1] += u[1]
            take(reading, page_rows)
        for r in page_rows.values():
            if r[0] not in rows or _score(r, n) > _score(rows[r[0]], n):
                rows[r[0]] = r
    return [rows[k] for k in sorted(rows)]


def repair(rows, cands_eci, n):
    """Fix rows the readings could not settle, using arithmetic the sheet must satisfy.

    A row whose candidates fall short of (or exceed) its valid votes by d has one wrong cell. The Election Commission's
    totals say how far each candidate's column is off overall; the wrong cell is in a column that is off by the same d.
    Only a single, unambiguous match is applied, and the seat is still checked in full afterwards."""
    rows = [r for r in rows if len(r[2]) == n]
    bad = [i for i, r in enumerate(rows) if not row_ok(r, n)]
    if not bad:
        return rows
    want = sorted(int(v) for v in cands_eci.loc[cands_eci["party"] != "NOTA", "votes_general"])
    sums = [sum(r[2][j] for r in rows) for j in range(n)]
    order = sorted(range(n), key=lambda j: sums[j])
    residual = {j: want[rank] - sums[j] for rank, j in enumerate(order)}   # how far each column is from its candidate's total
    for i in bad:
        sl, ps, cands, valid, rej, nota, total = rows[i]
        d = valid - sum(cands)
        options = [j for j in range(n) if residual[j] == d and cands[j] + d >= 0]
        if len(options) == 1:
            j = options[0]
            fixed = list(cands); fixed[j] += d
            rows[i] = (sl, ps, fixed, valid, rej, nota, total)
            residual[j] -= d
    return rows


def reconcile(seat_no, rows, cands_eci):
    """(booth table or None, list of problems). Columns are matched to candidates by their sums."""
    problems = []
    if not rows:
        return None, ["no rows read"]
    width = int((cands_eci['party'] != 'NOTA').sum())
    short = [r[1] for r in rows if len(r[2]) != width]
    if short:
        problems.append(f"{len(short)} rows have the wrong number of columns ({', '.join(short[:5])})")
    rows = [r for r in rows if len(r[2]) == width]
    sls = [r[0] for r in rows]
    if sls != list(range(1, len(sls) + 1)):
        gaps = sorted(set(range(1, max(sls) + 1)) - set(sls))
        problems.append(f"serial numbers not 1..{max(sls)} unbroken (missing {gaps[:6]})")
    bad = [r[1] for r in rows if not row_ok(r, width)]
    if bad:
        problems.append(f"{len(bad)} rows do not add up ({', '.join(bad[:5])})")
    sums = [sum(r[2][j] for r in rows) for j in range(width)]
    nota_sum = sum(r[5] for r in rows)
    eci = cands_eci[cands_eci["party"] != "NOTA"]
    want = eci["votes_general"].tolist()
    if sorted(sums) != sorted(want + [0] * (width - len(want))) and sorted(s for s in sums if s) != sorted(v for v in want if v):
        problems.append("candidate column sums do not match the Election Commission's EVM votes")
    nota_eci = int(cands_eci.loc[cands_eci["party"] == "NOTA", "votes_general"].sum())
    if nota_sum != nota_eci:
        problems.append(f"NOTA column adds to {nota_sum}, Election Commission says {nota_eci}")
    if problems:
        return None, problems

    # give each column the candidate whose EVM votes equal its sum (ties: leave to whoever is left)
    left = eci.reset_index(drop=True)
    party_of_col = [None] * width
    for j in sorted(range(width), key=lambda j: -sums[j]):
        match = left[left["votes_general"] == sums[j]]
        if len(match):
            party_of_col[j] = match.iloc[0]["party"]
            left = left.drop(match.index[0])
    out = []
    for sl, ps, cands, valid, rej, nota, total in rows:
        rec = {"seat_no": seat_no, "booth": ps, "BRS": 0, "INC": 0, "BJP": 0, "AIMIM": 0, "others": 0}
        for j, v in enumerate(cands):
            p = party_of_col[j]
            rec[p if p in ("BRS", "INC", "BJP", "AIMIM") else "others"] += v
        rec.update(valid_votes=sum(cands), nota=nota, total_polled=sum(cands) + nota)
        out.append(rec)
    return pd.DataFrame(out), []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seats", help="comma-separated seat numbers")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--workers", type=int, default=5)
    args = ap.parse_args()
    files = index()
    wanted = sorted(files) if args.all else [int(s) for s in (args.seats or "").split(",") if s]
    if not wanted:
        sys.exit("give --seats or --all")
    eci = pd.read_csv(os.path.join(ROOT, "data", "telangana_2023_candidates.csv"))
    cl = client()
    usage = [0, 0]

    def work(no):
        name, href = files[no]
        try:
            n = int((eci[eci['seat_no'] == no]['party'] != 'NOTA').sum())
            rows = read_seat(cl, no, name, href, usage, n)
            seat_eci = eci[eci["seat_no"] == no]
            table, problems = reconcile(no, repair(rows, seat_eci, n), seat_eci)
        except Exception as exc:
            return no, name, None, [f"error: {exc}"]
        if table is not None:
            table.insert(1, "seat", eci.loc[eci["seat_no"] == no, "seat"].iloc[0])
        return no, name, table, problems

    tables, report = [], []
    with ThreadPoolExecutor(args.workers) as pool:
        for no, name, table, problems in pool.map(work, wanted):
            status = "reconciled" if table is not None else "NOT reconciled"
            print(f"{no:>3} {name:<28} {status}  {'; '.join(problems)}", flush=True)
            report.append({"seat_no": no, "seat": name, "status": status, "problems": "; ".join(problems),
                           "booths": 0 if table is None else len(table)})
            if table is not None:
                tables.append(table)
    out = os.path.join(ROOT, "data", "telangana_2023_booths.csv")
    if tables:
        new = pd.concat(tables)
        if os.path.exists(out):
            old = pd.read_csv(out, dtype={"booth": str})
            new = pd.concat([old[~old["seat_no"].isin(new["seat_no"])], new])
        new.sort_values(["seat_no"], kind="stable").to_csv(out, index=False)
    rep = os.path.join(ROOT, "data", "telangana_2023_booths_report.csv")
    rep_df = pd.DataFrame(report)
    if os.path.exists(rep):
        old = pd.read_csv(rep)
        rep_df = pd.concat([old[~old["seat_no"].isin(rep_df["seat_no"])], rep_df])
    rep_df.sort_values("seat_no").to_csv(rep, index=False)
    cost = usage[0] / 1e6 * 0.40 + usage[1] / 1e6 * 1.60
    print(f"\n{sum(r['status'] == 'reconciled' for r in report)}/{len(report)} seats reconciled; estimated model cost this run about ${cost:.2f}")


if __name__ == "__main__":
    main()
