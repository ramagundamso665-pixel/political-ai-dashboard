"""Manage Leaders — add names to the Live Pulse "Leaders" tracker without
editing config.py. KEY_LEADERS in config.py stays the curated baseline (it
ships with the app); anything added here is stored in Supabase and merged
on top of it wherever Live Pulse builds the leader list.

Unlike Field Reports, this isn't a public open form — it's plain staff
config, so it lives behind the same app password as everything else and
writes through the service key rather than a public insert policy.
"""

import streamlit as st

import db
from components import empty_state, section
from config import KEY_LEADERS, is_valid_api_key

TITLE = "Manage Leaders"


def _secrets():
    url = st.secrets.get("SUPABASE_URL", None) if hasattr(st, "secrets") else None
    key = st.secrets.get("SUPABASE_SERVICE_KEY", None) if hasattr(st, "secrets") else None
    return url, key


def _split(text):
    return [t.strip() for t in text.split(",") if t.strip()] or None


@st.cache_data(ttl=30, show_spinner=False)
def _load(url, key):
    return db.fetch_manual_leaders(url, key)


def render(ctx, sidebar):
    section(
        "Manage leaders",
        "Add a name here to make it selectable under Live Pulse → Leaders. "
        "These are stored separately from the built-in list below, which ships with the app.",
    )

    url, key = _secrets()
    if not (is_valid_api_key(url, placeholder_prefix="https://REPLACE") and is_valid_api_key(key, placeholder_prefix="REPLACE")):
        st.info(
            "Add SUPABASE_URL and SUPABASE_SERVICE_KEY to `.streamlit/secrets.toml` to enable this page."
        )
        return

    with st.form("add_leader_form", clear_on_submit=True):
        name = st.text_input(
            "Display name", placeholder="e.g. Jane Doe (MLA, Some Constituency)"
        )
        term = st.text_input(
            "Search alias (optional)",
            placeholder="Short form headlines actually use, e.g. \"Jane Doe\" — defaults to the display name",
        )
        with st.expander("Disambiguation (optional) — only needed if this name is shared with someone else"):
            headline_terms = st.text_input(
                "Headline terms, comma-separated",
                placeholder="jane doe, mla jane, j. doe",
                help="Only headlines containing one of these terms count as 'about them'.",
            )
            exclude_terms = st.text_input(
                "Exclude terms, comma-separated",
                placeholder="jane doe actress, other jane",
                help="Headlines containing any of these are dropped even if a headline term also matched.",
            )
        submitted = st.form_submit_button("Add leader", type="primary")

    if submitted:
        if not name.strip():
            st.warning("Display name is required.")
        else:
            row = {
                "display_name": name.strip(),
                "term": term.strip() or None,
                "headline_terms": _split(headline_terms),
                "exclude_terms": _split(exclude_terms),
            }
            try:
                db.add_manual_leader(url, key, row)
                _load.clear()
                st.success(f"Added {name.strip()}. It now appears under Live Pulse → Leaders.")
            except Exception as exc:
                st.error(f"Could not save: {exc}")

    st.markdown("---")

    try:
        manual = _load(url, key)
    except Exception as exc:
        st.error(f"Could not reach Supabase: {exc}")
        return

    st.markdown(f"##### Added here ({len(manual)})")
    if manual.empty:
        empty_state("No leaders added yet — use the form above.")
    else:
        for _, r in manual.iterrows():
            cols = st.columns([5, 1])
            with cols[0]:
                alias = f" — tracked as “{db.as_text(r.get('term'))}”" if db.as_text(r.get("term")) else ""
                st.markdown(f"**{r['display_name']}**{alias}")
                if db.as_list(r.get("headline_terms")):
                    st.caption("Headline terms: " + ", ".join(db.as_list(r["headline_terms"])))
            with cols[1]:
                if st.button("Remove", key=f"del_leader_{r['id']}", width="stretch"):
                    db.delete_manual_leader(url, key, r["id"])
                    _load.clear()
                    st.rerun()

    st.markdown("---")
    st.markdown(f"##### Built into the app ({len(KEY_LEADERS)})")
    st.caption("Edit config.py to change these — they ship with the dashboard, same for every deploy.")
    st.write(", ".join(KEY_LEADERS.keys()))
