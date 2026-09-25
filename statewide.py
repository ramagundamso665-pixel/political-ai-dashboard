"""Statewide view of the Telangana 2023 assembly election, all 119 constituencies.

Reads the two CSVs produced by pipeline/fetch_eci_2023.py from the Election Commission's
published Detailed Results report. They ship with the app, so this page works on any host
and never waits on the database. The same figures are also loaded into Supabase.
"""

import os

import pandas as pd

ROOT = os.path.dirname(os.path.abspath(__file__))
SEATS_CSV = os.path.join(ROOT, "data", "telangana_2023_seats.csv")
CANDIDATES_CSV = os.path.join(ROOT, "data", "telangana_2023_candidates.csv")

MARGINAL_PCT = 5.0      # a seat decided by under 5% of the votes polled
RAZOR_VOTES = 2000      # or by under 2,000 votes


def load():
    seats = pd.read_csv(SEATS_CSV)
    candidates = pd.read_csv(CANDIDATES_CSV)
    return seats, candidates


def seat_tally(seats):
    """Seats won per party, largest first."""
    return seats["winner_party"].value_counts()


def vote_share_by_party(candidates):
    """Each party's share of all valid votes polled across the state, next to seats won."""
    real = candidates[candidates["party"] != "NOTA"]
    total = candidates["votes_total"].sum()
    by_party = real.groupby("party")["votes_total"].sum().sort_values(ascending=False)
    return (by_party / total * 100).round(2)


def seats_vs_votes(seats, candidates, top=6):
    """For the biggest parties: vote share against seats won. A gap between the two is
    what a first-past-the-post system does to a party's votes."""
    share = vote_share_by_party(candidates)
    tally = seat_tally(seats)
    parties = list(share.head(top).index)
    return pd.DataFrame(
        {
            "Party": parties,
            "Vote share %": [share[p] for p in parties],
            "Seats won": [int(tally.get(p, 0)) for p in parties],
            "Seat share %": [round(tally.get(p, 0) / len(seats) * 100, 1) for p in parties],
        }
    )


def battlegrounds(seats, max_margin_pct=MARGINAL_PCT):
    """Seats decided narrowly, closest first."""
    close = seats[seats["margin_pct"] < max_margin_pct]
    return close.sort_values("margin_votes")


def lost_narrowly(seats, party, max_margin_pct=MARGINAL_PCT):
    """Seats where `party` finished second within `max_margin_pct` of the winner."""
    return seats[(seats["runner_up_party"] == party) & (seats["margin_pct"] < max_margin_pct)].sort_values("margin_votes")


def seat_candidates(candidates, seat):
    rows = candidates[candidates["seat"] == seat].sort_values("votes_total", ascending=False)
    return rows[["rank", "candidate", "party", "votes_total", "pct"]].rename(
        columns={"rank": "Rank", "candidate": "Candidate", "party": "Party", "votes_total": "Votes", "pct": "% of votes"}
    )


def swing_needed(seat_row):
    """Votes that would have had to change sides for the runner-up to win: half the margin, rounded up."""
    return int(seat_row["margin_votes"] // 2 + 1)


# ----------------------------------------------------------------------
# Two elections side by side: 2018 and 2023
# ----------------------------------------------------------------------
MAJOR = ["BRS", "INC", "BJP", "AIMIM"]


def load_year(year):
    seats = pd.read_csv(os.path.join(ROOT, "data", f"telangana_{year}_seats.csv"))
    candidates = pd.read_csv(os.path.join(ROOT, "data", f"telangana_{year}_candidates.csv"))
    return seats, candidates


def party_share_by_seat(candidates):
    """Each party's share of the votes polled in each seat: seat number x party."""
    return candidates.groupby(["seat_no", "party"])["pct"].sum().unstack(fill_value=0.0)


def seat_changes(seats_then, seats_now):
    """One row per seat: who won each time, whether it changed hands, and the margin then and now.
    Seats are matched by their constituency number, which has not changed between the two elections."""
    then = seats_then[["seat_no", "seat", "winner_party", "margin_votes", "margin_pct"]].rename(
        columns={"winner_party": "winner_then", "margin_votes": "margin_votes_then", "margin_pct": "margin_pct_then"}
    )
    now = seats_now[["seat_no", "seat", "reservation", "winner_party", "margin_votes", "margin_pct"]].rename(
        columns={"seat": "seat_now", "winner_party": "winner_now", "margin_votes": "margin_votes_now", "margin_pct": "margin_pct_now"}
    )
    out = then.merge(now, on="seat_no", how="inner")
    out["changed_hands"] = out["winner_then"] != out["winner_now"]
    return out


def swing_by_seat(cands_then, cands_now, parties=MAJOR):
    """Change in each major party's share of the vote, in points, per seat (now minus then)."""
    a, b = party_share_by_seat(cands_then), party_share_by_seat(cands_now)
    rows = pd.DataFrame(index=sorted(set(a.index) | set(b.index)))
    for p in parties:
        rows[p] = (b[p] if p in b else 0).reindex(rows.index).fillna(0) - (a[p] if p in a else 0).reindex(rows.index).fillna(0)
    rows.index.name = "seat_no"
    return rows.round(2).reset_index()


def flows(changes):
    """How seats moved between parties: (winner then, winner now) -> count, only seats that changed."""
    moved = changes[changes["changed_hands"]]
    return moved.groupby(["winner_then", "winner_now"]).size().sort_values(ascending=False).rename("Seats").reset_index()
