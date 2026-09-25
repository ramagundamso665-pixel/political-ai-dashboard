import streamlit as st

from components import result_banner, section
from config import CONSTITUENCY_NAME, PARTIES, PARTY_LABELS

TITLE = "Overview"


def render(ctx, sidebar):
    section(
        "Campaign intelligence overview",
        "A single read on where the race stands, and how much of it is actually solid.",
    )

    pred = ctx.analyzer.predict_outcome()
    result = ctx.analyzer.latest_result()
    result_banner(result, pred)
    swing = ctx.analyzer.swing_divisions(top_n=100)
    survey = ctx.analyzer.survey_landscape()
    conflicted = [c for c in survey["conflicts"] if c["conflict_exists"]]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Model's pre-election call" if result else "Predicted leader", PARTY_LABELS.get(pred["predicted_leader"]), f"+{pred['margin_pct']}pt")
    c2.metric("Prediction confidence", f"{pred['confidence_pct']}%", pred["confidence_label"])
    c3.metric("Swing divisions tracked", len(swing))
    c4.metric(
        "Surveys in conflict",
        f"{len(conflicted)}/{len(PARTIES)} parties",
        "flagged" if conflicted else "none",
    )

    st.markdown("---")
    tabs = st.tabs(["Why this dashboard is different", "This constituency", "Methodology"])

    with tabs[0]:
        st.markdown(
            """
            Most campaign decks show a single confident number. This one shows **what
            the data actually says, including where it disagrees with itself.**

            - Every chart and claim carries a source badge — verified official result,
              internal field tracking, or third-party survey.
            - When sources conflict (see the Survey Reliability page — one poll has BJP
              at 1%, another at 41%, for the *same seat*), we surface it instead of
              quietly averaging it away.
            - The prediction confidence score is **calculated from actual survey
              disagreement**, not a fixed marketing number.
            """
        )

    with tabs[1]:
        st.markdown(f"**{CONSTITUENCY_NAME}** — built directly from this campaign's own tracking data:")
        st.dataframe(ctx.sheets["demographics"], hide_index=True, width="stretch")

    with tabs[2]:
        st.markdown(
            """
            1. **Data validation** — every sheet is checked for missing values and unfilled
               placeholder cells before any analysis runs (see sidebar quality score).
            2. **Source attribution** — every number is tagged: verified / internal / external.
            3. **Blended prediction** — historical result (20%), internal division tracking
               (50%), survey average (30%), confidence penalized by survey disagreement.
            4. **Recommendations** — derived programmatically from swing divisions, contested
               demographics, survey conflicts, and event-tempo — not hardcoded talking points.
            """
        )
