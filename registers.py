"""Staff-kept registers: RTI requests and local issues.

Both live in Supabase (see supabase/registers.sql) and are written through the service key, so
they sit behind the app password like everything else. Nothing here is verified by the app: it
is what staff typed in, and is labelled that way wherever it is shown to the AI.
"""

from datetime import date

import pandas as pd

import db

RTI_STATUSES = ["Draft", "Filed", "Reply received", "Partial reply", "Rejected", "First appeal filed", "Closed"]
OPEN_RTI = {"Draft", "Filed", "Partial reply", "First appeal filed"}
ISSUE_STATUSES = ["Open", "In progress", "Raised with authority", "Resolved", "Dropped"]
SEVERITIES = ["Low", "Medium", "High"]
CATEGORIES = ["Roads", "Water supply", "Drainage and flooding", "Garbage and sanitation", "Street lights",
              "Parks and playgrounds", "Traffic and parking", "Encroachment", "Health", "Schools", "Power",
              "Safety", "Welfare schemes", "Other"]
RTI_DAYS = 30  # the Act's time for a reply


def fetch(url, key, table):
    try:
        return db._rest(url, key, table, {"order": "created_at.desc"})
    except Exception:
        raise


def _clean(row):
    return {k: (v if v not in ("", None) else None) for k, v in row.items()}


def add(url, key, table, row):
    db.insert_row(url, key, table, _clean(row))


def change(url, key, table, row_id, changes):
    db.update_rows(url, key, table, {"id": f"eq.{row_id}"}, _clean(changes))


def remove(url, key, table, row_id):
    db.delete_rows(url, key, table, {"id": f"eq.{row_id}"})


def due_date(filed_on):
    return filed_on + pd.Timedelta(days=RTI_DAYS)


def rti_overdue(df, today=None):
    """Open requests whose reply date has passed."""
    if df.empty:
        return df
    today = pd.Timestamp(today or date.today())
    due = pd.to_datetime(df["reply_due_on"], errors="coerce")
    return df[df["status"].isin(OPEN_RTI) & due.notna() & (due < today)]


def context_text(rti, issues):
    """The registers as plain text for the AI, marked as staff-entered and unverified."""
    lines = []
    if rti is not None and not rti.empty:
        lines.append("RTI REQUESTS (entered by campaign staff, not independently verified):")
        for _, r in rti.iterrows():
            lines.append(
                f"- {db.as_text(r.get('subject'))} | department {db.as_text(r.get('department')) or 'n/a'} | "
                f"filed {db.as_text(r.get('filed_on')) or 'n/a'} | status {db.as_text(r.get('status'))} | "
                f"reply: {db.as_text(r.get('reply_summary')) or 'none recorded'}"
            )
    if issues is not None and not issues.empty:
        lines.append("LOCAL ISSUES (entered by campaign staff, not independently verified):")
        for _, r in issues.iterrows():
            where = ", ".join(x for x in (db.as_text(r.get("division")), db.as_text(r.get("location"))) if x) or "location n/a"
            lines.append(
                f"- {db.as_text(r.get('title'))} | {db.as_text(r.get('category')) or 'other'} | {where} | "
                f"severity {db.as_text(r.get('severity'))} | status {db.as_text(r.get('status'))}"
            )
    return "\n".join(lines)
