import streamlit as st

import charts
import live_pulse
from components import empty_state, fact_card, section
from config import CANDIDATES, PARTY_LABELS, PULSE_KEYWORD, SOURCE_METADATA, is_valid_api_key

TITLE = "Live Pulse"


@st.cache_data(ttl=3600, show_spinner=False)
def _load_search_interest(keyword):
    return live_pulse.fetch_search_interest(keyword)


# GDELT enforces ~1 request per 5s per IP. Caching the result — including a
# failed one — for 5 minutes is what actually keeps this under that limit;
# without it, every plain page view re-hits GDELT and risks tripping a 429.
@st.cache_data(ttl=300, show_spinner=False)
def _load_news_tone(keyword):
    return live_pulse.fetch_news_tone(keyword)


@st.cache_data(ttl=300, show_spinner=False)
def _load_headlines(keyword):
    return live_pulse.fetch_headlines(keyword)


@st.cache_data(ttl=1800, show_spinner=False)
def _load_youtube(keyword, api_key):
    return live_pulse.fetch_youtube_mentions(keyword, api_key)


@st.cache_data(ttl=1800, show_spinner=False)
def _load_reddit(keyword, client_id, client_secret):
    return live_pulse.fetch_reddit_mentions(keyword, client_id, client_secret)


def _keyword_options():
    """Constituency plus every 2023 candidate, so the default choices are names
    that actually appear on this seat's ballot rather than a guessed keyword."""
    options = [("Constituency — " + PULSE_KEYWORD, PULSE_KEYWORD)]
    for code, name in CANDIDATES.items():
        options.append((f"{PARTY_LABELS.get(code, code)} — {name}", name))
    return options


def _pick_keyword():
    options = _keyword_options()
    labels = [label for label, _ in options] + ["Custom search term"]

    choice = st.selectbox("Track", labels, key="pulse_track_choice")

    if choice == "Custom search term":
        typed = st.text_input(
            "Search term",
            value=st.session_state.get("pulse_custom_term", PULSE_KEYWORD),
            key="pulse_custom_term",
        )
        return typed.strip() or PULSE_KEYWORD

    return dict(options)[choice]


def render(ctx, sidebar):
    section(
        "Live pulse",
        "Free-tier search interest, news tone, and public post activity — track the "
        "constituency, a candidate, or type your own search term.",
    )
    st.caption(
        "This is a sampled proxy for public mood, not a measured survey — treat direction "
        "and relative change as the signal, not the absolute numbers."
    )

    keyword = _pick_keyword()

    with st.spinner("Reading live signals..."):
        interest = _load_search_interest(keyword)
        tone = _load_news_tone(keyword)
        headlines = _load_headlines(keyword)

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("##### Search interest")
        if not interest["ok"]:
            empty_state(f"Google Trends unavailable right now ({interest['error']}).")
        elif not interest["points"]:
            empty_state("No search interest returned for this window.")
        else:
            st.plotly_chart(
                charts.pulse_trend(interest["points"], "interest", "Search interest (0-100)"),
                width="stretch",
            )

    with col2:
        st.markdown("##### News tone")
        if not tone["ok"]:
            empty_state(f"GDELT unavailable right now ({tone['error']}).")
        elif not tone["points"]:
            empty_state("No news coverage found in this window.")
        else:
            st.plotly_chart(
                charts.pulse_trend(tone["points"], "tone", "Average news tone (-10 to +10)"),
                width="stretch",
            )

    st.markdown("##### Recent coverage")
    if not headlines["ok"]:
        empty_state(f"GDELT unavailable right now ({headlines['error']}).")
    elif not headlines["articles"]:
        empty_state("No recent articles found for this search term.")
    else:
        for a in headlines["articles"]:
            st.markdown(
                f"- [{a['title']}]({a['url']}) "
                f"<span style='opacity:.55;font-size:.8rem'>· {a['domain']}</span>",
                unsafe_allow_html=True,
            )

    col3, col4 = st.columns(2)

    with col3:
        st.markdown("##### YouTube activity")
        youtube_key = st.secrets.get("YOUTUBE_API_KEY", None) if hasattr(st, "secrets") else None
        if not is_valid_api_key(youtube_key, placeholder_prefix="AIza-REPLACE"):
            st.info(
                "Add `YOUTUBE_API_KEY` to `.streamlit/secrets.toml` — free, from "
                "Google Cloud Console with the YouTube Data API v3 enabled."
            )
        else:
            youtube = _load_youtube(keyword, youtube_key)
            if not youtube["ok"]:
                empty_state(f"YouTube unavailable right now ({youtube['error']}).")
            elif not youtube["videos"]:
                empty_state("No recent videos found for this search term.")
            else:
                for v in youtube["videos"]:
                    st.markdown(f"- [{v['title']}]({v['url']}) — {v['channel']}")

    with col4:
        st.markdown("##### Reddit activity")
        reddit_id = st.secrets.get("REDDIT_CLIENT_ID", None) if hasattr(st, "secrets") else None
        reddit_secret = st.secrets.get("REDDIT_CLIENT_SECRET", None) if hasattr(st, "secrets") else None
        reddit_ready = is_valid_api_key(reddit_id, placeholder_prefix="REPLACE") and is_valid_api_key(
            reddit_secret, placeholder_prefix="REPLACE"
        )
        if not reddit_ready:
            st.info(
                "Add `REDDIT_CLIENT_ID` and `REDDIT_CLIENT_SECRET` to `.streamlit/secrets.toml` "
                "— free, from a 'script' app at reddit.com/prefs/apps."
            )
        else:
            reddit = _load_reddit(keyword, reddit_id, reddit_secret)
            if not reddit["ok"]:
                empty_state(f"Reddit unavailable right now ({reddit['error']}).")
            elif not reddit["posts"]:
                empty_state("No recent posts found for this search term.")
            else:
                for p in reddit["posts"]:
                    st.markdown(
                        f"- [{p['title']}]({p['url']}) — {p['subreddit']} · "
                        f"{p['score']} pts, {p['num_comments']} comments"
                    )

    with st.expander("Facebook & Instagram — why they're not here"):
        st.markdown(
            "Meta's Graph API doesn't allow free public search across posts or accounts you "
            "don't manage — that access was shut down after Cambridge Analytica and now needs "
            "special App Review approval, not available on a free tier. The only thing Meta's "
            "free API allows is a Page you officially administer pulling **its own** posts and "
            "insights, not searching what the public or other parties are posting. If your "
            "campaign runs an official Page and you want its own engagement tracked here, "
            "that's a separate, narrower integration — say so and it can be added."
        )

    fact_card(
        "Search interest, news tone, and post activity are sampled public signals, "
        "not verified sentiment or a scientific poll.",
        SOURCE_METADATA["live_pulse"]["name"],
        SOURCE_METADATA["live_pulse"]["type"],
        "low",
    )

    ctx.logger.log_analysis("live_pulse", ["live_pulse"], f"reviewed for '{keyword}'")
