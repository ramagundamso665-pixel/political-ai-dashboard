"""Opponent Watch: what a rival says, spends and gets, from official public sources only.

Four feeds, each an API or a file its publisher releases for machine use (no scraping):
- News: Google News RSS (English and Telugu editions), headline tone read by a language model.
- YouTube: the rival's own channel (uploads, views, how often they post) and videos other channels make
  about them, through the YouTube Data API.
- Google political ads: Google's Political Advertising transparency bundle, the daily file Google publishes
  for download. Only the three small tables inside the 300 MB zip are read, with HTTP range requests.
- Meta political ads: the Meta Ad Library API, which covers political and issue ads in India. It needs an
  access token from someone who has confirmed their identity with Meta.

Plus the rival's own record from the election results already in the app (2014, 2018, 2023, and for
Jubilee Hills the booth sheet). Every fetch returns {"ok", "error", ...} and never raises, as in live_pulse.
"""

import csv
import io
import re
import zipfile
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import pandas as pd
import requests

import live_pulse

GOOGLE_ADS_BUNDLE = "https://storage.googleapis.com/political-csv/google-political-ads-transparency-bundle.zip"
META_ADS_API = "https://graph.facebook.com/v20.0/ads_archive"
YT_CHANNELS_API = "https://www.googleapis.com/youtube/v3/channels"
YT_PLAYLIST_API = "https://www.googleapis.com/youtube/v3/playlistItems"
YT_VIDEOS_API = "https://www.googleapis.com/youtube/v3/videos"

# how each party's own advertiser accounts are named in the ad libraries
PARTY_AD_NAMES = {
    "BRS": ["bharat rashtra samithi", "telangana rashtra samithi", "brs party"],
    "INC": ["indian national congress", "telangana congress", "telangana pradesh congress", "inc telangana"],
    "BJP": ["bharatiya janata party", "bjp telangana"],
    "AIMIM": ["all india majlis", "aimim"],
}


# ----------------------------------------------------------------------
# Google political ads
# ----------------------------------------------------------------------
class _RangeFile(io.RawIOBase):
    """A remote file read on demand with HTTP Range requests, so zipfile can pull one member out of
    Google's 300 MB bundle while downloading only that member's bytes (a few MB)."""

    def __init__(self, url, timeout=30):
        self.url, self.timeout, self.pos = url, timeout, 0
        head = requests.head(url, timeout=timeout)
        head.raise_for_status()
        self.size = int(head.headers["content-length"])
        self.updated = head.headers.get("last-modified", "")

    def readable(self):
        return True

    def seekable(self):
        return True

    def tell(self):
        return self.pos

    def seek(self, offset, whence=0):
        self.pos = offset if whence == 0 else (self.pos + offset if whence == 1 else self.size + offset)
        return self.pos

    def readinto(self, buf):
        if self.pos >= self.size:
            return 0
        end = min(self.size, self.pos + len(buf)) - 1
        resp = requests.get(self.url, headers={"Range": f"bytes={self.pos}-{end}"}, timeout=self.timeout)
        resp.raise_for_status()
        data = resp.content
        buf[: len(data)] = data
        self.pos += len(data)
        return len(data)


def _rows(zf, name):
    with zf.open(name) as fh:
        yield from csv.DictReader(io.TextIOWrapper(fh, encoding="utf-8"))


def fetch_google_ads():
    """{'ok', 'error', 'updated', 'advertisers': DataFrame, 'weekly': DataFrame} for every advertiser whose
    election ads ran in India. Spend is in rupees as Google reports it. About 4 MB is downloaded."""
    try:
        remote = _RangeFile(GOOGLE_ADS_BUNDLE)
        zf = zipfile.ZipFile(io.BufferedReader(remote, 1 << 20))
        advertisers = [
            {"Advertiser_ID": r["Advertiser_ID"], "Advertiser": r["Advertiser_Name"], "Ads": int(r["Total_Creatives"] or 0),
             "Spend_INR": int(r["Spend_INR"] or 0)}
            for r in _rows(zf, "google-political-ads-advertiser-stats.csv")
            if "IN" in (r["Regions"] or "").split(",")
        ]
        ids = {a["Advertiser_ID"] for a in advertisers}
        weekly = [
            {"Advertiser_ID": r["Advertiser_ID"], "Week": r["Week_Start_Date"], "Spend_INR": int(r["Spend_INR"] or 0)}
            for r in _rows(zf, "google-political-ads-advertiser-weekly-spend.csv")
            if r["Advertiser_ID"] in ids and r["Spend_INR"] not in ("", "0")
        ]
    except Exception as exc:
        return {"ok": False, "error": live_pulse._reason(exc), "advertisers": pd.DataFrame(), "weekly": pd.DataFrame(), "updated": ""}
    adv = pd.DataFrame(advertisers).sort_values("Spend_INR", ascending=False)
    wk = pd.DataFrame(weekly)
    if not wk.empty:
        wk["Week"] = pd.to_datetime(wk["Week"])
    return {"ok": True, "error": None, "advertisers": adv, "weekly": wk, "updated": remote.updated}


def match_advertisers(advertisers, terms):
    """Advertisers whose name contains any of the terms (case-insensitive, whole words for short terms)."""
    if advertisers.empty or not terms:
        return advertisers.iloc[0:0]
    parts = [rf"\b{re.escape(t)}\b" if len(t) <= 4 else re.escape(t) for t in terms if t.strip()]
    mask = advertisers["Advertiser"].str.contains("|".join(parts), case=False, regex=True)
    return advertisers[mask]


def spend_summary(weekly, advertiser_ids, today=None):
    """Totals for the chosen advertisers: all-time, the last 30 and 90 days, and the busiest week."""
    wk = weekly[weekly["Advertiser_ID"].isin(advertiser_ids)] if not weekly.empty else weekly
    if wk.empty:
        return {"weeks": wk, "last_30": 0, "last_90": 0, "peak_week": None, "peak": 0, "last_seen": None}
    today = pd.Timestamp(today or datetime.now(timezone.utc).date())
    by_week = wk.groupby("Week", as_index=False)["Spend_INR"].sum().sort_values("Week")
    peak = by_week.loc[by_week["Spend_INR"].idxmax()]
    return {
        "weeks": by_week,
        "last_30": int(by_week[by_week["Week"] >= today - pd.Timedelta(days=30)]["Spend_INR"].sum()),
        "last_90": int(by_week[by_week["Week"] >= today - pd.Timedelta(days=90)]["Spend_INR"].sum()),
        "peak_week": peak["Week"].date(),
        "peak": int(peak["Spend_INR"]),
        "last_seen": by_week["Week"].max().date(),
    }


# ----------------------------------------------------------------------
# Meta political ads
# ----------------------------------------------------------------------
META_FIELDS = ",".join([
    "id", "page_id", "page_name", "bylines", "ad_creative_bodies", "ad_delivery_start_time", "ad_delivery_stop_time",
    "ad_snapshot_url", "spend", "impressions", "currency", "delivery_by_region", "publisher_platforms", "languages",
])


def fetch_meta_ads(token, search=None, page_ids=None, days=90, max_ads=300, timeout=20):
    """Political and issue ads shown in India from the Meta Ad Library API, newest first.
    Search by words (the ad text and page name) or by Facebook page IDs, which is exact."""
    if not token or not str(token).isascii():
        return {"ok": False, "error": "no usable Meta Ad Library token", "ads": []}
    params = {
        "access_token": token, "ad_type": "POLITICAL_AND_ISSUE_ADS", "ad_reached_countries": '["IN"]', "ad_active_status": "ALL",
        "ad_delivery_date_min": (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d"),
        "fields": META_FIELDS, "limit": 100,
    }
    if page_ids:
        params["search_page_ids"] = ",".join(page_ids[:10])
    elif search:
        params["search_terms"] = search
    else:
        return {"ok": False, "error": "give a name or page ID to search for", "ads": []}
    ads, url = [], META_ADS_API
    while url and len(ads) < max_ads:
        try:
            resp = requests.get(url, params=params, timeout=timeout)
            if resp.status_code >= 400:
                msg = (resp.json().get("error") or {}).get("message", f"HTTP {resp.status_code}")
                return {"ok": bool(ads), "error": msg, "ads": ads}
            payload = resp.json()
        except Exception as exc:
            return {"ok": bool(ads), "error": live_pulse._reason(exc), "ads": ads}
        ads += payload.get("data", [])
        url, params = (payload.get("paging") or {}).get("next"), None  # the next link carries every parameter
    return {"ok": True, "error": None, "ads": ads[:max_ads]}


def _bounds(rng):
    rng = rng or {}
    lo = int(rng.get("lower_bound") or 0)
    hi = int(rng.get("upper_bound") or lo)
    return lo, hi


def meta_summary(ads, region="Telangana"):
    """Per page: ads, spend range, the share delivered in the region, and a table of the ads themselves.
    Meta gives spend and reach as ranges, so every total here is a range too."""
    pages = defaultdict(lambda: {"Ads": 0, "Spend min": 0, "Spend max": 0, "In region min": 0.0, "In region max": 0.0})
    rows = []
    for ad in ads:
        lo, hi = _bounds(ad.get("spend"))
        share = sum(float(r.get("percentage") or 0) for r in ad.get("delivery_by_region") or [] if r.get("region") == region)
        name = ad.get("page_name") or ad.get("page_id") or "?"
        p = pages[name]
        p["Ads"] += 1
        p["Spend min"] += lo
        p["Spend max"] += hi
        p["In region min"] += lo * share
        p["In region max"] += hi * share
        imp_lo, imp_hi = _bounds(ad.get("impressions"))
        rows.append({
            "Page": name, "Started": (ad.get("ad_delivery_start_time") or "")[:10], "Stopped": (ad.get("ad_delivery_stop_time") or "")[:10],
            "Spend (Rs)": f"{lo:,}–{hi:,}", "Seen (impressions)": f"{imp_lo:,}–{imp_hi:,}", f"Shown in {region}": f"{share * 100:.0f}%",
            "Paid for by": ad.get("bylines") or "", "Text": " | ".join(ad.get("ad_creative_bodies") or [])[:300],
            "Platforms": ", ".join(ad.get("publisher_platforms") or []), "Link": ad.get("ad_snapshot_url") or "",
        })
    table = [{"Page": k, **{c: round(v) for c, v in p.items()}} for k, p in pages.items()]
    return sorted(table, key=lambda r: -r["Spend max"]), rows


def meta_regions(ads):
    """Spend range by state across all the ads: where the money is going."""
    out = defaultdict(lambda: [0.0, 0.0])
    for ad in ads:
        lo, hi = _bounds(ad.get("spend"))
        for r in ad.get("delivery_by_region") or []:
            pct = float(r.get("percentage") or 0)
            out[r.get("region", "?")][0] += lo * pct
            out[r.get("region", "?")][1] += hi * pct
    return sorted(({"State": k, "Spend min": round(v[0]), "Spend max": round(v[1])} for k, v in out.items()), key=lambda r: -r["Spend max"])


# ----------------------------------------------------------------------
# YouTube: the rival's own channel
# ----------------------------------------------------------------------
CHANNEL_ID = re.compile(r"(UC[A-Za-z0-9_-]{22})")
HANDLE = re.compile(r"@([A-Za-z0-9._-]{3,30})")


def resolve_channel(text, api_key, timeout=10):
    """A channel from a link, an @handle or a UC... ID. Returns {'ok', 'error', 'channel'}."""
    text = (text or "").strip()
    params = {"part": "snippet,statistics,contentDetails", "key": api_key}
    if m := CHANNEL_ID.search(text):
        params["id"] = m.group(1)
    elif m := HANDLE.search(text):
        params["forHandle"] = "@" + m.group(1)
    elif re.fullmatch(r"[A-Za-z0-9._-]{3,30}", text):
        params["forHandle"] = "@" + text
    else:
        return {"ok": False, "error": "give a channel link, an @handle or a channel ID", "channel": None}
    try:
        resp = requests.get(YT_CHANNELS_API, params=params, timeout=timeout)
        resp.raise_for_status()
        items = resp.json().get("items") or []
    except Exception as exc:
        return {"ok": False, "error": live_pulse._reason(exc), "channel": None}
    if not items:
        return {"ok": False, "error": "no channel found for that", "channel": None}
    it = items[0]
    s = it.get("statistics", {})
    return {"ok": True, "error": None, "channel": {
        "id": it["id"], "title": it["snippet"].get("title", ""), "created": it["snippet"].get("publishedAt", "")[:10],
        "subscribers": None if s.get("hiddenSubscriberCount") else int(s.get("subscriberCount", 0) or 0),
        "views": int(s.get("viewCount", 0) or 0), "videos": int(s.get("videoCount", 0) or 0),
        "uploads": (it.get("contentDetails", {}).get("relatedPlaylists") or {}).get("uploads"),
    }}


def search_channels(query, api_key, n=6, timeout=10):
    """Channels matching a name, most subscribers first. Fan and copycat channels share the official
    names ("BRS Party OFFICIAL" with 6 subscribers), so the person picks; subscribers are the usual tell.
    Search costs 100 of the 10,000 daily quota units."""
    try:
        resp = requests.get(live_pulse.YOUTUBE_SEARCH_API, params={"part": "snippet", "q": query, "type": "channel", "maxResults": n, "regionCode": "IN", "key": api_key}, timeout=timeout)
        resp.raise_for_status()
        ids = [i["id"]["channelId"] for i in resp.json().get("items", []) if i.get("id", {}).get("channelId")]
        if not ids:
            return {"ok": True, "error": None, "channels": []}
        resp = requests.get(YT_CHANNELS_API, params={"part": "snippet,statistics", "id": ",".join(ids), "key": api_key}, timeout=timeout)
        resp.raise_for_status()
    except Exception as exc:
        return {"ok": False, "error": live_pulse._reason(exc), "channels": []}
    found = [{
        "id": it["id"], "title": it["snippet"].get("title", ""), "handle": it["snippet"].get("customUrl", ""),
        "subscribers": int(it.get("statistics", {}).get("subscriberCount", 0) or 0),
    } for it in resp.json().get("items", [])]
    return {"ok": True, "error": None, "channels": sorted(found, key=lambda c: -c["subscribers"])}


def channel_uploads(uploads_playlist, api_key, max_videos=200, timeout=10):
    """The channel's latest uploads with views, likes and comment counts, 50 per call (1 quota unit each).
    A party channel can post 15 videos a day, so 50 alone may not reach back a month."""
    ids, token = [], None
    try:
        while len(ids) < max_videos:
            params = {"part": "contentDetails", "playlistId": uploads_playlist, "maxResults": 50, "key": api_key}
            if token:
                params["pageToken"] = token
            resp = requests.get(YT_PLAYLIST_API, params=params, timeout=timeout)
            resp.raise_for_status()
            page = resp.json()
            ids += [i["contentDetails"]["videoId"] for i in page.get("items", [])]
            token = page.get("nextPageToken")
            if not token:
                break
        items = []
        for i in range(0, len(ids), 50):
            resp = requests.get(YT_VIDEOS_API, params={"part": "snippet,statistics", "id": ",".join(ids[i:i + 50]), "key": api_key}, timeout=timeout)
            resp.raise_for_status()
            items += resp.json().get("items", [])
    except Exception as exc:
        return {"ok": False, "error": live_pulse._reason(exc), "videos": []}
    videos = []
    for it in items:
        s = it.get("statistics", {})
        videos.append({
            "Published": it["snippet"].get("publishedAt", "")[:10], "Title": it["snippet"].get("title", ""),
            "Views": int(s.get("viewCount", 0) or 0), "Likes": int(s.get("likeCount", 0) or 0), "Comments": int(s.get("commentCount", 0) or 0),
            "Link": f"https://www.youtube.com/watch?v={it['id']}",
        })
    return {"ok": True, "error": None, "videos": sorted(videos, key=lambda v: v["Published"], reverse=True)}


def upload_summary(videos, today=None):
    """How often they post and how it lands: uploads and views in the last 30 days against the 30 before."""
    today = today or datetime.now(timezone.utc).date()
    df = pd.DataFrame(videos)
    if df.empty:
        return {}
    df["date"] = pd.to_datetime(df["Published"]).dt.date
    recent = df[df["date"] >= today - timedelta(days=30)]
    before = df[(df["date"] < today - timedelta(days=30)) & (df["date"] >= today - timedelta(days=60))]
    oldest = df["date"].min()
    return {
        "uploads_30": len(recent), "uploads_prev_30": len(before),
        # when even the oldest video read is recent, the counts are floors, not totals
        "partial_30": oldest >= today - timedelta(days=30), "partial_60": oldest >= today - timedelta(days=60),
        "median_views_30": int(recent["Views"].median()) if len(recent) else None,
        "median_views_prev_30": int(before["Views"].median()) if len(before) else None,
        "top": df.sort_values("Views", ascending=False).head(5).to_dict("records"),
        "oldest_read": str(df["date"].min()),
    }


# ----------------------------------------------------------------------
# News
# ----------------------------------------------------------------------
def news_names(name):
    """The ballot name and the shorter one the press uses: ballot papers carry the family name first
    ("Vallala Naveen Yadav"), headlines usually drop it ("Naveen Yadav")."""
    words = [w for w in re.split(r"\s+", name.strip()) if w]
    words = [w for w in words if not re.fullmatch(r"(dr|smt|sri|shri)\.?", w, re.I)]
    names = [" ".join(words)]
    if len(words) >= 3:
        names.append(" ".join(words[1:]))
    return names


def fetch_news(name, name_te=None, place=None):
    """English and (when a Telugu spelling is given) Telugu Google News for the last 7 days, widened to 30 if thin.
    A bare name drags in namesakes ("Naveen Yadav" returned film gossip), so the English search also needs the
    place, the seat or 'Telangana', somewhere in the article."""
    names = news_names(name)
    who = " OR ".join(f'"{n}"' for n in names)
    who = f"({who})" if len(names) > 1 else who
    query = f'{who} "{place}"' if place else f"{who} Telangana"
    result = live_pulse.fetch_recent_news(query, lang="en")
    if name_te:
        result = live_pulse.merge_news(result, live_pulse.fetch_recent_news(f'"{name_te}"', lang="te"))
    if result["ok"]:
        result["articles"] = live_pulse.latest_first(result["articles"])
    return result


def news_tone(name, articles, api_key, n=40):
    """Headline tone toward the rival, via the same model call Live Pulse uses. Labels line up with articles[:n]."""
    heads = [a["title"] for a in articles[:n]]
    return live_pulse.classify_headline_mood(name, heads, api_key)


# ----------------------------------------------------------------------
# The rival's record, from the results already in the app
# ----------------------------------------------------------------------
def _name_key(name):
    """Letters of the longest words only, so 'Dr. Palvai Harish Babu' and 'Palvai Harish Babu' match."""
    words = [w for w in re.findall(r"[a-z]+", str(name).lower()) if len(w) > 2 and w not in {"dr", "smt", "sri", "shri"}]
    return set(words)


def electoral_record(name, years):
    """Every contest the name appears in: {year: candidates DataFrame}. A match needs two shared name words
    (or the only word, for one-word names), so common first names alone never match. Namesakes do match:
    parties sometimes field a same-named independent to split a rival's vote, so the party column matters."""
    key = _name_key(name)
    if not key:
        return pd.DataFrame()
    need = min(2, len(key))
    rows = []
    for year, cands in years.items():
        for _, r in cands.iterrows():
            if len(key & _name_key(r["candidate"])) >= need:
                rows.append({"Year": year, "Seat": r["seat"], "Party": r["party"], "Rank": int(r["rank"]), "Votes": int(r["votes_total"]), "Vote %": r["pct"]})
    return pd.DataFrame(rows)


def party_trend(years, seat, party):
    """The party's vote share in one seat across the years on file."""
    out = []
    for year, cands in years.items():
        rows = cands[(cands["seat"] == seat) & (cands["party"] == party)]
        if not rows.empty:
            out.append({"Year": year, "Vote %": float(rows["pct"].sum()), "Rank": int(rows["rank"].min())})
    return pd.DataFrame(out)


def booth_battleground(booths, rival, us, n=12):
    """For a seat with booth results: where the rival is strongest, where they are weakest, and the close
    booths where a small swing changes who leads. Shares are of each booth's valid votes."""
    b = booths.copy()
    for p in (rival, us):
        b[f"{p} %"] = (b[p] / b["valid_votes"] * 100).round(1)
    b["Lead (rival − us)"] = b[f"{rival} %"] - b[f"{us} %"]
    b["Votes to flip"] = ((b[rival] - b[us]).abs() // 2 + 1).where(b[rival] >= b[us], 0)
    cols = ["booth", f"{rival} %", f"{us} %", "Lead (rival − us)", "Votes to flip", "valid_votes"]
    ren = {"booth": "Booth", "valid_votes": "Valid votes"}
    strong = b.sort_values("Lead (rival − us)", ascending=False).head(n)[cols].rename(columns=ren)
    weak = b.sort_values("Lead (rival − us)").head(n)[cols].rename(columns=ren)
    close = b[(b["Lead (rival − us)"] > 0) & (b["Lead (rival − us)"] <= 5)].sort_values("Votes to flip")[cols].rename(columns=ren)
    counts = {"rival_leads": int((b[rival] > b[us]).sum()), "we_lead": int((b[us] > b[rival]).sum()), "booths": len(b),
              "close": len(close), "votes_to_flip_close": int(close["Votes to flip"].sum())}
    return strong, weak, close, counts


# ----------------------------------------------------------------------
# For Ask AI
# ----------------------------------------------------------------------
def context_text(snapshot):
    """A few plain lines from the last Opponent Watch run, for Ask AI. Empty when nothing was run."""
    if not snapshot:
        return ""
    lines = [f"OPPONENT WATCH (live public feeds, read on {snapshot['when']}; rival: {snapshot['rival']} of {snapshot['party']}):"]
    for line in snapshot.get("lines", []):
        lines.append(f"- {line}")
    return "\n".join(lines)
