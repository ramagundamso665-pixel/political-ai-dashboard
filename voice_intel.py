"""Language-model steps for Voice & Truth: turning a spoken complaint into a ticket, and finding promises
in a speech. Both return plain dicts and never raise; each result says what the model was asked, so a
person confirms before anything is filed or published."""

import hashlib
import json
from datetime import datetime, timezone

import live_pulse
from config import ANSWER_MODEL
from registers import CATEGORIES

TICKET_PROMPT = f"""A resident of a Telangana constituency has spoken a complaint to the MLA's office. You get the transcript
(Telugu, Urdu, Dakhni, Hindi or English, often mixed). Return ONLY JSON:
{{"summary_en": one plain English sentence of what is wrong and where,
 "summary_te": the same in Telugu script,
 "category": one of {json.dumps(CATEGORIES)},
 "area": the colony, street, landmark or division named, or "" if none,
 "department": the body that fixes this (for example GHMC, HMWSSB, TGSPDCL, Police, Revenue, Health, Education, Civil Supplies), or "",
 "urgency": "High" if there is danger to life, health or a total loss of water or power for days, "Medium" if a service is failing, else "Low",
 "readback_te": a short Telugu sentence the office reads back to the caller to confirm: what the problem is and where,
 "missing": what the office should ask for if the area or problem is unclear, or ""}}
Use only what the caller said. Do not invent names, places or numbers."""

PROMISE_PROMPT = """You read a transcript of a Telangana politician's speech, in pieces with start times in seconds.
Find every PROMISE or COMMITMENT the speaker makes: something they say will be done, built, given, fixed or delivered.
Ignore slogans, attacks on opponents, general praise and past achievements (unless restated as a future commitment).
Return ONLY JSON: {"promises": [{"at_s": start time of the piece it is in,
 "quote": the exact words (in the original language),
 "promise": one plain English sentence of what was promised,
 "area": the place it is for, or "",
 "due": the deadline or time frame if one is stated (for example "within six months", "next year"), or ""}]}
If there are none, return {"promises": []}. Do not invent promises that are not in the words."""


def _chat(api_key, system, user, model=ANSWER_MODEL):
    from openai import OpenAI

    resp = OpenAI(api_key=api_key, timeout=120).chat.completions.create(
        model=model, temperature=0, response_format={"type": "json_object"},
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
    )
    return json.loads(resp.choices[0].message.content)


def ticket_number(text):
    stamp = datetime.now(timezone.utc).strftime("%y%m%d")
    return f"JV-{stamp}-{hashlib.sha1((text + datetime.now(timezone.utc).isoformat()).encode()).hexdigest()[:5].upper()}"


def structure_complaint(transcript, api_key):
    try:
        data = _chat(api_key, TICKET_PROMPT, transcript)
    except Exception as exc:
        return {"ok": False, "error": live_pulse._openai_reason(exc)}
    cat = data.get("category") if data.get("category") in CATEGORIES else "Other"
    return {"ok": True, "error": None, **{k: str(data.get(k, "") or "") for k in ("summary_en", "summary_te", "area", "department", "readback_te", "missing")},
            "category": cat, "urgency": data.get("urgency") if data.get("urgency") in ("High", "Medium", "Low") else "Medium"}


def find_promises(segments, api_key, chunk=60):
    """Promises in a timestamped transcript. Long speeches are read in pieces of ~60 segments."""
    found, error = [], None
    for i in range(0, len(segments), chunk):
        part = segments[i:i + chunk]
        text = "\n".join(f"[{s['start']:.0f}s] {s['text']}" for s in part)
        try:
            data = _chat(api_key, PROMISE_PROMPT, text)
        except Exception as exc:
            error = live_pulse._openai_reason(exc)
            continue
        for p in data.get("promises", []):
            if p.get("promise") and p.get("quote"):
                found.append({"at_s": float(p.get("at_s") or part[0]["start"]), "quote": p["quote"], "promise": p["promise"],
                              "area": p.get("area", ""), "due": p.get("due", "")})
    return {"ok": not error or bool(found), "error": error, "promises": found}


# ----------------------------------------------------------------------
# Open Office Ledger: an append-only record anyone can check has not been edited
# ----------------------------------------------------------------------
GENESIS = "0" * 64


def entry_hash(seq, kind, body, prev_hash):
    """sha256 over the entry's number, kind, contents (which carry their own timestamp) and the previous hash."""
    canonical = json.dumps({"seq": seq, "kind": kind, "body": body, "prev": prev_hash}, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def new_entry(entries, kind, body):
    """The next ledger row, chained to the last one. `entries` are the existing rows."""
    last = max(entries, key=lambda e: int(e["seq"])) if entries else None
    seq = (int(last["seq"]) + 1) if last else 1
    prev = last["hash"] if last else GENESIS
    body = {**body, "_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    return {"seq": seq, "kind": kind, "body": body, "prev_hash": prev, "hash": entry_hash(seq, kind, body, prev)}


def verify(entries):
    """Recompute the chain. Returns (ok, first bad seq or None, reason)."""
    prev = GENESIS
    for e in sorted(entries, key=lambda e: int(e["seq"])):
        body = e["body"] if isinstance(e["body"], dict) else json.loads(e["body"])
        if e["prev_hash"] != prev:
            return False, e["seq"], "an entry before this one was removed or changed"
        if e["hash"] != entry_hash(int(e["seq"]), e["kind"], body, prev):
            return False, e["seq"], "this entry's contents were changed after it was recorded"
        prev = e["hash"]
    return True, None, "every entry is unchanged since it was recorded"
