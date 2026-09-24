"""Accuracy gate: checks a workbook before anyone trusts a number from it.

data_manager.validate_sheet counts blanks. This goes further and checks that the
numbers agree with each other: vote shares add up, the 2023->2025 deltas match
the two share tables they were computed from, official vote counts match their
percentages, and a point written under one party's column doesn't obviously
belong to another party's candidate.

Works on sheets keyed by internal name (config.SHEET_KEY_MAP values), so the
same checks run on the live data and on a file someone is about to upload.
"""

import difflib
import re

import pandas as pd

from config import normalize_party

SHARE_COLS = ["BRS", "INC", "BJP", "AIMIM", "Others"]
PARTY_COLS = ["BRS", "INC", "BJP", "AIMIM"]

REQUIRED_COLUMNS = {
    "demographics": ["Metric", "Count"],
    "division_shares": ["Division", "Year"],
    "division_deltas": ["Division"],
    "demo_preferences": ["Subgroup"],
    "surveys": ["Survey"],
    "historical_results": ["Year", "Party", "Votes", "Pct", "Turnout"],
    "social_media": ["Date", "Party"],
    "ground_campaign": ["Category", "Subcategory"],
    "campaign_activity": ["Date", "Party", "Area / Division"],
}

# Ground_Campaign's party columns are named as people write them, not as codes
GROUND_PARTY_COLUMN = {"INC": "Congress", "BRS": "BRS", "BJP": "BJP"}

# Surnames and titles shared by many unrelated people; matching on them would
# flag any note that mentions "Kishan Reddy" against a different "Reddy".
COMMON_NAME_TOKENS = {
    "reddy", "kumar", "rao", "naidu", "goud", "yadav", "singh", "khan", "mohammed",
    "ahmed", "sharma", "prasad", "chandra", "krishna", "kumari", "devi",
}

SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2}


def _issue(sheet, severity, message):
    return {"sheet": sheet, "severity": severity, "message": message}


def _num(series):
    return pd.to_numeric(series, errors="coerce")


def _present(cols, df):
    return [c for c in cols if c in df.columns]


# ----------------------------------------------------------------------
# Structure
# ----------------------------------------------------------------------
def _check_structure(sheets):
    issues = []
    for key, required in REQUIRED_COLUMNS.items():
        if key not in sheets:
            issues.append(_issue(key, "error", "Sheet is missing from the workbook."))
            continue
        missing = [c for c in required if c not in sheets[key].columns]
        if missing:
            issues.append(_issue(key, "error", f"Missing column(s): {', '.join(missing)}."))
    return issues


# ----------------------------------------------------------------------
# Numbers that must add up
# ----------------------------------------------------------------------
def _check_division_shares(sheets):
    issues = []
    df = sheets.get("division_shares")
    if df is None or not {"Division", "Year"} <= set(df.columns):
        return issues

    cols = _present(SHARE_COLS, df)
    for _, row in df.iterrows():
        values = _num(row[cols])
        label = f"{row['Division']} {row['Year']}"
        if ((values < 0) | (values > 100)).any():
            issues.append(_issue("division_shares", "error", f"{label}: a share is outside 0-100."))
            continue
        total = values.sum()
        if not 97 <= total <= 103:
            issues.append(_issue("division_shares", "warning", f"{label}: shares add up to {total:.1f}, not ~100."))

    years = _num(df["Year"]).dropna()
    if not years.empty and not years.between(2000, 2040).all():
        issues.append(_issue("division_shares", "error", "A Year is outside 2000-2040."))
    return issues


def _check_deltas_match_shares(sheets):
    """Each delta should equal the later share minus the earlier one. A mismatch
    means one of the two tables was edited without the other."""
    issues = []
    shares, deltas = sheets.get("division_shares"), sheets.get("division_deltas")
    if shares is None or deltas is None or not {"Division", "Year"} <= set(shares.columns):
        return issues

    years = sorted(_num(shares["Year"]).dropna().unique())
    if len(years) < 2:
        return issues
    first, last = years[0], years[-1]
    by_year = {y: shares[_num(shares["Year"]) == y].set_index("Division") for y in (first, last)}

    for _, row in deltas.iterrows():
        division = row["Division"]
        if division not in by_year[first].index or division not in by_year[last].index:
            issues.append(_issue("division_deltas", "warning", f"{division}: not present in both tracking rounds of Division_Shares."))
            continue
        for party in PARTY_COLS:
            col = f"{party}_Delta"
            if col not in deltas.columns or party not in shares.columns:
                continue
            expected = float(by_year[last].loc[division, party]) - float(by_year[first].loc[division, party])
            actual = _num(pd.Series([row[col]])).iloc[0]
            if pd.notna(actual) and abs(actual - expected) > 0.25:
                issues.append(_issue(
                    "division_deltas", "warning",
                    f"{division} {party}: delta is {actual:+.1f} but the share tables give {expected:+.1f}.",
                ))
    return issues


def _check_demo_preferences(sheets):
    issues = []
    df = sheets.get("demo_preferences")
    if df is None or "Subgroup" not in df.columns:
        return issues
    cols = _present(PARTY_COLS, df)
    for _, row in df.iterrows():
        total = _num(row[cols]).sum()
        if not 95 <= total <= 105:
            issues.append(_issue("demo_preferences", "warning", f"{row['Subgroup']}: preferences add up to {total:.1f}, not ~100."))
    return issues


def _check_surveys(sheets):
    issues = []
    df = sheets.get("surveys")
    if df is None or "Survey" not in df.columns:
        return issues
    cols = _present(PARTY_COLS, df)
    for _, row in df.iterrows():
        name = row["Survey"]
        total = _num(row[cols]).sum()
        if total > 105:
            issues.append(_issue("surveys", "error", f"{name}: party shares add up to {total:.1f}, more than 100."))
        if "Sample" in df.columns and pd.isna(_num(pd.Series([row["Sample"]])).iloc[0]):
            issues.append(_issue("surveys", "warning", f"{name}: no sample size, so it can't be weighted against the others."))
    return issues


def _check_historical(sheets):
    issues = []
    df = sheets.get("historical_results")
    if df is None or not {"Year", "Votes", "Pct", "Turnout"} <= set(df.columns):
        return issues
    for _, row in df.iterrows():
        votes, pct, turnout = (_num(pd.Series([row[c]])).iloc[0] for c in ("Votes", "Pct", "Turnout"))
        if pd.isna(votes) or pd.isna(pct) or pd.isna(turnout) or turnout == 0:
            continue
        implied = votes / turnout * 100
        if abs(implied - pct) > 0.5:
            issues.append(_issue(
                "historical_results", "warning",
                f"{row['Year']} {row['Party']}: {votes:.0f} of {turnout:.0f} votes is {implied:.1f}%, sheet says {pct}%.",
            ))
    return issues


# ----------------------------------------------------------------------
# Rows that look unfinished or unrecognised
# ----------------------------------------------------------------------
def _check_party_names_and_placeholders(sheets):
    issues = []
    numeric = {"social_media": ["#Posts", "Likes", "Shares", "Comments", "Impressions", "Reach"]}
    for key in ("social_media", "campaign_activity"):
        df = sheets.get(key)
        if df is None or "Party" not in df.columns:
            continue
        for i, row in df.iterrows():
            row_no = i + 2  # header row + 1-based
            if normalize_party(row["Party"]) is None:
                issues.append(_issue(key, "warning", f"Row {row_no}: party {row['Party']!r} isn't a recognised party."))
                continue
            for col in _present(numeric.get(key, []), df):
                if pd.isna(_num(pd.Series([row[col]])).iloc[0]):
                    issues.append(_issue(key, "warning", f"Row {row_no}: {col} is {row[col]!r}, not a number."))
                    break
    return issues


def _check_division_spelling(sheets):
    """Campaign events name their area in free text. 'Rahmat Nagar' vs 'Rehmat
    Nagar' silently breaks any join between the two sheets."""
    issues = []
    shares, activity = sheets.get("division_shares"), sheets.get("campaign_activity")
    if shares is None or activity is None or "Division" not in shares.columns or "Area / Division" not in activity.columns:
        return issues
    known = sorted(shares["Division"].dropna().unique())
    for area in sorted(activity["Area / Division"].dropna().unique()):
        if area in known:
            continue
        close = difflib.get_close_matches(area, known, n=1, cutoff=0.8)
        if close:
            issues.append(_issue("campaign_activity", "info", f"Area {area!r} looks like the division {close[0]!r} spelled differently."))
    return issues


# ----------------------------------------------------------------------
# Whose point is it?
# ----------------------------------------------------------------------
def _candidate_tokens(historical):
    """{name token: party code} from each candidate's most recent contest.
    Tokens that appear under two parties are dropped rather than guessed."""
    latest = {}
    for _, row in historical.sort_values("Year").iterrows():
        latest[row["Candidate"]] = normalize_party(row["Party"]) or row["Party"]

    token_party = {}
    for candidate, party in latest.items():
        for token in re.findall(r"[A-Za-z]+", str(candidate)):
            t = token.lower()
            if len(t) < 6 or t in COMMON_NAME_TOKENS:
                continue
            if token_party.get(t, party) != party:
                token_party[t] = None
            else:
                token_party[t] = party
    return {t: p for t, p in token_party.items() if p}


def check_party_attribution(sheets):
    """Flag a Ground_Campaign cell that names another party's candidate.

    A candidate can change party, so these are questions for a person to answer,
    not automatic corrections.
    """
    ground, hist = sheets.get("ground_campaign"), sheets.get("historical_results")
    if ground is None or hist is None or not {"Candidate", "Party", "Year"} <= set(hist.columns):
        return []

    tokens = _candidate_tokens(hist)
    ground = ground.copy()
    ground["Category"] = ground["Category"].ffill()

    issues = []
    for party_code, column in GROUND_PARTY_COLUMN.items():
        if column not in ground.columns:
            continue
        for _, row in ground.iterrows():
            text = str(row[column])
            for token, owner in tokens.items():
                if owner != party_code and owner in GROUND_PARTY_COLUMN and re.search(rf"\b{re.escape(token)}", text, re.I):
                    issues.append(_issue(
                        "ground_campaign", "warning",
                        f"{row['Category']} > {row['Subcategory']}, {column} column: \"{text}\" names "
                        f"{token.title()}, whose latest contest in Historical_Results was for {owner}. "
                        f"Is this really a {column} point?",
                    ))
    return issues


# ----------------------------------------------------------------------
def validate_workbook(sheets):
    """Every check, worst first. `sheets` is keyed by internal sheet name."""
    sheets = {k: v for k, v in sheets.items() if not k.startswith("_") and isinstance(v, pd.DataFrame)}

    issues = _check_structure(sheets)
    for check in (
        _check_division_shares,
        _check_deltas_match_shares,
        _check_demo_preferences,
        _check_surveys,
        _check_historical,
        _check_party_names_and_placeholders,
        _check_division_spelling,
        check_party_attribution,
    ):
        issues.extend(check(sheets))

    return sorted(issues, key=lambda i: (SEVERITY_ORDER[i["severity"]], i["sheet"]))
