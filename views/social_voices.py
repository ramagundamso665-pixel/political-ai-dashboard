import pandas as pd
import streamlit as st

import charts
import live_pulse
import social_voices as sv
from components import empty_state, fact_card, section
from config import SOURCE_METADATA, is_valid_api_key

TITLE = "Social Voices"

MAX_VIDEOS = 5
MAX_COMMENTS = 300
MAX_SENTIMENT = 900


def _keys():
    yt = st.secrets.get("YOUTUBE_API_KEY", None) if hasattr(st, "secrets") else None
    meta = st.secrets.get("META_ACCESS_TOKEN", None) if hasattr(st, "secrets") else None
    return yt, meta


def _gather(vids, yt_key):
    comments, notes = [], []
    for vid in vids:
        got = sv.fetch_comments(vid, yt_key, MAX_COMMENTS)
        comments += got["comments"]
        if got["error"]:
            notes.append(f"{vid}: {got['error']}")
    channels = sv.fetch_channels([c["channel_id"] for c in comments], yt_key)
    return comments, channels, notes


def _analyse(vids, titles, yt_key, openai_key, prefetched=None):
    if prefetched is not None:
        comments, channels, notes = prefetched
    else:
        comments, channels, notes = _gather(vids, yt_key)
    if not comments:
        return {"error": "No comments could be read. " + " ".join(notes), "comments": []}
    comments, clusters = sv.score(comments, channels)
    sentiment = {"ok": False, "error": "no OpenAI key set", "read": 0}
    if is_valid_api_key(openai_key):
        sentiment = sv.read_sentiment(comments[:MAX_SENTIMENT], openai_key)
    return {"error": None, "notes": notes, "comments": comments, "clusters": clusters, "sentiment": sentiment,
            "channels_found": len(channels), "titles": titles}


MODES = ["YouTube: search", "YouTube: paste links", "Facebook or Instagram (your own page)", "Upload comments (any platform)"]


def _pick_videos(yt_key):
    mode = st.radio("Where the comments are", MODES, key="sv_mode")
    if mode == MODES[1]:
        text = st.text_area("One YouTube link (or video ID) per line", height=90, key="sv_links")
        vids = [v for v in (sv.video_id(line) for line in text.splitlines()) if v][:MAX_VIDEOS]
        return mode, vids, {v: v for v in vids}
    if mode == MODES[0]:
        query = st.text_input("Search for", value="Jubilee Hills", key="sv_query")
        found = st.session_state.get("sv_found", {}).get(query)
        if st.button("Find videos", key="sv_find"):
            res = live_pulse.fetch_youtube_mentions(query, yt_key, max_results=8, days=90)
            if res["ok"]:
                st.session_state.setdefault("sv_found", {})[query] = res["videos"]
                found = res["videos"]
            else:
                st.warning(f"YouTube search failed: {res['error']}.")
        if not found:
            return mode, [], {}
        labels = {v["url"]: f"{v['title'][:80]}  ({v['channel']})" for v in found}
        chosen = st.multiselect(f"Choose up to {MAX_VIDEOS} videos", list(labels), format_func=labels.get, default=list(labels)[:3], max_selections=MAX_VIDEOS, key="sv_chosen")
        vids = [sv.video_id(u) for u in chosen]
        return mode, vids, {sv.video_id(u): labels[u] for u in chosen}
    return mode, [], {}


def _meta_inputs(meta_token):
    """Facebook posts and Instagram media of an account the campaign manages, read through Meta's Graph API."""
    if not meta_token:
        st.info(
            "This reads comments on posts of a Facebook Page or Instagram professional account **you manage**. Add `META_ACCESS_TOKEN` to the app's "
            "secrets: a Page or system-user token from your Meta app with `pages_read_engagement` (Facebook) and `instagram_manage_comments` (Instagram). "
            "Meta does not give comments on other people's pages to ordinary apps. For those, use Upload comments, or paste them in."
        )
        return None
    c1, c2 = st.columns(2)
    fb = c1.text_area("Facebook post IDs (one per line, like 1234567890_9876543210)", height=90, key="sv_fb")
    ig = c2.text_area("Instagram media IDs (one per line)", height=90, key="sv_ig")
    return [x.strip() for x in fb.splitlines() if x.strip()][:MAX_VIDEOS], [x.strip() for x in ig.splitlines() if x.strip()][:MAX_VIDEOS]


def _upload_inputs():
    up = st.file_uploader("A CSV or Excel export of comments", type=["csv", "xlsx"], key="sv_upload")
    st.caption(
        "Needs a column named text, comment or message. Optional: author, date, likes. Meta Business Suite and most social tools can export "
        "comments this way, or paste them into a spreadsheet."
    )
    if not up:
        return None
    df = pd.read_csv(up) if up.name.lower().endswith(".csv") else pd.read_excel(up)
    comments = sv.from_table(df, f"Upload: {up.name}")[: MAX_COMMENTS * MAX_VIDEOS]
    if not comments:
        st.warning("No column named text, comment or message was found, or it was empty.")
        return None
    return comments


def _top_voices(result):
    comments = result["comments"]
    st.markdown("**Most-liked comments that look organic**")
    top = sv.top_comments(comments)
    if not top:
        empty_state("No comment looks organic yet.")
    else:
        st.dataframe(pd.DataFrame({
            "Rank": range(1, len(top) + 1), "Likes": [c["likes"] for c in top], "Comment": [c["text"][:220] for c in top],
            "About": [c.get("stance", "") for c in top], "Tone": [c.get("tone", "") for c in top], "Source": [c["video"] for c in top],
        }), hide_index=True, width="stretch")
    if any("stance" in c for c in comments):
        by = sv.top_by_stance(comments)
        party = st.selectbox("See what people say about", list(sv.PARTIES), key="sv_top_party")
        c1, c2 = st.columns(2)
        for col, tone, title in ((c1, "positive", "In favour"), (c2, "negative", "Against")):
            col.markdown(f"**{title}**")
            rows = by[party][tone]
            if not rows:
                col.caption("None among the organic comments read.")
            for c in rows:
                col.markdown(f"> {c['text'][:200]}  \n> *{c['likes']} likes*")
    st.markdown("**By video or post**")
    st.dataframe(pd.DataFrame(sv.by_source(comments)), hide_index=True, width="stretch")


def _show(result):
    comments = result["comments"]
    df = pd.DataFrame(comments)
    tiers = df["tier"].value_counts().to_dict()
    n = len(df)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Comments read", n)
    c2.metric("Likely organic", f"{tiers.get('Likely organic', 0) / n * 100:.0f}%")
    c3.metric("Uncertain", f"{tiers.get('Uncertain', 0) / n * 100:.0f}%")
    c4.metric("Flagged", f"{tiers.get('Flagged', 0) / n * 100:.0f}%")
    for note in result.get("notes", []):
        st.caption(note)

    tabs = st.tabs(["Organic or not", "Sentiment", "Top voices", "Copied messages", "All comments"])
    with tabs[0]:
        st.plotly_chart(charts.organic_split(tiers), width="stretch")
        st.caption(
            "The score starts at 100 and loses points for: a channel under 30 days old when it commented (35) or under 6 months (15); "
            "the same message from 3 or more accounts (50), or from 2 (20); one account repeating itself (25); near-identical comments "
            "in a burst of 5 or more within 10 minutes (15). Below 40 is flagged, 40 to 69 uncertain. Short slogans such as "
            "'Jai Congress' never count as copies, because real people post them. These are flags to look at, not proof."
        )
    with tabs[1]:
        sent = result["sentiment"]
        if not sent["ok"]:
            st.info(f"Sentiment was not read: {sent['error']}.")
        else:
            read = [c for c in comments if "stance" in c]
            organic = [c for c in read if c["tier"] == "Likely organic"]
            all_rows, org_rows = sv.stance_table(read), sv.stance_table(organic)
            st.caption(f"{len(read)} comments read for sentiment, {len(organic)} of them likely organic.")
            st.plotly_chart(charts.stance_tone(all_rows, org_rows), width="stretch")
            left, right = st.columns(2)
            left.markdown("**All comments**")
            left.dataframe(pd.DataFrame(all_rows), hide_index=True, width="stretch")
            right.markdown("**Likely organic only**")
            right.dataframe(pd.DataFrame(org_rows), hide_index=True, width="stretch")
            issues = sv.top_issues(organic)
            if issues:
                st.markdown("**Issues people raise (likely organic comments)**")
                st.dataframe(pd.DataFrame(issues, columns=["Issue", "Comments"]), hide_index=True, width="stretch")
            st.caption(
                "'Net tone' is positive minus negative comments about a party, as a share of the comments about it. A party with few "
                "comments about it has a noisy number. Comments are a sample of who chooses to comment on these videos, not of voters."
            )
    with tabs[2]:
        _top_voices(result)
    with tabs[3]:
        if not result["clusters"]:
            empty_state("No message was posted more than once (short slogans are ignored).")
        else:
            st.dataframe(pd.DataFrame(result["clusters"]).rename(columns={"text": "Message", "comments": "Times posted", "accounts": "Accounts", "burst": "In a burst"}),
                         hide_index=True, width="stretch")
    with tabs[4]:
        show = df[[c for c in ("score", "tier", "author", "text", "likes", "published", "flags", "stance", "tone", "issue") if c in df.columns]]
        st.dataframe(show.sort_values("score"), hide_index=True, width="stretch")
        st.download_button("Download as CSV", show.to_csv(index=False).encode(), "youtube_comments_scored.csv", "text/csv")


def render(ctx, sidebar):
    section(
        "Social voices",
        "What people say under political YouTube videos, with the copied and brand-new-account comments set apart so they don't drown the real ones.",
    )
    yt_key, meta_token = _keys()
    have_yt = bool(yt_key and str(yt_key).isascii())
    if not have_yt:
        st.info("YouTube is off until YOUTUBE_API_KEY is in the secrets. Uploading comments and the Facebook or Instagram option still work.")

    mode, vids, titles = _pick_videos(yt_key)
    pre, ready = None, bool(vids)
    if mode == MODES[2]:
        ids = _meta_inputs(meta_token)
        ready = bool(ids and (ids[0] or ids[1]))
        if ready:
            def pre():
                comments, notes = [], []
                for pid in ids[0]:
                    got = sv.fetch_facebook_comments(pid, meta_token, MAX_COMMENTS)
                    comments += got["comments"]
                    notes += [f"Facebook {pid}: {got['error']}"] if got["error"] else []
                for mid in ids[1]:
                    got = sv.fetch_instagram_comments(mid, meta_token, MAX_COMMENTS)
                    comments += got["comments"]
                    notes += [f"Instagram {mid}: {got['error']}"] if got["error"] else []
                return comments, {}, notes
    elif mode == MODES[3]:
        uploaded = _upload_inputs()
        ready = bool(uploaded)
        if ready:
            def pre():
                return uploaded, {}, []
    if st.button("Analyse comments", type="primary", disabled=not ready, key="sv_go"):
        with st.spinner("Reading comments and sentiment (about a minute)"):
            st.session_state["sv_result"] = _analyse(vids, titles, yt_key, ctx.api_key, prefetched=pre() if pre else None)
    result = st.session_state.get("sv_result")
    if result:
        if result["error"]:
            st.warning(result["error"])
        else:
            _show(result)

    st.caption(
        "Facebook and Instagram: comments on pages and accounts you manage can be read with a Meta token; comments on other people's pages "
        "are only open to apps that pass Meta's review, so paste or upload those. X (Twitter) charges per post read and is not connected. "
        "Comments from uploads have no account age, so they are scored on copied and bursty text only."
    )
    fact_card(
        "Comments are public and read through YouTube's official API. Organic likelihood is a heuristic from visible signals, "
        "and sentiment is read by a language model, so both are guides to look at, not measurements of the electorate.",
        SOURCE_METADATA["youtube_comments"]["name"],
        SOURCE_METADATA["youtube_comments"]["type"],
        "low",
    )
    ctx.logger.log_analysis("social_voices", ["youtube_comments"], "analysed YouTube comments")
