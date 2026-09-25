"""Prompt pieces shared by every page that asks the model a question about the data."""

import pandas as pd

from config import SHEET_KEY_MAP

LANGUAGES = ["English", "Telugu"]


def language_rule(language):
    """One prompt line, or nothing for English. Numbers stay as digits so the
    post-generation number check (speech_generator) still works on Telugu text."""
    if language == "Telugu":
        return (
            "- Write every text value you return (answer, reply, bullet points) in Telugu (తెలుగు script). "
            "Keep the JSON keys in English, every number as ordinary digits (0-9), and party names, "
            "candidate names and sheet names exactly as they appear in the data."
        )
    return ""


# Wide numeric sheets are read badly by a small model (it lands on the wrong column or the
# wrong year), so each number is written out on its own line with its full label instead.
LONG_FORM_SHEETS = {
    "division_shares": ["Division", "Year"],
    "division_deltas": ["Division"],
    "demo_preferences": ["Subgroup"],
    "surveys": ["Survey", "Sample", "Area", "Year", "Notes"],
}


def _one_number_per_line(name, df, id_cols):
    ids = [c for c in id_cols if c in df.columns]
    values = [c for c in df.columns if c not in ids and pd.api.types.is_numeric_dtype(df[c])]
    if name.lower().startswith("survey"):
        # survey party columns hold "-" for a party a poll didn't cover
        values = [c for c in df.columns if c not in ids]
    lines = []
    for _, row in df.iterrows():
        label = ", ".join(f"{c}={row[c]}" for c in ids if pd.notna(row[c]))
        for col in values:
            val = pd.to_numeric(pd.Series([row[col]]), errors="coerce").iloc[0]
            if pd.notna(val):
                lines.append(f"{label} | {col} = {val:g}")
    return "\n".join(lines)


def result_rule(ctx):
    """Once the vote the tracking was for has been held, every tracking and poll
    figure is a pre-election estimate. The model must not present it as the state
    of the race today."""
    result = ctx.analyzer.latest_result()
    if not result:
        return ""
    return (
        f"- IMPORTANT: the {result['year']} vote has ALREADY BEEN HELD (see Historical_Results). Division_Shares, "
        "Demo_Preferences, Surveys, Social_Media and the ground-campaign notes were recorded BEFORE it, so they are "
        "pre-election estimates. Every time you cite a figure from those sheets you MUST call it a "
        "\"pre-election estimate\" and add what the official result was, for example: \"The pre-election "
        "estimate had BRS at 50.2% among women, but at the vote BRS got 38.13% overall.\" "
        "Never say a party \"is\" ahead or winning from those sheets: only the official result says who won."
    )


def build_data_context(ctx):
    """Serialize every sheet for the prompt.

    Ground_Campaign is the one sheet where three parties' notes sit side by side in
    a wide row — sent as-is, an LLM summary tends to blend them (e.g. folding BRS's
    "ruling fatigue" into an undifferentiated answer). Melting it into one fact per
    (party, subcategory) line removes that ambiguity.
    """
    parts = []
    # once the vote has been held, everything except the official history was recorded before it;
    # a "Year 2025" column on those sheets is a tracking round, not an election result
    held = ctx.analyzer.latest_result()
    pre_election = {"division_shares", "division_deltas", "demo_preferences", "surveys", "social_media",
                    "ground_campaign", "campaign_activity"}
    for name, df in ctx.raw_sheets.items():
        key = SHEET_KEY_MAP.get(name)
        flag = " — PRE-ELECTION ESTIMATE, NOT AN OFFICIAL RESULT (a Year column here is a tracking round)" if held and key in pre_election else ""
        if key == "ground_campaign":
            facts = "\n".join(ctx.analyzer.ground_campaign_facts())
            parts.append(f"### Sheet: {name} (one fact per party per row){flag}\n{facts}\n")
        elif key in LONG_FORM_SHEETS:
            facts = _one_number_per_line(name, df, LONG_FORM_SHEETS[key])
            parts.append(f"### Sheet: {name} (one number per line){flag}\n{facts}\n")
        else:
            columns = ", ".join(map(str, df.columns))
            parts.append(f"### Sheet: {name}{flag}\nColumns: {columns}\n{df.to_string(index=False)}\n")
    return "\n".join(parts)
