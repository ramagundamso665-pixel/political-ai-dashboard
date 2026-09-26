"""Build the 2014 Telangana assembly results CSVs from the open Lok Dhaba (TCPD) extract.

    python pipeline/build_2014_results.py

There is no Election Commission detailed-results PDF for 2014 that parses like 2018 and 2023
(2014 was a joint Andhra Pradesh election), so this uses the Trivedi Centre's Lok Dhaba
compilation of the Commission's results, published as a CSV on data.opencity.in. Only the
result columns are used. The file also carries a column derived from MyNeta; it is dropped.

Written in the same shape as the 2018 and 2023 files. A seat is written only if the candidates'
votes add up to its valid votes, and the winner-first order holds.

Attribution: Lok Dhaba, Trivedi Centre for Political Data, Ashoka University (from ECI results).
Check their terms before using the figures commercially.
"""

import os

import pandas as pd
import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
URL = ("https://data.opencity.in/dataset/d04849f0-e55c-4821-b857-b85746cbc773/resource/"
       "bd8a598d-8d62-475e-9025-b30293321e11/download/0880930f-ad89-47cb-8501-1e9720885752.csv")
CACHE = os.path.join(ROOT, "pipeline", "cache", "tg2014.csv")
PARTY = {"TRS": "BRS"}  # Telangana Rashtra Samithi, renamed BRS in October 2022 (same mapping as 2018)
RESERVATION = {"GEN": "GENERAL", "SC": "SC", "ST": "ST"}


def load():
    if not os.path.exists(CACHE):
        os.makedirs(os.path.dirname(CACHE), exist_ok=True)
        resp = requests.get(URL, timeout=90)
        resp.raise_for_status()
        open(CACHE, "wb").write(resp.content)
    return pd.read_csv(CACHE)


def build():
    raw = load()
    raw = raw[raw["Election_Type"].str.contains("AE")]
    cands, seats = [], []
    for no, g in raw.groupby("Constituency_No"):
        g = g.sort_values("Position")
        valid = int(g["Valid_Votes"].iloc[0])
        problems = []
        if int(g["Votes"].sum()) != valid:
            problems.append("votes do not add up to valid votes")
        if list(g["Position"]) != list(range(1, len(g) + 1)):
            problems.append("positions are not 1..n")
        if g["Votes"].iloc[0] != g["Votes"].max():
            problems.append("first is not the top vote-getter")
        if problems:
            raise SystemExit(f"seat {no} {g['Constituency_Name'].iloc[0]}: {problems}")
        name = g["Constituency_Name"].iloc[0].title()
        reservation = RESERVATION.get(g["Constituency_Type"].iloc[0], "GENERAL")
        for _, r in g.iterrows():
            party = PARTY.get(r["Party"], r["Party"])
            nota = party == "NOTA"
            cands.append({
                "seat_no": int(no), "seat": name, "reservation": reservation, "rank": int(r["Position"]),
                "candidate": r["Candidate"].title() if not nota else "Nota",
                "sex": {"M": "MALE", "F": "FEMALE"}.get(r["Sex"], "") if not nota else "",
                "age": int(r["Age"]) if pd.notna(r["Age"]) and not nota else "",
                "category": RESERVATION.get(r["Candidate_Type"], "") if not nota else "",
                "party": party, "votes_general": "", "votes_postal": "", "votes_total": int(r["Votes"]),
                "pct": round(r["Votes"] / valid * 100, 2),
            })
        top = g[g["Party"] != "NOTA"]
        w, ru = top.iloc[0], top.iloc[1]
        seats.append({
            "seat_no": int(no), "seat": name, "reservation": reservation, "electors": int(g["Electors"].iloc[0]),
            "votes_polled": valid, "turnout_pct": round(float(g["Turnout_Percentage"].iloc[0]), 2),
            "winner": w["Candidate"].title(), "winner_party": PARTY.get(w["Party"], w["Party"]), "winner_votes": int(w["Votes"]),
            "runner_up": ru["Candidate"].title(), "runner_up_party": PARTY.get(ru["Party"], ru["Party"]), "runner_up_votes": int(ru["Votes"]),
            "margin_votes": int(w["Votes"] - ru["Votes"]), "margin_pct": round((w["Votes"] - ru["Votes"]) / valid * 100, 2),
        })
    return pd.DataFrame(cands), pd.DataFrame(seats)


if __name__ == "__main__":
    cands, seats = build()
    assert len(seats) == 119
    cands.to_csv(os.path.join(ROOT, "data", "telangana_2014_candidates.csv"), index=False)
    seats.to_csv(os.path.join(ROOT, "data", "telangana_2014_seats.csv"), index=False)
    print(len(seats), "seats,", len(cands), "candidates")
    print(seats["winner_party"].value_counts().to_dict())
