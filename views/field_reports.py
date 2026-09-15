import streamlit as st

import db
from components import empty_state, fact_card, section
from config import CONSTITUENCY_NAME, SOURCE_METADATA, is_valid_api_key

TITLE = "Field Reports"

STATUS_LABELS = {"new": "New", "reviewed": "Reviewed", "resolved": "Resolved"}


def _secrets():
    url = st.secrets.get("SUPABASE_URL", None) if hasattr(st, "secrets") else None
    key = st.secrets.get("SUPABASE_SERVICE_KEY", None) if hasattr(st, "secrets") else None
    return url, key


@st.cache_data(ttl=60, show_spinner=False)
def _load(url, key, constituency_name):
    cid = db.resolve_constituency_id(url, key, constituency_name)
    return cid, db.fetch_field_reports(url, key, cid)


def render(ctx, sidebar):
    section(
        "Field reports",
        "Issues submitted directly from the ground through the public intake form — "
        "unverified until reviewed here.",
    )

    url, key = _secrets()
    if not (is_valid_api_key(url, placeholder_prefix="https://REPLACE") and is_valid_api_key(key, placeholder_prefix="REPLACE")):
        st.info(
            "Add SUPABASE_URL and SUPABASE_SERVICE_KEY to `.streamlit/secrets.toml` to enable "
            "this page — it reads directly from the field-report form's submissions."
        )
        return

    try:
        cid, reports = _load(url, key, CONSTITUENCY_NAME)
    except Exception as exc:
        st.error(f"Could not reach Supabase: {exc}")
        return

    if reports.empty:
        empty_state("No field reports submitted yet.")
        fact_card(
            "0 reports on file",
            SOURCE_METADATA["field_reports"]["name"],
            SOURCE_METADATA["field_reports"]["type"],
            "low",
        )
        return

    counts = reports["status"].value_counts()
    c1, c2, c3 = st.columns(3)
    c1.metric("New", int(counts.get("new", 0)))
    c2.metric("Reviewed", int(counts.get("reviewed", 0)))
    c3.metric("Resolved", int(counts.get("resolved", 0)))

    st.markdown("---")

    status_filter = st.radio(
        "Show", ["new", "reviewed", "resolved", "all"], horizontal=True, index=0,
        format_func=lambda s: "All" if s == "all" else STATUS_LABELS[s],
    )
    shown = reports if status_filter == "all" else reports[reports["status"] == status_filter]

    if shown.empty:
        empty_state(f"No {STATUS_LABELS.get(status_filter, status_filter)} reports.")

    for _, r in shown.iterrows():
        with st.container(border=True):
            top = st.columns([3, 1])
            with top[0]:
                party_tag = f" · {r['party']}" if r.get("party") else ""
                st.markdown(f"**{r['division']}** — {r['category']}{party_tag}")
            with top[1]:
                st.caption(str(r["submitted_at"])[:16].replace("T", " "))

            st.write(r["issue_text"])

            meta_bits = []
            if r.get("reporter_name"):
                meta_bits.append(f"Reported by {r['reporter_name']}")
            if r.get("reporter_phone"):
                meta_bits.append(r["reporter_phone"])
            if meta_bits:
                st.caption(" · ".join(meta_bits))

            actions = st.columns(3)
            for i, status in enumerate(["new", "reviewed", "resolved"]):
                disabled = r["status"] == status
                if actions[i].button(
                    STATUS_LABELS[status], key=f"status_{r['id']}_{status}",
                    disabled=disabled, width="stretch",
                ):
                    db.update_field_report_status(url, key, r["id"], status)
                    _load.clear()
                    st.rerun()

    fact_card(
        f"{len(reports)} report(s) on file, {int(counts.get('new', 0))} awaiting review",
        SOURCE_METADATA["field_reports"]["name"],
        SOURCE_METADATA["field_reports"]["type"],
        "low",
    )

    ctx.logger.log_analysis("field_reports", ["field_reports"], f"{len(reports)} reports reviewed")
