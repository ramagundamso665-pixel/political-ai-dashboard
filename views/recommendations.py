import streamlit as st

from components import empty_state, fact_card, section
from config import SOURCE_METADATA

TITLE = "Recommendations"


def _source_type(source_name):
    key = next((k for k, v in SOURCE_METADATA.items() if v["name"] == source_name), "")
    return SOURCE_METADATA.get(key, {}).get("type", "internal")


def render(ctx, sidebar):
    section(
        "Daily campaign recommendations",
        "Priority order reflects swing potential derived from the data, not a fixed script.",
    )

    recs = ctx.analyzer.recommendations()

    if not recs:
        empty_state("No recommendations generated — the source sheets returned no actionable signal.")
        return

    for rec in recs:
        left, right = st.columns([0.15, 0.85])
        with left:
            st.metric("Priority", rec["priority"])
        with right:
            st.markdown(f"##### {rec['action']}")
            st.markdown(f"**Reasoning:** {rec['reasoning']}")
            st.markdown(f"**Timeline:** {rec['timeline']}")
            fact_card(rec["action"], rec["source"], _source_type(rec["source"]), "medium")
        st.divider()

    ctx.logger.log_analysis("recommendations", ["multiple"], f"{len(recs)} recommendations generated")
