import pandas as pd
import streamlit as st

import charts
import statewide
from components import empty_state, fact_card, section
from config import PARTY_LABELS, SOURCE_METADATA

TITLE = "Telangana Seats"

SEAT_COLUMNS = {
    "seat": "Seat",
    "reservation": "Reserved",
    "winner": "Winner",
    "winner_party": "Party",
    "runner_up": "Runner-up",
    "runner_up_party": "Runner-up party",
    "margin_votes": "Margin (votes)",
    "margin_pct": "Margin %",
    "turnout_pct": "Turnout %",
    "electors": "Electors",
}


@st.cache_data(show_spinner=False)
def _load():
    return statewide.load()


@st.cache_data(show_spinner=False)
def _load_2018():
    return statewide.load_year(2018)


def _table(df):
    out = df[list(SEAT_COLUMNS)].rename(columns=SEAT_COLUMNS)
    out["Reserved"] = out["Reserved"].replace({"GENERAL": ""})
    return out


def _headline(seats, candidates):
    tally = statewide.seat_tally(seats)
    cols = st.columns(5)
    cols[0].metric("Seats", len(seats))
    short = {"INC": "Congress"}
    for col, party in zip(cols[1:], ["INC", "BRS", "BJP", "AIMIM"]):
        col.metric(f"{short.get(party, party)} won", int(tally.get(party, 0)))
    c1, c2, c3 = st.columns(3)
    c1.metric("Decided by under 5%", len(statewide.battlegrounds(seats)))
    c2.metric(f"Decided by under {statewide.RAZOR_VOTES:,} votes", int((seats["margin_votes"] < statewide.RAZOR_VOTES).sum()))
    c3.metric("Average turnout", f"{seats['turnout_pct'].mean():.1f}%")


def _all_seats(seats):
    c1, c2, c3 = st.columns([1.2, 1.2, 2])
    parties = ["All"] + list(statewide.seat_tally(seats).index)
    winner = c1.selectbox("Won by", parties, format_func=lambda p: p if p == "All" else PARTY_LABELS.get(p, p))
    reserved = c2.selectbox("Seat type", ["All", "General", "SC", "ST"])
    find = c3.text_input("Find a seat or winner", placeholder="e.g. Karimnagar or Revanth")

    view = seats
    if winner != "All":
        view = view[view["winner_party"] == winner]
    if reserved != "All":
        view = view[view["reservation"] == reserved.upper()]
    if find.strip():
        needle = find.strip().lower()
        view = view[view["seat"].str.lower().str.contains(needle) | view["winner"].str.lower().str.contains(needle)]

    st.caption(f"{len(view)} of {len(seats)} seats")
    st.dataframe(_table(view), hide_index=True, width="stretch")


def _battlegrounds(seats, candidates):
    st.plotly_chart(charts.margin_distribution(seats), width="stretch")

    st.markdown("##### Closest contests")
    close = statewide.battlegrounds(seats).copy()
    close["Votes that would flip it"] = close.apply(statewide.swing_needed, axis=1)
    show = _table(close)
    show.insert(len(show.columns), "Votes that would flip it", close["Votes that would flip it"].values)
    st.dataframe(show, hide_index=True, width="stretch")
    st.caption("A seat flips if half the margin (plus one) of voters had switched to the runner-up.")

    st.markdown("##### Seats a party lost narrowly")
    party = st.selectbox("Party", ["BRS", "INC", "BJP", "AIMIM"], format_func=lambda p: PARTY_LABELS.get(p, p), key="seats_lost_party")
    lost = statewide.lost_narrowly(seats, party)
    if lost.empty:
        empty_state(f"{PARTY_LABELS.get(party, party)} did not finish second in any seat by under 5%.")
    else:
        st.dataframe(_table(lost), hide_index=True, width="stretch")
        st.caption(f"{len(lost)} seat(s) where {PARTY_LABELS.get(party, party)} came second by under 5% of the votes polled.")


def _one_seat(seats, candidates):
    seat = st.selectbox("Constituency", list(seats["seat"]), key="seats_pick")
    row = seats[seats["seat"] == seat].iloc[0]
    rows = statewide.seat_candidates(candidates, seat)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Electors", f"{int(row['electors']):,}")
    c2.metric("Votes polled", f"{int(row['votes_polled']):,}", f"{row['turnout_pct']}% turnout", delta_color="off")
    c3.metric("Winner", f"{row['winner_party']}", row["winner"], delta_color="off")
    c4.metric("Margin", f"{int(row['margin_votes']):,} votes", f"{row['margin_pct']}%", delta_color="off")

    real = rows[rows["Party"] != "NOTA"]
    st.plotly_chart(charts.seat_shares(real), width="stretch")
    st.dataframe(rows, hide_index=True, width="stretch")
    if seat == "Jubilee Hills":
        st.info("Jubilee Hills also has the full campaign analysis. Use the other pages in the sidebar.")


def _change_since_2018(seats, candidates):
    try:
        seats18, cands18 = _load_2018()
    except FileNotFoundError:
        empty_state("The 2018 results file is missing. Run pipeline/fetch_eci_results.py --year 2018.")
        return

    changes = statewide.seat_changes(seats18, seats)
    swing = statewide.swing_by_seat(cands18, candidates)
    table = changes.merge(swing, on="seat_no")
    won18, won23 = statewide.seat_tally(seats18), statewide.seat_tally(seats)

    c = st.columns(4)
    c[0].metric("Seats that changed hands", int(changes["changed_hands"].sum()), f"of {len(changes)}", delta_color="off")
    for col, party, name in zip(c[1:], ["INC", "BRS", "BJP"], ["Congress", "BRS", "BJP"]):
        col.metric(f"{name} seats", int(won23.get(party, 0)), f"{int(won23.get(party, 0)) - int(won18.get(party, 0)):+d} vs 2018")

    share18, share23 = statewide.vote_share_by_party(cands18), statewide.vote_share_by_party(candidates)
    left, right = st.columns([3, 2])
    with left:
        st.plotly_chart(charts.vote_share_compare(share18, share23, statewide.MAJOR), width="stretch")
    with right:
        st.markdown("##### Where the seats went")
        flow = statewide.flows(changes).rename(columns={"winner_then": "2018 winner", "winner_now": "2023 winner"})
        st.dataframe(flow, hide_index=True, width="stretch")

    st.markdown("##### Seat by seat")
    f1, f2 = st.columns([1, 2])
    only_moved = f1.checkbox("Only seats that changed hands", value=True)
    gained = f2.selectbox("Biggest gain in vote share for", ["Any"] + statewide.MAJOR, format_func=lambda p: p if p == "Any" else PARTY_LABELS.get(p, p))
    view = table[table["changed_hands"]] if only_moved else table
    if gained != "Any":
        view = view.sort_values(gained, ascending=False).head(15)
    view = view.assign(**{"Changed hands": view["changed_hands"].map({True: "Yes", False: ""})})
    show = view[["seat_now", "winner_then", "winner_now", "Changed hands", "margin_pct_now", "BRS", "INC", "BJP", "AIMIM"]].rename(
        columns={
            "seat_now": "Seat", "winner_then": "2018 winner", "winner_now": "2023 winner", "margin_pct_now": "2023 margin %",
            "BRS": "BRS swing (pts)", "INC": "Congress swing (pts)", "BJP": "BJP swing (pts)", "AIMIM": "AIMIM swing (pts)",
        }
    )
    st.dataframe(show, hide_index=True, width="stretch")
    st.caption("Swing is the change in a party's share of the votes polled in that seat between 2018 and 2023, in percentage points. 2018's TRS is shown as BRS.")


def render(ctx, sidebar):
    section(
        "Telangana seats",
        "All 119 assembly constituencies, 2023 and 2018, straight from the Election Commission's "
        "published results. Every seat's figures add up exactly to its own turnout line.",
    )
    try:
        seats, candidates = _load()
    except FileNotFoundError:
        empty_state("The statewide results files are missing. Run pipeline/fetch_eci_2023.py to create them.")
        return

    _headline(seats, candidates)
    st.markdown("---")
    tabs = st.tabs(["Votes and seats", "All seats", "Battlegrounds", "Change since 2018", "One seat"])
    with tabs[0]:
        table = statewide.seats_vs_votes(seats, candidates)
        st.plotly_chart(charts.seats_vs_votes(table), width="stretch")
        st.dataframe(table, hide_index=True, width="stretch")
        table["gap"] = table["Seat share %"] - table["Vote share %"]
        gain, loss = table.loc[table["gap"].idxmax()], table.loc[table["gap"].idxmin()]
        st.caption(
            f"{PARTY_LABELS.get(gain['Party'], gain['Party'])} took {gain['Seat share %']:.0f}% of the seats with "
            f"{gain['Vote share %']:.0f}% of the votes; {PARTY_LABELS.get(loss['Party'], loss['Party'])} got "
            f"{loss['Vote share %']:.0f}% of the votes but {loss['Seat share %']:.0f}% of the seats. "
            "First-past-the-post rewards finishing first, not vote share."
        )
    with tabs[1]:
        _all_seats(seats)
    with tabs[2]:
        _battlegrounds(seats, candidates)
    with tabs[3]:
        _change_since_2018(seats, candidates)
    with tabs[4]:
        _one_seat(seats, candidates)

    fact_card(
        "Results are the Election Commission's published Detailed Results for the 2023 and 2018 Telangana assembly "
        "elections. Every constituency is checked against its own turnout line before it is used.",
        SOURCE_METADATA["eci_2023"]["name"],
        SOURCE_METADATA["eci_2023"]["type"],
        "high",
    )
    ctx.logger.log_analysis("telangana_seats", ["eci_2023"], "viewed statewide results")
