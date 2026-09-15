"""Layer 5: live signals. Free-tier pulls of public search interest, news
coverage, video activity, and forum posts — only APIs and feeds meant to be
queried, no scraping. Every fetch returns {"ok": bool, ...} and never raises: a
blocked or rate-limited upstream should degrade one panel, not the page.

Errors are reduced to a short reason before they leave this module. A raw
requests exception embeds the full request URL, and for YouTube that URL carries
the API key — showing it on the page would hand the key to every viewer.
"""

import json
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import requests

GDELT_DOC_API = "https://api.gdeltproject.org/api/v2/doc/doc"
GOOGLE_NEWS_RSS = "https://news.google.com/rss/search"
YOUTUBE_SEARCH_API = "https://www.googleapis.com/youtube/v3/search"
YOUTUBE_NEWS_AND_POLITICS = "25"
REDDIT_TOKEN_API = "https://www.reddit.com/api/v1/access_token"
REDDIT_SEARCH_API = "https://oauth.reddit.com/search"
REDDIT_USER_AGENT = "peoples-mandate-ai/1.0 (live pulse panel)"
MOOD_LABELS = ("positive", "neutral", "negative")


def _reason(exc):
    if isinstance(exc, requests.exceptions.HTTPError) and exc.response is not None:
        code = exc.response.status_code
        return {
            400: "request rejected (HTTP 400) — check the API key",
            401: "not authorised (HTTP 401) — check the credentials",
            403: "access denied (HTTP 403) — key restricted or daily quota used up",
            429: "rate-limited (HTTP 429) — try again in a few minutes",
        }.get(code, f"HTTP {code}")
    if isinstance(exc, requests.exceptions.Timeout):
        return "timed out"
    if isinstance(exc, requests.exceptions.ConnectionError):
        return "could not connect"
    return type(exc).__name__


def _openai_reason(exc):
    name = type(exc).__name__
    return {
        "AuthenticationError": "OpenAI rejected the API key",
        "RateLimitError": "OpenAI rate limit hit or account out of credit",
        "APIConnectionError": "could not reach OpenAI",
    }.get(name, name)


def fetch_search_interest(term, geo="IN-TG", timeframe="today 3-m"):
    """Google Trends interest-over-time via pytrends (unofficial and scrape-based —
    Google throttles or reshapes this endpoint without notice, so an occasional
    failure is expected, not a bug)."""
    try:
        from pytrends.request import TrendReq
    except ImportError:
        return {"ok": False, "error": "pytrends not installed", "points": []}

    try:
        pytrends = TrendReq(hl="en-US", tz=330, timeout=(3, 8))
        pytrends.build_payload([term], geo=geo, timeframe=timeframe)
        df = pytrends.interest_over_time()
    except Exception as exc:
        reason = "rate-limited (HTTP 429) — try again later" if "429" in str(exc) else "Google Trends request failed"
        return {"ok": False, "error": reason, "points": []}

    if df is None or df.empty or term not in df.columns:
        return {"ok": True, "points": []}

    points = [{"date": idx.to_pydatetime(), "interest": int(row[term])} for idx, row in df.iterrows()]
    return {"ok": True, "points": points}


def fetch_google_news(query, days=7, max_items=100, timeout=15):
    """Google News RSS search — free, no key, and without GDELT's strict
    one-request-per-5-seconds limit, which a shared hosting IP trips constantly."""
    params = {"q": f"{query} when:{days}d", "hl": "en-IN", "gl": "IN", "ceid": "IN:en"}
    try:
        resp = requests.get(GOOGLE_NEWS_RSS, params=params, timeout=timeout)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
    except Exception as exc:
        return {"ok": False, "error": _reason(exc), "articles": []}

    articles = []
    for item in root.findall("./channel/item")[:max_items]:
        source = item.findtext("source") or ""
        title = item.findtext("title") or "Untitled"
        suffix = f" - {source}"
        if source and title.endswith(suffix):
            title = title[: -len(suffix)]
        try:
            published = parsedate_to_datetime(item.findtext("pubDate"))
        except (TypeError, ValueError):
            published = None
        articles.append({"title": title, "url": item.findtext("link") or "", "source": source, "published": published})
    return {"ok": True, "articles": articles}


def fetch_recent_news(query, min_articles=10):
    """Last 7 days, widened to 30 when the week is thin. Lower-profile leaders and
    small seats often have zero articles in a given week but several in the
    month — a strict 7-day window left their whole page empty."""
    result = fetch_google_news(query, days=7)
    if result["ok"] and len(result["articles"]) < min_articles:
        wider = fetch_google_news(query, days=30)
        if wider["ok"] and len(wider["articles"]) > len(result["articles"]):
            return {**wider, "days": 30}
    return {**result, "days": 7}


def latest_first(articles):
    oldest = datetime.min.replace(tzinfo=timezone.utc)
    return sorted(articles, key=lambda a: a["published"] or oldest, reverse=True)


def coverage_by_day(articles, days=7):
    today = datetime.now(timezone.utc).date()
    counts = Counter(a["published"].astimezone(timezone.utc).date() for a in articles if a["published"])
    return [
        {"date": today - timedelta(days=offset), "articles": counts.get(today - timedelta(days=offset), 0)}
        for offset in range(days - 1, -1, -1)
    ]


def fetch_news_tone(query, timespan="30d", timeout=20):
    """GDELT 2.0 DOC API, timelinetone mode — free, no key. Tone runs roughly
    -10 (very negative) to +10 (very positive), averaged per day. GDELT allows
    about one request per 5 seconds per IP, so on shared hosting this is the
    panel most likely to be rate-limited."""
    params = {"query": query, "mode": "timelinetone", "format": "json", "timespan": timespan}
    try:
        resp = requests.get(GDELT_DOC_API, params=params, timeout=timeout)
        resp.raise_for_status()
        payload = resp.json()
    except Exception as exc:
        return {"ok": False, "error": _reason(exc), "points": []}

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


def fetch_youtube_mentions(query, api_key, max_results=8, days=30, timeout=10):
    """YouTube Data API v3 search — free tier, ~10k quota units/day, 100 per call.
    Restricted to the News & Politics category, India, and the last 30 days,
    ranked by relevance: an unfiltered newest-first search for a place name
    returns shop ads and food vlogs, not political coverage."""
    if not api_key or not str(api_key).isascii():
        return {"ok": False, "error": "no usable API key", "videos": []}

    published_after = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    params = {
        "part": "snippet",
        "q": query,
        "type": "video",
        "order": "relevance",
        "videoCategoryId": YOUTUBE_NEWS_AND_POLITICS,
        "regionCode": "IN",
        "publishedAfter": published_after,
        "maxResults": max_results,
        "key": api_key,
    }
    try:
        resp = requests.get(YOUTUBE_SEARCH_API, params=params, timeout=timeout)
        resp.raise_for_status()
        payload = resp.json()
    except Exception as exc:
        return {"ok": False, "error": _reason(exc), "videos": []}

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


def fetch_reddit_mentions(query, client_id, client_secret, max_results=6, timeout=10):
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
            params={"q": query, "sort": "new", "limit": max_results},
            headers={"Authorization": f"Bearer {token}", "User-Agent": REDDIT_USER_AGENT},
            timeout=timeout,
        )
        search_resp.raise_for_status()
        payload = search_resp.json()
    except Exception as exc:
        return {"ok": False, "error": _reason(exc), "posts": []}

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


MOOD_PROMPT = """You label news headlines by their tone toward one subject — a Telangana constituency, politician, or party.

Rules:
- Judge ONLY from the headline text. Do not use outside knowledge about the subject.
- "positive": favourable for the subject (achievement, welfare delivered, praise, win).
- "negative": unfavourable (crime, failure, protest, scandal, criticism, disaster, defeat).
- "neutral": factual or routine coverage that is about the subject.
- "unrelated": the headline is not actually about the subject.
- themes: up to 4 short recurring topics among the related headlines, each under 6 words, only if 2 or more headlines support it.

Return ONLY JSON: {"labels": [one of "positive"|"neutral"|"negative"|"unrelated" per headline, same order], "themes": ["..."]}"""


def classify_headline_mood(subject, headlines, api_key, model="gpt-4o-mini"):
    """One batched, temperature-0 call that labels each headline's tone toward the
    subject. A headline-wording read, not a verified sentiment measure."""
    if not headlines:
        return {"ok": True, "counts": {}, "themes": [], "unrelated": 0}
    try:
        from openai import OpenAI

        numbered = "\n".join(f"{i + 1}. {h}" for i, h in enumerate(headlines))
        resp = OpenAI(api_key=api_key).chat.completions.create(
            model=model,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": MOOD_PROMPT},
                {"role": "user", "content": f"Subject: {subject}\n\nHeadlines:\n{numbered}"},
            ],
        )
        data = json.loads(resp.choices[0].message.content)
    except Exception as exc:
        return {"ok": False, "error": _openai_reason(exc)}

    labels = data.get("labels") or []
    if len(labels) != len(headlines):
        return {"ok": False, "error": "the model returned an incomplete answer"}

    tally = Counter(str(label).lower() for label in labels)
    return {
        "ok": True,
        "counts": {label: tally.get(label, 0) for label in MOOD_LABELS},
        "unrelated": len(labels) - sum(tally.get(label, 0) for label in MOOD_LABELS),
        "themes": [str(t) for t in (data.get("themes") or [])][:4],
    }
