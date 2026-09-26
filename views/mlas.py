import pandas as pd
import streamlit as st

import mla_history as mlas
from components import empty_state, fact_card, section
from config import PARTY_LABELS, SOURCE_METADATA

TITLE = "MLAs 2014-2023"


@st.cache_data(show_spinner=False)
def _load():
    return mlas.table()


def _label(party):
    return PARTY_LABELS.get(party, party)


def _all(df):
    c1, c2, c3 = st.columns([1.2, 1.2, 2])
    parties = sorted(set(df["party_2023"]))
    party = c1.selectbox("Party today", ["All"] + parties, format_func=lambda p: p if p == "All" else _label(p), key="mla_party")
    terms = c2.selectbox("Terms in a row", ["All", "1 (new in 2023)", "2 or more", "3 (all three)"], key="mla_terms")
    find = c3.text_input("Find a seat or MLA", placeholder="e.g. Sircilla or Harish", key="mla_find")
    view = df
    if party != "All":
        view = view[view["party_2023"] == party]
    if terms.startswith("1"):
        view = view[view["terms_in_a_row"] == 1]
    elif terms.startswith("2"):
        view = view[view["terms_in_a_row"] >= 2]
    elif terms.startswith("3"):
        view = view[view["terms_in_a_row"] == 3]
    if find.strip():
        text = find.strip().lower()
        hay = view[["seat", "mla_2014", "mla_2018", "mla_2023"]].astype(str).agg(" ".join, axis=1).str.lower()
        view = view[hay.str.contains(text, regex=False)]
    table = view.rename(columns={
        "seat": "Seat", "mla_2014": "MLA 2014", "party_2014": "Party", "mla_2018": "MLA 2018", "party_2018": "Party ",
        "mla_2023": "MLA 2023", "party_2023": "Party  ", "terms_in_a_row": "Terms in a row",
    })[["Seat", "MLA 2014", "Party", "MLA 2018", "Party ", "MLA 2023", "Party  ", "Terms in a row"]]
    st.caption(f"{len(table)} seats")
    st.dataframe(table, hide_index=True, width="stretch")
    st.download_button("Download as CSV", view.to_csv(index=False).encode(), "telangana_mlas_2014_2023.csv", "text/csv")


def _turnover(df):
    c1, c2, c3 = st.columns(3)
    c1.metric("2014 winners who won again in 2018", int(df["kept_2018"].sum()))
    c2.metric("2018 winners who won again in 2023", int(df["kept_2023"].sum()))
    c3.metric("Won all three", int((df["terms_in_a_row"] == 3).sum()))
    rows = []
    for party in ["BRS", "INC", "BJP", "AIMIM"]:
        held = df[df["party_2018"] == party]
        rows.append({"Party": _label(party), "Seats won in 2018": len(held), "Same MLA won again in 2023": int(held["kept_2023"].sum()),
                     "Share": f"{held['kept_2023'].mean() * 100:.0f}%" if len(held) else ""})
    st.markdown("**How many of each party's 2018 winners won again in 2023**")
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    st.caption("An MLA counts as re-elected when the same person won the seat again, for whichever party.")


def _switchers(df):
    table = mlas.party_switch(df)
    if table.empty:
        empty_state("No one won again under a different party.")
        return
    st.dataframe(table, hide_index=True, width="stretch")
    st.caption(
        "Winners who won the same seat again, but for a different party than the time before. A change of party by an MLA "
        "in the middle of a term is not shown, so the list understates how many actually crossed over."
    )


def render(ctx, sidebar):
    section(
        "MLAs, 2014 to 2023",
        "Who held each of the 119 seats after each of the last three elections, and who kept them.",
    )
    df = _load()
    tabs = st.tabs(["All seats", "Re-elected", "Won again under a new party", "What this does not cover"])
    with tabs[0]:
        _all(df)
    with tabs[1]:
        _turnover(df)
    with tabs[2]:
        _switchers(df)
    with tabs[3]:
        st.markdown(
            """
**Attendance, questions asked and debate contributions are not here, because nobody publishes them member by member.**

- The Telangana Legislature website has the official debates for every sitting since June 2014 (259 sittings up to 2026), but as scanned page images, about 60 MB and 126 pages for a single day. Reading them all would mean text recognition on some 30,000 pages in English and Telugu, then working out who was speaking.
- PRS Legislative Research tracks attendance and questions for members of Parliament, not for state MLAs.
- The dependable route is an RTI to the Legislature Secretariat asking for each member's attendance and number of questions, session by session. Log it under **RTI Tracker**, and the reply can be added here.

Also missing: mid-term changes of party, and MLAs who changed after a by-election (Jubilee Hills 2025 is not in this table).
            """
        )
    fact_card(
        "The 2018 and 2023 winners are from the Election Commission's Detailed Results reports. The 2014 winners are from the open "
        "Lok Dhaba compilation of the Commission's 2014 results, checked so that every seat's votes add up and the winners by party "
        "match the known 2014 tally. Whether two spellings are the same person is judged by the name, so a few could be wrong.",
        SOURCE_METADATA["eci_2023"]["name"] + " (and 2018; 2014 from Lok Dhaba)",
        SOURCE_METADATA["eci_2023"]["type"],
        "high",
    )
