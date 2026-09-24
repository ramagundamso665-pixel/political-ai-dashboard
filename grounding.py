"""Prompt pieces shared by every page that asks the model a question about the data."""

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


def build_data_context(ctx):
    """Serialize every sheet for the prompt.

    Ground_Campaign is the one sheet where three parties' notes sit side by side in
    a wide row — sent as-is, an LLM summary tends to blend them (e.g. folding BRS's
    "ruling fatigue" into an undifferentiated answer). Melting it into one fact per
    (party, subcategory) line removes that ambiguity.
    """
    parts = []
    for name, df in ctx.raw_sheets.items():
        if SHEET_KEY_MAP.get(name) == "ground_campaign":
            facts = "\n".join(ctx.analyzer.ground_campaign_facts())
            parts.append(f"### Sheet: {name} (one fact per party per row)\n{facts}\n")
        else:
            columns = ", ".join(map(str, df.columns))
            parts.append(f"### Sheet: {name}\nColumns: {columns}\n{df.to_string(index=False)}\n")
    return "\n".join(parts)
