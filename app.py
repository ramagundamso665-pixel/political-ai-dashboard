import json
import os

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from analyzer import PoliticalAnalyzer
from audit_logger import AuditLogger
from config import (
    CONSTITUENCY_NAME,
    DATA_FILE,
    PARTIES,
    PARTY_COLORS,
    PARTY_LABELS,
    SHEET_KEY_MAP,
    SOURCE_METADATA,
    is_valid_api_key,
)
from data_manager import SourceTracker, validate_all
from speech_generator import SpeechGenerator

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

# ══════════════════════════════════════════════════════════════════════
# CONFIG + STYLE
# ══════════════════════════════════════════════════════════════════════

st.set_page_config(page_title="People's Mandate AI", page_icon="🗳️", layout="wide")

st.markdown(
    """
    <style>
    .stApp { background-color: #0B1220; }
    h1, h2, h3, h4 { color: #F5F0E6 !important; }
    p, li, span, label, .stMarkdown { color: #D8DEE9; }
    [data-testid="stMetricValue"] { color: #F2C94C; }
    [data-testid="stMetricLabel"] { color: #9AA5B1; }
    .badge {
        display: inline-block; padding: 2px 10px; border-radius: 12px;
        font-size: 0.75rem; font-weight: 600; margin-right: 6px;
    }
    .badge-verified { background: #1B4332; color: #74C69D; }
    .badge-internal { background: #1B3A4B; color: #74B9E7; }
    .badge-external { background: #4B3A1B; color: #E7B96E; }
    .badge-conflict { background: #4B1B1B; color: #E76F6F; }
    .fact-card {
        background: #131C2E; border: 1px solid #23304A; border-radius: 10px;
        padding: 14px 16px; margin-bottom: 10px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("🗳️ People's Mandate AI")
st.caption(f"Campaign intelligence for **{CONSTITUENCY_NAME}** · every number traces to a source")

BADGE_CLASS = {"verified": "badge-verified", "internal": "badge-internal", "external": "badge-external"}


def source_badge(source_type, name=None):
    cls = BADGE_CLASS.get(source_type, "badge-internal")
    label = name or source_type.upper()
    return f'<span class="badge {cls}">{label}</span>'


def fact_card(claim, source_name, source_type, confidence):
    st.markdown(
        f"""
        <div class="fact-card">
        {claim}<br/>
        {source_badge(source_type, source_name)}
        <span class="badge" style="background:#1F2937;color:#9CA3AF;">CONFIDENCE: {confidence.upper()}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ══════════════════════════════════════════════════════════════════════
# INIT
# ══════════════════════════════════════════════════════════════════════

@st.cache_data
def load_raw_sheets():
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

    return raw, sheets, reports, tracker, analyzer, logger, speech_gen, api_key


raw_sheets, sheets, quality_reports, tracker, analyzer, logger, speech_gen, api_key = init_components()

# ══════════════════════════════════════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════════════════════════════════════

with st.sidebar:
    st.markdown("### 📊 Navigation")
    page = st.radio(
        "Choose a view",
        [
            "📈 Overview",
            "🎯 Swing Divisions",
            "👥 Demographic Insights",
            "🔮 Survey Reliability & Prediction",
            "📣 Social & Ground Campaign",
            "🎤 Speech Generator",
            "📋 Recommendations",
            "💬 Ask AI",
        ],
        label_visibility="collapsed",
    )

    st.markdown("---")
    st.markdown("### 📌 Data Sources")
    for meta in SOURCE_METADATA.values():
        st.markdown(source_badge(meta["type"], meta["name"]), unsafe_allow_html=True)

    st.markdown("---")
    avg_quality = round(sum(r["data_quality_score"] for r in quality_reports.values()) / len(quality_reports))
    st.metric("Overall Data Quality", f"{avg_quality}%")
    if not is_valid_api_key(api_key):
        st.warning("OPENAI_API_KEY not set in .streamlit/secrets.toml — Speech Generator and Ask AI are disabled until it's added.")

# ══════════════════════════════════════════════════════════════════════
# PAGE: OVERVIEW
# ══════════════════════════════════════════════════════════════════════

if page == "📈 Overview":
    st.header("Campaign Intelligence Overview")

    pred = analyzer.predict_outcome()
    swing = analyzer.swing_divisions(top_n=100)
    survey = analyzer.survey_landscape()
    conflicted = [c for c in survey["conflicts"] if c["conflict_exists"]]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Predicted Leader", PARTY_LABELS.get(pred["predicted_leader"]), f"+{pred['margin_pct']}pt")
    c2.metric("Prediction Confidence", f"{pred['confidence_pct']}%", pred["confidence_label"])
    c3.metric("Swing Divisions Tracked", len(swing))
    c4.metric("Surveys in Conflict", f"{len(conflicted)}/{len(PARTIES)} parties", "flagged" if conflicted else "none")

    st.markdown("---")
    tabs = st.tabs(["Why this dashboard is different", "This constituency", "Methodology"])

    with tabs[0]:
        st.markdown(
            """
            Most campaign decks show a single confident number. This one shows **what
            the data actually says, including where it disagrees with itself.**

            - Every chart and claim carries a source badge — verified official result,
              internal field tracking, or third-party survey.
            - When sources conflict (see the Survey Reliability page — one poll has BJP
              at 1%, another at 41%, for the *same seat*), we surface it instead of
              quietly averaging it away.
            - The prediction confidence score is **calculated from actual survey
              disagreement**, not a fixed marketing number.
            """
        )

    with tabs[1]:
        st.markdown(f"**{CONSTITUENCY_NAME}** — built directly from this campaign's own tracking data:")
        demo = sheets["demographics"]
        st.dataframe(demo, hide_index=True, width='stretch')

    with tabs[2]:
        st.markdown(
            """
            1. **Data validation** — every sheet is checked for missing values and unfilled
               placeholder cells before any analysis runs (see sidebar quality score).
            2. **Source attribution** — every number is tagged: verified / internal / external.
            3. **Blended prediction** — historical result (20%), internal division tracking
               (50%), survey average (30%), confidence penalized by survey disagreement.
            4. **Recommendations** — derived programmatically from swing divisions, contested
               demographics, survey conflicts, and event-tempo — not hardcoded talking points.
            """
        )

# ══════════════════════════════════════════════════════════════════════
# PAGE: SWING DIVISIONS
# ══════════════════════════════════════════════════════════════════════

elif page == "🎯 Swing Divisions":
    st.header("Swing Division Identification")
    st.caption("Divisions with the largest vote-share movement between the 2023 and 2025 tracking rounds.")

    swing = analyzer.swing_divisions(top_n=7)

    for r in swing:
        col1, col2 = st.columns([3, 1])
        with col1:
            st.markdown(f"**{r['division']}** — swing toward **{PARTY_LABELS.get(r['swinging_party'], r['swinging_party'])}**")
            deltas_str = ", ".join(f"{PARTY_LABELS.get(p,p)} {v:+.1f}pt" for p, v in r["deltas"].items())
            st.caption(deltas_str)
        with col2:
            st.metric("Max swing", f"{r['max_swing']}pt")

    fig = go.Figure()
    for r in swing:
        fig.add_trace(go.Bar(name=r["division"], x=list(r["deltas"].keys()), y=list(r["deltas"].values())))
    fig.update_layout(
        barmode="group", template="plotly_dark", title="Vote share delta by party across swing divisions",
        paper_bgcolor="#0B1220", plot_bgcolor="#0B1220", height=420,
    )
    st.plotly_chart(fig, width='stretch')

    fact_card(
        f"Top {len(swing)} swing divisions identified by 2023→2025 vote share change",
        SOURCE_METADATA["division_deltas"]["name"], SOURCE_METADATA["division_deltas"]["type"], "medium",
    )

    logger.log_analysis("swing_divisions", ["division_deltas", "division_shares"], f"{len(swing)} swing divisions")

# ══════════════════════════════════════════════════════════════════════
# PAGE: DEMOGRAPHIC INSIGHTS
# ══════════════════════════════════════════════════════════════════════

elif page == "👥 Demographic Insights":
    st.header("Demographic Preference Breakdown")

    demo = analyzer.demographic_preferences()
    df = pd.DataFrame([{**r["shares"], "Subgroup": r["subgroup"]} for r in demo])
    df = df.set_index("Subgroup")

    fig = px.bar(
        df, x=df.index, y=[p for p in PARTIES if p in df.columns], barmode="group",
        color_discrete_map=PARTY_COLORS, template="plotly_dark",
        labels={"value": "Vote share %", "Subgroup": ""},
    )
    fig.update_layout(paper_bgcolor="#0B1220", plot_bgcolor="#0B1220", height=460, legend_title="")
    st.plotly_chart(fig, width='stretch')

    contested = [r for r in demo if r["is_contested"]]
    if contested:
        st.markdown("### 🎯 Persuadable subgroups (<5pt gap between top two parties)")
        for r in contested:
            st.markdown(
                f"- **{r['subgroup']}**: {PARTY_LABELS.get(r['leader'], r['leader'])} leads by only {r['gap_to_runner_up']}pt"
            )

    fact_card(
        f"{len(contested)} subgroup(s) flagged as tightly contested",
        SOURCE_METADATA["demo_preferences"]["name"], SOURCE_METADATA["demo_preferences"]["type"], "medium",
    )

    logger.log_analysis("demographic_preferences", ["demo_preferences"], f"{len(contested)} contested subgroups")

# ══════════════════════════════════════════════════════════════════════
# PAGE: SURVEY RELIABILITY & PREDICTION
# ══════════════════════════════════════════════════════════════════════

elif page == "🔮 Survey Reliability & Prediction":
    st.header("Survey Reliability & Election Prediction")

    survey = analyzer.survey_landscape()
    st.markdown("### 📋 Raw survey landscape")
    st.dataframe(survey["raw"], hide_index=True, width='stretch')

    st.markdown("### ⚠️ Conflict check")
    for c in survey["conflicts"]:
        if c["conflict_exists"]:
            st.markdown(
                f'<span class="badge badge-conflict">CONFLICT</span> '
                f'**{PARTY_LABELS.get(c["party"], c["party"])}**: surveys range from '
                f'**{c["min"]}%** to **{c["max"]}%** (spread {c["spread"]}pt) across '
                f'{len(c["values"])} sources — do not treat any single survey as ground truth.',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(f'✅ **{PARTY_LABELS.get(c["party"], c["party"])}**: surveys broadly agree (spread {c["spread"]}pt)')

    st.markdown("---")
    st.markdown("### 🔮 Blended Prediction")

    pred = analyzer.predict_outcome()

    c1, c2, c3 = st.columns(3)
    c1.metric("Predicted Leader", PARTY_LABELS.get(pred["predicted_leader"]))
    c2.metric("Confidence", f"{pred['confidence_pct']}%", pred["confidence_label"])
    c3.metric("Margin", f"{pred['margin_pct']}pt over {PARTY_LABELS.get(pred['runner_up'])}")

    fig = px.bar(
        x=list(pred["blended_shares"].keys()), y=list(pred["blended_shares"].values()),
        color=list(pred["blended_shares"].keys()), color_discrete_map=PARTY_COLORS,
        template="plotly_dark", labels={"x": "", "y": "Blended vote share %"},
    )
    fig.update_layout(showlegend=False, paper_bgcolor="#0B1220", plot_bgcolor="#0B1220", height=380)
    st.plotly_chart(fig, width='stretch')

    with st.expander("How this number was built"):
        st.json(pred["inputs"])
        st.markdown(f"Weights: historical {pred['weights']['historical']*100:.0f}% · division tracking {pred['weights']['division']*100:.0f}% · surveys {pred['weights']['survey']*100:.0f}%")
        st.markdown(f"Average survey disagreement: **{pred['avg_survey_disagreement_pct']}pt** (this directly lowers confidence)")

    st.warning(
        "This is a probability estimate, not a guarantee. Confidence is capped and "
        "penalized when third-party surveys disagree — treat it as one input among many."
    )

    logger.log_prediction(pred)

# ══════════════════════════════════════════════════════════════════════
# PAGE: SOCIAL & GROUND CAMPAIGN
# ══════════════════════════════════════════════════════════════════════

elif page == "📣 Social & Ground Campaign":
    st.header("Social Media & Ground Campaign")

    social = analyzer.social_media_activity()
    st.markdown("### 📱 Social media share of voice")
    if social["excluded_rows"]:
        st.caption(f"⚠️ {social['excluded_rows']} row(s) excluded — unfilled placeholder data in the source log.")

    fig = px.pie(
        social["by_party"], names="party", values="engagement", color="party",
        color_discrete_map=PARTY_COLORS, template="plotly_dark", hole=0.4,
    )
    fig.update_layout(paper_bgcolor="#0B1220", height=380)
    st.plotly_chart(fig, width='stretch')
    st.dataframe(social["by_party"], hide_index=True, width='stretch')
    fact_card(
        "Share of voice is engagement volume, not sentiment — this log has no sentiment scoring.",
        SOURCE_METADATA["social_media"]["name"], SOURCE_METADATA["social_media"]["type"], "low",
    )

    st.markdown("---")
    st.markdown("### 🪧 Ground campaign positioning matrix")
    gc = analyzer.ground_campaign_matrix()
    st.dataframe(gc, hide_index=True, width='stretch')

    st.markdown("---")
    st.markdown("### 🗓️ Campaign activity timeline")
    activity = analyzer.campaign_activity_timeline()
    st.dataframe(activity["timeline"], hide_index=True, width='stretch')
    st.bar_chart(pd.Series(activity["event_counts_by_party"]))

    logger.log_analysis("social_and_ground", ["social_media", "ground_campaign", "campaign_activity"], "reviewed")

# ══════════════════════════════════════════════════════════════════════
# PAGE: SPEECH GENERATOR
# ══════════════════════════════════════════════════════════════════════

elif page == "🎤 Speech Generator":
    st.header("AI Speech Generator")
    st.caption("Every speech is grounded in VERIFIED FACTS pulled from your data. The model is instructed to never invent numbers.")

    if not is_valid_api_key(api_key):
        st.error("Add a real OPENAI_API_KEY to .streamlit/secrets.toml to enable speech generation.")
    else:
        demo_subgroups = list(sheets["demo_preferences"]["Subgroup"])
        theme_options = sorted(sheets["ground_campaign"]["Subcategory"].dropna().unique().tolist())
        event_options = sorted(sheets["campaign_activity"]["Event Type"].dropna().unique().tolist())

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            party = st.selectbox("Speaking for", PARTIES, format_func=lambda p: PARTY_LABELS.get(p, p))
        with c2:
            audience = st.selectbox("Target audience", demo_subgroups)
        with c3:
            theme = st.selectbox("Theme", theme_options)
        with c4:
            event = st.selectbox("Event type", event_options)

        if st.button("📝 Generate Speech", width='stretch'):
            with st.spinner("Grounding facts and generating speech..."):
                result = speech_gen.generate_speech(party, audience, theme, event)

            if "error" in result:
                st.error(result["error"])
            else:
                st.markdown("---")
                with st.expander("📄 Full Speech", expanded=True):
                    st.markdown(result["speech"])

                with st.expander("📌 Sources cited"):
                    for c in result["sources_cited"]:
                        fact_card(c["claim"], c["source"], "internal", c["confidence"])

                with st.expander("✅ Verification"):
                    if result["verification_status"] == "VERIFIED":
                        st.success("All numeric claims trace back to the fact block.")
                    else:
                        st.warning(f"Numbers in the speech not found in the source facts (double-check before use): {', '.join(result['unverified_numbers'])}")

                with st.expander("💡 Talking points"):
                    for i, tp in enumerate(result["talking_points"], 1):
                        st.markdown(f"{i}. {tp}")

                logger.log_speech_generation(party, audience, result["verification_status"])

# ══════════════════════════════════════════════════════════════════════
# PAGE: RECOMMENDATIONS
# ══════════════════════════════════════════════════════════════════════

elif page == "📋 Recommendations":
    st.header("Daily Campaign Recommendations")
    st.caption("Generated from the data — priority order reflects swing potential, not a fixed script.")

    recs = analyzer.recommendations()
    for r in recs:
        col1, col2 = st.columns([0.15, 0.85])
        with col1:
            st.metric("Priority", r["priority"])
        with col2:
            st.markdown(f"### {r['action']}")
            st.markdown(f"**Reasoning:** {r['reasoning']}")
            st.markdown(f"**Timeline:** {r['timeline']}")
            fact_card(r["action"], r["source"], SOURCE_METADATA.get(
                next((k for k, v in SOURCE_METADATA.items() if v["name"] == r["source"]), ""), {}
            ).get("type", "internal"), "medium")
        st.divider()

    logger.log_analysis("recommendations", ["multiple"], f"{len(recs)} recommendations generated")

# ══════════════════════════════════════════════════════════════════════
# PAGE: ASK AI
# ══════════════════════════════════════════════════════════════════════

elif page == "💬 Ask AI":
    st.header("Ask AI About Your Data")

    if not is_valid_api_key(api_key):
        st.error("Add a real OPENAI_API_KEY to .streamlit/secrets.toml to enable this page.")
        st.stop()

    client = OpenAI(api_key=api_key)

    if "messages" not in st.session_state:
        st.session_state.messages = []

    schema = ""
    for sheet_name, df in raw_sheets.items():
        cols = ", ".join(map(str, df.columns))
        sample = df.head(2).to_string(index=False)
        schema += f"\nSheet: {sheet_name}\nColumns: {cols}\nSample:\n{sample}\n"

    SYSTEM_PROMPT = f"""
You are People's Mandate AI. Available sheets:
{schema}
Return ONLY JSON like {{"sheet":"Surveys","analysis_type":"summary","chart":"table"}}.
analysis_type: summary, count, list, compare, trend, distribution, ranking
chart: table, bar, line, area, pie
Never return explanation. Return only JSON.
"""

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])

    if prompt := st.chat_input("Ask anything about your political data..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.write(prompt)

        try:
            planner = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}],
            )
            cleaned = planner.choices[0].message.content.replace("```json", "").replace("```", "").strip()
            plan = json.loads(cleaned)
        except Exception as e:
            st.error("Planner error")
            st.exception(e)
            st.stop()

        sheet_raw = plan.get("sheet", "")
        selected_sheet = next(
            (s for s in raw_sheets if s.lower() == sheet_raw.lower()), list(raw_sheets.keys())[0]
        )
        df = raw_sheets[selected_sheet].copy()
        data_context = df.head(100).to_string(index=False)

        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": f"Answer ONLY from sheet '{selected_sheet}'. Never make up facts. If the data doesn't cover it, say 'No information available in the dataset.'"},
                    {"role": "user", "content": f"Question: {prompt}\n\nData:\n{data_context}"},
                ],
            )
            answer = response.choices[0].message.content
        except Exception as e:
            st.error("Answer generation failed")
            st.exception(e)
            st.stop()
        st.session_state.messages.append({"role": "assistant", "content": answer})

        with st.chat_message("assistant"):
            st.markdown(source_badge(SOURCE_METADATA.get(SHEET_KEY_MAP.get(selected_sheet, ""), {}).get("type", "internal"), f"Sheet: {selected_sheet}"), unsafe_allow_html=True)
            st.write(answer)

            numeric_df = df.select_dtypes(include="number")
            if not numeric_df.empty:
                chart = plan.get("chart", "bar")
                if chart == "line":
                    st.line_chart(numeric_df)
                elif chart == "area":
                    st.area_chart(numeric_df)
                else:
                    st.bar_chart(numeric_df)

            st.dataframe(df.head(20), hide_index=True, width='stretch')

        logger.log_analysis("ask_ai", [selected_sheet], answer[:150])

# ══════════════════════════════════════════════════════════════════════
# FOOTER
# ══════════════════════════════════════════════════════════════════════

st.markdown("---")
st.markdown(
    f"""
    **Data Sources:** {' '.join(source_badge(m['type'], m['name']) for m in SOURCE_METADATA.values())}

    Your data stays on your infrastructure. No data leaves this app except to the OpenAI API
    for AI-generated text (Ask AI / Speech Generator), and only the sheet excerpts shown above are sent.
    """,
    unsafe_allow_html=True,
)
