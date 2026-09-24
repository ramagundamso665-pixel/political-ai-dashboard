import html

import pandas as pd
import streamlit as st

from components import empty_state, section
from config import SHEET_KEY_MAP, SOURCE_METADATA
from validation import validate_workbook

TITLE = "Data Check"

BADGE = {"error": "badge-conflict", "warning": "badge-external", "info": "badge-internal"}


def _show_issues(issues):
    if not issues:
        st.success("No problems found. Shares add up, deltas match, and no point sits under the wrong party.")
        return
    counts = {level: sum(1 for i in issues if i["severity"] == level) for level in BADGE}
    st.caption(f"{counts['error']} error(s) · {counts['warning']} warning(s) · {counts['info']} note(s)")
    for issue in issues:
        st.markdown(
            f'<span class="badge {BADGE[issue["severity"]]}">{issue["severity"].upper()}</span> '
            f'<strong>{html.escape(issue["sheet"])}</strong> — {html.escape(issue["message"])}',
            unsafe_allow_html=True,
        )


def _current(ctx):
    st.markdown(f"Loaded from **{ctx.data_source}**.")
    issues = validate_workbook(ctx.sheets)
    _show_issues(issues)

    st.markdown("##### Sheet by sheet")
    rows = []
    for key, report in ctx.quality_reports.items():
        meta = SOURCE_METADATA.get(key, {})
        rows.append({
            "Sheet": key,
            "Source": meta.get("name", ""),
            "Type": meta.get("type", ""),
            "Rows": report["rows_count"],
            "Blank cells": report["missing_values"],
            "Quality": f"{report['data_quality_score']}%",
        })
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")


def _upload():
    st.markdown(
        "Drop in a new workbook to test it before it replaces anything. Nothing is saved: this only reports "
        "what the checks find."
    )
    uploaded = st.file_uploader("Excel workbook", type=["xlsx"])
    if not uploaded:
        return

    try:
        raw = pd.read_excel(uploaded, sheet_name=None)
    except Exception as exc:
        st.error(f"Couldn't read that file: {exc}")
        return

    sheets = {SHEET_KEY_MAP[name]: df for name, df in raw.items() if name in SHEET_KEY_MAP}
    ignored = [name for name in raw if name not in SHEET_KEY_MAP]
    if ignored:
        st.caption(f"Ignored sheets that aren't part of the data model: {', '.join(ignored)}")
    if not sheets:
        empty_state("None of the sheet names match the expected ones (Division_Shares, Surveys, and so on).")
        return

    _show_issues(validate_workbook(sheets))


def render(ctx, sidebar):
    section(
        "Data check",
        "Do the numbers agree with each other? Shares add up, changes match the tables they came from, "
        "official counts match their percentages, and no point sits under the wrong party.",
    )
    current, upload = st.tabs(["Current data", "Check a new file"])
    with current:
        _current(ctx)
    with upload:
        _upload()
