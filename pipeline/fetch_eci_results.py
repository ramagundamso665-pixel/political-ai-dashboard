"""Download an ECI "Detailed Results" report for Telangana and turn it into two CSVs.

    python pipeline/fetch_eci_results.py --year 2023
    python pipeline/fetch_eci_results.py --year 2018

Writes data/telangana_<year>_candidates.csv (one row per candidate) and
data/telangana_<year>_seats.csv (one row per constituency). Refuses to write anything
unless every constituency passes its own arithmetic checks.

These are published Election Commission of India documents; keep the attribution when the
figures are shown. One file is downloaded, once, and cached in pipeline/cache/.
"""

import argparse
import csv
import html
import os
import re
import sys
import urllib.parse

import requests

sys.path.insert(0, os.path.dirname(__file__))
from eci_detailed_results import parse  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UA = {"User-Agent": "Mozilla/5.0 (political-ai-dashboard; one-time download of a public ECI report)"}
# the old site ties each download link to the page visit that produced it, so one session carries it all
SESSION = requests.Session()
SESSION.headers.update(UA)

SOURCES = {
    # a direct file on the ECI's current site
    2023: {"url": "https://www.eci.gov.in/eci-backend/public/all_files/full-statistical-reports/telangana/2023/Detailed_Results.pdf"},
    # the 2018 report only survives on the ECI's old site, as one of 11 files on a download page
    2018: {
        "page": "https://old.eci.gov.in/files/file/9691-telangana-general-legislative-election-2018-statistical-report/",
        "filename": "10.Detailed Results.pdf",
    },
}


def cache_path(year):
    return os.path.join(ROOT, "pipeline", "cache", f"telangana_{year}_detailed_results.pdf")


def _get(url):
    resp = SESSION.get(url, timeout=120)
    resp.raise_for_status()
    return resp


def _resolve_2018(source):
    """The download page lists every file of the report; find the one named 'Detailed Results'."""
    listing = _get(source["page"] + "?do=download").text
    for href in re.findall(r"href=['\"]([^'\"]*do=download[^'\"]*r=\d+[^'\"]*)['\"]", listing):
        href = html.unescape(href)
        head = SESSION.get(href, timeout=60, headers={"Range": "bytes=0-0"}, stream=True)
        disposition = head.headers.get("Content-Disposition", "")
        head.close()
        # the server sends the name percent-encoded to some clients and plain to others
        if source["filename"] in urllib.parse.unquote(disposition):
            return href
    raise SystemExit("Could not find the Detailed Results file on the ECI download page; it may have moved.")


def download(year):
    dest = cache_path(year)
    if os.path.exists(dest) and os.path.getsize(dest) > 100_000:
        return dest
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    source = SOURCES[year]
    content = _get(source.get("url") or _resolve_2018(source)).content
    if not content.startswith(b"%PDF"):
        raise SystemExit("The download was not a PDF; the file may have moved.")
    with open(dest, "wb") as f:
        f.write(content)
    return dest


def main(year):
    seats = parse(download(year), year=year)
    bad = [s for s in seats if s.problems]
    if bad:
        for s in bad:
            print(f"seat {s.number} {s.name}: {s.problems}")
        raise SystemExit(f"{len(bad)} seat(s) failed their own checks; nothing written.")
    if [s.number for s in seats] != list(range(1, 120)):
        raise SystemExit("Expected seats 1..119.")

    out_candidates = os.path.join(ROOT, "data", f"telangana_{year}_candidates.csv")
    out_seats = os.path.join(ROOT, "data", f"telangana_{year}_seats.csv")
    os.makedirs(os.path.dirname(out_candidates), exist_ok=True)
    with open(out_candidates, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["seat_no", "seat", "reservation", "rank", "candidate", "sex", "age", "category", "party",
                    "votes_general", "votes_postal", "votes_total", "pct"])
        for s in seats:
            for c in s.candidates:
                w.writerow([s.number, s.name, s.reservation, c.rank, c.name, c.sex, c.age if c.age is not None else "",
                            c.category, c.party, c.votes_general, c.votes_postal, c.votes_total, c.pct])

    with open(out_seats, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["seat_no", "seat", "reservation", "electors", "votes_polled", "turnout_pct",
                    "winner", "winner_party", "winner_votes", "runner_up", "runner_up_party", "runner_up_votes",
                    "margin_votes", "margin_pct"])
        for s in seats:
            ranked = sorted((c for c in s.candidates if c.party != "NOTA"), key=lambda c: -c.votes_total)
            win, run = ranked[0], ranked[1]
            margin = win.votes_total - run.votes_total
            w.writerow([s.number, s.name, s.reservation, s.electors, s.turnout_total, s.turnout_pct,
                        win.name, win.party, win.votes_total, run.name, run.party, run.votes_total,
                        margin, round(margin / s.turnout_total * 100, 2)])
    print(f"{year}: wrote {sum(len(s.candidates) for s in seats)} candidate rows and {len(seats)} seats.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, required=True, choices=sorted(SOURCES))
    main(parser.parse_args().year)
