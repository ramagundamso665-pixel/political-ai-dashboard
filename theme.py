"""Presentation layer only.

Colors, fonts, radii and dataframe chrome come from .streamlit/config.toml, which
defines a full light and a full dark palette. Streamlit's Appearance switch flips
between them and native widgets follow automatically.

Everything here is deliberately written to work under *either* palette: surfaces
are translucent neutrals layered over whatever background is active, and text
inherits. That way nothing has to know which mode is showing, so the theme never
lags a rerun behind the switch.
"""

import streamlit as st

FONTS = (
    "https://fonts.googleapis.com/css2"
    "?family=Inter:wght@400;500;600;700"
    "&family=Source+Serif+4:opsz,wght@8..60,400;8..60,600;8..60,700"
    "&family=JetBrains+Mono:wght@400;500&display=swap"
)

CSS = """
<style>
@import url('FONT_URL');

:root {
    /* neutral overlays: readable on cream and on charcoal alike */
    --pm-raise:  rgba(128, 128, 128, .055);
    --pm-line:   rgba(128, 128, 128, .28);
    --pm-line-soft: rgba(128, 128, 128, .16);
    --pm-dim:    color-mix(in srgb, currentColor 58%, transparent);
    --pm-accent: var(--primary-color, #C2603C);
}

/* ---------- rhythm ---------- */
.block-container { max-width: 1180px; padding-top: 4.25rem; padding-bottom: 4rem; }

h1, h2, h3 { letter-spacing: -.012em; }
h2 { margin-top: 2.4rem; }
h3 { margin-top: 1.6rem; }

/* Streamlit's anchor links add visual noise to a reading-heavy page */
h1 a, h2 a, h3 a, h4 a { display: none !important; }

hr { border-color: var(--pm-line-soft) !important; margin: 2rem 0; }

/* ---------- sidebar wordmark ---------- */
.pm-brand {
    display: flex;
    align-items: center;
    gap: 9px;
    padding: 2px 0 14px;
    margin-bottom: 6px;
    border-bottom: 1px solid var(--pm-line-soft);
}

.pm-brand-dot {
    width: 7px; height: 7px; border-radius: 50%;
    background: var(--pm-accent);
    flex: none;
}

.pm-brand strong {
    display: block;
    font-family: 'Source Serif 4', Georgia, serif;
    font-size: 1.02rem;
    font-weight: 600;
    line-height: 1.15;
}

.pm-brand span {
    display: block;
    font-size: .72rem;
    opacity: .55;
    margin-top: 1px;
}

/* ---------- section heading ---------- */
.pm-section { margin: 2.6rem 0 1.1rem; }

.pm-section h2 {
    font-family: 'Source Serif 4', Georgia, serif;
    font-size: 1.35rem;
    font-weight: 600;
    margin: 0 0 .25rem;
}

.pm-section p {
    font-size: .9rem;
    opacity: .68;
    margin: 0;
    max-width: 72ch;
}

/* ---------- badges ---------- */
.badge {
    display: inline-block;
    padding: 2px 9px;
    border-radius: 999px;
    font-size: .7rem;
    font-weight: 600;
    letter-spacing: .01em;
    margin: 0 6px 5px 0;
    border: 1px solid;
    white-space: nowrap;
}

/* source names are long; in the narrow sidebar they wrap instead of overflowing */
[data-testid="stSidebar"] .badge {
    white-space: normal;
    display: block;
    line-height: 1.4;
}

.badge-verified { color: #3F7D58; border-color: rgba(63, 125, 88, .42);  background: rgba(63, 125, 88, .09); }
.badge-internal { color: #4A6E96; border-color: rgba(74, 110, 150, .42); background: rgba(74, 110, 150, .09); }
.badge-external { color: #9A6B2F; border-color: rgba(154, 107, 47, .42); background: rgba(154, 107, 47, .09); }
.badge-conflict { color: #A9523F; border-color: rgba(169, 82, 63, .45);  background: rgba(169, 82, 63, .10); }
.badge-meta     { color: inherit; border-color: var(--pm-line); background: var(--pm-raise); opacity: .75; }

/* dark mode needs lighter ink on the same hues to stay legible */
@media (prefers-color-scheme: dark) {
    .badge-verified { color: #8FC7A4; }
    .badge-internal { color: #9BBCDE; }
    .badge-external { color: #DDB273; }
    .badge-conflict { color: #E0998A; }
}

/* ---------- fact card ---------- */
.fact-card {
    border: 1px solid var(--pm-line-soft);
    border-left: 2px solid var(--pm-accent);
    border-radius: 0 10px 10px 0;
    background: var(--pm-raise);
    padding: 13px 16px;
    margin: 10px 0 14px;
    font-size: .9rem;
    line-height: 1.55;
}

.fact-card .badge { margin-top: 8px; }

/* ---------- empty state ---------- */
.pm-empty {
    border: 1px dashed var(--pm-line);
    border-radius: 10px;
    padding: 26px 20px;
    text-align: center;
    font-size: .9rem;
    opacity: .62;
}

/* ---------- metrics as quiet stat blocks ---------- */
[data-testid="stMetric"] {
    border: 1px solid var(--pm-line-soft);
    border-radius: 10px;
    background: var(--pm-raise);
    padding: 14px 16px;
}

[data-testid="stMetricLabel"], [data-testid="stMetricLabel"] * {
    font-size: .7rem !important;
    font-weight: 600 !important;
    letter-spacing: .07em;
    text-transform: uppercase;
    opacity: .6;
    white-space: normal !important;
    overflow: visible !important;
    text-overflow: clip !important;
    line-height: 1.3;
}

[data-testid="stMetricValue"], [data-testid="stMetricValue"] * {
    font-family: 'Source Serif 4', Georgia, serif;
    white-space: normal !important;
    overflow-wrap: anywhere;
    overflow: visible !important;
    text-overflow: clip !important;
    line-height: 1.2;
}

/* ---------- sidebar nav ---------- */
[data-testid="stSidebar"] .stRadio [role="radiogroup"] { gap: 1px; }

[data-testid="stSidebar"] .stRadio [role="radiogroup"] label {
    border-radius: 8px;
    padding: 7px 10px;
    transition: background .15s ease;
}

[data-testid="stSidebar"] .stRadio [role="radiogroup"] label:hover { background: var(--pm-raise); }

[data-testid="stSidebar"] .stRadio [role="radiogroup"] label:has(input:checked) {
    background: color-mix(in srgb, var(--pm-accent) 13%, transparent);
}

[data-testid="stSidebar"] .stRadio [role="radiogroup"] label:has(input:checked) p { font-weight: 600; }

.pm-rail {
    font-size: .68rem;
    font-weight: 600;
    letter-spacing: .12em;
    text-transform: uppercase;
    opacity: .5;
    margin: 1.4rem 0 .5rem;
}

/* ---------- tabs (1.60 renders these with react-aria) ---------- */
[data-testid="stTabs"] [role="tablist"] {
    gap: 22px;
    border-bottom: 1px solid var(--pm-line-soft);
}

[data-testid="stTab"] {
    padding: 0 0 9px;
    font-weight: 500;
    opacity: .6;
    border-bottom: 2px solid transparent;
    margin-bottom: -1px;
}

[data-testid="stTab"]:hover { opacity: .85; }

[data-testid="stTab"][aria-selected="true"] {
    opacity: 1;
    font-weight: 600;
    border-bottom-color: var(--pm-accent);
}

/* ---------- plotly: SVG text inherits app color, so charts follow the theme ---------- */
.js-plotly-plot .xtick text,
.js-plotly-plot .ytick text,
.js-plotly-plot .legendtext,
.js-plotly-plot .gtitle,
.js-plotly-plot .xtitle,
.js-plotly-plot .ytitle,
.js-plotly-plot .annotation-text,
.js-plotly-plot text.bartext-outside {
    fill: currentColor !important;
    opacity: .78;
}

.js-plotly-plot .gtitle { opacity: 1; font-weight: 600; }
.js-plotly-plot .xgrid, .js-plotly-plot .ygrid { stroke: var(--pm-line-soft) !important; }
.js-plotly-plot .xaxislayer-above path.xtick,
.js-plotly-plot .yaxislayer-above path.ytick { stroke: var(--pm-line-soft) !important; }

[data-testid="stPlotlyChart"], [data-testid="stVegaLiteChart"] {
    border: 1px solid var(--pm-line-soft);
    border-radius: 10px;
    padding: 6px 4px;
}

/* ---------- Ask AI landing ---------- */
.pm-landing {
    position: relative;
    display: grid;
    place-items: center;
    min-height: 58vh;
    margin: 0;
    text-align: center;
}

/* the map is decoration: it inherits text color and sits behind everything */
.pm-map {
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    height: min(52vh, 430px);
    width: auto;
    color: var(--pm-accent);
    pointer-events: none;
    z-index: 0;
}

.pm-landing-inner { position: relative; z-index: 1; max-width: 44ch; }

.pm-landing-inner h2 {
    font-family: 'Source Serif 4', Georgia, serif;
    font-size: clamp(1.5rem, 3vw, 2.15rem);
    font-weight: 600;
    line-height: 1.2;
    margin: 0 0 .55rem;
}

.pm-landing-inner p {
    font-size: .92rem;
    line-height: 1.55;
    opacity: .62;
    margin: 0;
}

/* suggestions read as quiet list items, not call-to-action buttons */
[data-testid="stSidebar"] .stButton > button {
    text-align: left;
    justify-content: flex-start;
    font-weight: 400;
    font-size: .84rem;
    line-height: 1.35;
    padding: 8px 11px;
    min-height: 0;
    height: auto;
    white-space: normal;
    border-color: transparent;
    background: transparent;
}

[data-testid="stSidebar"] .stButton > button:hover {
    background: var(--pm-raise);
    border-color: var(--pm-line-soft);
}

[data-testid="stSidebar"] .stButton > button p { font-size: .84rem; line-height: 1.35; }

/* ---------- recents list ---------- */
/* outlined rather than filled: one accent value that reads on cream and charcoal */
[data-testid="stSidebar"] .stButton > button[kind="primary"] {
    background: transparent;
    border: 1px solid var(--pm-accent);
    color: var(--pm-accent);
    font-weight: 600;
    text-align: center;
    justify-content: center;
    font-size: .86rem;
    margin-bottom: .5rem;
}

[data-testid="stSidebar"] .stButton > button[kind="primary"]:hover {
    background: color-mix(in srgb, var(--pm-accent) 12%, transparent);
    border-color: var(--pm-accent);
    color: var(--pm-accent);
}

[data-testid="stSidebar"] .stButton > button[kind="primary"] p {
    font-weight: 600;
    color: var(--pm-accent);
}

/* delete affordance stays hidden until the row is hovered */
[data-testid="stSidebar"] [data-testid="stHorizontalBlock"] button {
    opacity: .0;
    transition: opacity .14s ease;
    padding-left: 4px;
    padding-right: 4px;
}

[data-testid="stSidebar"] [data-testid="stHorizontalBlock"]:hover button { opacity: .55; }
[data-testid="stSidebar"] [data-testid="stHorizontalBlock"] button:hover { opacity: 1; }

/* the conversation title itself must always be readable */
[data-testid="stSidebar"] [data-testid="stHorizontalBlock"] > div:first-child button {
    opacity: 1;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    display: block;
}

[data-testid="stSidebar"] [data-testid="stExpander"] {
    border: none;
    background: transparent;
    box-shadow: none;
}

[data-testid="stSidebar"] [data-testid="stExpander"] summary { padding-left: 0; font-size: .8rem; }

/* ---------- chat ---------- */
[data-testid="stChatMessage"] {
    background: var(--pm-raise);
    border: 1px solid var(--pm-line-soft);
    border-radius: 10px;
    padding: 12px 15px;
}

@media (max-width: 900px) {
    .block-container { padding-top: 3.25rem; }
}

@media (prefers-reduced-motion: reduce) {
    * { transition: none !important; animation: none !important; }
}
</style>
""".replace("FONT_URL", FONTS)


def inject_theme():
    st.markdown(CSS, unsafe_allow_html=True)
