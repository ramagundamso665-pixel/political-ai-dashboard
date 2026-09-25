"""How close were the numbers to what actually happened.

Two honest checks, neither of which needs a claim we can't back up:

1. calibration: for a past election that we also have internal division tracking
   for, does the tracking reproduce the official result?
2. score_prediction: once a real result is on file, how far off was a prediction
   that was logged before it?
"""

import pandas as pd

from config import PARTIES, normalize_party


def _official_shares(historical, year):
    rows = historical[pd.to_numeric(historical["Year"], errors="coerce") == year]
    out = {}
    for _, row in rows.iterrows():
        party = normalize_party(row["Party"])
        if party:
            out[party] = float(row["Pct"])
    return out


def _winner(shares):
    contenders = {p: v for p, v in shares.items() if p in PARTIES}
    return max(contenders, key=contenders.get) if contenders else None


def calibration(sheets):
    """One entry per year that appears in both the official results and the
    division tracking. Only parties with an official number are compared, since
    Historical_Results lists just the top finishers."""
    historical, shares = sheets.get("historical_results"), sheets.get("division_shares")
    if historical is None or shares is None:
        return []

    hist_years = set(pd.to_numeric(historical["Year"], errors="coerce").dropna().astype(int))
    track_years = set(pd.to_numeric(shares["Year"], errors="coerce").dropna().astype(int))

    out = []
    for year in sorted(hist_years & track_years):
        actual = _official_shares(historical, year)
        rows = shares[pd.to_numeric(shares["Year"], errors="coerce") == year]
        tracked = {
            p: float(pd.to_numeric(rows[p], errors="coerce").mean()) for p in PARTIES if p in rows.columns
        }
        compared = [p for p in actual if p in tracked]
        if not compared:
            continue

        errors = {p: round(tracked[p] - actual[p], 2) for p in compared}

        # what a person would do with no tracking: assume last time's share repeats
        carry = {}
        for p in compared:
            earlier = [
                (int(r["Year"]), float(r["Pct"]))
                for _, r in historical.iterrows()
                if normalize_party(r["Party"]) == p and int(r["Year"]) < year
            ]
            if earlier:
                prior_year, prior = max(earlier)
                carry[p] = {"from_year": prior_year, "prior": prior, "error": round(prior - actual[p], 2)}

        out.append({
            "year": year,
            "actual": {p: actual[p] for p in compared},
            "tracked": {p: round(tracked[p], 1) for p in compared},
            "errors": errors,
            "mae": round(sum(abs(e) for e in errors.values()) / len(errors), 2),
            "winner_actual": _winner(actual),
            "winner_tracked": _winner({p: tracked[p] for p in compared}),
            "carry_forward": carry,
        })
    return out


def score_prediction(predicted, actual):
    """`predicted` and `actual` are {party: percent}. Compared on the parties both cover."""
    compared = [p for p in PARTIES if p in predicted and p in actual]
    if not compared:
        return None
    errors = {p: round(float(predicted[p]) - float(actual[p]), 1) for p in compared}
    called, won = _winner({p: predicted[p] for p in compared}), _winner({p: actual[p] for p in compared})
    return {
        "compared": compared,
        "errors": errors,
        "mae": round(sum(abs(e) for e in errors.values()) / len(errors), 1),
        "winner_called": called,
        "winner_actual": won,
        "winner_correct": called == won,
    }


def input_scorecard(actual, estimates):
    """Score each estimate ({name: {party: pct}}) against a real result, closest first."""
    rows = []
    for name, estimate in estimates.items():
        scored = score_prediction(estimate, actual)
        if scored:
            rows.append({"name": name, **scored})
    return sorted(rows, key=lambda r: r["mae"])


# ----------------------------------------------------------------------
# Headline mood: does the AI's reading match a person's?
# ----------------------------------------------------------------------
MOOD_CLASSES = ("positive", "neutral", "negative", "unrelated")
MIN_LABELS_FOR_ACCURACY = 30


def _wilson(agree, n, z=1.96):
    """95% range for a proportion. With few labels it is wide, which is the point:
    2 right out of 3 is not evidence of 67% accuracy."""
    if not n:
        return (0.0, 0.0)
    p = agree / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def mood_agreement(rows):
    """`rows` are {"model": label, "human": label}. Agreement between the AI's
    reading of a headline and a person's, overall and per label."""
    pairs = [(r["model"], r["human"]) for r in rows if r.get("model") in MOOD_CLASSES and r.get("human") in MOOD_CLASSES]
    n = len(pairs)
    if not n:
        return None
    agree = sum(m == h for m, h in pairs)
    low, high = _wilson(agree, n)
    return {
        "n": n,
        "agree": agree,
        "pct": round(agree / n * 100, 1),
        "low_pct": round(low * 100, 1),
        "high_pct": round(high * 100, 1),
        "enough": n >= MIN_LABELS_FOR_ACCURACY,
        "per_class": {
            c: {
                "labelled": sum(1 for _, h in pairs if h == c),
                "agreed": sum(1 for m, h in pairs if h == c and m == c),
            }
            for c in MOOD_CLASSES
        },
    }
