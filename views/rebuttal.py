import json
import re

import streamlit as st

from components import empty_state, section
from config import ANSWER_MODEL, CONSTITUENCY_NAME, PARTIES, PARTY_LABELS, is_valid_api_key
from grounding import LANGUAGES, build_data_context, language_rule, result_rule
from speech_generator import SpeechGenerator

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

TITLE = "Rebuttal Builder"


def _system_prompt(ctx, party, language):
    speaker = PARTY_LABELS.get(party, party)
    return f"""You help the {speaker} campaign in {CONSTITUENCY_NAME} answer a claim made by another campaign.
Below is the COMPLETE dataset, every sheet in full.

{build_data_context(ctx)}

Rules:
{result_rule(ctx)}
- Use ONLY the data above. Never invent numbers, names, events or facts that are not there.
- Every fact belongs to exactly one party (it is tagged or sits in that party's column). Never
  attribute a fact to a different party, and name the party whenever you cite a fact.
- First find EVERY fact in the data that touches the claim's topic, from every party, including the
  party the claim is about, and list them all under what_the_data_says. Do not skip a party's own entry.
- Judge the claim against the data honestly. If the data contradicts it, say what the data shows.
  If the data supports it, say so. If the data neither supports nor contradicts it, say that plainly
  and keep the reply to what can be backed. Do not stretch unrelated facts to fit.
- The sheets record what parties promise and claim, not verified results. When the only fact is a promise
  or a claim (\"Promised waivers\", \"Claimed earlier works\"), say it is a promise or claim with nothing
  showing it was delivered, and count that under where_they_may_be_right.
- No personal attacks and no allegations about anyone's family or character.
- The reply is what a spokesperson could say aloud in their own voice ("we", "our"), 2 to 4 short
  sentences, without saying "the data shows". It must contain no claim the data doesn't back.
{language_rule(language)}

Respond with ONLY minified JSON, no markdown fences, in exactly this shape:
{{"what_the_data_says": ["<fact with its party and number>", "..."], "reply": "<spokesperson reply>", "where_they_may_be_right": "<the part of the claim the data does support, or a plain statement that nothing in the data supports it>"}}
"""


@st.cache_data(show_spinner=False)
def _rebut(_client, claim, party, language, _system):
    resp = _client.chat.completions.create(
        model=ANSWER_MODEL,
        messages=[{"role": "system", "content": _system}, {"role": "user", "content": f"The claim: {claim}"}],
        temperature=0.2,
    )
    cleaned = resp.choices[0].message.content.replace("```json", "").replace("```", "").strip()
    return json.loads(cleaned)


def render(ctx, sidebar):
    section(
        "Rebuttal builder",
        "Paste something an opponent has said. The reply comes only from your data, and it also tells you "
        "where the claim may be fair, so you don't get caught out.",
    )

    if not is_valid_api_key(ctx.api_key):
        st.error("Add a real OPENAI_API_KEY to .streamlit/secrets.toml to enable this page.")
        return

    c1, c2 = st.columns([3, 1])
    with c1:
        party = st.selectbox("Replying for", PARTIES, format_func=lambda p: PARTY_LABELS.get(p, p))
    with c2:
        language = st.selectbox("Language", LANGUAGES)

    claim = st.text_area("What did they say?", height=110, placeholder="e.g. Congress has done nothing on water bills in Jubilee Hills.")
    if not st.button("Build the rebuttal", type="primary"):
        return
    if not claim.strip():
        empty_state("Paste a claim first.")
        return

    try:
        with st.spinner("Checking the claim against your sheets..."):
            result = _rebut(OpenAI(api_key=ctx.api_key), claim.strip(), party, language, _system_prompt(ctx, party, language))
    except Exception as exc:
        st.error("Couldn't build the rebuttal.")
        st.exception(exc)
        return

    st.markdown("##### What the data says")
    for point in result.get("what_the_data_says", []):
        st.markdown(f"- {point}")

    st.markdown("##### Suggested reply")
    st.info(result.get("reply", ""))

    st.markdown("##### Where they may be right")
    st.write(result.get("where_they_may_be_right", ""))

    written = " ".join([*result.get("what_the_data_says", []), result.get("reply", ""), result.get("where_they_may_be_right", "")])
    unmatched = SpeechGenerator._check_unverified_numbers(written, build_data_context(ctx))
    if unmatched:
        st.warning(f"These numbers don't appear anywhere in your sheets, so check them before use: {', '.join(unmatched)}")
    elif re.search(r"\d", written):
        st.caption("Every number above appears in your sheets. That does not prove it is attached to the right fact, so read it once.")

    ctx.logger.log_analysis("rebuttal", ["all sheets"], claim.strip()[:120])
