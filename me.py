"""Who the app is working for: one seat, one leader, one party, chosen once in the sidebar and used by
every page. The campaign's own tracking data (surveys, division estimates, booth sheet, ground notes)
exists only for Jubilee Hills; for every other seat the app uses public data only and says so."""

import os

import pandas as pd
import streamlit as st

from config import PARTY_LABELS, normalize_party

ROOT = os.path.dirname(os.path.abspath(__file__))
CAMPAIGN_SEAT = "Jubilee Hills"          # the only seat with the campaign's own tracking data
DEFAULT_SEAT = CAMPAIGN_SEAT
OTHER = "Someone else…"


@st.cache_data(show_spinner=False)
def _results_2023():
    return pd.read_csv(os.path.join(ROOT, "data", "telangana_2023_candidates.csv"))


def seats():
    return sorted(_results_2023()["seat"].unique())


def candidates(seat, ctx=None):
    """(name, party, votes %) of the latest contest in the seat, winner first. For Jubilee Hills the 2025
    by-election in the campaign's results sheet is newer than the 2023 general election."""
    if seat == CAMPAIGN_SEAT and ctx is not None:
        try:
            h = ctx.sheets["historical_results"].copy()
            h["Year"] = pd.to_numeric(h["Year"], errors="coerce")
            latest = h[h["Year"] == h["Year"].max()].sort_values("Votes", ascending=False)
            rows = [(r["Candidate"], normalize_party(r["Party"]) or r["Party"], float(r["Pct"])) for _, r in latest.iterrows()]
            if rows:
                return rows, int(h["Year"].max())
        except Exception:
            pass
    c = _results_2023()
    rows = c[(c["seat"] == seat) & (c["party"] != "NOTA")].sort_values("rank").head(6)
    return [(r["candidate"], r["party"], float(r["pct"])) for _, r in rows.iterrows()], 2023


def picker(ctx):
    """The 'Working for' control at the top of the sidebar. Returns the choice."""
    all_seats = seats()
    seat = st.selectbox("Seat", all_seats, index=all_seats.index(DEFAULT_SEAT), key="me_seat")
    cands, year = candidates(seat, ctx)
    labels = [f"{n} ({p})" for n, p, _ in cands] + [OTHER]
    pick = st.selectbox("Working for", labels, index=0, key=f"me_who_{seat}",
                        help=f"Candidates in the {year} election here, winner first. Pick 'Someone else' for a new face.")
    if pick == OTHER:
        name = st.text_input("Name", key=f"me_name_{seat}", placeholder="Leader's name")
        party = st.selectbox("Party", ["INC", "BRS", "BJP", "AIMIM", "Other"], key=f"me_party_{seat}")
        leader = name.strip() or "(name not set)"
    else:
        leader, party, _ = cands[labels.index(pick)]
    st.session_state["me"] = {"seat": seat, "leader": leader, "party": party, "year": year,
                              "rivals": [(n, p) for n, p, _ in cands if p != party][:4]}
    return st.session_state["me"]


def get():
    return st.session_state.get("me") or {"seat": DEFAULT_SEAT, "leader": "", "party": "INC", "year": 2025, "rivals": []}


def has_campaign_data(seat=None):
    return (seat or get()["seat"]) == CAMPAIGN_SEAT


def party_label(p):
    return PARTY_LABELS.get(p, p)


def banner():
    """One line at the top of every page: who this is for, and what data exists for the seat."""
    m = get()
    extra = "" if has_campaign_data(m["seat"]) else \
        " · <span style='opacity:.75'>public data only (the campaign's own surveys and booth sheets cover Jubilee Hills)</span>"
    st.markdown(
        f"<div style='padding:8px 14px;border-radius:10px;background:rgba(37,99,235,.09);border:1px solid rgba(37,99,235,.25);"
        f"font-size:.95rem;margin-bottom:10px'>👤 Working for <b>{m['leader']}</b> · {party_label(m['party'])} · <b>{m['seat']}</b>{extra}</div>",
        unsafe_allow_html=True,
    )
