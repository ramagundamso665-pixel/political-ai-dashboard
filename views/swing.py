import streamlit as st

import charts
from components import empty_state, fact_card, section
from config import PARTY_LABELS, SOURCE_METADATA

TITLE = "Swing Divisions"


def render(ctx, sidebar):
    section(
        "Swing division identification",
        "Divisions with the largest vote-share movement between the 2023 and 2025 tracking rounds.",
    )

    swing = ctx.analyzer.swing_divisions(top_n=7)

    if not swing:
        empty_state("No division-level movement recorded between the two tracking rounds.")
        return

    for row in swing:
        left, right = st.columns([3, 1])
        with left:
            party = PARTY_LABELS.get(row["swinging_party"], row["swinging_party"])
            st.markdown(f"**{row['division']}** — swing toward **{party}**")
            st.caption(
                ", ".join(f"{PARTY_LABELS.get(p, p)} {v:+.1f}pt" for p, v in row["deltas"].items())
            )
        with right:
            st.metric("Max swing", f"{row['max_swing']}pt")

    st.plotly_chart(charts.swing_deltas(swing), width="stretch")

    fact_card(
        f"Top {len(swing)} swing divisions identified by 2023→2025 vote share change",
        SOURCE_METADATA["division_deltas"]["name"],
        SOURCE_METADATA["division_deltas"]["type"],
        "medium",
    )

    ctx.logger.log_analysis(
        "swing_divisions", ["division_deltas", "division_shares"], f"{len(swing)} swing divisions"
    )
