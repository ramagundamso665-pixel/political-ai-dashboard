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


def match_area(name, known):
    """Map a free-text area to one of the constituency's known divisions when one is named in it, else keep it as written."""
    low = re.sub(r"\s+", " ", str(name).strip().casefold())
    for k in known:
        kk = re.sub(r"\s+", " ", str(k).strip().casefold())
        if kk and (kk == low or kk in low or low in kk):
            return k
    return str(name).strip().title() if str(name).isascii() else str(name).strip()


def board(issues, ratings, known=(), min_n=MIN_RESPONSES):
    """One row per area, from three sources side by side: issues staff logged or read from newspapers, and what WhatsApp
    respondents rated and named. WhatsApp figures appear only for areas with at least `min_n` answers."""
    rows = {}
    if issues is not None and not issues.empty:
        live = issues[~issues["status"].isin(["Resolved", "Dropped"])]
        for _, r in live.iterrows():
            d = r.get("division")
            area = "Not set" if (d is None or pd.isna(d) or not str(d).strip()) else match_area(d, known)
            row = rows.setdefault(area, {"Area": area, "issues": [], "high": 0, "waves": []})
            row["issues"].append(str(r.get("category") or "Other"))
            row["high"] += str(r.get("severity")) == "High"
    if ratings is not None and not ratings.empty:
        for _, r in ratings.iterrows():
            area = match_area(r["area"], known)
            rows.setdefault(area, {"Area": area, "issues": [], "high": 0, "waves": []})["waves"].append((r["issue"], int(r["rating"])))
    out = []
    for area, r in rows.items():
        top_logged = pd.Series(r["issues"]).value_counts().index[0] if r["issues"] else ""
        n = len(r["waves"])
        wa_ok = n >= min_n
        out.append({
            "Area": area, "Open issues logged": len(r["issues"]), "High severity": r["high"], "Most logged": top_logged,
            "WhatsApp answers": n if wa_ok else (f"under {min_n}" if n else 0),
            "WhatsApp rating": round(sum(x for _, x in r["waves"]) / n, 2) if wa_ok else None,
            "Most named on WhatsApp": pd.Series([i for i, _ in r["waves"]]).value_counts().index[0] if wa_ok else "",
        })
    df = pd.DataFrame(out)
    if df.empty:
        return df
    return df.sort_values(["High severity", "Open issues logged"], ascending=False).reset_index(drop=True)


def area_by_category(issues):
    """Open issues: area against category, counts."""
    if issues is None or issues.empty:
        return pd.DataFrame()
    live = issues[~issues["status"].isin(["Resolved", "Dropped"])].copy()
    if live.empty:
        return pd.DataFrame()
    live["division"] = live["division"].fillna("Not set")
    live["category"] = live["category"].fillna("Other")
    return live.pivot_table(index="division", columns="category", values="title", aggfunc="count", fill_value=0)
