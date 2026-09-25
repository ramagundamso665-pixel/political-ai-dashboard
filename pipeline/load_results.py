"""Load the statewide results for one election year into Supabase.

    python pipeline/load_results.py --year 2018            # dry run: says what it would do, writes nothing
    python pipeline/load_results.py --year 2018 --apply    # does it

Adds one `constituencies` row per seat, every candidate to `historical_results`, and each seat's
electors and valid votes to `demographics`. Safe to re-run: a seat that already has results for the
year is skipped, so Jubilee Hills (loaded earlier from the campaign workbook) is left exactly as it is.
"""

import argparse
import csv
import difflib
import os
import re
import sys
import tomllib

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import config  # noqa: E402

BATCH = 400
EXISTING_JUBILEE_HILLS = "Jubilee Hills (GHMC)"


def credentials():
    url, key = os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_SERVICE_KEY")
    if url and key:
        return url, key
    with open(os.path.join(ROOT, ".streamlit", "secrets.toml"), "rb") as f:
        secrets = tomllib.load(f)
    return secrets["SUPABASE_URL"], secrets["SUPABASE_SERVICE_KEY"]


def app_name(eci_name):
    """The spelling the rest of the app already uses for this seat."""
    norm = lambda n: re.sub(r"[^a-z]", "", n.lower())
    known = {norm(n): n for n in config.TELANGANA_CONSTITUENCIES}
    hit = known.get(norm(eci_name)) or (lambda m: known[m[0]] if m else None)(difflib.get_close_matches(norm(eci_name), list(known), n=1, cutoff=0.8))
    if not hit:
        raise SystemExit(f"No app name for ECI seat {eci_name!r}")
    return hit


def main(apply, year):
    source_id = f"eci_detailed_results_{year}"
    url, key = credentials()
    headers = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    rest = lambda t: f"{url}/rest/v1/{t}"

    def get(table, params):
        """Every matching row. The database returns at most 1,000 per request, so page through:
        an 'already loaded?' check that only saw the first page once re-inserted 68 seats."""
        rows, offset = [], 0
        while True:
            r = requests.get(rest(table), headers={**headers, "Range": f"{offset}-{offset + 999}"}, params=params, timeout=90)
            r.raise_for_status()
            page = r.json()
            rows += page
            if len(page) < 1000:
                return rows
            offset += 1000

    def post(table, rows, prefer="return=minimal"):
        r = requests.post(rest(table), headers={**headers, "Prefer": prefer}, json=rows, timeout=120)
        if r.status_code not in (200, 201):
            raise SystemExit(f"{table}: HTTP {r.status_code} {r.text[:300]}")
        return r.json() if prefer != "return=minimal" else None

    seats = list(csv.DictReader(open(os.path.join(ROOT, "data", f"telangana_{year}_seats.csv"))))
    cands = list(csv.DictReader(open(os.path.join(ROOT, "data", f"telangana_{year}_candidates.csv"))))

    have = {c["name"]: c["id"] for c in get("constituencies", {"select": "id,name"})}
    already = {r["constituency_id"] for r in get("historical_results", {"select": "constituency_id", "year": f"eq.{year}"})}

    new_constituencies, plan = [], []
    for s in seats:
        name = EXISTING_JUBILEE_HILLS if s["seat"] == "Jubilee Hills" else app_name(s["seat"])
        if name not in have:
            new_constituencies.append({"name": name, "short_name": name, "state": "Telangana"})
        plan.append((s, name))
    if len({name for _, name in plan}) != len(plan):
        raise SystemExit("Two ECI seats map to the same app name; fix the name matching before loading.")
    print(f"seats in file: {len(seats)} | constituencies to create: {len(new_constituencies)} | already in database: {len(seats) - len(new_constituencies)}")

    if apply:
        # the database requires every source_id to be registered first; re-running just updates the row
        r = requests.post(
            rest("data_sources") + "?on_conflict=id",
            headers={**headers, "Prefer": "resolution=merge-duplicates,return=minimal"},
            json={
                "id": source_id,
                "name": f"Election Commission of India: Telangana {year} Detailed Results (statistical report)",
                "type": "verified",
                "methodology": "Candidate-wise results for all 119 constituencies, read from the ECI's published "
                               "Detailed Results PDF. Every constituency is checked against its own turnout line "
                               "before loading: the candidates' votes add up exactly.",
            },
            timeout=60,
        )
        if r.status_code not in (200, 201):
            raise SystemExit(f"data_sources: HTTP {r.status_code} {r.text[:300]}")

    if apply and new_constituencies:
        for i in range(0, len(new_constituencies), BATCH):
            post("constituencies", new_constituencies[i:i + BATCH])
        have = {c["name"]: c["id"] for c in get("constituencies", {"select": "id,name"})}

    results, demo, skipped = [], [], []
    by_seat = {}
    for c in cands:
        by_seat.setdefault(int(c["seat_no"]), []).append(c)
    for s, name in plan:
        cid = have.get(name)
        if cid in already:
            skipped.append(name)
            continue
        polled = int(s["votes_polled"])
        for c in by_seat[int(s["seat_no"])]:
            results.append({"constituency_id": cid, "source_id": source_id, "year": year, "party": c["party"],
                            "candidate": c["candidate"], "votes": int(c["votes_total"]), "pct": float(c["pct"]), "turnout": polled})
        demo += [{"constituency_id": cid, "source_id": source_id, "metric": f"Total_Electors_{year}", "count": int(s["electors"])},
                 {"constituency_id": cid, "source_id": source_id, "metric": f"Valid_Votes_{year}", "count": polled}]
    print(f"candidate rows to insert: {len(results)} | demographic rows: {len(demo)} | seats skipped (already have {year} results): {skipped}")

    if not apply:
        print("\nDry run only. Re-run with --apply to write.")
        return
    for i in range(0, len(results), BATCH):
        post("historical_results", results[i:i + BATCH])
    for i in range(0, len(demo), BATCH):
        post("demographics", demo[i:i + BATCH])
    stored = get("historical_results", {"select": "constituency_id,votes", "year": f"eq.{year}", "source_id": f"eq.{source_id}"})
    expected = sum(len(v) for v in by_seat.values()) - len(by_seat[next(int(s["seat_no"]) for s in seats if s["seat"] == "Jubilee Hills")])
    if len(stored) != expected:
        raise SystemExit(f"Post-load check failed: {len(stored)} stored rows, expected {expected}. Investigate before re-running.")
    print(f"Done. Post-load check passed: {len(stored)} candidate rows stored.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, required=True, choices=[2018, 2023])
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    main(args.apply, args.year)
