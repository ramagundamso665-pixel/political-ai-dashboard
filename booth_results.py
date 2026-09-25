"""Booth-level (polling station) results for Jubilee Hills, 2023.

Read from the Chief Electoral Officer Telangana's published Form 20 (the final result sheet, one
line per polling station). The sheet is a scanned image, so the numbers were read off the scan and
then checked against the Election Commission's own totals: each candidate column adds up to that
candidate's EVM votes in the ECI Detailed Results report, to the vote. Postal votes are not in a
booth, so they are not in this table.
"""

import os

import pandas as pd

ROOT = os.path.dirname(os.path.abspath(__file__))
BOOTHS_CSV = os.path.join(ROOT, "data", "jubilee_hills_2023_booths.csv")

PARTIES = ["BRS", "INC", "BJP", "AIMIM"]
# candidates whose columns were read off the sheet: the four parties above plus BSP (a candidate
# with 841 votes); the remaining candidates are combined under "other_candidates"
COUNTED = PARTIES + ["BSP", "other_candidates"]


def load():
    df = pd.read_csv(BOOTHS_CSV, dtype={"booth": str})
    for party in COUNTED:
        df[f"{party}_pct"] = (df[party] / df["valid_votes"] * 100).round(2)
    ranked = df[PARTIES].apply(lambda r: r.sort_values(ascending=False).index.tolist(), axis=1)
    df["winner"] = ranked.str[0]
    df["runner_up"] = ranked.str[1]
    top = df[PARTIES].max(axis=1)
    second = df[PARTIES].apply(lambda r: r.sort_values(ascending=False).iloc[1], axis=1)
    df["margin_votes"] = top - second
    df["margin_pct"] = (df["margin_votes"] / df["valid_votes"] * 100).round(2)
    return df


def totals(df):
    """Whole-constituency EVM totals: the sum of the booths."""
    return df[COUNTED + ["valid_votes", "nota", "total_polled"]].sum()


def booths_won(df):
    return df["winner"].value_counts().reindex(PARTIES, fill_value=0)


def strongest(df, party, n=15):
    return df.sort_values(f"{party}_pct", ascending=False).head(n)


def weakest(df, party, n=15):
    return df.sort_values(f"{party}_pct").head(n)


def closest(df, n=20):
    return df.sort_values(["margin_votes", "booth"]).head(n)


def swing_booths(df, a="BRS", b="INC", within=10.0):
    """Booths where the two parties finished within `within` points of each other: the ones that decide a close race."""
    gap = (df[f"{a}_pct"] - df[f"{b}_pct"]).abs()
    return df[gap <= within].assign(gap=gap).sort_values("gap")
