"""People's Mandate AI — entry point.

This module only wires things together: page config, one-time data/component
init, sidebar navigation, and dispatch into views/. All analysis lives in
analyzer.py, all styling in theme.py.
"""

import os
import subprocess

import pandas as pd
import streamlit as st

import conversations
import db
import health
from analyzer import PoliticalAnalyzer
from auth import require_password
from audit_logger import AuditLogger
from components import source_badge, wordmark
from config import (
    CONSTITUENCY_NAME,
    DATA_FILE,
    SHEET_KEY_MAP,
    SOURCE_METADATA,
    is_valid_api_key,
)
from context import Ctx
from data_manager import SourceTracker, validate_all
from speech_generator import SpeechGenerator
from theme import inject_theme
from views import (
    ask_ai,
    backtest,
    brief,
    data_check,
    demographics,
    field_reports,
    live_pulse,
    overview,
    rebuttal,
    recommendations,
    simulator,
    social,
    speech,
    survey,
    swing,
)

st.set_page_config(
    page_title="People's Mandate AI",
    page_icon="🗳️",
    layout="wide",
    initial_sidebar_state="expanded",
)

VIEWS = [
    ask_ai, overview, live_pulse, field_reports,
    swing, demographics, survey, backtest, simulator, social,
    speech, rebuttal, recommendations, brief, data_check,
]

# Both caches below expire together. With only the data cached on a timer, the
# components built from it were cached forever, so a number edited in Supabase
# never reached the pages until the whole app restarted.
DATA_TTL = 300
STATUS_MARKS = {"ok": "✓", "off": "–", "broken": "✗"}


@st.cache_data(ttl=60, show_spinner=False)
def app_version():
    """The deployed commit, shown in the sidebar so anyone can tell whether the
    hosted app has picked up the latest push. Short-lived cache: the host pulls
    new code into the running process without restarting it."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=os.path.dirname(os.path.abspath(__file__)),
        )
        return out.stdout.strip() or None
    except Exception:
        return None


@st.cache_data(ttl=DATA_TTL, show_spinner=False)
def load_raw_sheets():
    """Supabase is the source of truth when configured; the Excel file is the
    fallback so the app still runs before the database is set up or while it's
    briefly unreachable. Returns (sheets, where they came from, problem)."""
    problem = None
    creds = health.supabase_credentials()
    if creds:
        try:
            return db.load_sheets_from_supabase(*creds, CONSTITUENCY_NAME), "Supabase", None
        except Exception as exc:
            problem = f"The database couldn't be reached ({type(exc).__name__}) — showing {DATA_FILE} instead."

    data_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), DATA_FILE)
    return pd.read_excel(data_path, sheet_name=None), DATA_FILE, problem


@st.cache_resource(ttl=DATA_TTL)
def init_components():
    raw, data_source, data_problem = load_raw_sheets()
    sheets = {SHEET_KEY_MAP.get(name, name): df for name, df in raw.items()}
    sheets["_constituency"] = CONSTITUENCY_NAME

    reports = validate_all({k: v for k, v in sheets.items() if not k.startswith("_")})

    tracker = SourceTracker()
    for meta in SOURCE_METADATA.values():
        tracker.add_source(meta)

    analyzer = PoliticalAnalyzer(sheets, tracker)
    logger = AuditLogger()

    api_key = health.secret("OPENAI_API_KEY")
    speech_gen = SpeechGenerator(analyzer, tracker, api_key if is_valid_api_key(api_key) else None)

    return Ctx(
        raw_sheets=raw,
        sheets=sheets,
        quality_reports=reports,
        tracker=tracker,
        analyzer=analyzer,
        logger=logger,
        speech_gen=speech_gen,
        api_key=api_key,
        data_source=data_source,
        data_problem=data_problem,
    )


def render_status():
    report = health.integration_status()
    broken = [item for item in report if item["state"] == "broken"]
    title = f"System status · {len(broken)} need attention" if broken else "System status · all working"

    with st.expander(title, expanded=bool(broken)):
        for item in report:
            suffix = " · not set up (optional)" if item["state"] == "off" else ""
            st.markdown(f"{STATUS_MARKS[item['state']]} **{item['label']}**{suffix}")
            if item["state"] == "broken":
                for problem in item["problems"]:
                    st.caption(problem)

        if conversations.backend() == "supabase":
            st.caption("Chat history and the audit log are saved to the database.")
        else:
            st.caption("Chat history is kept on this server only — it's lost whenever the app restarts.")


def render_sidebar(ctx):
    with st.sidebar:
        wordmark("People's Mandate AI", CONSTITUENCY_NAME)

        st.markdown('<div class="pm-rail">Navigation</div>', unsafe_allow_html=True)
        choice = st.radio(
            "Choose a view",
            [view.TITLE for view in VIEWS],
            label_visibility="collapsed",
        )

        # claimed here so a view's own sidebar content lands directly under the
        # nav rather than below the data-source list
        view_slot = st.container()

        scores = [r["data_quality_score"] for r in ctx.quality_reports.values()]
        quality = round(sum(scores) / len(scores))

        # nine long source names crowd the rail, so they fold away behind the score
        with st.expander(f"Data sources · {quality}% quality"):
            st.caption(f"Loaded from {ctx.data_source}.")
            for meta in SOURCE_METADATA.values():
                st.markdown(source_badge(meta["type"], meta["name"]), unsafe_allow_html=True)

        render_status()

        version = app_version()
        st.caption(
            "Light or dark: ⋮ menu → Settings → Appearance" + (f" · Version {version}" if version else "")
        )

    return next(view for view in VIEWS if view.TITLE == choice), view_slot


inject_theme()
require_password()  # nothing below renders until the viewer is authenticated

ctx = init_components()
view, view_slot = render_sidebar(ctx)
if ctx.data_problem:
    st.warning(ctx.data_problem)
view.render(ctx, view_slot)
