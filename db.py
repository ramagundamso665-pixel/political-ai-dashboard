"""Layer 0: Supabase-backed data loading. Reconstructs the same wide-format
sheets the app used to read from Book 13.xlsx (same column names, same shapes)
so analyzer.py, data_manager.py, and every view need zero changes — only where
the sheets come from changes.
"""

import pandas as pd
import requests


def _rest(supabase_url, service_key, table, params=None):
    resp = requests.get(
        f"{supabase_url}/rest/v1/{table}",
        headers={"apikey": service_key, "Authorization": f"Bearer {service_key}"},
        params=params or {},
        timeout=15,
    )
    resp.raise_for_status()
    return pd.DataFrame(resp.json())


def load_sheets_from_supabase(supabase_url, service_key, constituency_name):
    const_df = _rest(
        supabase_url, service_key, "constituencies",
        {"name": f"eq.{constituency_name}", "select": "id"},
    )
    if const_df.empty:
        raise ValueError(f"No constituency named {constituency_name!r} found in Supabase")
    cid = const_df.iloc[0]["id"]

    def fetch(table):
        return _rest(supabase_url, service_key, table, {"constituency_id": f"eq.{cid}"})

    sheets = {}

    demo = fetch("demographics")
    sheets["Demographics"] = demo.rename(columns={"metric": "Metric", "count": "Count"})[["Metric", "Count"]]

    ds = fetch("division_shares")
    ds_wide = ds.pivot_table(
        index=["division", "year"], columns="party", values="share_pct", aggfunc="first"
    ).reset_index().rename(columns={"division": "Division", "year": "Year"})
    sheets["Division_Shares"] = ds_wide

    dd = fetch("division_deltas")
    dd_wide = dd.pivot_table(
        index="division", columns="party", values="delta_pct", aggfunc="first"
    ).reset_index()
    dd_wide = dd_wide.rename(columns={"division": "Division"})
    dd_wide = dd_wide.rename(columns={p: f"{p}_Delta" for p in ["BRS", "INC", "BJP", "AIMIM"] if p in dd_wide.columns})
    sheets["Division_Deltas"] = dd_wide

    dp = fetch("demo_preferences")
    dp_wide = dp.pivot_table(
        index="subgroup", columns="party", values="share_pct", aggfunc="first"
    ).reset_index().rename(columns={"subgroup": "Subgroup"})
    sheets["Demo_Preferences"] = dp_wide

    sv = fetch("surveys")
    sv_wide = sv.pivot_table(
        index=["survey_name", "sample", "area", "year", "notes"],
        columns="party", values="share_pct", aggfunc="first",
    ).reset_index()
    sv_wide = sv_wide.rename(columns={
        "survey_name": "Survey", "sample": "Sample", "area": "Area", "year": "Year", "notes": "Notes",
    })
    sheets["Surveys"] = sv_wide

    hr = fetch("historical_results").rename(columns={
        "year": "Year", "party": "Party", "candidate": "Candidate",
        "votes": "Votes", "pct": "Pct", "turnout": "Turnout",
    })
    sheets["Historical_Results"] = hr[["Year", "Party", "Candidate", "Votes", "Pct", "Turnout"]]

    sm = fetch("social_media").rename(columns={
        "activity_date": "Date", "party": "Party", "posts": "#Posts", "likes": "Likes",
        "shares": "Shares", "comments": "Comments", "impressions": "Impressions",
        "reach": "Reach", "notes": "Notes",
    })
    sheets["Social_Media"] = sm[["Date", "Party", "#Posts", "Likes", "Shares", "Comments", "Impressions", "Reach", "Notes"]]

    # Notes is a per-(category, subcategory) constant but often null — pivoting
    # on it directly would silently drop null-note rows, since pandas excludes
    # NaN grouping keys by default. Looked up separately instead.
    gc = fetch("ground_campaign")
    notes_lookup = gc.groupby(["category", "subcategory"], dropna=False)["notes"].first()
    gc_wide = gc.pivot_table(
        index=["category", "subcategory"], columns="party", values="position_text", aggfunc="first"
    ).reset_index()
    gc_wide["Notes"] = gc_wide.apply(lambda r: notes_lookup.get((r["category"], r["subcategory"])), axis=1)
    gc_wide = gc_wide.rename(columns={"category": "Category", "subcategory": "Subcategory", "INC": "Congress"})
    sheets["Ground_Campaign"] = gc_wide

    ca = fetch("campaign_activity").rename(columns={
        "activity_date": "Date", "party": "Party", "leaders": "Leader(s) / VIP",
        "event_type": "Event Type", "area_division": "Area / Division",
        "attendance": "Attendance", "remarks": "Remarks",
    })
    sheets["Campaign_Activity"] = ca[
        ["Date", "Party", "Leader(s) / VIP", "Event Type", "Area / Division", "Attendance", "Remarks"]
    ]

    return sheets


def resolve_constituency_id(supabase_url, service_key, constituency_name):
    const_df = _rest(
        supabase_url, service_key, "constituencies",
        {"name": f"eq.{constituency_name}", "select": "id"},
    )
    if const_df.empty:
        raise ValueError(f"No constituency named {constituency_name!r} found in Supabase")
    return const_df.iloc[0]["id"]


def fetch_field_reports(supabase_url, service_key, constituency_id, status=None):
    """Reports submitted through the public field-report form. Service role
    bypasses RLS, so this sees everything regardless of the public insert-only
    policy that protects the form itself."""
    params = {"constituency_id": f"eq.{constituency_id}", "order": "submitted_at.desc"}
    if status:
        params["status"] = f"eq.{status}"
    return _rest(supabase_url, service_key, "field_reports", params)


def update_field_report_status(supabase_url, service_key, report_id, new_status):
    resp = requests.patch(
        f"{supabase_url}/rest/v1/field_reports",
        params={"id": f"eq.{report_id}"},
        headers={
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        },
        json={"status": new_status},
        timeout=15,
    )
    resp.raise_for_status()


def _headers(service_key, prefer=None):
    headers = {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Content-Type": "application/json",
    }
    if prefer:
        headers["Prefer"] = prefer
    return headers


def select_rows(supabase_url, service_key, table, params):
    resp = requests.get(
        f"{supabase_url}/rest/v1/{table}", headers=_headers(service_key), params=params, timeout=10
    )
    resp.raise_for_status()
    return resp.json()


def insert_row(supabase_url, service_key, table, row):
    resp = requests.post(
        f"{supabase_url}/rest/v1/{table}",
        headers=_headers(service_key, "return=minimal"),
        json=row,
        timeout=10,
    )
    resp.raise_for_status()


def upsert_row(supabase_url, service_key, table, row):
    resp = requests.post(
        f"{supabase_url}/rest/v1/{table}",
        headers=_headers(service_key, "resolution=merge-duplicates,return=minimal"),
        json=row,
        timeout=10,
    )
    resp.raise_for_status()


def delete_rows(supabase_url, service_key, table, params):
    resp = requests.delete(
        f"{supabase_url}/rest/v1/{table}",
        headers=_headers(service_key, "return=minimal"),
        params=params,
        timeout=10,
    )
    resp.raise_for_status()
