"""War Room: seeing the next attack, the next story and the rival's next target before they arrive.

Everything here is computed from public feeds (Google News RSS, YouTube search, Google Trends) and the
campaign's own records (event log, division estimates, complaints, promises). The language-model steps
are only allowed to use the evidence they are handed, and every output says what it rests on.
"""

import json
import re
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone

import numpy as np
import pandas as pd

import live_pulse
from config import ANSWER_MODEL

PARTY_WORDS = {
    "BRS": ["brs", "bharat rashtra", "ktr", "kcr", "harish rao", "kavitha", "గులాబీ", "బీఆర్ఎస్"],
    "INC": ["congress", "revanth", "inc ", "కాంగ్రెస్", "రేవంత్"],
    "BJP": ["bjp", "kishan reddy", "bandi sanjay", "బీజేపీ"],
    "AIMIM": ["aimim", "mim ", "owaisi", "majlis", "మజ్లిస్"],
}
PARTY_ALIASES = {"CONGRESS": "INC", "CONG": "INC", "INC": "INC", "BRS": "BRS", "TRS": "BRS", "BJP": "BJP", "AIMIM": "AIMIM", "MIM": "AIMIM"}


def _chat(api_key, system, user, model=ANSWER_MODEL):
    from openai import OpenAI

    resp = OpenAI(api_key=api_key, timeout=120).chat.completions.create(
        model=model, temperature=0.2, response_format={"type": "json_object"},
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
    )
    return json.loads(resp.choices[0].message.content)


# ----------------------------------------------------------------------
# Attack Forecast
# ----------------------------------------------------------------------
ATTACK_PROMPT = """You are the opposition research desk of a Telangana campaign, turned on your OWN leader so they are ready first.
You get an EVIDENCE PACK of public and internal facts about the leader and the seat, numbered [E1], [E2]...
[E1] says who OUR leader and party are. Attacks are what RIVAL parties would say against OUR leader. Read election lines carefully:
if our party won the latest contest, do not call it a loss.
Find the attacks rivals (BRS, Congress, BJP, AIMIM) are most likely to make: broken or late promises, service failures in named areas,
weak electoral spots, contradictions. Use ONLY the evidence pack; cite it by number; never add outside facts or numbers.
For the defence, you may ONLY point to evidence lines that genuinely answer the attack. Do NOT write the defence in prose.
Return ONLY JSON: {"attacks": [{"attack": the line a rival would say (one sentence),
 "who": the party most likely to use it, "evidence": ["E3"], "likelihood": "High|Medium|Low", "damage": "High|Medium|Low",
 "defence_evidence": ["E5"] (evidence lines that answer it, or [] if none truly do),
 "todo": the specific thing to do or proof to gather now (a site visit, a completion certificate, an RTI reply, a satellite check)}]}
ranked most dangerous first, at most 10."""


def evidence_pack(lines):
    return "\n".join(f"[E{i + 1}] {line}" for i, line in enumerate(lines) if line)


def attack_forecast(lines, api_key):
    if not lines:
        return {"ok": False, "error": "no evidence to work from yet"}
    try:
        data = _chat(api_key, ATTACK_PROMPT, evidence_pack(lines))
    except Exception as exc:
        return {"ok": False, "error": live_pulse._openai_reason(exc)}
    # the defence is assembled from the cited evidence lines themselves, never written by the model
    numbered = [l for l in lines if l]
    out = []
    for a in data.get("attacks", [])[:10]:
        ids = [int(re.sub(r"\D", "", e)) for e in a.get("defence_evidence") or [] if re.sub(r"\D", "", str(e))]
        facts = [numbered[i - 1] for i in ids if 0 < i <= len(numbered)]
        a["defence"] = facts
        a["answer"] = ("On record: " + " ".join(facts)) if facts else "No answer on record yet."
        out.append(a)
    return {"ok": True, "error": None, "attacks": out}


# ----------------------------------------------------------------------
# Pre-Viral Radar
# ----------------------------------------------------------------------
def news_velocity(term, lang="en"):
    """Stories per day over 30 days; the last 3 days against the 27 before. Returns counts and a velocity ratio."""
    res = live_pulse.fetch_google_news(term, days=30, max_items=100, lang=lang)
    if not res["ok"]:
        return {"ok": False, "error": res["error"]}
    today = datetime.now(timezone.utc).date()
    per_day = Counter(a["published"].astimezone(timezone.utc).date() for a in res["articles"] if a["published"])
    recent = sum(per_day.get(today - timedelta(days=d), 0) for d in range(3))
    before = sum(per_day.get(today - timedelta(days=d), 0) for d in range(3, 30))
    base = before / 27 * 3
    return {"ok": True, "error": None, "recent": recent, "baseline": round(base, 1), "ratio": round((recent + 1) / (base + 1), 2),
            "capped": len(res["articles"]) >= 100, "latest": [a["title"] for a in live_pulse.latest_first(res["articles"])[:3]]}


def youtube_velocity(term, api_key):
    """Videos about the term in the last 3 days against the 27 before (two searches, 200 quota units)."""
    if not api_key:
        return {"ok": False, "error": "no YouTube key"}
    import requests

    def count(after, before):
        try:
            r = requests.get(live_pulse.YOUTUBE_SEARCH_API, params={"part": "id", "q": term, "type": "video", "regionCode": "IN", "maxResults": 50,
                                                                    "publishedAfter": after, "publishedBefore": before, "key": api_key}, timeout=10)
            r.raise_for_status()
            return len(r.json().get("items", []))
        except Exception:
            return None
    now = datetime.now(timezone.utc)
    fmt = "%Y-%m-%dT%H:%M:%SZ"
    recent = count((now - timedelta(days=3)).strftime(fmt), now.strftime(fmt))
    before = count((now - timedelta(days=30)).strftime(fmt), (now - timedelta(days=3)).strftime(fmt))
    if recent is None or before is None:
        return {"ok": False, "error": "YouTube search failed"}
    base = before / 27 * 3
    return {"ok": True, "error": None, "recent": recent, "baseline": round(base, 1), "ratio": round((recent + 1) / (base + 1), 2)}


def local_velocity(records, date_col, key_cols):
    """Complaints per area/category: last 7 days against the 4 weeks before. Rising clusters first."""
    if records.empty or date_col not in records:
        return pd.DataFrame()
    r = records.copy()
    r["_d"] = pd.to_datetime(r[date_col], errors="coerce", utc=True).dt.date
    r = r.dropna(subset=["_d"])
    today = date.today()
    r["_recent"] = r["_d"] >= today - timedelta(days=7)
    r["_before"] = (r["_d"] < today - timedelta(days=7)) & (r["_d"] >= today - timedelta(days=35))
    g = r.groupby(key_cols).agg(recent=("_recent", "sum"), before=("_before", "sum")).reset_index()
    g["weekly before"] = (g["before"] / 4).round(1)
    g["ratio"] = ((g["recent"] + 1) / (g["weekly before"] + 1)).round(2)
    return g[g["recent"] > 0].sort_values(["ratio", "recent"], ascending=False)


def radar_level(ratio, recent):
    if ratio >= 3 and recent >= 3:
        return "🔴 Rising fast"
    if ratio >= 1.8 and recent >= 2:
        return "🟠 Rising"
    return "⚪ Normal"


# ----------------------------------------------------------------------
# Opponent Target Detector
# ----------------------------------------------------------------------
def rival_activity(events, places, parties=("BRS", "INC", "BJP", "AIMIM"), days=45):
    """Events per place per party in the window, from the campaign's event log and staff-logged field events."""
    if events.empty:
        return pd.DataFrame()
    e = events.copy()
    e["party"] = e["party"].astype(str).str.upper().map(lambda p: PARTY_ALIASES.get(p.strip(), p.strip()))
    e["date"] = pd.to_datetime(e["date"], errors="coerce")
    latest = e["date"].max()
    e = e[e["date"] >= latest - pd.Timedelta(days=days)]
    e["place"] = e["place"].map(lambda p: match_place(p, places))
    t = e.pivot_table(index="place", columns="party", values="date", aggfunc="count", fill_value=0)
    for p in parties:
        if p not in t:
            t[p] = 0
    return t[list(parties)].reset_index()


def match_place(text, places):
    t = str(text).lower().replace(" ", "")
    for p in places:
        key = p.lower().replace(" ", "")
        if key[:6] and (key[:6] in t or t[:6] in key):
            return p
    return str(text)


def news_place_mentions(party, places, days=30):
    """How often recent Telugu and English news puts the party together with each place."""
    out = {}
    for place in places:
        q = f'"{place}" ({" OR ".join(w.strip() for w in PARTY_WORDS[party][:3])})'
        res = live_pulse.fetch_google_news(q, days=days, max_items=60)
        out[place] = len(res["articles"]) if res["ok"] else None
    return out


# ----------------------------------------------------------------------
# Counter-Proof
# ----------------------------------------------------------------------
COUNTER_PROMPT = """A rival politician has made a public claim about OUR leader or the constituency. You get the claim and an EVIDENCE PACK;
[E1] says who our leader and party are.
1. Split the claim into the separate factual assertions it makes.
2. For each, say whether the evidence SUPPORTS the rival, CONTRADICTS the rival, or says NOTHING about it. Cite [E#] lines. Never use outside knowledge.
3. Draft a reply the leader could post, in Telugu and in English, using only contradicting evidence, with the numbers. If the evidence supports the rival, say so plainly in "advice" and do not draft a denial.
Return ONLY JSON: {"assertions": [{"assertion": "...", "verdict": "Supports rival|Contradicts rival|No evidence", "evidence": ["E2"], "why": "..."}],
 "reply_te": "...", "reply_en": "...", "advice": "what to check or fix before replying"}"""


def counter_proof(claim, lines, api_key):
    try:
        data = _chat(api_key, COUNTER_PROMPT, f"CLAIM: {claim}\n\nEVIDENCE PACK:\n{evidence_pack(lines)}")
    except Exception as exc:
        return {"ok": False, "error": live_pulse._openai_reason(exc)}
    return {"ok": True, "error": None, **data}


# ----------------------------------------------------------------------
# Rally Impact Meter
# ----------------------------------------------------------------------
def rally_impact(event_date, place, other_places, leader=None, window=7):
    """News mentions of the place (and leader) in the week after an event against the week before, next to the
    same change for other places over the same dates. Google News only reaches back about 30 days."""
    def weekly(q):
        res = live_pulse.fetch_google_news(q, days=30, max_items=100)
        if not res["ok"]:
            return None, None
        d0 = pd.Timestamp(event_date).date()
        days = [a["published"].date() for a in res["articles"] if a["published"]]
        before = sum(1 for d in days if d0 - timedelta(days=window) <= d < d0)
        after = sum(1 for d in days if d0 <= d < d0 + timedelta(days=window))
        return before, after

    q = f'"{place}"' + (f' "{leader}"' if leader else "")
    b, a = weekly(q)
    controls = []
    for p in other_places[:4]:
        cb, ca = weekly(f'"{p}"')
        if cb is not None:
            controls.append((p, cb, ca))
    ctrl_change = np.mean([(ca + 1) / (cb + 1) for _, cb, ca in controls]) if controls else None
    return {"before": b, "after": a, "change": round((a + 1) / (b + 1), 2) if b is not None else None,
            "controls": controls, "control_change": round(float(ctrl_change), 2) if ctrl_change else None}


# ----------------------------------------------------------------------
# Money-to-Votes
# ----------------------------------------------------------------------
def money_to_votes(spend, shares, party, y0, y1):
    """Spending per division against the change in the party's share there between two tracking rounds.
    `spend` has division, amount; `shares` is the Division_Shares sheet (Division, Year, party columns)."""
    s = shares.copy()
    s["Year"] = pd.to_numeric(s["Year"], errors="coerce")
    a = s[s["Year"] == y0].set_index("Division")[party]
    b = s[s["Year"] == y1].set_index("Division")[party]
    change = (b - a).rename("Share change (points)")
    money = spend.groupby("division")["amount"].sum().rename("Spent (₹)")
    df = pd.concat([money, change], axis=1).dropna().reset_index().rename(columns={"index": "Division"})
    corr = df["Spent (₹)"].corr(df["Share change (points)"]) if len(df) >= 3 else None
    return df.sort_values("Spent (₹)", ascending=False), (round(float(corr), 2) if corr is not None and corr == corr else None)


# ----------------------------------------------------------------------
# Grievance Season Calendar
# ----------------------------------------------------------------------
SEASON_TERMS = {
    "Water scarcity": "water tanker",
    "Flooding": "Hyderabad rain",
    "Power cuts": "power cut",
    "Mosquito fevers": "dengue",
    "Fee reimbursement": "fee reimbursement",
}


def seasonal_profile(terms=SEASON_TERMS, geo="IN-TG"):
    """Five years of weekly Google Trends interest per issue, folded into an average by month (0-100 within each term)."""
    try:
        from pytrends.request import TrendReq

        client = TrendReq(hl="en-US", tz=330, timeout=(5, 25))
        client.build_payload(list(terms.values()), geo=geo, timeframe="today 5-y")
        df = client.interest_over_time()
    except Exception as exc:
        return {"ok": False, "error": "Google Trends rate-limited, try again in a few minutes" if "429" in str(exc) else f"Google Trends failed ({type(exc).__name__})"}
    if df is None or df.empty:
        return {"ok": False, "error": "no Trends data"}
    df = df.drop(columns=["isPartial"], errors="ignore")
    by_month = df.groupby(df.index.month).mean()
    rows = []
    for label, term in terms.items():
        col = by_month[term]
        peak = col.max() or 1
        rows.append({"Issue": label, **{date(2000, m, 1).strftime("%b"): round(col.get(m, 0) / peak * 100) for m in range(1, 13)}})
    return {"ok": True, "error": None, "profile": pd.DataFrame(rows)}


def peaking_now(profile, today=None):
    """Issues at or near their yearly high this month."""
    m = (today or date.today()).strftime("%b")
    return [{"Issue": r["Issue"], "Level now": r[m]} for _, r in profile.iterrows() if r[m] >= 80]


def coming_up(profile, today=None, weeks=6):
    """Issues whose seasonal level in the next few weeks is well above the current month's."""
    today = today or date.today()
    now_m = today.strftime("%b")
    ahead = [(today + timedelta(weeks=w)).strftime("%b") for w in range(1, weeks + 1)]
    out = []
    for _, r in profile.iterrows():
        nxt = max(r[m] for m in ahead)
        if nxt >= 60 and nxt - r[now_m] >= 15:
            peak_m = max(ahead, key=lambda m: r[m])
            out.append({"Issue": r["Issue"], "Now": r[now_m], "Peak soon": nxt, "Month": peak_m})
    return sorted(out, key=lambda x: -(x["Peak soon"] - x["Now"]))
