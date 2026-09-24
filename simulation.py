"""What-if arithmetic on the division tracking data.

Deliberately simple enough to explain to a candidate: pick parties, move their
vote share by some points, and the points come from (or go back to) the parties
you did not touch, in proportion to what they hold now. Every division still adds
up to what it did before. Nothing here forecasts turnout or vote transfers.
"""

import pandas as pd

from config import PARTIES

SHARE_COLS = ["BRS", "INC", "BJP", "AIMIM", "Others"]


def latest_round(division_shares):
    """(shares indexed by division, year) for the most recent tracking round."""
    year = division_shares["Year"].max()
    df = division_shares[division_shares["Year"] == year].copy()
    cols = [c for c in SHARE_COLS if c in df.columns]
    df[cols] = df[cols].apply(pd.to_numeric, errors="coerce").fillna(0.0)
    return df.set_index("Division")[cols], year


def _shift_row(row, shifts):
    """One division. Shifted parties move by exactly their shift when the others
    hold enough share to fund it; otherwise the increases are scaled back."""
    moved = [p for p, pts in shifts.items() if pts and p in row.index]
    if not moved:
        return row
    rest = [c for c in row.index if c not in moved]
    total = row.sum()

    target = (row[moved] + pd.Series(shifts)[moved]).clip(lower=0, upper=total)
    gain = target - row[moved]
    pool = row[rest].sum()

    up, down = gain[gain > 0].sum(), gain[gain < 0].sum()
    if up + down > pool:  # the untouched parties can't fund it all
        room = max(pool - down, 0.0)
        gain[gain > 0] = gain[gain > 0] * (room / up if up else 0.0)

    needed = gain.sum()
    out = row.copy()
    out[moved] = row[moved] + gain
    if pool > 0:
        out[rest] = row[rest] - needed * row[rest] / pool
    return out.clip(lower=0)


def apply_shift(shares, shifts, division=None):
    """Return a copy of `shares` with `shifts` ({party: points}) applied to every
    division, or to just `division`."""
    out = shares.copy()
    for name in out.index:
        if division in (None, name):
            out.loc[name] = _shift_row(out.loc[name], shifts)
    return out


def summarize(shares):
    """Constituency average (a plain mean over divisions, not vote-weighted, since
    no division-level turnout is on file), the leader, and divisions led."""
    parties = [p for p in PARTIES if p in shares.columns]
    average = shares.mean()
    ranked = average[parties].sort_values(ascending=False)
    led = shares[parties].idxmax(axis=1).value_counts().to_dict()
    return {
        "average": average.round(1).to_dict(),
        "leader": ranked.index[0],
        "runner_up": ranked.index[1],
        "margin": round(float(ranked.iloc[0] - ranked.iloc[1]), 1),
        "divisions_led": {p: int(led.get(p, 0)) for p in parties},
    }


def points_to_overtake(shares, challenger, step=0.1, limit=25.0):
    """Smallest uniform gain (in points) that puts `challenger` ahead of whoever
    leads now, or None if even `limit` points isn't enough."""
    base = summarize(shares)
    if base["leader"] == challenger:
        return 0.0
    gain = step
    while gain <= limit:
        if summarize(apply_shift(shares, {challenger: gain}))["leader"] == challenger:
            return round(gain, 1)
        gain += step
    return None
