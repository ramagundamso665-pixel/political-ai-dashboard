"""Integration credentials and whether each one is usable.

Keys pasted into a host's secrets manager can arrive broken in ways that only
surface later as an unexplained HTTP 400 deep inside one page — most often a key
copied from a screen that masks secrets, which pastes bullets (•) in place of
the real characters. Every credential is checked here, and the sidebar names the
exact problem instead.
"""

import streamlit as st


def secret(name):
    try:
        return st.secrets.get(name)
    except Exception:
        return None


def key_problem(value, placeholder_prefix):
    if not value:
        return "is not set"
    value = str(value)
    if value.startswith(placeholder_prefix):
        return "is still the example placeholder"
    if not value.isascii():
        return "is masked (contains • characters) — paste the real key again"
    if value != value.strip() or " " in value:
        return "contains spaces"
    return None


def supabase_credentials():
    url, key = secret("SUPABASE_URL"), secret("SUPABASE_SERVICE_KEY")
    if key_problem(url, "https://REPLACE") or key_problem(key, "REPLACE"):
        return None
    return url, key


UNSET = ("is not set", "is still the example placeholder")

# (label, {secret name: placeholder prefix}, optional)
INTEGRATIONS = [
    ("Database (Supabase)", {"SUPABASE_URL": "https://REPLACE", "SUPABASE_SERVICE_KEY": "REPLACE"}, False),
    ("OpenAI — Ask AI, speeches, headline mood", {"OPENAI_API_KEY": "sk-REPLACE"}, False),
    ("YouTube", {"YOUTUBE_API_KEY": "AIza-REPLACE"}, False),
    ("Reddit", {"REDDIT_CLIENT_ID": "REPLACE", "REDDIT_CLIENT_SECRET": "REPLACE"}, True),
]


def integration_status():
    """state is "ok", "off" (an optional integration nobody set up), or "broken"."""
    report = []
    for label, keys, optional in INTEGRATIONS:
        found = {name: key_problem(secret(name), prefix) for name, prefix in keys.items()}
        problems = [f"{name} {problem}" for name, problem in found.items() if problem]
        if not problems:
            state = "ok"
        elif optional and all(problem in UNSET for problem in found.values()):
            state = "off"
        else:
            state = "broken"
        report.append({"label": label, "state": state, "problems": problems})
    return report
