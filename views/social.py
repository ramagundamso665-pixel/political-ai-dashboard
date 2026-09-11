import streamlit as st

import charts
from components import empty_state, fact_card, section
from config import SOURCE_METADATA

TITLE = "Social & Ground Campaign"


def render(ctx, sidebar):
    section(
        "Social media and ground campaign",
        "Engagement volume, field positioning, and campaign tempo.",
    )

    social = ctx.analyzer.social_media_activity()

    st.markdown("##### Social media share of voice")
    if social["excluded_rows"]:
        st.caption(
            f"{social['excluded_rows']} row(s) excluded — unfilled placeholder data in the source log."
        )

    if social["by_party"].empty:
        empty_state("No usable social media rows in the activity log.")
    else:
        st.plotly_chart(charts.social_share(social["by_party"]), width="stretch")
        st.dataframe(social["by_party"], hide_index=True, width="stretch")

    fact_card(
        "Share of voice is engagement volume, not sentiment — this log has no sentiment scoring.",
        SOURCE_METADATA["social_media"]["name"],
        SOURCE_METADATA["social_media"]["type"],
        "low",
    )

    section("Ground campaign positioning", "Field notes by category, one row per observation.")
    st.dataframe(ctx.analyzer.ground_campaign_matrix(), hide_index=True, width="stretch")

    section("Campaign activity timeline", "Rallies, visits and press events as logged.")
    activity = ctx.analyzer.campaign_activity_timeline()
    st.dataframe(activity["timeline"], hide_index=True, width="stretch")

    counts = activity["event_counts_by_party"]
    if counts:
        st.plotly_chart(charts.event_counts(counts), width="stretch")

    ctx.logger.log_analysis(
        "social_and_ground",
        ["social_media", "ground_campaign", "campaign_activity"],
        "reviewed",
    )
