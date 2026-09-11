import pandas as pd
import streamlit as st

import charts
from components import empty_state, fact_card, section
from config import PARTY_LABELS, SOURCE_METADATA

TITLE = "Demographic Insights"


def render(ctx, sidebar):
    section(
        "Demographic preference breakdown",
        "Where each subgroup currently sits, and which ones are still genuinely winnable.",
    )

    demo = ctx.analyzer.demographic_preferences()

    if not demo:
        empty_state("No demographic preference data available in the source workbook.")
        return

    df = pd.DataFrame([{**r["shares"], "Subgroup": r["subgroup"]} for r in demo]).set_index("Subgroup")
    st.plotly_chart(charts.demographic_preferences(df), width="stretch")

    contested = [r for r in demo if r["is_contested"]]
    if contested:
        st.markdown("##### Persuadable subgroups")
        st.caption("Fewer than 5 points separate the top two parties.")
        for row in contested:
            leader = PARTY_LABELS.get(row["leader"], row["leader"])
            st.markdown(f"- **{row['subgroup']}** — {leader} leads by only {row['gap_to_runner_up']}pt")
    else:
        empty_state("No subgroup is within 5 points — every segment currently has a clear leader.")

    fact_card(
        f"{len(contested)} subgroup(s) flagged as tightly contested",
        SOURCE_METADATA["demo_preferences"]["name"],
        SOURCE_METADATA["demo_preferences"]["type"],
        "medium",
    )

    ctx.logger.log_analysis(
        "demographic_preferences", ["demo_preferences"], f"{len(contested)} contested subgroups"
    )
