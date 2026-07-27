"""Layer 4: speech generation. Every speech is grounded in a fact block built
from real sheet data; the model is instructed to never invent numbers, and a
post-generation check flags any number that doesn't trace back to a fact."""

import re

from openai import OpenAI

from config import PARTIES, PARTY_LABELS


SYSTEM_PROMPT = """You are a campaign speechwriter for an Indian local election.

You will be given a block of VERIFIED FACTS pulled directly from campaign data.

Rules (do not break these):
1. Use ONLY the numbers, names, and claims present in VERIFIED FACTS.
2. Never invent a percentage, scheme name, date, or statistic that is not in VERIFIED FACTS.
3. If the speech would benefit from a fact you don't have, write the bracketed
   placeholder [DATA NEEDED: <what's missing>] instead of guessing.
4. Tone: respectful, energetic, grounded — not inflammatory, no personal attacks
   on rival candidates' families or unverifiable allegations.
5. Keep it deliverable out loud: short sentences, clear structure.
"""


class SpeechGenerator:
    def __init__(self, analyzer, tracker, api_key):
        self.analyzer = analyzer
        self.tracker = tracker
        self.client = OpenAI(api_key=api_key) if api_key else None

    def _build_facts(self, party, audience_subgroup, theme_keyword):
        facts = []
        cited = []

        demo = self.analyzer.demographic_preferences()
        match = next((d for d in demo if d["subgroup"] == audience_subgroup), None)
        if match:
            shares_str = ", ".join(f"{PARTY_LABELS.get(p, p)} {v}%" for p, v in match["shares"].items())
            fact = f"Among {audience_subgroup} voters, current estimated support: {shares_str}."
            facts.append(fact)
            cited.append({"claim": fact, "source": "Internal Demographic Preference Tracking", "confidence": "medium"})

        gc = self.analyzer.ground_campaign_matrix()
        theme_rows = gc[gc["Subcategory"].astype(str).str.contains(theme_keyword, case=False, na=False)]
        party_col = "Congress" if party == "INC" else party
        for _, row in theme_rows.iterrows():
            if party_col in row.index and str(row[party_col]).strip() not in ("", "–", "nan", "NaN"):
                fact = f"On {row['Subcategory']}, our campaign's position: {row[party_col]}."
                facts.append(fact)
                cited.append({"claim": fact, "source": "Ground Campaign Field Notes", "confidence": "low"})

        pred = self.analyzer.predict_outcome()
        lead_fact = (
            f"Blended estimate across historical results, division tracking, and surveys: "
            f"{PARTY_LABELS.get(pred['predicted_leader'], pred['predicted_leader'])} leads by "
            f"{pred['margin_pct']} points (confidence: {pred['confidence_label']})."
        )
        facts.append(lead_fact)
        cited.append({"claim": lead_fact, "source": "Prediction Engine (blended)", "confidence": "medium"})

        return "\n".join(f"- {f}" for f in facts), cited

    def generate_speech(self, party, audience_subgroup, theme_keyword, event_type):
        if self.client is None:
            return {
                "error": "No OpenAI API key configured. Add OPENAI_API_KEY to .streamlit/secrets.toml.",
            }

        facts_block, cited = self._build_facts(party, audience_subgroup, theme_keyword)

        user_prompt = f"""
Write a {event_type} speech for {PARTY_LABELS.get(party, party)}, targeted at {audience_subgroup} voters,
focused on the theme "{theme_keyword}", for the {self.analyzer.sheets.get('_constituency', 'constituency')} seat.

VERIFIED FACTS:
{facts_block}

Write the full speech now.
"""

        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
            )
        except Exception as e:
            return {"error": f"OpenAI request failed: {e}"}
        speech = response.choices[0].message.content

        unverified = self._check_unverified_numbers(speech, facts_block)

        talking_points = [f.strip("- ") for f in facts_block.split("\n") if f.strip()]

        self.tracker.add_claim({
            "claim": f"Speech generated for {audience_subgroup} / {theme_keyword} / {event_type}",
            "source_id": "campaign_activity",
            "confidence": "medium",
            "data_point": {"party": party, "audience": audience_subgroup},
        })

        return {
            "speech": speech,
            "sources_cited": cited,
            "talking_points": talking_points,
            "verification_status": "NEEDS_REVIEW" if unverified else "VERIFIED",
            "unverified_numbers": unverified,
        }

    @staticmethod
    def _check_unverified_numbers(speech, facts_block):
        """Heuristic: every standalone number in the speech should appear
        somewhere in the facts block it was grounded on."""
        speech_numbers = set(re.findall(r"\d+(?:\.\d+)?%?", speech))
        fact_numbers = set(re.findall(r"\d+(?:\.\d+)?%?", facts_block))
        return sorted(speech_numbers - fact_numbers)
