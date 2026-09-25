import pandas as pd
import streamlit as st

import live_pulse
import scoring
from components import empty_state, section
from config import PARTY_LABELS, PARTY_SEARCH_TERMS, is_valid_api_key

TITLE = "Mood Check"

MAX_HEADLINES = 15
CUSTOM = "Custom search"
CHOICES = {"Positive": "positive", "Neutral": "neutral", "Negative": "negative", "Unrelated": "unrelated"}


@st.cache_data(ttl=900, show_spinner=False)
def _headlines(query):
    news = live_pulse.fetch_recent_news(query)
    if not news["ok"]:
        return {"ok": False, "error": news["error"], "titles": []}
    titles, seen = [], set()
    for article in live_pulse.latest_first(news["articles"]):
        title = article["title"].strip()
        if title and title not in seen:
            seen.add(title)
            titles.append(title)
    return {"ok": True, "titles": titles[:MAX_HEADLINES]}


def _history(ctx):
    """Every hand label ever saved, one per (subject, headline), latest wins."""
    latest = {}
    for event in ctx.logger.recent(1000):
        details = event.get("details")
        if event.get("action_type") == "mood_label" and isinstance(details, dict):
            latest[(details.get("subject"), details.get("headline"))] = details
    return list(latest.values())


def _show_result(result, title):
    st.markdown(f"##### {title}")
    if result is None:
        empty_state("No labels yet.")
        return
    c1, c2, c3 = st.columns(3)
    c1.metric("Labelled by you", result["n"])
    c2.metric("AI agreed", f"{result['agree']} of {result['n']}")
    if result["enough"]:
        c3.metric("Agreement", f"{result['pct']}%", f"likely {result['low_pct']}-{result['high_pct']}%", delta_color="off")
    else:
        c3.metric("Agreement", "too few", f"needs {scoring.MIN_LABELS_FOR_ACCURACY}+ labels", delta_color="off")

    if not result["enough"]:
        st.caption(
            f"With only {result['n']} label(s) any percentage would be misleading (it could plausibly be "
            f"anywhere from {result['low_pct']}% to {result['high_pct']}%). Keep labelling."
        )
    rows = [
        {
            "You called it": name.title(),
            "Headlines": stats["labelled"],
            "AI agreed": stats["agreed"],
        }
        for name, stats in result["per_class"].items()
        if stats["labelled"]
    ]
    if rows:
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")


def render(ctx, sidebar):
    section(
        "Mood check",
        "How often does the AI's reading of a headline match yours? Label real headlines yourself first. "
        "The AI's answer stays hidden until you submit, so it can't sway you.",
    )

    if not is_valid_api_key(ctx.api_key):
        st.error("Add a real OPENAI_API_KEY to .streamlit/secrets.toml to enable this page.")
        return

    codes = list(PARTY_SEARCH_TERMS)
    subject = st.selectbox(
        "Headlines about", codes + [CUSTOM], format_func=lambda c: c if c == CUSTOM else PARTY_LABELS.get(c, c)
    )
    if subject == CUSTOM:
        typed = st.text_input("Search term", placeholder="A person, place, scheme or issue").strip()
        if not typed:
            empty_state("Type a search term to load headlines.")
            return
        query, label = typed, typed
    else:
        query, label = PARTY_SEARCH_TERMS[subject], PARTY_LABELS.get(subject, subject)

    fetched = _headlines(query)
    if not fetched["ok"]:
        empty_state(f"Couldn't load headlines — {fetched['error']}.")
        return
    titles = fetched["titles"]
    if not titles:
        empty_state("No recent headlines for that.")
        return

    st.caption(
        f"Tone toward **{label}**. Choose Unrelated if the headline isn't really about them. "
        "Label as many as you can. Skip any you're unsure of."
    )
    with st.form("mood_check_form"):
        picks = {
            i: st.radio(f"{i + 1}. {title}", list(CHOICES), index=None, horizontal=True, key=f"mc_{label}_{i}")
            for i, title in enumerate(titles)
        }
        submitted = st.form_submit_button("Submit my labels", type="primary")

    if submitted:
        labelled = [(titles[i], CHOICES[choice]) for i, choice in picks.items() if choice]
        if not labelled:
            st.warning("Label at least one headline first.")
        else:
            with st.spinner("Comparing with the AI's reading..."):
                model = live_pulse.classify_headline_mood(label, [t for t, _ in labelled], ctx.api_key)
            if not model["ok"]:
                st.error(f"Couldn't get the AI's reading — {model['error']}.")
            else:
                rows = [
                    {"model": model["labels"][i], "human": human, "headline": title}
                    for i, (title, human) in enumerate(labelled)
                ]
                for row in rows:
                    ctx.logger.log_event("mood_label", subject=label, headline=row["headline"], model=row["model"], human=row["human"])
                _show_result(scoring.mood_agreement(rows), "This round")
                misses = [r for r in rows if r["model"] != r["human"]]
                if misses:
                    with st.expander(f"Where the AI and you differed ({len(misses)})"):
                        for r in misses:
                            st.markdown(f"- {r['headline']}  \nYou: **{r['human']}** · AI: **{r['model'] or 'no answer'}**")

    st.markdown("---")
    _show_result(scoring.mood_agreement(_history(ctx)), "All labels so far")
