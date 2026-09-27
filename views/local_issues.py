from datetime import date

import pandas as pd
import streamlit as st

import area_survey
import db
import registers
from components import empty_state, section
from config import is_valid_api_key

TITLE = "Local Issues"
TABLE = "local_issues"
SETUP = "Run supabase/registers.sql once in the Supabase SQL editor to create the RTI and local-issue tables."


def _secrets():
    url = st.secrets.get("SUPABASE_URL", None) if hasattr(st, "secrets") else None
    key = st.secrets.get("SUPABASE_SERVICE_KEY", None) if hasattr(st, "secrets") else None
    return url, key


@st.cache_data(ttl=30, show_spinner=False)
def _load(url, key):
    return registers.fetch(url, key, TABLE)


def _divisions(ctx):
    try:
        return sorted(ctx.sheets["division_shares"]["Division"].dropna().astype(str).unique())
    except Exception:
        return []


def _add_form(ctx, url, key):
    with st.form("add_issue", clear_on_submit=True):
        title = st.text_input("Issue", placeholder="e.g. Open drain overflowing near the Road No. 45 junction")
        c1, c2, c3 = st.columns(3)
        category = c1.selectbox("Category", registers.CATEGORIES)
        severity = c2.selectbox("How serious", registers.SEVERITIES, index=1)
        status = c3.selectbox("Status", registers.ISSUE_STATUSES)
        divisions = _divisions(ctx)
        c4, c5, c6 = st.columns(3)
        division = c4.selectbox("Division", [""] + divisions) if divisions else c4.text_input("Division")
        booth = c5.text_input("Booth number (optional)", placeholder="e.g. 2A")
        location = c6.text_input("Street or landmark")
        source = st.text_input("Where it came from", placeholder="e.g. Field visit, resident WhatsApp group, news link")
        details = st.text_area("Details", height=80)
        link = st.text_input("Link (news, photo, complaint)")
        submitted = st.form_submit_button("Save issue", type="primary")
    if not submitted:
        return
    if not title.strip():
        st.warning("Describe the issue.")
        return
    try:
        registers.add(url, key, TABLE, {
            "title": title.strip(), "category": category, "severity": severity, "status": status, "division": division,
            "booth": booth.strip(), "location": location.strip(), "source": source.strip(), "details": details.strip(),
            "link": link.strip(), "reported_on": str(date.today()),
        })
        _load.clear()
        st.success("Saved.")
    except Exception as exc:
        st.error(f"Could not save: {exc}. {SETUP}")


def _list(url, key, df):
    for _, r in df.iterrows():
        with st.container(border=True):
            top, side = st.columns([5, 1])
            top.markdown(f"**{r['title']}**")
            where = " · ".join(x for x in (db.as_text(r.get("division")), f"booth {db.as_text(r.get('booth'))}" if db.as_text(r.get("booth")) else None, db.as_text(r.get("location"))) if x)
            top.caption(" · ".join(x for x in (db.as_text(r.get("category")), where, f"{r['severity']} severity", r["status"]) if x))
            if db.as_text(r.get("details")):
                top.write(r["details"])
            if db.as_text(r.get("link")):
                top.markdown(f"[Link]({r['link']})")
            with side.popover("Update"):
                status = st.selectbox("Status", registers.ISSUE_STATUSES, index=registers.ISSUE_STATUSES.index(r["status"]) if r["status"] in registers.ISSUE_STATUSES else 0, key=f"is_{r['id']}")
                if st.button("Save", key=f"isv_{r['id']}"):
                    registers.change(url, key, TABLE, r["id"], {"status": status})
                    _load.clear()
                    st.rerun()
                if st.button("Delete", key=f"idl_{r['id']}"):
                    registers.remove(url, key, TABLE, r["id"])
                    _load.clear()
                    st.rerun()


@st.cache_data(ttl=60, show_spinner=False)
def _ratings(url, key):
    try:
        return area_survey.prepare(registers.fetch(url, key, "area_ratings"))
    except Exception:
        return None


def _board(ctx, url, key, df):
    """Which areas are facing which problems, from everything the team has: logged issues, newspaper items, WhatsApp answers."""
    known = _divisions(ctx)
    ratings = _ratings(url, key)
    board = area_survey.board(df, ratings, known)
    if board.empty:
        empty_state("Nothing to show yet. Log issues, upload newspaper pages, or start the WhatsApp survey.")
        return
    st.markdown("**Areas, most serious first**")
    st.dataframe(board, hide_index=True, width="stretch")
    grid = area_survey.area_by_category(df)
    if not grid.empty:
        st.markdown("**Open issues by area and category**")
        st.dataframe(grid, width="stretch")
    st.caption(
        "Logged issues include what staff entered and what was read from newspaper pages. WhatsApp figures are volunteered answers, shown only "
        f"for areas with at least {area_survey.MIN_RESPONSES} of them. Areas are matched by name against the constituency's divisions."
    )


def render(ctx, sidebar):
    section(
        "Local issues",
        "Problems residents raise, by division and booth: roads, water, drains, lights and so on. Track each until it is fixed.",
    )
    url, key = _secrets()
    if not (is_valid_api_key(url, placeholder_prefix="https://REPLACE") and is_valid_api_key(key, placeholder_prefix="REPLACE")):
        st.info("Add SUPABASE_URL and SUPABASE_SERVICE_KEY to `.streamlit/secrets.toml` to enable this page.")
        return
    try:
        df = _load(url, key)
    except Exception:
        st.warning(f"The local-issues table isn't there yet. {SETUP}")
        return

    if not df.empty:
        c1, c2, c3 = st.columns(3)
        openish = df[~df["status"].isin(["Resolved", "Dropped"])]
        c1.metric("Logged", len(df))
        c2.metric("Still open", len(openish))
        c3.metric("High severity, open", int((openish["severity"] == "High").sum()))

    tabs = st.tabs(["Issues", "Area board", "Add an issue"])
    with tabs[2]:
        _add_form(ctx, url, key)
    with tabs[0]:
        if df.empty:
            empty_state("No issues logged yet. Use the Add an issue tab.")
        else:
            c1, c2, c3 = st.columns(3)
            cat = c1.selectbox("Category", ["All"] + registers.CATEGORIES, key="iss_cat")
            stat = c2.selectbox("Status", ["All"] + registers.ISSUE_STATUSES, key="iss_stat")
            div = c3.selectbox("Division", ["All"] + sorted(df["division"].dropna().unique()), key="iss_div")
            view = df
            if cat != "All":
                view = view[view["category"] == cat]
            if stat != "All":
                view = view[view["status"] == stat]
            if div != "All":
                view = view[view["division"] == div]
            _list(url, key, view)
    with tabs[1]:
        _board(ctx, url, key, df)
    st.caption("A log kept by your team. Entries are what staff typed in, not verified facts, and Ask AI is told so.")
