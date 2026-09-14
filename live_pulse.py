"""Layer 5: live signals. Free-tier pulls of public search interest, news tone,
and video activity — no scraping of a platform's own feed, only APIs meant to be
queried. Every fetch returns {"ok": bool, ...} and never raises: a blocked or
rate-limited upstream should degrade the panel, not the app.
"""

from datetime import datetime

import requests

GDELT_DOC_API = "https://api.gdeltproject.org/api/v2/doc/doc"
YOUTUBE_SEARCH_API = "https://www.googleapis.com/youtube/v3/search"
REDDIT_TOKEN_API = "https://www.reddit.com/api/v1/access_token"
REDDIT_SEARCH_API = "https://oauth.reddit.com/search"
REDDIT_USER_AGENT = "peoples-mandate-ai/1.0 (live pulse panel)"


def fetch_search_interest(keyword, geo="IN-TG", timeframe="today 3-m"):
    """Google Trends interest-over-time via pytrends (unofficial, scrape-based —
    Google throttles or reshapes this endpoint without notice, so failure here
    is expected occasionally, not a bug)."""
    try:
        from pytrends.request import TrendReq
    except ImportError:
        return {"ok": False, "error": "pytrends not installed", "points": []}

    try:
        pytrends = TrendReq(hl="en-US", tz=330)
        pytrends.build_payload([keyword], geo=geo, timeframe=timeframe)
        df = pytrends.interest_over_time()
    except Exception as exc:
        return {"ok": False, "error": str(exc), "points": []}

    if df is None or df.empty or keyword not in df.columns:
        return {"ok": True, "points": []}

    points = [
        {"date": idx.to_pydatetime(), "interest": int(row[keyword])}
        for idx, row in df.iterrows()
    ]
    return {"ok": True, "points": points}


def _gdelt_get(params, timeout):
    """GDELT enforces roughly one request per 5 seconds per IP and answers a
    burst with 429s. No retry here on purpose — retrying into a live rate limit
    only adds to the burst; the caller's cache is what protects against that."""
    try:
        resp = requests.get(GDELT_DOC_API, params=params, timeout=timeout)
        resp.raise_for_status()
        return resp.json(), None
    except Exception as exc:
        return None, exc


def fetch_news_tone(keyword, timespan="30d", timeout=20):
    """GDELT 2.0 DOC API, timelinetone mode — free, no key, updated every 15 min.
    Tone is roughly -10 (very negative) to +10 (very positive) coverage, averaged
    across matching articles per day."""
    params = {
        "query": f'"{keyword}"',
        "mode": "timelinetone",
        "format": "json",
        "timespan": timespan,
    }
    payload, exc = _gdelt_get(params, timeout)
    if exc is not None:
        return {"ok": False, "error": str(exc), "points": []}

    series = (payload.get("timeline") or [{}])[0].get("data", [])
    points = []
    for p in series:
        raw_date = str(p.get("date", ""))
        value = p.get("value")
        if value is None or len(raw_date) < 8:
            continue
        try:
            dt = datetime.strptime(raw_date[:8], "%Y%m%d")
        except ValueError:
            continue
        points.append({"date": dt, "tone": float(value)})
    return {"ok": True, "points": points}


def fetch_headlines(keyword, maxrecords=8, timeout=20):
    """GDELT 2.0 DOC API, artlist mode — most relevant recent articles."""
    params = {
        "query": f'"{keyword}"',
        "mode": "artlist",
        "format": "json",
        "maxrecords": maxrecords,
        "sort": "hybridrel",
    }
    payload, exc = _gdelt_get(params, timeout)
    if exc is not None:
        return {"ok": False, "error": str(exc), "articles": []}

    articles = [
        {
            "title": a.get("title") or "Untitled",
            "url": a.get("url", ""),
            "domain": a.get("domain", ""),
            "seendate": a.get("seendate", ""),
        }
        for a in payload.get("articles") or []
    ]
    return {"ok": True, "articles": articles}


def fetch_youtube_mentions(keyword, api_key, max_results=6, timeout=10):
    """YouTube Data API v3 search — free tier, quota-limited (~10k units/day,
    100 units per search call). Requires a key; caller decides whether to skip."""
    if not api_key:
        return {"ok": False, "error": "no API key configured", "videos": []}

    params = {
        "part": "snippet",
        "q": keyword,
        "type": "video",
        "order": "date",
        "maxResults": max_results,
        "key": api_key,
    }
    try:
        resp = requests.get(YOUTUBE_SEARCH_API, params=params, timeout=timeout)
        resp.raise_for_status()
        payload = resp.json()
    except Exception as exc:
        return {"ok": False, "error": str(exc), "videos": []}

    videos = []
    for item in payload.get("items") or []:
        snippet = item.get("snippet", {})
        video_id = (item.get("id") or {}).get("videoId")
        if not video_id:
            continue
        videos.append({
            "title": snippet.get("title", ""),
            "channel": snippet.get("channelTitle", ""),
            "published": snippet.get("publishedAt", ""),
            "url": f"https://www.youtube.com/watch?v={video_id}",
        })
    return {"ok": True, "videos": videos}


def fetch_reddit_mentions(keyword, client_id, client_secret, max_results=6, timeout=10):
    """Reddit's public search via a script app's client-credentials token — free,
    read-only, no user login needed. Genuinely public search, unlike Meta's APIs."""
    if not client_id or not client_secret:
        return {"ok": False, "error": "no API credentials configured", "posts": []}

    try:
        token_resp = requests.post(
            REDDIT_TOKEN_API,
            auth=(client_id, client_secret),
            data={"grant_type": "client_credentials"},
            headers={"User-Agent": REDDIT_USER_AGENT},
            timeout=timeout,
        )
        token_resp.raise_for_status()
        token = token_resp.json().get("access_token")
        if not token:
            return {"ok": False, "error": "Reddit did not return an access token", "posts": []}

        search_resp = requests.get(
            REDDIT_SEARCH_API,
            params={"q": keyword, "sort": "new", "limit": max_results},
            headers={"Authorization": f"Bearer {token}", "User-Agent": REDDIT_USER_AGENT},
            timeout=timeout,
        )
        search_resp.raise_for_status()
        payload = search_resp.json()
    except Exception as exc:
        return {"ok": False, "error": str(exc), "posts": []}

    posts = []
    for child in ((payload.get("data") or {}).get("children")) or []:
        d = child.get("data", {})
        posts.append({
            "title": d.get("title", ""),
            "subreddit": d.get("subreddit_name_prefixed", ""),
            "score": d.get("score", 0),
            "num_comments": d.get("num_comments", 0),
            "url": f"https://reddit.com{d.get('permalink', '')}",
        })
    return {"ok": True, "posts": posts}
