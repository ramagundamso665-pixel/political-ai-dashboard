"""Small presentational helpers shared across views."""

import html

import streamlit as st

from config import PARTY_LABELS, SOURCE_METADATA

BADGE_CLASS = {
    "verified": "badge-verified",
    "internal": "badge-internal",
    "external": "badge-external",
}


def source_badge(source_type, name=None):
    cls = BADGE_CLASS.get(source_type, "badge-internal")
    label = name or source_type.upper()
    return f'<span class="badge {cls}">{label}</span>'


def wordmark(title, subtitle):
    """App identity, rendered once in the sidebar.

    Previously this was a full-width masthead repeated above every page, which
    double-titled the Ask AI landing and pushed it below the fold.
    """
    st.markdown(
        f"""
        <div class="pm-brand">
            <span class="pm-brand-dot"></span>
            <div>
                <strong>{title}</strong>
                <span>{subtitle}</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def section(title, description=None):
    body = f"<p>{description}</p>" if description else ""
    st.markdown(
        f'<div class="pm-section"><h2>{title}</h2>{body}</div>',
        unsafe_allow_html=True,
    )


def _refresh_of(source_name):
    """How often the named source is refreshed, or None if it isn't a registered one."""
    return next((m.get("refresh") for m in SOURCE_METADATA.values() if m["name"] == source_name), None)


def fact_card(claim, source_name, source_type, confidence):
    refresh = _refresh_of(source_name)
    freshness = f'<span class="badge badge-meta">Updated: {html.escape(refresh)}</span>' if refresh else ""
    st.markdown(
        f"""
        <div class="fact-card">
            {claim}<br/>
            {source_badge(source_type, source_name)}
            <span class="badge badge-meta">Confidence: {confidence.upper()}</span>
            {freshness}
        </div>
        """,
        unsafe_allow_html=True,
    )


def empty_state(message):
    st.markdown(f'<div class="pm-empty">{message}</div>', unsafe_allow_html=True)


def result_banner(result, prediction):
    """Shown wherever a pre-election prediction appears, once the vote has been held."""
    if not result:
        return
    label = lambda p: PARTY_LABELS.get(p, p)
    tally = ", ".join(f"{label(p)} {v}%" for p, v in sorted(result["shares"].items(), key=lambda kv: -kv[1]))
    called = prediction["predicted_leader"]
    verdict = (
        f"This model's pre-election call was {label(called)}, which was right."
        if called == result["winner"]
        else f"This model's pre-election call was **{label(called)}** by {prediction['margin_pct']} points, "
        f"which was **wrong**. See **Backtest** for how each input did."
    )
    st.info(f"The {result['year']} vote has been held: **{label(result['winner'])}** won by {result['margin']} points ({tally}). {verdict}")
