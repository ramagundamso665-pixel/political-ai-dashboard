"""Google search interest for several terms at once, by time, by rising query and by place.

Uses pytrends, an unofficial client for the public Google Trends site. Google throttles it without
notice, so every call can fail with a rate limit; callers show that plainly and retry later.
Trends gives relative interest (0 to 100 within the terms asked for together), not search counts.
"""

import time

import pandas as pd

TIMEFRAMES = {"Last 7 days": "now 7-d", "Last 30 days": "today 1-m", "Last 3 months": "today 3-m", "Last 12 months": "today 12-m"}
GEOS = {"Telangana": "IN-TG", "India": "IN"}
MAX_TERMS = 5


def _client():
    from pytrends.request import TrendReq
    return TrendReq(hl="en-US", tz=330, timeout=(5, 20))


def _reason(exc):
    return "Google is rate-limiting Trends right now (HTTP 429). Try again in a few minutes." if "429" in str(exc) else f"Google Trends request failed ({type(exc).__name__})."


def fetch(terms, geo="IN-TG", timeframe="today 3-m", pause=1.5):
    """{'ok', 'error', 'interest': DataFrame(date x term), 'rising': {term: DataFrame}, 'top': {term: DataFrame},
    'regions': DataFrame(place x term)}. Each of the three calls can fail on its own; what worked is kept."""
    terms = [t.strip() for t in terms if t.strip()][:MAX_TERMS]
    out = {"ok": False, "error": None, "terms": terms, "interest": pd.DataFrame(), "rising": {}, "top": {}, "regions": pd.DataFrame()}
    if not terms:
        out["error"] = "Enter at least one search term."
        return out
    try:
        client = _client()
        client.build_payload(terms, geo=geo, timeframe=timeframe)
        df = client.interest_over_time()
        if df is not None and not df.empty:
            out["interest"] = df.drop(columns=["isPartial"], errors="ignore")
        out["ok"] = True
    except Exception as exc:
        out["error"] = _reason(exc)
        return out
    time.sleep(pause)
    try:
        related = client.related_queries() or {}
        for term in terms:
            block = related.get(term) or {}
            if block.get("rising") is not None:
                out["rising"][term] = block["rising"]
            if block.get("top") is not None:
                out["top"][term] = block["top"]
    except Exception as exc:
        out["error"] = "Rising searches unavailable: " + _reason(exc)
    time.sleep(pause)
    try:
        regions = client.interest_by_region(resolution="REGION", inc_low_vol=True)
        if regions is not None and not regions.empty:
            out["regions"] = regions
    except Exception as exc:
        out["error"] = (out["error"] + " " if out["error"] else "") + "Places unavailable: " + _reason(exc)
    return out


def summary(interest):
    """One row per term: its average, its latest week, and the change between them."""
    if interest.empty:
        return pd.DataFrame()
    n = max(1, len(interest) // 4)
    rows = []
    for term in interest.columns:
        series = interest[term]
        earlier, recent = series.iloc[:-n].mean() if len(series) > n else 0.0, series.iloc[-n:].mean()
        rows.append({"Search term": term, "Average interest": round(series.mean(), 1), "Latest": round(recent, 1),
                     "Change vs earlier": round(recent - earlier, 1)})
    return pd.DataFrame(rows).sort_values("Average interest", ascending=False)


def top_places(regions, term, n=12):
    if regions.empty or term not in regions.columns:
        return pd.DataFrame()
    r = regions[term]
    r = r[r > 0].sort_values(ascending=False).head(n)
    return pd.DataFrame({"Place": r.index, "Relative interest": r.values})
