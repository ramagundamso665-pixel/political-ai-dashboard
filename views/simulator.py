import streamlit as st

import charts
import simulation
from components import empty_state, fact_card, section
from config import PARTIES, PARTY_LABELS, SOURCE_METADATA

TITLE = "What-If Simulator"

STEP = 0.5
RANGE = 15.0


def _reset():
    for party in PARTIES:
        st.session_state[f"sim_{party}"] = 0.0


def render(ctx, sidebar):
    section(
        "What-if simulator",
        "Move a party's vote share and see who leads. The points come from the other parties in "
        "proportion to what they hold, so every division still adds up.",
    )

    shares_sheet = ctx.sheets.get("division_shares")
    if shares_sheet is None or shares_sheet.empty:
        empty_state("No division-level tracking data is loaded, so there is nothing to simulate.")
        return

    shares, year = simulation.latest_round(shares_sheet)
    divisions = list(shares.index)

    scope_col, reset_col = st.columns([3, 1])
    with scope_col:
        scope = st.selectbox("Apply the shift to", ["All divisions"] + divisions)
    with reset_col:
        st.markdown("<div style='height:1.7rem'></div>", unsafe_allow_html=True)
        st.button("Reset", on_click=_reset, width="stretch")

    cols = st.columns(len(PARTIES))
    shifts = {}
    for col, party in zip(cols, PARTIES):
        shifts[party] = col.slider(
            f"{PARTY_LABELS.get(party, party)} (points)",
            -RANGE, RANGE, 0.0, STEP,
            key=f"sim_{party}",
            format="%+.1f",
        )

    division = None if scope == "All divisions" else scope
    scenario = simulation.apply_shift(shares, shifts, division)
    now, then = simulation.summarize(shares), simulation.summarize(scenario)
    moved = any(shifts.values())

    m1, m2, m3 = st.columns(3)
    m1.metric(
        "Leader",
        PARTY_LABELS.get(then["leader"], then["leader"]),
        None if then["leader"] == now["leader"] else f"was {PARTY_LABELS.get(now['leader'], now['leader'])}",
        delta_color="off",
    )
    m2.metric(
        f"Lead over {PARTY_LABELS.get(then['runner_up'], then['runner_up'])}",
        f"{then['margin']}pt",
        # a lead over a different runner-up isn't comparable to the lead it replaces
        f"{then['margin'] - now['margin']:+.1f}pt vs now" if moved and then["leader"] == now["leader"] else None,
    )
    m3.metric(
        "Divisions led",
        " · ".join(f"{PARTY_LABELS.get(p, p)} {n}" for p, n in then["divisions_led"].items() if n),
    )

    st.plotly_chart(charts.what_if(now["average"], then["average"]), width="stretch")

    st.markdown("##### What it would take")
    any_line = False
    for party in PARTIES:
        if party == now["leader"]:
            continue
        needed = simulation.points_to_overtake(shares, party)
        name = PARTY_LABELS.get(party, party)
        leader = PARTY_LABELS.get(now["leader"], now["leader"])
        if needed is None:
            st.markdown(f"- **{name}** cannot overtake {leader} on a uniform shift of up to 25 points.")
        else:
            st.markdown(f"- **{name}** needs about **+{needed} points** across every division to overtake {leader}.")
        any_line = True
    if not any_line:
        st.caption("Nobody is ahead of the leader to compare against.")

    with st.expander("Division by division"):
        table = scenario.round(1).copy()
        table.insert(0, "Leads", scenario[[p for p in PARTIES if p in scenario.columns]].idxmax(axis=1).map(lambda p: PARTY_LABELS.get(p, p)))
        st.dataframe(table.reset_index(), hide_index=True, width="stretch")

    fact_card(
        f"Starting point is the {year} division tracking round. Averages are a plain mean across "
        f"{len(divisions)} divisions, not weighted by votes, because no division-level turnout is on file. "
        "This is arithmetic on today's numbers, not a forecast.",
        SOURCE_METADATA["division_shares"]["name"],
        SOURCE_METADATA["division_shares"]["type"],
        "medium",
    )

    if moved:
        detail = ", ".join(f"{p} {pts:+.1f}" for p, pts in shifts.items() if pts)
        ctx.logger.log_analysis("what_if", ["division_shares"], f"{scope}: {detail} -> {then['leader']} by {then['margin']}")
