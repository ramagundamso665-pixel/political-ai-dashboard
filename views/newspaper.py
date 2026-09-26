from datetime import date

import pandas as pd
import streamlit as st

import newspaper_reader
import registers
from components import empty_state, fact_card, section
from config import SOURCE_METADATA, is_valid_api_key

TITLE = "Newspaper Clippings"
PAPERS = ["Eenadu", "Sakshi", "Andhra Jyothy", "Namaste Telangana", "Telangana Today", "The Hindu", "Deccan Chronicle", "Other"]


def _supabase():
    url = st.secrets.get("SUPABASE_URL", None) if hasattr(st, "secrets") else None
    key = st.secrets.get("SUPABASE_SERVICE_KEY", None) if hasattr(st, "secrets") else None
    ok = is_valid_api_key(url, placeholder_prefix="https://REPLACE") and is_valid_api_key(key, placeholder_prefix="REPLACE")
    return (url, key) if ok else (None, None)


def _save(rows, paper, day):
    url, key = _supabase()
    if not url:
        return "Add SUPABASE_URL and SUPABASE_SERVICE_KEY to save."
    try:
        for r in rows:
            registers.add(url, key, "local_issues", {
                "title": r["Issue"], "category": r["Category"], "division": r["Area"], "severity": r["Severity"], "status": "Open",
                "source": f"Newspaper: {paper}, {day:%d %b %Y}", "details": "Read from a newspaper clipping; check against the printed page.",
                "reported_on": str(day),
            })
        return None
    except Exception as exc:
        return f"Could not save: {exc}. Has supabase/registers.sql been run?"


def render(ctx, sidebar):
    section(
        "Newspaper clippings",
        "Photograph the local page of a paper, upload it, and the reader complaints on it become a checked list of local issues.",
    )
    if not is_valid_api_key(ctx.api_key):
        st.info("Add an OpenAI key to read page images.")
        return

    c1, c2 = st.columns(2)
    paper = c1.selectbox("Newspaper", PAPERS, key="np_paper")
    day = c2.date_input("Date of the edition", value=date.today(), key="np_day")
    files = st.file_uploader("Page photos or scans (JPG or PNG, up to 6)", type=["jpg", "jpeg", "png"], accept_multiple_files=True, key="np_files")
    files = (files or [])[:6]

    if st.button("Read the pages", type="primary", disabled=not files, key="np_read"):
        found, problems = [], []
        with st.spinner("Reading the pages"):
            for f in files:
                res = newspaper_reader.read_page(f.getvalue(), ctx.api_key)
                if res["ok"]:
                    found += [{**it, "file": f.name} for it in res["items"]]
                else:
                    problems.append(f"{f.name}: {res['error']}")
        st.session_state["np_found"] = found
        st.session_state["np_problems"] = problems
        st.session_state["np_meta"] = (paper, day)

    for p in st.session_state.get("np_problems", []):
        st.warning(p)
    found = st.session_state.get("np_found")
    if found is None:
        empty_state("Upload one or more pages, then choose Read the pages.")
    elif not found:
        empty_state("No local complaints were found on those pages.")
    else:
        st.markdown(f"**{len(found)} items found.** Correct anything that is wrong, untick what you don't want, then save.")
        table = pd.DataFrame({
            "Keep": True, "Issue": [i["title"] for i in found], "Category": [i["category"] for i in found],
            "Area": [i["area"] for i in found], "Severity": [i["severity"] for i in found], "Page": [i["file"] for i in found],
        })
        edited = st.data_editor(
            table, hide_index=True, width="stretch", key="np_editor", disabled=["Page"],
            column_config={
                "Category": st.column_config.SelectboxColumn(options=registers.CATEGORIES, required=True),
                "Severity": st.column_config.SelectboxColumn(options=registers.SEVERITIES, required=True),
            },
        )
        keep = edited[edited["Keep"]]
        saved_paper, saved_day = st.session_state.get("np_meta", (paper, day))
        if st.button(f"Save {len(keep)} to Local Issues", disabled=keep.empty, key="np_save"):
            error = _save(keep.to_dict("records"), saved_paper, saved_day)
            if error:
                st.error(error)
            else:
                st.success(f"Saved {len(keep)} issues, marked as from {saved_paper}. They are in the Local Issues page.")
                st.session_state["np_found"] = None

    st.caption(
        "Only a one-line summary in our own words, the area and the paper are kept, not the newspaper's text. A model reads the page, "
        "and Telugu print, small type or a crooked photo can be misread, so every line needs a look before saving."
    )
    fact_card(
        "Items are read from published newspaper pages by a vision model and then checked by staff. They are reports of what "
        "the paper printed, not verified facts about the problem.",
        SOURCE_METADATA["newspaper_clippings"]["name"],
        SOURCE_METADATA["newspaper_clippings"]["type"],
        "low",
    )
    ctx.logger.log_analysis("newspaper_clippings", ["newspaper_clippings"], "opened the clippings reader")
