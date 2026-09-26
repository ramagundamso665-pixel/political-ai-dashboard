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
    return yt


def _gather(vids, yt_key):
    comments, notes = [], []
    for vid in vids:
        got = sv.fetch_comments(vid, yt_key, MAX_COMMENTS)
        comments += got["comments"]
        if got["error"]:
            notes.append(f"{vid}: {got['error']}")
    channels = sv.fetch_channels([c["channel_id"] for c in comments], yt_key)
    return comments, channels, notes


def _analyse(vids, titles, yt_key, openai_key):
    comments, channels, notes = _gather(vids, yt_key)
    if not comments:
        return {"error": "No comments could be read. " + " ".join(notes), "comments": []}
    comments, clusters = sv.score(comments, channels)
    sentiment = {"ok": False, "error": "no OpenAI key set", "read": 0}
    if is_valid_api_key(openai_key):
        sentiment = sv.read_sentiment(comments[:MAX_SENTIMENT], openai_key)
    return {"error": None, "notes": notes, "comments": comments, "clusters": clusters, "sentiment": sentiment,
            "channels_found": len(channels), "titles": titles}


def _pick_videos(yt_key):
    mode = st.radio("Which videos", ["Search YouTube", "Paste video links"], horizontal=True, key="sv_mode")
    if mode == "Paste video links":
        text = st.text_area("One YouTube link (or video ID) per line", height=90, key="sv_links")
        vids = [v for v in (sv.video_id(line) for line in text.splitlines()) if v][:MAX_VIDEOS]
        return vids, {v: v for v in vids}
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
        return [], {}
    labels = {v["url"]: f"{v['title'][:80]}  ({v['channel']})" for v in found}
    chosen = st.multiselect(f"Choose up to {MAX_VIDEOS} videos", list(labels), format_func=labels.get, default=list(labels)[:3], max_selections=MAX_VIDEOS, key="sv_chosen")
    vids = [sv.video_id(u) for u in chosen]
    return vids, {sv.video_id(u): labels[u] for u in chosen}


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

    tabs = st.tabs(["Organic or not", "Sentiment", "Copied messages", "All comments"])
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
        if not result["clusters"]:
            empty_state("No message was posted more than once (short slogans are ignored).")
        else:
            st.dataframe(pd.DataFrame(result["clusters"]).rename(columns={"text": "Message", "comments": "Times posted", "accounts": "Accounts", "burst": "In a burst"}),
                         hide_index=True, width="stretch")
    with tabs[3]:
        show = df[[c for c in ("score", "tier", "author", "text", "likes", "published", "flags", "stance", "tone", "issue") if c in df.columns]]
        st.dataframe(show.sort_values("score"), hide_index=True, width="stretch")
        st.download_button("Download as CSV", show.to_csv(index=False).encode(), "youtube_comments_scored.csv", "text/csv")


def render(ctx, sidebar):
    section(
        "Social voices",
        "What people say under political YouTube videos, with the copied and brand-new-account comments set apart so they don't drown the real ones.",
    )
    yt_key = _keys()
    if not (yt_key and str(yt_key).isascii()):
        st.info("Add YOUTUBE_API_KEY to `.streamlit/secrets.toml` (or the host's secrets) to enable this page.")
        return

    vids, titles = _pick_videos(yt_key)
    if st.button("Analyse comments", type="primary", disabled=not vids, key="sv_go"):
        with st.spinner("Reading comments, looking up the commenters, and reading sentiment (about a minute)"):
            st.session_state["sv_result"] = _analyse(vids, titles, yt_key, ctx.api_key)
    result = st.session_state.get("sv_result")
    if result:
        if result["error"]:
            st.warning(result["error"])
        else:
            _show(result)

    st.caption(
        "Not included: X (Twitter) now charges per post read, and Facebook only opens public Page comments to apps that pass Meta's "
        "review. Both can be added here through the same scoring."
    )
    fact_card(
        "Comments are public and read through YouTube's official API. Organic likelihood is a heuristic from visible signals, "
        "and sentiment is read by a language model, so both are guides to look at, not measurements of the electorate.",
        SOURCE_METADATA["youtube_comments"]["name"],
        SOURCE_METADATA["youtube_comments"]["type"],
        "low",
    )
    ctx.logger.log_analysis("social_voices", ["youtube_comments"], "analysed YouTube comments")
