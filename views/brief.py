from datetime import date

import streamlit as st
import streamlit.components.v1 as components

from briefing import build_brief_html
from components import section
from config import PARTIES, PARTY_LABELS

TITLE = "Daily Brief"


def render(ctx, sidebar):
    section(
        "Daily brief",
        "A one-page summary to leave with a leader or read at the morning meeting. Built straight from "
        "the data, so it costs nothing and can't contain a number that isn't in your sheets.",
    )

    party = st.selectbox("Prepared for", PARTIES, format_func=lambda p: PARTY_LABELS.get(p, p))
    page = build_brief_html(ctx, party)

    st.download_button(
        "Download the brief",
        data=page,
        file_name=f"daily-brief-{date.today():%Y-%m-%d}.html",
        mime="text/html",
        type="primary",
    )
    st.caption("Open the file in a browser and use Print, then Save as PDF.")
    components.html(page, height=900, scrolling=True)

    ctx.logger.log_analysis("daily_brief", ["multiple"], f"brief for {party}")
