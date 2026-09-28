"""Watching rivals' and the leader's public social accounts through official APIs only.

Instagram: Meta's Business Discovery API lets an Instagram professional account (yours) read another business or creator
account's public profile and recent posts: captions, likes, comment counts, links. Most politicians' accounts are
business or creator accounts. Needs META_ACCESS_TOKEN (a token with instagram_basic and pages_read_engagement) and
INSTAGRAM_USER_ID (the ID of your own Instagram professional account, linked to a Facebook Page).

Not here, on purpose: other people's Facebook pages (Meta only opens them to apps that pass its "Page Public Content
Access" review), X (paid API), and downloading anyone's videos (YouTube's and Meta's terms forbid it; to check a clip,
upload a copy the office received or recorded).
"""

import requests

import live_pulse

GRAPH = "https://graph.facebook.com/v20.0"
FIELDS = ("username,name,followers_count,media_count,"
          "media.limit(25){caption,like_count,comments_count,media_type,media_product_type,permalink,timestamp}")


def instagram_account(handle, token, my_ig_user_id, timeout=20):
    """{'ok', 'error', 'profile', 'posts'} for a public business/creator account, newest posts first."""
    handle = handle.strip().lstrip("@")
    if not (token and my_ig_user_id):
        return {"ok": False, "error": "needs META_ACCESS_TOKEN and INSTAGRAM_USER_ID", "profile": None, "posts": []}
    try:
        r = requests.get(f"{GRAPH}/{my_ig_user_id}", params={"fields": f"business_discovery.username({handle}){{{FIELDS}}}", "access_token": token},
                         timeout=timeout)
        if r.status_code >= 400:
            msg = (r.json().get("error") or {}).get("message", f"HTTP {r.status_code}")
            if "not a business" in msg.lower() or "cannot be found" in msg.lower():
                msg += " (only business and creator accounts can be read this way)"
            return {"ok": False, "error": msg, "profile": None, "posts": []}
        bd = r.json().get("business_discovery") or {}
    except Exception as exc:
        return {"ok": False, "error": live_pulse._reason(exc), "profile": None, "posts": []}
    posts = [{
        "Posted": (m.get("timestamp") or "")[:10], "Type": m.get("media_product_type") or m.get("media_type"),
        "Likes": m.get("like_count"), "Comments": m.get("comments_count"), "Caption": (m.get("caption") or "")[:220], "Link": m.get("permalink"),
    } for m in (bd.get("media") or {}).get("data", [])]
    profile = {"username": bd.get("username"), "name": bd.get("name"), "followers": bd.get("followers_count"), "posts": bd.get("media_count")}
    return {"ok": True, "error": None, "profile": profile, "posts": posts}


def engagement_summary(posts, days=30):
    """Posts in the last `days`, their median likes, and the best-performing post."""
    import pandas as pd

    df = pd.DataFrame(posts)
    if df.empty:
        return {}
    df["Posted"] = pd.to_datetime(df["Posted"], errors="coerce")
    recent = df[df["Posted"] >= pd.Timestamp.now() - pd.Timedelta(days=days)]
    top = df.sort_values("Likes", ascending=False).iloc[0].to_dict() if df["Likes"].notna().any() else None
    return {"posts_recent": len(recent), "median_likes": int(recent["Likes"].median()) if len(recent) and recent["Likes"].notna().any() else None,
            "top": top, "reels_share": round(float((df["Type"] == "REELS").mean()) * 100) if "Type" in df else None}
