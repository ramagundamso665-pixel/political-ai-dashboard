"""YouTube comments, scored for how organic they look, then read for sentiment.

Source: the YouTube Data API (public comments, official API, no scraping). Each commenter gets an
"organic likelihood" score from 0 to 100 built from a few visible signals: how new the channel is,
whether the same words were posted by several different accounts, whether one account repeats itself,
and whether near-identical comments arrive in a burst. It is a set of flags for a person to look at,
not proof that an account is fake: a real supporter can post a slogan, and a coordinated campaign can
use old accounts. Sentiment is read from the comments by a language model (Telugu, English and mixed).
"""

import json
import re
import unicodedata
from collections import Counter
from datetime import datetime

import requests

import live_pulse

COMMENTS_API = "https://www.googleapis.com/youtube/v3/commentThreads"
CHANNELS_API = "https://www.googleapis.com/youtube/v3/channels"
VIDEO_ID = re.compile(r"(?:v=|youtu\.be/|shorts/|embed/)([A-Za-z0-9_-]{11})")
PARTIES = ("INC", "BRS", "BJP", "AIMIM")
TONES = ("positive", "neutral", "negative")

MIN_DUP_CHARS = 15        # a slogan like "jai congress" is posted by many real people, so short comments never count as copies
DUP_SIMILARITY = 0.8
BURST_MINUTES = 10
BURST_SIZE = 5


def video_id(text):
    text = text.strip()
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", text):
        return text
    m = VIDEO_ID.search(text)
    return m.group(1) if m else None


def fetch_comments(vid, api_key, max_comments=200, timeout=15):
    """{'ok', 'error', 'comments': [...]} for one video: top-level comments, newest pages last."""
    if not api_key or not str(api_key).isascii():
        return {"ok": False, "error": "no usable YouTube API key", "comments": []}
    out, token = [], None
    while len(out) < max_comments:
        params = {"part": "snippet", "videoId": vid, "maxResults": min(100, max_comments - len(out)), "order": "relevance",
                  "textFormat": "plainText", "key": api_key}
        if token:
            params["pageToken"] = token
        try:
            resp = requests.get(COMMENTS_API, params=params, timeout=timeout)
            if resp.status_code == 403 and "commentsDisabled" in resp.text:
                return {"ok": False, "error": "comments are turned off on this video", "comments": out}
            resp.raise_for_status()
            payload = resp.json()
        except Exception as exc:
            return {"ok": bool(out), "error": live_pulse._reason(exc), "comments": out}
        for item in payload.get("items", []):
            s = item["snippet"]["topLevelComment"]["snippet"]
            channel = (s.get("authorChannelId") or {}).get("value")
            out.append({
                "video": vid, "author": s.get("authorDisplayName", ""), "channel_id": channel, "text": s.get("textDisplay", "").strip(),
                "published": s.get("publishedAt", ""), "likes": int(s.get("likeCount", 0) or 0),
            })
        token = payload.get("nextPageToken")
        if not token:
            break
    return {"ok": True, "error": None, "comments": out}


def fetch_channels(ids, api_key, timeout=15):
    """{channel_id: {'created', 'subscribers', 'videos', 'views'}} for the commenters, 50 at a time."""
    found, ids = {}, sorted({i for i in ids if i})
    for i in range(0, len(ids), 50):
        try:
            resp = requests.get(CHANNELS_API, params={"part": "snippet,statistics", "id": ",".join(ids[i:i + 50]), "key": api_key}, timeout=timeout)
            resp.raise_for_status()
        except Exception:
            continue
        for item in resp.json().get("items", []):
            st = item.get("statistics", {})
            found[item["id"]] = {
                "created": item["snippet"].get("publishedAt", ""),
                "subscribers": None if st.get("hiddenSubscriberCount") else int(st.get("subscriberCount", 0) or 0),
                "videos": int(st.get("videoCount", 0) or 0),
                "views": int(st.get("viewCount", 0) or 0),
            }
    return found


def _when(text):
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        return None


def normalise(text):
    """Words only: lowercase, no emoji, digits, punctuation or repeated spaces, so near-copies compare equal."""
    kept = [c if (unicodedata.category(c)[0] in "LM" or c == " ") else " " for c in text.lower()]
    return re.sub(r"\s+", " ", "".join(kept)).strip()


def _shingles(s, k=3):
    return {s[i:i + k] for i in range(max(1, len(s) - k + 1))}


def find_copies(comments):
    """Group near-identical comments (long enough to be a message, not a slogan). Returns a list of index lists."""
    norm = [normalise(c["text"]) for c in comments]
    idx = [i for i, t in enumerate(norm) if len(t) >= MIN_DUP_CHARS]
    sh = {i: _shingles(norm[i]) for i in idx}
    parent = {i: i for i in idx}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    by_len = sorted(idx, key=lambda i: len(norm[i]))
    for a_pos, a in enumerate(by_len):
        for b in by_len[a_pos + 1:]:
            if len(norm[b]) > len(norm[a]) * 1.4 + 3:
                break
            if norm[a] == norm[b] or len(sh[a] & sh[b]) / len(sh[a] | sh[b]) >= DUP_SIMILARITY:
                parent[find(a)] = find(b)
    groups = {}
    for i in idx:
        groups.setdefault(find(i), []).append(i)
    return [g for g in groups.values() if len(g) > 1]


def score(comments, channels):
    """Add 'score', 'tier' and 'flags' to each comment. Returns (comments, clusters) where clusters are the copied messages."""
    copies = find_copies(comments)
    flags = [[] for _ in comments]
    penalty = [0] * len(comments)

    def mark(i, points, why):
        penalty[i] += points
        flags[i].append(why)

    clusters = []
    for group in copies:
        authors = {comments[i]["channel_id"] or comments[i]["author"] for i in group}
        times = sorted(t for t in (_when(comments[i]["published"]) for i in group) if t)
        burst = bool(times) and any(
            sum(1 for u in times if 0 <= (u - t).total_seconds() <= BURST_MINUTES * 60) >= BURST_SIZE for t in times
        )
        clusters.append({"text": comments[group[0]]["text"][:160], "comments": len(group), "accounts": len(authors), "burst": burst})
        for i in group:
            if len(authors) >= 3:
                mark(i, 50, f"same message from {len(authors)} accounts")
            elif len(authors) == 2:
                mark(i, 20, "same message from 2 accounts")
            elif len(group) >= 2:
                mark(i, 25, "this account repeats itself")
            if burst:
                mark(i, 15, f"{BURST_SIZE}+ near-identical comments within {BURST_MINUTES} minutes")
    for i, c in enumerate(comments):
        ch = channels.get(c["channel_id"] or "")
        posted, born = _when(c["published"]), _when(ch["created"]) if ch else None
        if posted and born:
            age = (posted - born).days
            if age < 30:
                mark(i, 35, "channel under 30 days old when it commented")
            elif age < 180:
                mark(i, 15, "channel under 6 months old when it commented")
        if re.search(r"\d{7,}$", c["author"]):
            mark(i, 5, "handle ends in a long run of digits")
        c["score"] = max(0, 100 - penalty[i])
        c["tier"] = "Likely organic" if c["score"] >= 70 else ("Uncertain" if c["score"] >= 40 else "Flagged")
        c["flags"] = "; ".join(dict.fromkeys(flags[i]))
    clusters.sort(key=lambda c: (-c["accounts"], -c["comments"]))
    return comments, clusters


SENTIMENT_PROMPT = """You read public YouTube comments about Telangana politics, written in Telugu, English, Hindi or a mix (Telugu in Latin letters is common).
For each numbered comment give:
- stance: the party the comment is mainly about or for: INC (Congress, Revanth Reddy, Rahul Gandhi), BRS (KCR, KTR, Harish Rao), BJP (Modi, Kishan Reddy, Bandi Sanjay), AIMIM (Owaisi), or none if it is about no party or is unclear.
- tone: the comment's tone toward that stance: positive, negative or neutral. Praise or support = positive; criticism, mockery or abuse = negative.
- issue: a two or three word civic or political issue if one is named (for example "water", "roads", "corruption", "farmers"), else "".
Return ONLY JSON: {"results": {"1": {"stance": "...", "tone": "...", "issue": "..."}, "2": {...}}} with one entry per comment number. Judge only from the words; do not guess."""


def read_sentiment(comments, api_key, model="gpt-4o-mini", batch=40):
    """Adds 'stance', 'tone' and 'issue' to each comment. Returns {'ok', 'error', 'read'}. A batch that fails is skipped."""
    from openai import OpenAI

    client = OpenAI(api_key=api_key, timeout=60)
    read, error = 0, None
    for i in range(0, len(comments), batch):
        chunk = comments[i:i + batch]
        numbered = "\n".join(f"{n + 1}. {c['text'][:300].replace(chr(10), ' ')}" for n, c in enumerate(chunk))
        try:
            resp = client.chat.completions.create(
                model=model, temperature=0, response_format={"type": "json_object"},
                messages=[{"role": "system", "content": SENTIMENT_PROMPT}, {"role": "user", "content": numbered}],
            )
            results = json.loads(resp.choices[0].message.content).get("results", {})
        except Exception as exc:
            error = live_pulse._openai_reason(exc)
            continue
        for n, c in enumerate(chunk):
            r = results.get(str(n + 1)) or {}
            stance, tone = str(r.get("stance", "")).upper(), str(r.get("tone", "")).lower()
            if stance in PARTIES or stance == "NONE":
                c["stance"] = stance
                c["tone"] = tone if tone in TONES else "neutral"
                c["issue"] = str(r.get("issue", "")).strip().lower()
                read += 1
    return {"ok": read > 0, "error": error, "read": read}


def stance_table(comments):
    """Rows for each party: how many comments are about it, and their tone. Only comments the model read."""
    rows = []
    for party in PARTIES:
        mine = [c for c in comments if c.get("stance") == party]
        tone = Counter(c["tone"] for c in mine)
        n = len(mine)
        rows.append({"Party": party, "Comments": n, "Positive": tone["positive"], "Neutral": tone["neutral"], "Negative": tone["negative"],
                     "Net tone": round((tone["positive"] - tone["negative"]) / n * 100) if n else 0})
    return rows


def top_issues(comments, n=8):
    counts = Counter(c["issue"] for c in comments if c.get("issue"))
    return counts.most_common(n)


# ----------------------------------------------------------------------
# Facebook and Instagram, and comments from anywhere
# ----------------------------------------------------------------------
GRAPH = "https://graph.facebook.com/v20.0"


def from_table(df, platform="Uploaded"):
    """Comments from a spreadsheet or CSV export. Needs a 'text' column; 'author', 'date' and 'likes' are used when present.
    Column names are matched loosely (message, comment, username, created_time and so on)."""
    names = {str(c).strip().lower(): c for c in df.columns}

    def col(*options):
        return next((names[o] for o in options if o in names), None)

    text_col = col("text", "comment", "message", "comment_text", "content", "body")
    if not text_col:
        return []
    author_col = col("author", "username", "user", "name", "from", "author_name")
    date_col = col("date", "published", "created_time", "timestamp", "created_at", "time")
    likes_col = col("likes", "like_count", "likecount", "reactions")
    out = []
    for _, row in df.iterrows():
        text = str(row[text_col]).strip()
        if not text or text.lower() == "nan":
            continue
        when = ""
        if date_col and str(row[date_col]) not in ("", "nan", "NaT"):
            try:
                import pandas as pd
                when = pd.to_datetime(row[date_col], utc=True).isoformat()
            except Exception:
                when = ""
        try:
            likes = int(float(row[likes_col])) if likes_col and str(row[likes_col]) not in ("", "nan") else 0
        except (TypeError, ValueError):
            likes = 0
        author = str(row[author_col]).strip() if author_col else ""
        out.append({"video": platform, "author": "" if author == "nan" else author, "channel_id": None, "text": text,
                    "published": when, "likes": likes})
    return out


def _graph(path, token, params, timeout=15):
    try:
        resp = requests.get(f"{GRAPH}/{path}", params={**params, "access_token": token}, timeout=timeout)
        if resp.status_code >= 400:
            msg = (resp.json().get("error") or {}).get("message", f"HTTP {resp.status_code}")
            return None, msg
        return resp.json(), None
    except Exception as exc:
        return None, live_pulse._reason(exc)


def fetch_facebook_comments(post_id, token, max_comments=300):
    """Comments on a post of a Facebook Page you manage. Meta only returns them to an app and token with access to that Page
    (pages_read_engagement); comments on other people's pages need Meta's app review and are not available this way."""
    out, url_path, params = [], f"{post_id}/comments", {"fields": "message,created_time,like_count,from", "limit": 100, "filter": "toplevel"}
    while len(out) < max_comments:
        data, error = _graph(url_path, token, params)
        if data is None:
            return {"ok": bool(out), "error": error, "comments": out}
        for c in data.get("data", []):
            who = c.get("from") or {}
            out.append({"video": f"Facebook {post_id}", "author": who.get("name", ""), "channel_id": who.get("id"), "text": (c.get("message") or "").strip(),
                        "published": c.get("created_time", ""), "likes": int(c.get("like_count", 0) or 0)})
        after = ((data.get("paging") or {}).get("cursors") or {}).get("after")
        if not (data.get("paging") or {}).get("next") or not after:
            break
        params = {**params, "after": after}
    return {"ok": True, "error": None, "comments": [c for c in out if c["text"]]}


def fetch_instagram_comments(media_id, token, max_comments=300):
    """Comments on a post of an Instagram professional account you own, through the Instagram Graph API."""
    out, params = [], {"fields": "text,timestamp,like_count,username", "limit": 100}
    path = f"{media_id}/comments"
    while len(out) < max_comments:
        data, error = _graph(path, token, params)
        if data is None:
            return {"ok": bool(out), "error": error, "comments": out}
        for c in data.get("data", []):
            out.append({"video": f"Instagram {media_id}", "author": c.get("username", ""), "channel_id": None, "text": (c.get("text") or "").strip(),
                        "published": c.get("timestamp", ""), "likes": int(c.get("like_count", 0) or 0)})
        after = ((data.get("paging") or {}).get("cursors") or {}).get("after")
        if not (data.get("paging") or {}).get("next") or not after:
            break
        params = {**params, "after": after}
    return {"ok": True, "error": None, "comments": [c for c in out if c["text"]]}


# ----------------------------------------------------------------------
# Ranking
# ----------------------------------------------------------------------
def top_comments(comments, n=15, tier="Likely organic"):
    """The most-liked comments among those that look organic, most liked first."""
    pool = [c for c in comments if c.get("tier") == tier]
    return sorted(pool, key=lambda c: (-c["likes"], -c["score"]))[:n]


def top_by_stance(comments, per=3):
    """For each party, its best-liked likely-organic comments: what supporters and critics are saying about it."""
    out = {}
    for party in PARTIES:
        pool = [c for c in comments if c.get("stance") == party and c.get("tier") == "Likely organic"]
        out[party] = {tone: sorted([c for c in pool if c["tone"] == tone], key=lambda c: -c["likes"])[:per] for tone in ("positive", "negative")}
    return out


def by_source(comments):
    """Per video or post: how many comments, and the share that look organic."""
    rows = {}
    for c in comments:
        r = rows.setdefault(c["video"], {"Source": c["video"], "Comments": 0, "organic": 0, "Likes": 0})
        r["Comments"] += 1
        r["organic"] += c["tier"] == "Likely organic"
        r["Likes"] += c["likes"]
    out = [{"Source": r["Source"], "Comments": r["Comments"], "Share organic": f"{r['organic'] / r['Comments'] * 100:.0f}%", "Likes": r["Likes"]} for r in rows.values()]
    return sorted(out, key=lambda r: -r["Comments"])
