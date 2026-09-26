"""Summaries of the WhatsApp "rate my area" answers.

The answers are volunteered by people who chose to message the bot, so they show what those people say, not what
the area thinks. Areas with fewer than MIN_RESPONSES answers are held back, so nobody can be picked out of a small group.
"""

import re

import pandas as pd

MIN_RESPONSES = 5


def prepare(df):
    """Clean area names so 'Shaikpet ' and 'shaikpet' are one place, and add a display name."""
    if df.empty:
        return df
    df = df.copy()
    df["area_key"] = df["area"].astype(str).map(lambda a: re.sub(r"\s+", " ", a.strip().casefold()))
    show = df.groupby("area_key")["area"].agg(lambda s: s.astype(str).str.strip().value_counts().index[0])
    df["area_name"] = df["area_key"].map(show).map(lambda a: a.title() if a.isascii() else a)
    return df


def headline(df):
    if df.empty:
        return {"answers": 0, "people": 0, "areas": 0, "average": None}
    return {"answers": len(df), "people": df["phone_hash"].nunique(), "areas": df["area_key"].nunique(), "average": round(float(df["rating"].mean()), 2)}


def by_area(df, min_n=MIN_RESPONSES):
    """One row per area with enough answers: how many, the average rating, and its most named issue."""
    if df.empty:
        return pd.DataFrame(), 0
    rows, held = [], 0
    for key, g in df.groupby("area_key"):
        if len(g) < min_n:
            held += 1
            continue
        issues = g["issue"].value_counts()
        rows.append({"Area": g["area_name"].iloc[0], "Answers": len(g), "Average rating": round(g["rating"].mean(), 2),
                     "Most named issue": issues.index[0], "Share naming it": f"{issues.iloc[0] / len(g) * 100:.0f}%"})
    table = pd.DataFrame(rows)
    if not table.empty:
        table = table.sort_values("Average rating")
    return table, held


def issue_mix(df):
    if df.empty:
        return pd.DataFrame()
    counts = df["issue"].value_counts()
    return pd.DataFrame({"Issue": counts.index, "Answers": counts.values, "Share": [f"{v / len(df) * 100:.0f}%" for v in counts.values]})


def area_by_issue(df, min_n=MIN_RESPONSES):
    """Areas (with enough answers) against issues: how many named each."""
    if df.empty:
        return pd.DataFrame()
    big = df.groupby("area_key")["area"].transform("size") >= min_n
    df = df[big]
    if df.empty:
        return pd.DataFrame()
    return df.pivot_table(index="area_name", columns="issue", values="rating", aggfunc="size", fill_value=0)


def weekly(df):
    if df.empty:
        return pd.DataFrame()
    g = df.groupby("week").agg(Answers=("rating", "size"), Average=("rating", "mean")).reset_index().sort_values("week")
    g["Average"] = g["Average"].round(2)
    return g
