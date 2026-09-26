import pandas as pd
import streamlit as st

import area_survey
import charts
import registers
from components import empty_state, fact_card, section
from config import SOURCE_METADATA, is_valid_api_key

TITLE = "Area Ratings"
SETUP = "Run supabase/area_ratings.sql once in the Supabase SQL editor to create the survey tables."


def _secrets():
    url = st.secrets.get("SUPABASE_URL", None) if hasattr(st, "secrets") else None
    key = st.secrets.get("SUPABASE_SERVICE_KEY", None) if hasattr(st, "secrets") else None
    number = st.secrets.get("WHATSAPP_BOT_NUMBER", None) if hasattr(st, "secrets") else None
    return url, key, number


@st.cache_data(ttl=60, show_spinner=False)
def _load(url, key):
    return registers.fetch(url, key, "area_ratings")


def _how_it_works(number):
    st.markdown(
        """
**How residents take part.** They message the survey number on WhatsApp and answer four short questions: language, the issue that
bothers them most this week, their area, and a 1 to 5 rating. It takes under a minute.

- It is voluntary, and the bot says so in its first message.
- The phone number is **never stored**. Only a scrambled code is kept, so a person counts once a week and can send **STOP** to have
  their answers deleted.
- Areas with fewer than 5 answers are not shown, so nobody can be picked out of a small group.

**Setting it up** (once): create a WhatsApp Business app on Meta, run `whatsapp_bot/` on a small host, and point the webhook at it.
The steps are in `whatsapp_bot/README.md`.
        """
    )
    if number:
        digits = "".join(ch for ch in str(number) if ch.isdigit())
        st.markdown("**Share this link** (it opens a chat with the bot and types Hi):")
        st.code(f"https://wa.me/{digits}?text=Hi", language=None)
    else:
        st.caption("Once the bot is live, add `WHATSAPP_BOT_NUMBER = \"91XXXXXXXXXX\"` to the app's secrets and the share link will appear here.")


def render(ctx, sidebar):
    section(
        "Area ratings",
        "What residents say when they message the WhatsApp survey: how they rate their area this week and what bothers them most.",
    )
    url, key, number = _secrets()
    if not (is_valid_api_key(url, placeholder_prefix="https://REPLACE") and is_valid_api_key(key, placeholder_prefix="REPLACE")):
        st.info("Add SUPABASE_URL and SUPABASE_SERVICE_KEY to `.streamlit/secrets.toml` to enable this page.")
        return
    try:
        raw = _load(url, key)
    except Exception:
        st.warning(f"The survey table isn't there yet. {SETUP}")
        _how_it_works(number)
        return

    tabs = st.tabs(["By area", "Issues", "Over time", "How it works"])
    if raw.empty:
        with tabs[0]:
            empty_state("No answers yet. Share the survey link (see How it works) and answers will appear here.")
        with tabs[3]:
            _how_it_works(number)
        return

    weeks = sorted(raw["week"].unique())
    window = st.selectbox("Period", ["All weeks", "Latest week", "Latest 4 weeks"], key="ar_window")
    keep = weeks if window == "All weeks" else (weeks[-1:] if window == "Latest week" else weeks[-4:])
    df = area_survey.prepare(raw[raw["week"].isin(keep)])
    head = area_survey.headline(df)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Answers", head["answers"])
    c2.metric("People", head["people"])
    c3.metric("Areas", head["areas"])
    c4.metric("Average rating", head["average"] if head["average"] is not None else "n/a")

    with tabs[0]:
        table, held = area_survey.by_area(df)
        if table.empty:
            empty_state(f"No area has {area_survey.MIN_RESPONSES} answers yet, so none can be shown.")
        else:
            st.plotly_chart(charts.rating_by_area(table), width="stretch")
            st.dataframe(table, hide_index=True, width="stretch")
        if held:
            st.caption(f"{held} area(s) with fewer than {area_survey.MIN_RESPONSES} answers are held back.")
    with tabs[1]:
        mix = area_survey.issue_mix(df)
        st.dataframe(mix, hide_index=True, width="stretch")
        grid = area_survey.area_by_issue(df)
        if not grid.empty:
            st.markdown("**Answers by area and issue**")
            st.dataframe(grid, width="stretch")
    with tabs[2]:
        trend = area_survey.weekly(raw.pipe(area_survey.prepare))
        st.dataframe(trend.rename(columns={"week": "Week"}), hide_index=True, width="stretch")
    with tabs[3]:
        _how_it_works(number)

    st.caption(
        "The people who answer are the ones who chose to, so this shows what they say, not what everyone in the area thinks. "
        "Compare areas only when each has a fair number of answers."
    )
    fact_card(
        "Answers are volunteered through a WhatsApp survey. One answer per person per week; no phone numbers are stored.",
        SOURCE_METADATA["area_survey"]["name"],
        SOURCE_METADATA["area_survey"]["type"],
        "medium",
    )
    ctx.logger.log_analysis("area_ratings", ["area_survey"], "viewed area ratings")
