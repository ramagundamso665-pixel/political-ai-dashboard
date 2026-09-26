import json
import random

import streamlit as st

import conversations
import area_survey
import registers
import telangana
from components import source_badge
from grounding import LANGUAGES, build_data_context, language_rule, result_rule
from config import (
    ANSWER_MODEL,
    CONSTITUENCY_NAME,
    PARTIES,
    PARTY_LABELS,
    SHEET_KEY_MAP,
    SOURCE_METADATA,
    is_valid_api_key,
)

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

TITLE = "Ask AI"

# Deliberately about evidence and fieldwork rather than persuasion — this sits in
# front of campaign staff every morning and should point them at the data.
GREETINGS = [
    "What does the ground say today?",
    "Where should the campaign look next?",
    "Which division deserves the next visit?",
    "What has changed since the last round?",
    "Which way is Jubilee Hills moving?",
    "Who is still undecided?",
    "What are the surveys disagreeing on?",
    "Start with what the data can prove.",
    "Ask before the rally, not after.",
    "Which numbers would survive a challenge?",
]

# Every one of these is answerable from the loaded sheets — a suggestion the data
# can't answer would teach people the tool doesn't work.
SUGGESTIONS = [
    "Which division is most winnable right now?",
    "Why do the surveys disagree so much on BJP?",
    "What's our biggest weakness with women voters?",
    "Summarize our ground campaign strengths vs weaknesses.",
    "Which divisions swung hardest between 2023 and 2025?",
    "How has Maganti Gopinath's vote share changed since 2014?",
    "Which age group is most up for grabs?",
    "Which community groups are closest to a tie?",
    "Who out-campaigned whom in the last week of October?",
    "Which party's social media posts got the most engagement?",
    "What issues is Congress attacking BRS on?",
    "Which survey looks least reliable, and why?",
]
SUGGESTIONS_SHOWN = 4


def _greeting():
    """One greeting per session, reshuffled only when the conversation is cleared."""
    if "greeting" not in st.session_state:
        st.session_state.greeting = random.choice(GREETINGS)
    return st.session_state.greeting


@st.cache_data(ttl=60, show_spinner=False)
def _registers_text():
    """Staff-kept RTI and local-issue logs, if the tables exist. Silent when they don't."""
    try:
        url, key = st.secrets.get("SUPABASE_URL"), st.secrets.get("SUPABASE_SERVICE_KEY")
        if not (url and key):
            return ""
        text = registers.context_text(registers.fetch(url, key, "rti_requests"), registers.fetch(url, key, "local_issues"))
        try:
            table, _ = area_survey.by_area(area_survey.prepare(registers.fetch(url, key, "area_ratings")))
        except Exception:
            table = None
        if table is not None and not table.empty:
            text += "\nAREA SURVEY (volunteered WhatsApp answers, self-selected; areas with at least 5 answers):\n" + "\n".join(
                f"- {r['Area']}: {r['Answers']} answers, average rating {r['Average rating']} of 5, most named issue {r['Most named issue']} ({r['Share naming it']})"
                for _, r in table.iterrows()
            )
        return text
    except Exception:
        return ""


def _system_prompt(ctx, speaking_party, language):
    extra = _registers_text()
    extra_block = f"\n{extra}\n(These entries were typed in by campaign staff. Treat them as unverified reports, and say so when you use them.)\n" if extra else ""
    speaker = PARTY_LABELS.get(speaking_party, speaking_party)
    return f"""You are People's Mandate AI, answering questions about the {CONSTITUENCY_NAME} campaign
on behalf of the {speaker} campaign.
Below is the COMPLETE dataset, every sheet in full — not a sample.

{build_data_context(ctx)}
{extra_block}
Rules:
{result_rule(ctx)}
- Answer ONLY using the data above. Never invent numbers, names, or facts not present here.
- This dataset covers MULTIPLE parties (BRS, Congress/INC, BJP, AIMIM). Every fact is
  attributable to exactly one party — never attribute a fact to a party other than the
  one it's tagged with, and never merge facts from different parties into one unlabeled claim.
- When the question says "we", "our", or "us", that means {speaker} specifically.
  Facts about other parties are about competitors, not "us" — name the party explicitly when citing them.
- If the data doesn't cover the question, say so plainly instead of guessing.
- Never tie a fact to a voter group (women, youth, a caste or religion) unless the data does:
  a Demo_Preferences row for that group, or a note that names the group. A general weakness
  such as party unity or anti-incumbency is NOT a weakness "with women". For a question about
  a group, give that group's Demo_Preferences numbers for every party, compare {speaker} against
  the leader, add any note that names the group, and say plainly if no group-specific weakness
  is recorded.
{language_rule(language)}
- Pick the ONE sheet most relevant to the question, or "none" if no single sheet applies.
- Pick a chart type only if comparing numbers across rows would help: table, bar, line, area, pie. Otherwise "none".

Respond with ONLY minified JSON, no markdown fences, in exactly this shape:
{{"sheet": "<sheet name or none>", "chart": "<table|bar|line|area|pie|none>", "answer": "<answer as plain text>"}}
"""


@st.cache_data(show_spinner=False)
def _ask_once(_client, question, party, language, _system):
    resp = _client.chat.completions.create(
        model=ANSWER_MODEL,
        messages=[{"role": "system", "content": _system}, {"role": "user", "content": question}],
        temperature=0.2,
    )
    cleaned = resp.choices[0].message.content.replace("```json", "").replace("```", "").strip()
    return json.loads(cleaned)


def _render_chart(df, chart):
    numeric = df.select_dtypes(include="number")
    if numeric.empty or chart not in ("bar", "line", "area"):
        return
    if chart == "line":
        st.line_chart(numeric)
    elif chart == "area":
        st.area_chart(numeric)
    else:
        st.bar_chart(numeric)


def _suggestions():
    """A fresh handful per conversation, so a new chat offers new starting points."""
    if "suggestions" not in st.session_state:
        st.session_state.suggestions = random.sample(SUGGESTIONS, SUGGESTIONS_SHOWN)
    return st.session_state.suggestions


def _start_new_chat():
    st.session_state.conversation_id = conversations.new_id()
    st.session_state.messages = []
    st.session_state.pop("greeting", None)
    st.session_state.pop("suggestions", None)


def _sidebar_panel(sidebar, messages):
    """Persistent controls live here so the landing stays a bare search bar."""
    with sidebar:
        if st.button("New chat", key="new_chat", width="stretch", type="primary"):
            _start_new_chat()
            st.rerun()

        recents = conversations.listing()
        if recents:
            st.markdown('<div class="pm-rail">Recent</div>', unsafe_allow_html=True)
            current = st.session_state.conversation_id
            for item in recents[:12]:
                row, remove = st.columns([0.84, 0.16])
                active = " ●" if item["id"] == current else ""
                if row.button(
                    item["title"] + active,
                    key=f"open_{item['id']}",
                    width="stretch",
                    help=f"{item['turns']} question(s) · {item['updated_at'][:16].replace('T', ' ')}",
                ):
                    st.session_state.conversation_id = item["id"]
                    st.session_state.messages = conversations.load(item["id"])
                    st.rerun()
                if remove.button("✕", key=f"del_{item['id']}", help="Delete this conversation"):
                    conversations.delete(item["id"])
                    if item["id"] == current:
                        _start_new_chat()
                    st.rerun()

        st.markdown('<div class="pm-rail">Speaking as</div>', unsafe_allow_html=True)
        party = st.selectbox(
            "Speaking as",
            PARTIES,
            format_func=lambda p: PARTY_LABELS.get(p, p),
            key="ask_ai_party",
            label_visibility="collapsed",
        )
        st.markdown('<div class="pm-rail">Reply in</div>', unsafe_allow_html=True)
        language = st.selectbox(
            "Reply in", LANGUAGES, key="ask_ai_language", label_visibility="collapsed"
        )
    return party, language


def _landing():
    st.markdown(
        f"""
        <div class="pm-landing">
            {telangana.svg()}
            <div class="pm-landing-inner">
                <h2>{_greeting()}</h2>
                <p>Grounded in this campaign's own sheets. Every answer names the source it came from.</p>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_message(ctx, msg):
    """Replay one stored message, chart and source badge included.

    The sheet and chart choice are kept on the message itself so a rerun
    reproduces the whole answer rather than just its text.
    """
    with st.chat_message(msg["role"]):
        sheet = msg.get("sheet")
        known = sheet in ctx.raw_sheets

        if known:
            source_type = SOURCE_METADATA.get(SHEET_KEY_MAP.get(sheet, ""), {}).get("type", "internal")
            st.markdown(source_badge(source_type, f"Sheet: {sheet}"), unsafe_allow_html=True)

        st.write(msg["content"])

        if known:
            df = ctx.raw_sheets[sheet]
            _render_chart(df, msg.get("chart", "none"))
            st.dataframe(df, hide_index=True, width="stretch")


def render(ctx, sidebar):
    st.session_state.setdefault("messages", [])
    st.session_state.setdefault("pending_prompt", None)
    st.session_state.setdefault("conversation_id", conversations.new_id())

    if not is_valid_api_key(ctx.api_key):
        st.error("Add a real OPENAI_API_KEY to .streamlit/secrets.toml to enable this page.")
        return

    client = OpenAI(api_key=ctx.api_key)
    messages = st.session_state.messages
    speaking_party, language = _sidebar_panel(sidebar, messages)

    if messages:
        for msg in messages:
            _render_message(ctx, msg)
    else:
        _landing()
        _, chips, _ = st.columns([1, 8, 1])
        with chips:
            cols = st.columns(2)
            for i, suggestion in enumerate(_suggestions()):
                if cols[i % 2].button(suggestion, key=f"sug_{i}", width="stretch"):
                    st.session_state.pending_prompt = suggestion

    # chat_input docks to the viewport bottom at page level; nested in a column it
    # stays inline, which is what keeps the empty state centred.
    _, middle, _ = st.columns([1, 8, 1])
    with middle:
        typed = st.chat_input("Ask anything about your campaign data...")

    prompt = st.session_state.pending_prompt or typed
    st.session_state.pending_prompt = None

    if not prompt:
        return

    try:
        with st.spinner("Reading the sheets..."):
            result = _ask_once(client, prompt, speaking_party, language, _system_prompt(ctx, speaking_party, language))
    except Exception as exc:
        st.error("Answer generation failed")
        st.exception(exc)
        return

    answer = result.get("answer", "")
    sheet = result.get("sheet", "none")

    messages.append({"role": "user", "content": prompt})
    messages.append(
        {"role": "assistant", "content": answer, "sheet": sheet, "chart": result.get("chart", "none")}
    )

    stored = conversations.save(st.session_state.conversation_id, messages, speaking_party)
    if stored == "local" and conversations.backend() == "supabase":
        st.session_state.pending_toast = "Couldn't reach the database — this chat is saved on this server only for now."
    ctx.logger.log_analysis("ask_ai", [sheet], answer[:150])
    # re-run so the exchange renders from history, above the input and without the landing
    st.rerun()
