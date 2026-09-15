"""People's Mandate AI — entry point.

This module only wires things together: page config, one-time data/component
init, sidebar navigation, and dispatch into views/. All analysis lives in
analyzer.py, all styling in theme.py.
"""

import os

import pandas as pd
import streamlit as st

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
import db
from context import Ctx
from data_manager import SourceTracker, validate_all
from speech_generator import SpeechGenerator
from theme import inject_theme
from views import (
    ask_ai,
    demographics,
    field_reports,
    live_pulse,
    overview,
    recommendations,
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

VIEWS = [ask_ai, overview, live_pulse, field_reports, swing, demographics, survey, social, speech, recommendations]


@st.cache_data(ttl=300)
def load_raw_sheets():
    """Supabase is the source of truth when configured; Excel is the fallback
    so the app still runs before the database is set up or if Supabase is
    briefly unreachable — same defensive pattern as every other integration
    here, never a hard failure on a missing key."""
    supabase_url = st.secrets.get("SUPABASE_URL", None) if hasattr(st, "secrets") else None
    service_key = st.secrets.get("SUPABASE_SERVICE_KEY", None) if hasattr(st, "secrets") else None

    if is_valid_api_key(supabase_url, placeholder_prefix="https://REPLACE") and is_valid_api_key(
        service_key, placeholder_prefix="REPLACE"
    ):
        try:
            return db.load_sheets_from_supabase(supabase_url, service_key, CONSTITUENCY_NAME)
        except Exception as exc:
            st.warning(f"Supabase unavailable ({exc}) — falling back to {DATA_FILE}.")

    data_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), DATA_FILE)
    return pd.read_excel(data_path, sheet_name=None)


@st.cache_resource
def init_components():
    raw = load_raw_sheets()
    sheets = {SHEET_KEY_MAP.get(name, name): df for name, df in raw.items()}
    sheets["_constituency"] = CONSTITUENCY_NAME

    reports = validate_all({k: v for k, v in sheets.items() if not k.startswith("_")})

    tracker = SourceTracker()
    for meta in SOURCE_METADATA.values():
        tracker.add_source(meta)

    analyzer = PoliticalAnalyzer(sheets, tracker)
    logger = AuditLogger()

    api_key = st.secrets.get("OPENAI_API_KEY", None) if hasattr(st, "secrets") else None
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
    )


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
            for meta in SOURCE_METADATA.values():
                st.markdown(source_badge(meta["type"], meta["name"]), unsafe_allow_html=True)

        if not is_valid_api_key(ctx.api_key):
            st.warning(
                "OPENAI_API_KEY not set in .streamlit/secrets.toml — Speech Generator "
                "and Ask AI are disabled until it's added."
            )

        st.caption("Light or dark: ⋮ menu → Settings → Appearance")

    return next(view for view in VIEWS if view.TITLE == choice), view_slot


inject_theme()
require_password()  # nothing below renders until the viewer is authenticated

ctx = init_components()
view, view_slot = render_sidebar(ctx)
view.render(ctx, view_slot)
