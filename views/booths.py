import pandas as pd
import streamlit as st

import booth_results as booth_data
import charts
from components import empty_state, fact_card, section
from config import PARTY_LABELS, SOURCE_METADATA

TITLE = "Booth Results"

PARTY_NAMES = {p: PARTY_LABELS.get(p, p) for p in booth_data.PARTIES}


@st.cache_data(show_spinner=False)
def _load():
    return booth_data.load()


def _table(df):
    out = pd.DataFrame(
        {
            "Booth": df["booth"],
            "Valid votes": df["valid_votes"],
            "BRS": df["BRS"],
            "Congress": df["INC"],
            "BJP": df["BJP"],
            "AIMIM": df["AIMIM"],
            "Won by": df["winner"].map(lambda p: PARTY_NAMES.get(p, p)),
            "Margin (votes)": df["margin_votes"],
            "Margin %": df["margin_pct"],
        }
    )
    return out


def _headline(df):
    won = booth_data.booths_won(df)
    total = booth_data.totals(df)
    cols = st.columns(5)
    cols[0].metric("Polling booths", len(df))
    for col, party in zip(cols[1:], booth_data.PARTIES):
        col.metric(f"{PARTY_NAMES[party]} won", int(won[party]))
    c1, c2, c3 = st.columns(3)
    c1.metric("EVM votes counted", f"{int(total['valid_votes']):,}")
    c2.metric("Average per booth", f"{df['valid_votes'].mean():.0f}")
    c3.metric("Decided by under 25 votes", int((df["margin_votes"] < 25).sum()))


def _strength(df):
    left, right = st.columns([1, 1])
    a = left.selectbox("First party", booth_data.PARTIES, index=0, format_func=PARTY_NAMES.get, key="booth_a")
    b = right.selectbox("Second party", booth_data.PARTIES, index=1, format_func=PARTY_NAMES.get, key="booth_b")
    if a == b:
        empty_state("Pick two different parties.")
        return
    st.plotly_chart(charts.booth_lead_curve(df, a, b), width="stretch")
    ahead = int(((df[f"{a}_pct"] - df[f"{b}_pct"]) > 0).sum())
    behind = int(((df[f"{a}_pct"] - df[f"{b}_pct"]) < 0).sum())
    st.caption(
        f"{PARTY_NAMES[a]} polled more than {PARTY_NAMES[b]} in {ahead} booths; {PARTY_NAMES[b]} was ahead in {behind}. "
        f"Comparison of these two parties only, whoever else was placed first."
    )
    st.plotly_chart(charts.booth_share_spread(df, booth_data.PARTIES), width="stretch")


def _extremes(df):
    party = st.selectbox("Party", booth_data.PARTIES, format_func=PARTY_NAMES.get, key="booth_extreme")
    n = st.slider("How many booths", 5, 40, 15, key="booth_extreme_n")
    show = ["booth", f"{party}_pct", party, "valid_votes", "winner"]
    names = {"booth": "Booth", f"{party}_pct": "Share %", party: "Votes", "valid_votes": "Valid votes", "winner": "Won by"}
    c1, c2 = st.columns(2)
    with c1:
        st.markdown(f"**{PARTY_NAMES[party]}'s strongest booths**")
        top = booth_data.strongest(df, party, n)[show].rename(columns=names)
        top["Won by"] = top["Won by"].map(lambda p: PARTY_NAMES.get(p, p))
        st.dataframe(top, hide_index=True, width="stretch")
    with c2:
        st.markdown(f"**{PARTY_NAMES[party]}'s weakest booths**")
        low = booth_data.weakest(df, party, n)[show].rename(columns=names)
        low["Won by"] = low["Won by"].map(lambda p: PARTY_NAMES.get(p, p))
        st.dataframe(low, hide_index=True, width="stretch")
    st.caption(
        "Booth numbers are polling station numbers on the Election Commission's sheet. The sheet has no address, "
        "so it can say which booth, not which street."
    )


def _close(df):
    n = st.slider("How many booths", 10, 60, 25, key="booth_close_n")
    st.dataframe(_table(booth_data.closest(df, n)), hide_index=True, width="stretch")
    st.caption("Booths where the top two parties were separated by the fewest votes.")


def _all(df):
    c1, c2 = st.columns([1, 2])
    winner = c1.selectbox("Won by", ["All"] + booth_data.PARTIES, format_func=lambda p: "All" if p == "All" else PARTY_NAMES[p], key="booth_won_by")
    find = c2.text_input("Booth number", placeholder="e.g. 2A or 17", key="booth_find")
    view = df
    if winner != "All":
        view = view[view["winner"] == winner]
    if find.strip():
        view = view[view["booth"].str.upper() == find.strip().upper()]
    table = _table(view)
    st.caption(f"{len(table)} booths")
    st.dataframe(table, hide_index=True, width="stretch")
    st.download_button("Download as CSV", table.to_csv(index=False).encode(), "jubilee_hills_2023_booths.csv", "text/csv")


def render(ctx, sidebar):
    section(
        "Booth results",
        "Jubilee Hills, 2023: what each of the 352 polling stations voted, from the Chief Electoral Officer's Form 20.",
    )
    try:
        df = _load()
    except FileNotFoundError:
        empty_state("The booth results file is missing.")
        return

    _headline(df)
    st.markdown("---")
    tabs = st.tabs(["Party strength", "Strongest and weakest", "Closest booths", "All booths"])
    with tabs[0]:
        _strength(df)
    with tabs[1]:
        _extremes(df)
    with tabs[2]:
        _close(df)
    with tabs[3]:
        _all(df)

    fact_card(
        "The sheet is a scanned image, so every figure was read off the scan and reconciled: each candidate's column "
        "adds up exactly to that candidate's EVM votes in the Election Commission's report. Postal votes (738 valid) "
        "are not counted in any booth. Shares here are of a booth's valid EVM votes.",
        SOURCE_METADATA["ceo_form20_2023"]["name"],
        SOURCE_METADATA["ceo_form20_2023"]["type"],
        "high",
    )
    ctx.logger.log_analysis("booth_results", ["ceo_form20_2023"], "viewed booth results")
