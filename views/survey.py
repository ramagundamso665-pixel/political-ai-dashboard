import streamlit as st

import charts
from components import result_banner, section
from config import PARTY_LABELS

TITLE = "Survey Reliability & Prediction"


def render(ctx, sidebar):
    section(
        "Survey reliability and election prediction",
        "Third-party polls disagree sharply on this seat. The prediction is penalized accordingly.",
    )

    survey = ctx.analyzer.survey_landscape()

    st.markdown("##### Raw survey landscape")
    st.dataframe(survey["raw"], hide_index=True, width="stretch")

    st.markdown("##### Conflict check")
    for c in survey["conflicts"]:
        party = PARTY_LABELS.get(c["party"], c["party"])
        if c["conflict_exists"]:
            st.markdown(
                f'<span class="badge badge-conflict">CONFLICT</span> '
                f"<strong>{party}</strong>: surveys range from <strong>{c['min']}%</strong> to "
                f"<strong>{c['max']}%</strong> (spread {c['spread']}pt) across {len(c['values'])} "
                "sources — do not treat any single survey as ground truth.",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(f"**{party}**: surveys broadly agree (spread {c['spread']}pt)")

    section("Blended prediction", "Historical result, internal tracking and surveys, weighted.")

    pred = ctx.analyzer.predict_outcome()
    result_banner(ctx.analyzer.latest_result(), pred)

    c1, c2, c3 = st.columns(3)
    c1.metric("Predicted leader", PARTY_LABELS.get(pred["predicted_leader"]))
    c2.metric("Confidence", f"{pred['confidence_pct']}%", pred["confidence_label"])
    c3.metric("Margin", f"{pred['margin_pct']}pt over {PARTY_LABELS.get(pred['runner_up'])}")

    st.plotly_chart(charts.blended_prediction(pred["blended_shares"]), width="stretch")

    with st.expander("How this number was built"):
        st.json(pred["inputs"])
        w = pred["weights"]
        st.markdown(
            f"Weights: historical {w['historical']*100:.0f}% · "
            f"division tracking {w['division']*100:.0f}% · surveys {w['survey']*100:.0f}%"
        )
        st.markdown(
            f"Average survey disagreement: **{pred['avg_survey_disagreement_pct']}pt** "
            "(this directly lowers confidence)"
        )

    st.warning(
        "This is a probability estimate, not a guarantee. Confidence is capped and "
        "penalized when third-party surveys disagree — treat it as one input among many."
    )

    ctx.logger.log_prediction(pred)
