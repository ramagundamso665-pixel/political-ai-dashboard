import pandas as pd
import streamlit as st

import charts
import search_trends
from components import empty_state, fact_card, section
from config import SOURCE_METADATA

TITLE = "Search Trends"

PRESETS = {
    "Leaders and parties": "Revanth Reddy, KTR, BRS, Congress, BJP",
    "Civic issues": "water problem, road repair, drainage, garbage, power cut",
    "Welfare and prices": "Rythu Bandhu, ration card, gas cylinder, petrol price, jobs",
}


@st.cache_data(ttl=3600, show_spinner=False)
def _fetch(terms, geo, timeframe):
    return search_trends.fetch(list(terms), geo, timeframe)


def render(ctx, sidebar):
    section(
        "Search trends",
        "What people in Telangana are searching for on Google, compared side by side: leaders, parties, and the local issues behind the votes.",
    )
    c1, c2, c3 = st.columns([1.3, 1, 1])
    preset = c1.selectbox("Start from", list(PRESETS) + ["My own terms"], key="trend_preset")
    geo_name = c2.selectbox("Where", list(search_trends.GEOS), key="trend_geo")
    span = c3.selectbox("Period", list(search_trends.TIMEFRAMES), index=2, key="trend_span")
    default = PRESETS.get(preset, st.session_state.get("trend_terms", ""))
    terms_text = st.text_input(f"Up to {search_trends.MAX_TERMS} search terms, separated by commas", value=default, key=f"trend_terms_{preset}")
    st.session_state["trend_terms"] = terms_text
    terms = tuple(t.strip() for t in terms_text.split(",") if t.strip())[: search_trends.MAX_TERMS]
    if not terms:
        empty_state("Enter at least one search term.")
        return

    with st.spinner("Asking Google Trends (this can take about 10 seconds)"):
        data = _fetch(terms, search_trends.GEOS[geo_name], search_trends.TIMEFRAMES[span])

    if not data["ok"]:
        st.warning(data["error"])
        return
    if data["error"]:
        st.caption(data["error"])
    if data["interest"].empty:
        empty_state("Google returned too little data for these terms in this period. Try a broader term or a longer period.")
        return

    tabs = st.tabs(["Over time", "Rising searches", "Where"])
    with tabs[0]:
        st.plotly_chart(charts.trend_lines(data["interest"]), width="stretch")
        st.dataframe(search_trends.summary(data["interest"]), hide_index=True, width="stretch")
        st.caption(
            "Interest is relative: 100 is the highest point among the terms above in this period, so a term's number only "
            "means something next to the others. It is not a count of searches."
        )
    with tabs[1]:
        term = st.selectbox("Term", list(terms), key="trend_rising_term")
        rising, top = data["rising"].get(term), data["top"].get(term)
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Rising: searches growing fastest alongside this term**")
            if rising is None or rising.empty:
                empty_state("Nothing rising for this term.")
            else:
                st.dataframe(rising.rename(columns={"query": "Search", "value": "Growth"}), hide_index=True, width="stretch")
        with c2:
            st.markdown("**Top: the most common related searches**")
            if top is None or top.empty:
                empty_state("No related searches.")
            else:
                st.dataframe(top.rename(columns={"query": "Search", "value": "Interest"}), hide_index=True, width="stretch")
        st.caption('"Growth" is the percentage rise on the previous period; "Breakout" means more than a fivefold rise.')
    with tabs[2]:
        term = st.selectbox("Term", list(terms), key="trend_place_term")
        places = search_trends.top_places(data["regions"], term)
        if places.empty:
            empty_state("Google gave no place breakdown for this term.")
        else:
            st.dataframe(places, hide_index=True, width="stretch")
            st.caption(
                "Google splits Telangana into sub-regions, roughly mandals and localities. It cannot go down to a pincode "
                "or a street, and low-volume places are grouped or hidden."
            )

    fact_card(
        "Google Trends shows relative interest, not the number of searches, and it is sampled. A rising search is a "
        "signal of what people are asking about, not of what they think.",
        SOURCE_METADATA["google_trends"]["name"],
        SOURCE_METADATA["google_trends"]["type"],
        "medium",
    )
    ctx.logger.log_analysis("search_trends", ["google_trends"], f"viewed trends for {', '.join(terms)}")
