"""One evidence pack about a leader and a seat, for every feature that lets a language model reason about
them (Attack Forecast, Counter-Proof, Debate Sparring, the Monday brief). Each line says where it came from,
so an answer that cites [E#] can be traced back to its source."""

from collections import Counter

import pandas as pd
import streamlit as st

import health
import live_pulse
import registers
import statewide
import store


def _safe(fn, default):
    try:
        return fn()
    except Exception:
        return default


def build(ctx, seat, leader=None, party=None, news=True):
    lines = []
    if leader:
        lines.append(f"OUR LEADER (the person this pack is about, 'you' and 'we'): {leader} of {party or 'their party'}, {seat} constituency. "
                     f"Every other party is a rival.")

    # election results
    for y in (2014, 2018, 2023):
        c = _safe(lambda: statewide.load_year(y)[1], None)
        if c is None:
            continue
        rows = c[(c["seat"] == seat) & (c["party"] != "NOTA")].sort_values("rank").head(4)
        if not rows.empty:
            lines.append(f"Election {y}, {seat} (ECI): " + "; ".join(f"{r['candidate']} ({r['party']}) {r['pct']}%" for _, r in rows.iterrows()))
    if seat == "Jubilee Hills":
        h = _safe(lambda: ctx.sheets["historical_results"].copy(), None)
        if h is not None:
            h["Year"] = pd.to_numeric(h["Year"], errors="coerce")
            for y in sorted(h["Year"].dropna().unique()):
                if y > 2023:
                    rr = h[h["Year"] == y].sort_values("Pct", ascending=False)
                    lines.append(f"By-election {int(y)}, {seat}: " + "; ".join(f"{r['Candidate']} ({r['Party']}) {r['Pct']}%" for _, r in rr.iterrows()))
        d = _safe(lambda: ctx.sheets["division_shares"], None)
        if d is not None:
            for div, g in d.groupby("Division"):
                parts = [f"{int(r['Year'])}: " + ", ".join(f"{p} {r[p]}%" for p in ("BRS", "INC", "BJP", "AIMIM") if p in r) for _, r in g.sort_values("Year").iterrows()]
                lines.append(f"Campaign division estimate (internal, not official), {div}: " + " | ".join(parts))

    # promises
    for p in _safe(lambda: store.rows("promises"), []):
        if p.get("status") in ("Suggested", "Rejected"):
            continue
        lines.append(f"Promise ({p.get('whose', 'Ours')}, said {p.get('said_on', '?')}): {p['promise']}" + (f" [{p['area']}]" if p.get("area") else "")
                     + (f", due {p['due']}" if p.get("due") else "") + f" — status: {p['status']}" + (f"; evidence: {p['evidence']}" if p.get("evidence") else ""))

    # complaints
    creds = health.supabase_credentials()
    if creds:
        issues = _safe(lambda: registers.fetch(*creds, "local_issues"), pd.DataFrame())
        if not issues.empty:
            open_ = issues[issues["status"].isin(["Open", "In progress", "Raised with authority"])]
            for (cat, loc), n in Counter(zip(open_["category"].fillna("Other"), open_["location"].fillna(open_["division"].fillna("")))).most_common(8):
                lines.append(f"Open local issues (staff register, unverified): {n} about {cat}" + (f" in {loc}" if loc else ""))
            done = issues[issues["status"] == "Resolved"]
            if len(done):
                lines.append(f"Local issues resolved (staff register): {len(done)}")
        rti = _safe(lambda: registers.fetch(*creds, "rti_requests"), pd.DataFrame())
        if not rti.empty:
            late = registers.rti_overdue(rti)
            lines.append(f"RTI requests filed by the office: {len(rti)}, of which {len(late)} are overdue for a reply")
    tickets = _safe(lambda: store.rows("voice_tickets"), [])
    if tickets:
        for (cat, area), n in Counter((t.get("category"), t.get("area") or "unnamed area") for t in tickets).most_common(6):
            lines.append(f"Janavani voice complaints: {n} about {cat} from {area}")

    # ledger
    for e in _safe(lambda: store.rows("ledger", order="seq.desc", limit=12), []):
        b = e["body"] if isinstance(e["body"], dict) else {}
        lines.append(f"Office ledger #{e['seq']} ({e['kind']}, {str(b.get('_at', ''))[:10]}): {b.get('what', '')}"
                     + (f", ₹{b['amount_rs']:,}" if b.get("amount_rs") else "") + (f", ref {b['ref']}" if b.get("ref") else ""))

    # what other pages measured this session
    for key, label in (("proof_snapshot", "Satellite measurement"), ("voice_snapshot", "Voice & Truth"), ("ow_snapshot", "Opponent Watch"), ("radar_snapshot", "Pre-viral radar")):
        snap = st.session_state.get(key)
        for line in (snap or {}).get("lines", []):
            lines.append(f"{label}: {line}")

    # recent headlines about the leader
    if news and leader:
        import opponent_watch
        res = opponent_watch.fetch_news(leader, place=seat)
        if res["ok"]:
            for a in live_pulse.latest_first(res["articles"])[:10]:
                when = a["published"].strftime("%d %b %Y") if a["published"] else ""
                lines.append(f"News headline ({a['source']}, {when}): {a['title']}")
    return lines
