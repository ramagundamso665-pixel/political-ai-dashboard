"""Small presentational helpers shared across views."""

import streamlit as st

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


def fact_card(claim, source_name, source_type, confidence):
    st.markdown(
        f"""
        <div class="fact-card">
            {claim}<br/>
            {source_badge(source_type, source_name)}
            <span class="badge badge-meta">Confidence: {confidence.upper()}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def empty_state(message):
    st.markdown(f'<div class="pm-empty">{message}</div>', unsafe_allow_html=True)
