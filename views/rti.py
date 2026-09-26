from datetime import date

import pandas as pd
import streamlit as st

import db
import registers
from components import empty_state, section
from config import is_valid_api_key

TITLE = "RTI Tracker"
TABLE = "rti_requests"

SETUP = "Run supabase/registers.sql once in the Supabase SQL editor to create the RTI and local-issue tables."


def _secrets():
    url = st.secrets.get("SUPABASE_URL", None) if hasattr(st, "secrets") else None
    key = st.secrets.get("SUPABASE_SERVICE_KEY", None) if hasattr(st, "secrets") else None
    return url, key


@st.cache_data(ttl=30, show_spinner=False)
def _load(url, key):
    return registers.fetch(url, key, TABLE)


def _add_form(url, key):
    with st.form("add_rti", clear_on_submit=True):
        subject = st.text_input("What was asked", placeholder="e.g. Funds spent on road repair in Shaikpet division, 2023-25")
        c1, c2 = st.columns(2)
        department = c1.text_input("Department", placeholder="e.g. GHMC Engineering, Jal Mandali")
        reference = c2.text_input("RTI reference number (optional)")
        c3, c4, c5 = st.columns(3)
        filed_on = c3.date_input("Filed on", value=date.today())
        status = c4.selectbox("Status", registers.RTI_STATUSES, index=1)
        division = c5.text_input("Division (optional)")
        notes = st.text_area("Notes (optional)", height=70)
        submitted = st.form_submit_button("Save RTI", type="primary")
    if not submitted:
        return
    if not subject.strip():
        st.warning("Say what the RTI asks.")
        return
    try:
        registers.add(url, key, TABLE, {
            "subject": subject.strip(), "department": department.strip(), "reference_no": reference.strip(),
            "filed_on": str(filed_on), "reply_due_on": str(registers.due_date(pd.Timestamp(filed_on)).date()),
            "status": status, "division": division.strip(), "notes": notes.strip(),
        })
        _load.clear()
        st.success(f"Saved. A reply is due by {registers.due_date(pd.Timestamp(filed_on)):%d %b %Y} (30 days).")
    except Exception as exc:
        st.error(f"Could not save: {exc}. {SETUP}")


def _list(url, key, df):
    for _, r in df.iterrows():
        with st.container(border=True):
            top, side = st.columns([5, 1])
            due = pd.to_datetime(r.get("reply_due_on"), errors="coerce")
            late = r["status"] in registers.OPEN_RTI and pd.notna(due) and due < pd.Timestamp(date.today())
            top.markdown(f"**{r['subject']}**" + ("  \n:red[Reply overdue]" if late else ""))
            bits = [db.as_text(r.get("department")), f"filed {db.as_text(r.get('filed_on'))}" if db.as_text(r.get("filed_on")) else None,
                    f"due {due:%d %b %Y}" if pd.notna(due) else None, db.as_text(r.get("reference_no"))]
            top.caption(" · ".join(b for b in bits if b))
            if db.as_text(r.get("reply_summary")):
                top.markdown(f"Reply: {r['reply_summary']}")
            with side.popover("Update"):
                status = st.selectbox("Status", registers.RTI_STATUSES, index=registers.RTI_STATUSES.index(r["status"]) if r["status"] in registers.RTI_STATUSES else 1, key=f"st_{r['id']}")
                reply = st.text_area("Reply summary", value=db.as_text(r.get("reply_summary")) or "", key=f"rp_{r['id']}", height=100)
                if st.button("Save", key=f"sv_{r['id']}"):
                    registers.change(url, key, TABLE, r["id"], {"status": status, "reply_summary": reply.strip()})
                    _load.clear()
                    st.rerun()
                if st.button("Delete", key=f"dl_{r['id']}"):
                    registers.remove(url, key, TABLE, r["id"])
                    _load.clear()
                    st.rerun()


def render(ctx, sidebar):
    section(
        "RTI tracker",
        "Right to Information requests your team has filed: what was asked, who was asked, when a reply is due, and what came back.",
    )
    url, key = _secrets()
    if not (is_valid_api_key(url, placeholder_prefix="https://REPLACE") and is_valid_api_key(key, placeholder_prefix="REPLACE")):
        st.info("Add SUPABASE_URL and SUPABASE_SERVICE_KEY to `.streamlit/secrets.toml` to enable this page.")
        return

    try:
        df = _load(url, key)
    except Exception:
        st.warning(f"The RTI table isn't there yet. {SETUP}")
        return

    if not df.empty:
        overdue = registers.rti_overdue(df)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Filed", len(df))
        c2.metric("Awaiting reply", int(df["status"].isin(registers.OPEN_RTI).sum()))
        c3.metric("Overdue", len(overdue))
        c4.metric("Replies in", int(df["status"].isin(["Reply received", "Partial reply", "Closed"]).sum()))

    tabs = st.tabs(["Requests", "Add an RTI"])
    with tabs[1]:
        _add_form(url, key)
    with tabs[0]:
        if df.empty:
            empty_state("No RTI logged yet. Use the Add an RTI tab.")
        else:
            pick = st.selectbox("Show", ["All"] + registers.RTI_STATUSES, key="rti_filter")
            _list(url, key, df if pick == "All" else df[df["status"] == pick])
    st.caption(
        "This is a log kept by your team. Nothing here is checked against any government record, and Ask AI is told "
        "so when it uses it. An RTI is answered within 30 days under the Act, so the due date is set to 30 days from filing."
    )
