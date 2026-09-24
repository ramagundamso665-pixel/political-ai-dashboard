import streamlit as st

from components import fact_card, section
from config import PARTIES, PARTY_LABELS, is_valid_api_key
from grounding import LANGUAGES

TITLE = "Speech Generator"


def render(ctx, sidebar):
    section(
        "AI speech generator",
        "Every speech is grounded in verified facts pulled from your data. "
        "The model is instructed to never invent numbers.",
    )

    if not is_valid_api_key(ctx.api_key):
        st.error("Add a real OPENAI_API_KEY to .streamlit/secrets.toml to enable speech generation.")
        return

    demo_subgroups = list(ctx.sheets["demo_preferences"]["Subgroup"])
    theme_options = sorted(ctx.sheets["ground_campaign"]["Subcategory"].dropna().unique().tolist())
    event_options = sorted(ctx.sheets["campaign_activity"]["Event Type"].dropna().unique().tolist())

    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        party = st.selectbox("Speaking for", PARTIES, format_func=lambda p: PARTY_LABELS.get(p, p))
    with c2:
        audience = st.selectbox("Target audience", demo_subgroups)
    with c3:
        theme = st.selectbox("Theme", theme_options)
    with c4:
        event = st.selectbox("Event type", event_options)
    with c5:
        language = st.selectbox("Language", LANGUAGES)

    if not st.button("Generate speech", width="stretch"):
        return

    with st.spinner("Grounding facts and generating speech..."):
        result = ctx.speech_gen.generate_speech(party, audience, theme, event, language)

    if "error" in result:
        st.error(result["error"])
        return

    st.markdown("---")
    with st.expander("Full speech", expanded=True):
        st.markdown(result["speech"])

    with st.expander("Sources cited"):
        for cited in result["sources_cited"]:
            fact_card(cited["claim"], cited["source"], "internal", cited["confidence"])

    with st.expander("Verification"):
        if result["verification_status"] == "VERIFIED":
            st.success("All numeric claims trace back to the fact block.")
        else:
            st.warning(
                "Numbers in the speech not found in the source facts "
                f"(double-check before use): {', '.join(result['unverified_numbers'])}"
            )

    with st.expander("Talking points"):
        for i, point in enumerate(result["talking_points"], 1):
            st.markdown(f"{i}. {point}")

    ctx.logger.log_speech_generation(party, audience, result["verification_status"])
