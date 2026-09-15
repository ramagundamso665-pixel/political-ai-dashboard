import html
from concurrent.futures import ThreadPoolExecutor

import streamlit as st

import charts
import health
import live_pulse
from components import empty_state, fact_card, section
from config import (
    CANDIDATES,
    KEY_LEADERS,
    PARTY_LABELS,
    PARTY_SEARCH_TERMS,
    PULSE_KEYWORD,
    SOURCE_METADATA,
    TELANGANA_CONSTITUENCIES,
    TELANGANA_LOK_SABHA,
    is_valid_api_key,
)

TITLE = "Live Pulse"

SCOPES = ["This campaign", "MLA seats (119)", "MP seats (17)", "Leaders", "Parties", "Custom"]
COVERAGE_SHOWN = 12
MOOD_HEADLINES = 25
MUTED = "opacity:.62;font-size:.9rem"

# how each party is named in a headline, as opposed to the search phrase used
PARTY_HEADLINE_TERMS = {
    "BRS": ["brs", "bharat rashtra samithi"],
    "INC": ["congress"],
    "BJP": ["bjp"],
    "AIMIM": ["aimim", "majlis", "owaisi"],
}


SKIPPED = {"ok": False, "error": "not configured"}


@st.cache_data(ttl=900, show_spinner=False)
def _signals(trends, news, video, youtube_key, reddit_id, reddit_secret):
    """Every independent source fetched at once. Run one after another they took
    6+ seconds before the page drew anything; in parallel the wait is only the
    slowest source. Worker threads call the plain fetchers — Streamlit's own
    calls aren't safe off the script thread."""
    jobs = {
        "interest": (live_pulse.fetch_search_interest, (trends,)),
        "news": (live_pulse.fetch_recent_news, (news,)),
    }
    if youtube_key:
        jobs["youtube"] = (live_pulse.fetch_youtube_mentions, (video, youtube_key))
    if reddit_id and reddit_secret:
        jobs["reddit"] = (live_pulse.fetch_reddit_mentions, (news, reddit_id, reddit_secret))

    with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
        futures = {name: pool.submit(fn, *args) for name, (fn, args) in jobs.items()}
        results = {name: future.result() for name, future in futures.items()}
    return {"youtube": SKIPPED, "reddit": SKIPPED, **results}


# GDELT allows ~1 request per 5s per IP; caching even a failed result for 5
# minutes is what keeps reruns from tripping that limit over and over.
@st.cache_data(ttl=300, show_spinner=False)
def _gdelt_tone(query):
    return live_pulse.fetch_news_tone(query)


@st.cache_data(ttl=1800, show_spinner=False)
def _mood(subject, headlines, api_key):
    return live_pulse.classify_headline_mood(subject, list(headlines), api_key)


def _link(title, url):
    """Headlines and video titles are third-party text rendered as HTML, so both
    the text and the URL are escaped, and only http(s) links are allowed."""
    text = html.escape(html.unescape(title or "Untitled"))
    if not str(url).startswith(("https://", "http://")):
        return text
    return f'<a href="{html.escape(url, quote=True)}" target="_blank" rel="noopener">{text}</a>'


def _place(name):
    # a bare place name ("Uppal", "Wyra") matches unrelated news across India
    return {
        "label": name,
        "trends": name,
        "news": f'"{name}" Telangana',
        "video": f'"{name}"',
        "headline_terms": [name.lower()],
    }


def _person(name, spec=None):
    if isinstance(spec, dict):
        return {
            "label": name,
            "trends": spec["term"],
            "news": spec["news"],
            "video": f'"{spec["term"]}"',
            "headline_terms": spec["headline_terms"],
        }
    term = spec or name
    return {"label": name, "trends": term, "news": f'"{term}"', "video": f'"{term}"', "headline_terms": [term.lower()]}


def _split_by_headline(articles, terms):
    """Articles naming the subject in the headline, and those that only matched
    somewhere in the body. Only the first group is presented as coverage of the
    subject — body matches are where a leader showed up as someone else's story."""
    about, mentioned = [], []
    for a in articles:
        (about if any(t in a["title"].lower() for t in terms) else mentioned).append(a)
    return about, mentioned


def _pick_target():
    scope = st.radio("What to track", SCOPES, horizontal=True, key="pulse_scope")

    if scope == "This campaign":
        choices = {f"Constituency — {PULSE_KEYWORD}": _place(PULSE_KEYWORD)}
        for code, name in CANDIDATES.items():
            choices[f"{PARTY_LABELS.get(code, code)} candidate — {name}"] = _person(name)
        return choices[st.selectbox("Seat or candidate", list(choices), key="pulse_campaign_choice")]

    if scope == "MLA seats (119)":
        name = st.selectbox(
            "Assembly constituency — click and type to search",
            TELANGANA_CONSTITUENCIES,
            index=TELANGANA_CONSTITUENCIES.index(PULSE_KEYWORD),
            key="pulse_mla_seat",
        )
        return _place(name)

    if scope == "MP seats (17)":
        name = st.selectbox("Lok Sabha constituency", TELANGANA_LOK_SABHA, key="pulse_mp_seat")
        query = f'("{name} Lok Sabha" OR "{name} MP")'
        return {
            "label": f"{name} (Lok Sabha)",
            "trends": name,
            "news": query,
            "video": query,
            "headline_terms": [name.lower()],
        }

    if scope == "Leaders":
        label = st.selectbox("Leader — click and type to search", list(KEY_LEADERS), key="pulse_leader")
        return _person(label, KEY_LEADERS[label])

    if scope == "Parties":
        code = st.selectbox(
            "Party", list(PARTY_SEARCH_TERMS), format_func=lambda c: PARTY_LABELS.get(c, c), key="pulse_party"
        )
        term = PARTY_SEARCH_TERMS[code]
        return {
            "label": PARTY_LABELS.get(code, code),
            "trends": term,
            "news": term,
            "video": term,
            "headline_terms": PARTY_HEADLINE_TERMS[code],
        }

    typed = st.text_input(
        "Search term", key="pulse_custom_term", placeholder="A person, place, scheme or issue"
    ).strip()
    if not typed:
        return None
    return {"label": typed, "trends": typed, "news": typed, "video": typed, "headline_terms": [typed.lower()]}


def _render_search_interest(interest):
    st.markdown("##### Google searches in Telangana")
    if not interest["ok"]:
        empty_state(f"Google Trends unavailable right now — {interest['error']}.")
    elif not interest["points"]:
        empty_state("Too few searches for Google to report a trend.")
    else:
        st.plotly_chart(
            charts.pulse_trend(interest["points"], "interest", "Search interest, last 90 days (0-100)"),
            width="stretch",
        )


def _render_volume(news):
    st.markdown("##### News coverage")
    if not news["ok"]:
        empty_state(f"Google News unavailable right now — {news['error']}.")
    elif not news["articles"]:
        empty_state("No news coverage in the last 30 days.")
    else:
        days = news["days"]
        st.plotly_chart(
            charts.coverage_volume(live_pulse.coverage_by_day(news["articles"], days), days), width="stretch"
        )
        capped = " (Google News returns at most 100)" if len(news["articles"]) >= 100 else ""
        widened = " — widened from 7 days because the last week had too little coverage" if days > 7 else ""
        st.caption(f"{len(news['articles'])} articles in the last {days} days{capped}{widened}.")


def _render_mood(ctx, target, articles, mentioned_count):
    st.markdown("##### Headline mood")
    if not articles:
        if mentioned_count:
            empty_state(
                f"No recent headline is directly about {target['label']} — they're only mentioned inside "
                f"{mentioned_count} article(s), listed under “Also mentioned in”. Mood isn't judged from those."
            )
        else:
            empty_state("No recent headlines to read.")
        return
    if not is_valid_api_key(ctx.api_key):
        st.info("Headline mood needs a working OPENAI_API_KEY — see System status in the sidebar.")
        return

    headlines = tuple(a["title"] for a in articles[:MOOD_HEADLINES])
    mood = _mood(target["label"], headlines, ctx.api_key)
    if not mood["ok"]:
        empty_state(f"Couldn't read headline mood — {mood['error']}.")
        return

    counts = mood["counts"]
    if not sum(counts.values()):
        empty_state("None of the latest headlines are actually about this subject.")
        return

    c1, c2, c3 = st.columns(3)
    c1.metric("Positive", counts["positive"])
    c2.metric("Neutral", counts["neutral"])
    c3.metric("Negative", counts["negative"])
    if mood["themes"]:
        st.markdown("**Recurring themes:** " + " · ".join(html.escape(t) for t in mood["themes"]))
    unrelated = f" ({mood['unrelated']} judged unrelated)" if mood["unrelated"] else ""
    st.caption(
        f"AI read of the tone of the {mood['rated']} latest headlines toward {target['label']}{unrelated}. "
        "Based on headline wording only — not a verified sentiment measure."
    )


def _article_list(articles):
    lines = []
    for a in articles[:COVERAGE_SHOWN]:
        when = a["published"].strftime("%d %b") if a["published"] else ""
        meta = " · ".join(part for part in (a["source"], when) if part)
        lines.append(f"<li>{_link(a['title'], a['url'])} <span style='{MUTED}'>· {html.escape(meta)}</span></li>")
    st.markdown(f"<ul>{''.join(lines)}</ul>", unsafe_allow_html=True)


def _render_coverage(target, about, mentioned):
    st.markdown(f"##### Headlines about {html.escape(target['label'])}")
    if about:
        _article_list(about)
    else:
        empty_state("No recent headlines name them directly.")

    if mentioned:
        st.markdown("##### Also mentioned in")
        st.caption(
            "These articles matched the search somewhere in the story, not the headline — the story is "
            "usually about something else. Check before quoting any of them."
        )
        _article_list(mentioned)


def _render_youtube(youtube, problem):
    st.markdown("##### YouTube — news & politics, last 30 days")
    if problem:
        st.info(f"YouTube is off: YOUTUBE_API_KEY {problem}. Update it in the app's Secrets settings.")
        return

    if not youtube["ok"]:
        empty_state(f"YouTube unavailable right now — {youtube['error']}.")
    elif not youtube["videos"]:
        empty_state("No news or politics videos about this in the last 30 days.")
    else:
        lines = [
            f"<li>{_link(v['title'], v['url'])} <span style='{MUTED}'>"
            f"· {html.escape(v['channel'])} · {html.escape(v['published'][:10])}</span></li>"
            for v in youtube["videos"]
        ]
        st.markdown(f"<ul>{''.join(lines)}</ul>", unsafe_allow_html=True)


def _render_reddit(reddit, configured):
    st.markdown("##### Reddit")
    if not configured:
        st.info("Reddit is off — add REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET to enable it.")
        return

    if not reddit["ok"]:
        empty_state(f"Reddit unavailable right now — {reddit['error']}.")
    elif not reddit["posts"]:
        empty_state("No recent Reddit posts about this.")
    else:
        lines = [
            f"<li>{_link(p['title'], p['url'])} <span style='{MUTED}'>· {html.escape(p['subreddit'])} "
            f"· {p['score']} pts, {p['num_comments']} comments</span></li>"
            for p in reddit["posts"]
        ]
        st.markdown(f"<ul>{''.join(lines)}</ul>", unsafe_allow_html=True)


def _render_gdelt(target):
    # an expander's body runs even while collapsed, so the fetch sits behind a
    # toggle — otherwise every page load waits on GDELT's 20-second timeout
    if not st.toggle("Show global news tone (GDELT — slower, often rate-limited)", key="pulse_gdelt"):
        return
    with st.container(border=True):
        tone = _gdelt_tone(target["news"])
        if not tone["ok"]:
            empty_state(f"GDELT unavailable right now — {tone['error']}.")
        elif not tone["points"]:
            empty_state("No GDELT-indexed coverage in the last 30 days.")
        else:
            st.plotly_chart(
                charts.pulse_trend(tone["points"], "tone", "Average news tone (-10 to +10)"), width="stretch"
            )


def render(ctx, sidebar):
    section(
        "Live pulse",
        "Public search interest, news coverage and video activity for any Telangana seat, leader or party.",
    )
    st.caption("A sampled proxy for public mood, not a survey — read the direction and the change, not the absolute numbers.")

    target = _pick_target()
    if target is None:
        empty_state("Type a search term to see its live signals.")
        return

    youtube_key = health.secret("YOUTUBE_API_KEY")
    youtube_problem = health.key_problem(youtube_key, "AIza-REPLACE")
    reddit_id = health.secret("REDDIT_CLIENT_ID")
    reddit_secret = health.secret("REDDIT_CLIENT_SECRET")
    reddit_ready = not (health.key_problem(reddit_id, "REPLACE") or health.key_problem(reddit_secret, "REPLACE"))

    with st.spinner(f"Reading live signals for {target['label']}…"):
        signals = _signals(
            target["trends"],
            target["news"],
            target["video"],
            None if youtube_problem else youtube_key,
            reddit_id if reddit_ready else None,
            reddit_secret if reddit_ready else None,
        )
    interest, news = signals["interest"], signals["news"]
    articles = live_pulse.latest_first(news["articles"]) if news["ok"] else []

    st.markdown(f"### {html.escape(target['label'])}")

    col1, col2 = st.columns(2)
    with col1:
        _render_search_interest(interest)
    with col2:
        _render_volume(news)

    about, mentioned = _split_by_headline(articles, target["headline_terms"])
    _render_mood(ctx, target, about, len(mentioned))
    _render_coverage(target, about, mentioned)

    col3, col4 = st.columns(2)
    with col3:
        _render_youtube(signals["youtube"], youtube_problem)
    with col4:
        _render_reddit(signals["reddit"], reddit_ready)

    _render_gdelt(target)

    fact_card(
        "Search interest, news coverage, headline mood and video activity are sampled public signals, "
        "not verified sentiment or a scientific poll.",
        SOURCE_METADATA["live_pulse"]["name"],
        SOURCE_METADATA["live_pulse"]["type"],
        "low",
    )

    ctx.logger.log_analysis("live_pulse", ["live_pulse"], f"reviewed for '{target['label']}'")
