"""Prep: walking into a colony knowing its problems, practising against a rival, handling the first hour of a
crisis, testing messages on real people, and the Monday brief that pulls it all together."""

import json
import math
import random

import numpy as np
import requests

import geo
import live_pulse
from config import ANSWER_MODEL

NOMINATIM = "https://nominatim.openstreetmap.org/search"


def _chat(api_key, messages, temperature=0.3, json_mode=True, model=ANSWER_MODEL):
    from openai import OpenAI

    kw = {"response_format": {"type": "json_object"}} if json_mode else {}
    resp = OpenAI(api_key=api_key, timeout=120).chat.completions.create(model=model, temperature=temperature, messages=messages, **kw)
    text = resp.choices[0].message.content
    return json.loads(text) if json_mode else text


# ----------------------------------------------------------------------
# Walk-In Brief
# ----------------------------------------------------------------------
def geocode(place, near="Hyderabad, Telangana"):
    """A colony or landmark name -> (lon, lat, label), via OpenStreetMap's Nominatim (one request, cached by callers)."""
    try:
        r = requests.get(NOMINATIM, params={"q": f"{place}, {near}", "format": "json", "limit": 1},
                         headers={"User-Agent": "peoples-mandate-ai/1.0 (walk-in brief)"}, timeout=15)
        r.raise_for_status()
        hits = r.json()
    except Exception:
        return None
    if not hits:
        return None
    return float(hits[0]["lon"]), float(hits[0]["lat"]), hits[0].get("display_name", place)


def ward_at(lon, lat):
    for w in geo.all_wards():
        if geo.contains(w, lon, lat):
            return w["properties"]["ward"]
    return None


def seat_at(lon, lat):
    for s in geo.seats():
        if geo.contains(geo.area(s, use_wards=False), lon, lat):
            return s
    return None


def _squash(text):
    """Lowercase letters only, 'ward 102' and doubled letters removed: Rahamath/Rahmath/Rehmat Nagar come close."""
    import re
    t = re.sub(r"\bward\b|\d+", " ", str(text).lower())
    t = "".join(ch for ch in t if ch.isalpha())
    return re.sub(r"(.)\1+", r"\1", t)


def _near(name, text):
    """True when a place name appears in the text, allowing the spelling variants of Hyderabad locality names."""
    from difflib import SequenceMatcher

    a, b = _squash(name), _squash(text)
    if len(a) < 4 or not b:
        return False
    if a in b:
        return True
    n = len(a)
    return any(SequenceMatcher(None, a, b[i:i + n]).ratio() >= 0.72 for i in range(0, max(1, len(b) - n + 1)))


def walk_in(lon, lat, place_label, tickets, issues, promises, division_shares, party):
    """Facts for the exact place: ward, seat, complaints and promises that name it or its ward, and the division estimate."""
    ward = ward_at(lon, lat)
    seat = seat_at(lon, lat)
    names = [n for n in (place_label.split(",")[0], ward) if n and _squash(n)]
    facts = {"ward": ward, "seat": seat, "names": names}
    facts["tickets"] = [t for t in tickets if any(_near(n, t.get("area", "")) for n in names)]
    facts["issues"] = [i for i in issues if any(_near(n, f"{i.get('location', '')} {i.get('division', '')} {i.get('title', '')}") for n in names)]
    facts["promises"] = [p for p in promises if p.get("status") not in ("Suggested", "Rejected") and any(_near(n, p.get("area", "") + " " + p.get("promise", "")) for n in names)]
    facts["division"] = None
    if division_shares is not None and ward:
        for div in division_shares["Division"].unique():
            if _near(div, ward) or _near(ward, div):
                d = division_shares[division_shares["Division"] == div].sort_values("Year")
                facts["division"] = {"name": div, "rows": d.to_dict("records")}
    return facts


BRIEF_PROMPT = """You prepare a leader for walking into a colony in the next five minutes. You get FACTS about the place.
Write, using ONLY the facts: three talking points the leader can say there (each one sentence, specific to the place, with any numbers),
one thing NOT to say or promise there, and one question to ask residents. Give each in English and Telugu.
Return ONLY JSON: {"points": [{"en": "...", "te": "..."}], "avoid": {"en": "...", "te": "..."}, "ask": {"en": "...", "te": "..."}}.
If the facts are thin, keep the points general and say so in "avoid"."""


def talking_points(facts_text, api_key):
    try:
        return {"ok": True, **_chat(api_key, [{"role": "system", "content": BRIEF_PROMPT}, {"role": "user", "content": facts_text}])}
    except Exception as exc:
        return {"ok": False, "error": live_pulse._openai_reason(exc)}


# ----------------------------------------------------------------------
# Debate Sparring
# ----------------------------------------------------------------------
def rival_turn(rival, party, rival_lines, history, api_key):
    """The simulated rival's next line: sharp, in their public style, using only their public record and the evidence."""
    system = (f"SIMULATION FOR PRACTICE ONLY. You play {rival} of {party} in a Telugu TV debate against OUR leader. Speak in their public style: sharp, "
              "specific, short (2-3 sentences), in the language the leader last used (Telugu or English). Attack using ONLY these facts, which include what "
              f"{rival} has publicly said and the record of the constituency:\n" + "\n".join(f"- {l}" for l in rival_lines) +
              "\nNever invent statistics or events. Push on the weakest points. Return plain text only.")
    msgs = [{"role": "system", "content": system}] + [{"role": "assistant" if h["who"] == "rival" else "user", "content": h["text"]} for h in history]
    if not history:
        msgs.append({"role": "user", "content": "Open the debate with your strongest attack."})
    try:
        return {"ok": True, "text": _chat(api_key, msgs, temperature=0.7, json_mode=False)}
    except Exception as exc:
        return {"ok": False, "error": live_pulse._openai_reason(exc)}


JUDGE_PROMPT = """You coach a politician after a practice debate exchange. You get the EVIDENCE (numbered), the rival's attack and the politician's answer.
Score the answer and return ONLY JSON:
{"facts_right": 0-10 (are the numbers and claims in the answer supported by the evidence? penalise anything the evidence contradicts or lacks),
 "responsiveness": 0-10 (did it answer the attack, or dodge?),
 "trap": "" or the trap the answer fell into (conceding a false premise, promising something new, attacking a person, getting a number wrong),
 "missed": the strongest fact from the evidence they could have used, with its [E#],
 "better": a better answer in two sentences, in the language they used, using only the evidence}"""


def judge(evidence_lines, attack, answer, api_key):
    ev = "\n".join(f"[E{i + 1}] {l}" for i, l in enumerate(evidence_lines))
    try:
        return {"ok": True, **_chat(api_key, [{"role": "system", "content": JUDGE_PROMPT},
                                                {"role": "user", "content": f"EVIDENCE:\n{ev}\n\nRIVAL: {attack}\n\nANSWER: {answer}"}], temperature=0)}
    except Exception as exc:
        return {"ok": False, "error": live_pulse._openai_reason(exc)}


# ----------------------------------------------------------------------
# Crisis Playbook
# ----------------------------------------------------------------------
CRISIS_PROMPT = """A crisis has just happened in a Telangana constituency. You write the leader's first-hour playbook.
You get the CRISIS description, the office's CONTACTS list, and an EVIDENCE PACK. Use ONLY names and numbers from the contacts; never invent a
person, phone number, scheme amount or statistic. Where you would need a fact you do not have, write "CONFIRM:" and what to confirm.
Return ONLY JSON:
{"confirm_first": [facts to confirm before saying anything, each short],
 "first_hour": [{"minute": "0-10", "do": "...", "who": a name from contacts or "", "why": "..."}] (6-10 steps),
 "relief": [{"help": the kind of relief usually available for this (ex gratia, hospital costs, shelter, temporary water supply), "how": "CONFIRM: ... with which office"}],
 "statement_te": a short first statement in Telugu (sympathy, what is being done, when the next update comes; no blame, no numbers not confirmed),
 "statement_en": the same in English,
 "do_not": [things not to say or do, drawn from how such crises go wrong: blaming, speculating on cause, promising amounts, photo-ops before help],
 "next_update": "when to give the next update"}"""


def crisis_playbook(crisis, contacts, lines, api_key):
    ct = "\n".join(f"- {c.get('name')} · {c.get('role', '')} · {c.get('department', '')} · {c.get('phone', '')} · {c.get('area', '')}" for c in contacts) or "(no contacts saved)"
    ev = "\n".join(f"[E{i + 1}] {l}" for i, l in enumerate(lines))
    try:
        return {"ok": True, **_chat(api_key, [{"role": "system", "content": CRISIS_PROMPT},
                                                {"role": "user", "content": f"CRISIS: {crisis}\n\nCONTACTS:\n{ct}\n\nEVIDENCE PACK:\n{ev}"}], temperature=0.2)}
    except Exception as exc:
        return {"ok": False, "error": live_pulse._openai_reason(exc)}


# ----------------------------------------------------------------------
# Message Lab
# ----------------------------------------------------------------------
VARIANT_PROMPT = """Draft message variants for a real-people test. You get the GOAL and FACTS. Write N short messages (each under 40 words, in the
language asked), each taking a genuinely different angle (a number, a local story, a contrast with the rival, a promise kept, a question).
Use only the facts. Return ONLY JSON: {"variants": ["...", "..."]}"""


def draft_variants(goal, facts, n, language, api_key):
    try:
        data = _chat(api_key, [{"role": "system", "content": VARIANT_PROMPT},
                               {"role": "user", "content": f"GOAL: {goal}\nLANGUAGE: {language}\nN: {n}\nFACTS:\n" + "\n".join(f"- {f}" for f in facts)}], temperature=0.8)
        return {"ok": True, "variants": [v for v in data.get("variants", []) if v][:n]}
    except Exception as exc:
        return {"ok": False, "error": live_pulse._openai_reason(exc)}


def pick_variant(n):
    return random.randrange(n)


def results(responses, n_variants):
    """Per variant: responses, average rating with a 95% interval, share who would forward it; and whether one clearly leads."""
    rows = []
    for v in range(n_variants):
        rs = [r for r in responses if int(r.get("variant", -1)) == v]
        ratings = [int(r["rating"]) for r in rs if r.get("rating") is not None]
        shares = [bool(r.get("would_share")) for r in rs]
        n = len(ratings)
        mean = float(np.mean(ratings)) if n else None
        half = 1.96 * float(np.std(ratings, ddof=1)) / math.sqrt(n) if n > 1 else None
        rows.append({"Variant": v + 1, "Responses": n, "Average (1-5)": round(mean, 2) if mean is not None else None,
                     "95% range": f"{mean - half:.2f}–{mean + half:.2f}" if half is not None else "–",
                     "Would forward": f"{sum(shares) / len(shares) * 100:.0f}%" if shares else "–", "_lo": mean - half if half is not None else None,
                     "_hi": mean + half if half is not None else None, "_mean": mean})
    ranked = sorted([r for r in rows if r["_mean"] is not None], key=lambda r: -r["_mean"])
    verdict = "Not enough responses yet (aim for 30+ per variant)."
    if len(ranked) >= 2 and all(r["Responses"] >= 30 for r in ranked):
        if ranked[0]["_lo"] is not None and ranked[1]["_hi"] is not None and ranked[0]["_lo"] > ranked[1]["_hi"]:
            verdict = f"Variant {ranked[0]['Variant']} is clearly ahead."
        else:
            verdict = f"Variant {ranked[0]['Variant']} leads, but not clearly: the ranges overlap. Keep collecting or treat them as equal."
    return [{k: v for k, v in r.items() if not k.startswith("_")} for r in rows], verdict


# ----------------------------------------------------------------------
# Monday brief
# ----------------------------------------------------------------------
BRIEF_TEXT_PROMPT = """Write the leader's Monday 7 am brief from the ITEMS below (numbered). It is read aloud in about three minutes, so:
- open with the single most urgent thing, then at most six items, most urgent first;
- each item: what is happening, where, and the one action for this week;
- use only the items' facts and numbers, no invented ones; say "(internal estimate)" for campaign estimates.
Return ONLY JSON: {"en": the brief in English (plain paragraphs), "te": the same brief in natural spoken Telugu}"""


def monday_brief(items, api_key):
    text = "\n".join(f"{i + 1}. {x}" for i, x in enumerate(items))
    try:
        return {"ok": True, **_chat(api_key, [{"role": "system", "content": BRIEF_TEXT_PROMPT}, {"role": "user", "content": text}], temperature=0.2)}
    except Exception as exc:
        return {"ok": False, "error": live_pulse._openai_reason(exc)}


def speak(text, api_key, voice="onyx"):
    """Spoken audio (MP3 bytes) of the brief, via OpenAI's text-to-speech. Labelled as AI voice wherever it is played."""
    from openai import OpenAI

    try:
        r = OpenAI(api_key=api_key, timeout=180).audio.speech.create(model="gpt-4o-mini-tts", voice=voice, input=text[:4000],
                                                                     instructions="Speak clearly and calmly, like a news briefing, in the language of the text.")
        return {"ok": True, "audio": r.content}
    except Exception as exc:
        return {"ok": False, "error": live_pulse._openai_reason(exc)}
