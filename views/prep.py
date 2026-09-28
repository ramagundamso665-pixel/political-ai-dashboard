"""Prep: walk into any colony knowing it, practise against a rival, handle the first hour of a crisis,
test messages on real people, and hear the Monday brief."""

from datetime import date

import pandas as pd
import streamlit as st

import evidence
import health
import live_pulse
import opponent_watch as ow
import prep
import registers
import store
import warroom as wr
from components import empty_state, fact_card, section
from config import SOURCE_METADATA, is_valid_api_key
from views.opponent_watch import _rivals
from views.war_room import leader_picker

TITLE = "Prep"


@st.cache_data(ttl=7 * 24 * 3600, show_spinner=False)
def _geocode(place):
    return prep.geocode(place)


def _issues():
    creds = health.supabase_credentials()
    if not creds:
        return []
    try:
        return registers.fetch(*creds, "local_issues").to_dict("records")
    except Exception:
        return []


# ----------------------------------------------------------------------
def _walk_in(ctx, seat, leader, party, snap):
    st.markdown("Arriving somewhere? Everything the office knows about that exact place, and what to say there.")
    c1, c2 = st.columns([3, 1])
    place = c1.text_input("Colony, street or landmark", placeholder="e.g. Rahmath Nagar, Karmika Nagar, Borabanda bus stop", key="wi_place")
    use_gps = c2.toggle("Use my phone's location", key="wi_gps")
    lonlat, label = None, None
    if use_gps:
        from streamlit_js_eval import get_geolocation

        loc = get_geolocation()
        if loc and loc.get("coords"):
            lonlat = (loc["coords"]["longitude"], loc["coords"]["latitude"])
            label = f"your location ({lonlat[1]:.4f}, {lonlat[0]:.4f})"
        else:
            st.caption("Waiting for the browser to share the location (allow it when asked).")
    elif place.strip():
        g = _geocode(place.strip())
        if g:
            lonlat, label = (g[0], g[1]), g[2]
        else:
            st.warning("Could not find that place on the map. Try a better-known name nearby.")
    if not lonlat:
        return
    try:
        shares = ctx.sheets["division_shares"]
    except Exception:
        shares = None
    facts = prep.walk_in(lonlat[0], lonlat[1], label or place, store.rows("voice_tickets"), _issues(), store.rows("promises"), shares, party)
    m = st.columns(3)
    m[0].metric("Ward", facts["ward"] or "outside GHMC")
    m[1].metric("Constituency", facts["seat"] or "?")
    m[2].metric("Complaints on record here", len(facts["tickets"]) + len(facts["issues"]))
    st.caption(f"Found: {label}")
    lines = [f"Place: {label}; ward {facts['ward']}; constituency {facts['seat']}."]
    if facts["division"]:
        for r in facts["division"]["rows"]:
            lines.append(f"Division {facts['division']['name']} {int(r['Year'])} (campaign estimate): " + ", ".join(f"{p} {r[p]}%" for p in ("BRS", "INC", "BJP", "AIMIM") if p in r))
    for t in facts["tickets"][:8]:
        lines.append(f"Voice complaint {t.get('ticket_no')}: {t.get('summary_en')} ({t.get('status', 'Open')})")
    for i in facts["issues"][:8]:
        lines.append(f"Local issue: {i.get('title')} ({i.get('status')})")
    for p in facts["promises"][:6]:
        lines.append(f"Promise: {p['promise']} — {p['status']}")
    proof_snap = st.session_state.get("proof_snapshot") or {}
    lines += [f"Satellite: {l}" for l in proof_snap.get("lines", []) if facts["ward"] and facts["ward"].split()[0].lower() in l.lower()]
    news = live_pulse.fetch_google_news(f'"{(label or place).split(",")[0]}"', days=30, max_items=5)
    for a in (news["articles"] if news["ok"] else [])[:3]:
        lines.append(f"Recent news: {a['title']}")
    st.markdown("**What the office knows here**")
    for l in lines:
        st.markdown(f"- {l}")
    if is_valid_api_key(ctx.api_key) and st.button("Give me talking points", key="wi_points"):
        with st.spinner("Preparing"):
            tp = prep.talking_points("\n".join(lines), ctx.api_key)
        if tp.get("ok"):
            for p in tp.get("points", []):
                st.markdown(f"🗣️ {p['en']}  \n{p['te']}")
            if tp.get("avoid"):
                st.warning(f"Don't: {tp['avoid']['en']}  \n{tp['avoid']['te']}")
            if tp.get("ask"):
                st.info(f"Ask them: {tp['ask']['en']}  \n{tp['ask']['te']}")
        else:
            st.warning(tp["error"])
    snap.append(f"Walk-in brief for {label}: {len(facts['tickets']) + len(facts['issues'])} complaints on record")


def _debate(ctx, seat, leader, party, snap):
    st.markdown("**Practice only.** An AI plays the rival from their public record; you answer; a coach scores each answer against the evidence. Nothing here is published.")
    rivals = [r for r in _rivals(ctx, seat, party)]
    labels = [f"{n} ({p})" for n, p in rivals] + ["Someone else…"]
    pick = st.selectbox("Practise against", labels, key="db_rival")
    if pick == "Someone else…":
        c1, c2 = st.columns(2)
        rname = c1.text_input("Name", key="db_rname")
        rparty = c2.text_input("Party", key="db_rparty")
    else:
        rname, rparty = rivals[labels.index(pick)]
    if not rname:
        return
    key = f"db_{rname}"
    if st.button("Start a new debate", type="primary", key="db_start"):
        with st.spinner(f"Reading {rname}'s public record"):
            ours = evidence.build(ctx, seat, leader, party)
            news = ow.fetch_news(rname, place=None)
            said = [f"{rname} in the news ({a['source']}): {a['title']}" for a in (news["articles"] if news["ok"] else [])[:12]]
            st.session_state[key] = {"evidence": ours, "rival_lines": ours + said, "history": [], "scores": []}
            first = prep.rival_turn(rname, rparty, ours + said, [], ctx.api_key)
            if first["ok"]:
                st.session_state[key]["history"].append({"who": "rival", "text": first["text"]})
    s = st.session_state.get(key)
    if not s:
        return
    for i, h in enumerate(s["history"]):
        with st.chat_message("assistant" if h["who"] == "rival" else "user", avatar="🎭" if h["who"] == "rival" else "🗣️"):
            st.markdown(("**" + rname + " (simulated):** " if h["who"] == "rival" else "") + h["text"])
        sc = next((x for x in s["scores"] if x["turn"] == i), None)
        if sc:
            st.caption(f"Coach: facts {sc.get('facts_right')}/10 · answered the point {sc.get('responsiveness')}/10"
                       + (f" · ⚠️ trap: {sc['trap']}" if sc.get("trap") else ""))
            with st.expander("What you missed and a better answer"):
                st.markdown(f"**Missed:** {sc.get('missed', '')}  \n**Better:** {sc.get('better', '')}")
    answer = st.chat_input("Your answer (Telugu or English)", key="db_input")
    if answer:
        attack = next((h["text"] for h in reversed(s["history"]) if h["who"] == "rival"), "")
        s["history"].append({"who": "you", "text": answer})
        with st.spinner("The coach is scoring; the rival is replying"):
            sc = prep.judge(s["evidence"], attack, answer, ctx.api_key)
            if sc.get("ok"):
                s["scores"].append({"turn": len(s["history"]) - 1, **sc})
            nxt = prep.rival_turn(rname, rparty, s["rival_lines"], s["history"], ctx.api_key)
            if nxt["ok"]:
                s["history"].append({"who": "rival", "text": nxt["text"]})
        st.rerun()
    if s["scores"]:
        f = sum(x.get("facts_right", 0) for x in s["scores"]) / len(s["scores"])
        r = sum(x.get("responsiveness", 0) for x in s["scores"]) / len(s["scores"])
        st.metric("Average so far", f"facts {f:.1f}/10 · answering {r:.1f}/10", f"{sum(1 for x in s['scores'] if x.get('trap'))} traps")
        snap.append(f"Debate practice vs {rname}: facts {f:.1f}/10, answering {r:.1f}/10")


def _crisis(ctx, seat, leader, party, snap):
    st.markdown("The first hour decides the story. Describe what happened; the playbook uses only the office's own contacts and the record, and marks everything to confirm.")
    crisis = st.text_area("What happened, where, when", placeholder="e.g. A wall collapsed in Borabanda after heavy rain at 6 pm; two people injured, one missing.", key="cr_text")
    contacts = store.rows("contacts", order="name.asc")
    if st.button("Build the first-hour playbook", type="primary", key="cr_go") and crisis.strip():
        with st.spinner("Building the playbook"):
            lines = evidence.build(ctx, seat, leader, party, news=False)
            st.session_state["cr_result"] = prep.crisis_playbook(crisis, contacts, lines, ctx.api_key)
    r = st.session_state.get("cr_result")
    if r:
        if not r.get("ok"):
            st.warning(r.get("error"))
        else:
            st.error("**Confirm before saying anything:**\n" + "\n".join(f"- {x}" for x in r.get("confirm_first", [])))
            st.markdown("**First hour**")
            st.dataframe(pd.DataFrame(r.get("first_hour", [])), hide_index=True, width="stretch")
            if r.get("relief"):
                st.markdown("**Relief to line up**")
                st.dataframe(pd.DataFrame(r["relief"]), hide_index=True, width="stretch")
            c1, c2 = st.columns(2)
            c1.markdown("**First statement (తెలుగు)**")
            c1.write(r.get("statement_te", ""))
            c2.markdown("**First statement (English)**")
            c2.write(r.get("statement_en", ""))
            st.warning("**Do not:**\n" + "\n".join(f"- {x}" for x in r.get("do_not", [])))
            st.caption(f"Next update: {r.get('next_update', '')}")
            snap.append(f"Crisis playbook prepared: {st.session_state.get('cr_text', '')[:80]}")
    with st.expander(f"The office's contacts ({len(contacts)}) — the playbook only uses these"):
        with st.form("ct_form", clear_on_submit=True):
            c1, c2, c3, c4 = st.columns(4)
            name = c1.text_input("Name")
            role = c2.text_input("Role", placeholder="e.g. Deputy Commissioner")
            dept = c3.text_input("Department", placeholder="GHMC, HMWSSB, Police…")
            phone = c4.text_input("Phone")
            area = st.text_input("Area covered")
            if st.form_submit_button("Save contact") and name:
                store.add("contacts", {"name": name, "role": role, "department": dept, "phone": phone, "area": area})
                st.rerun()
        if contacts:
            st.dataframe(pd.DataFrame(contacts)[[c for c in ("name", "role", "department", "phone", "area") if c in pd.DataFrame(contacts)]], hide_index=True, width="stretch")
        st.caption(f"Saved to: {store.where('contacts')}")


def _lab(ctx, seat, leader, party, snap):
    st.markdown("Which message works? Real people rate one randomly chosen version each, through a link; no simulated voters.")
    tests = store.rows("message_tests")
    with st.expander("Create a test", expanded=not tests):
        goal = st.text_input("What should the message do?", placeholder="e.g. Tell Rahmath Nagar about the new water line", key="ml_goal")
        c1, c2 = st.columns(2)
        n = c1.slider("Versions", 2, 4, 3, key="ml_n")
        lang = c2.selectbox("Language", ["Telugu", "English", "Urdu", "Hindi"], key="ml_lang")
        if st.button("Draft versions", key="ml_draft") and goal:
            facts = evidence.build(ctx, seat, leader, party, news=False)[:25]
            got = prep.draft_variants(goal, facts, n, lang, ctx.api_key)
            if got["ok"]:
                st.session_state["ml_variants"] = got["variants"]
            else:
                st.warning(got["error"])
        variants = st.session_state.get("ml_variants", [""] * n)
        edited = [st.text_area(f"Version {i + 1}", value=variants[i] if i < len(variants) else "", key=f"ml_v{i}") for i in range(n)]
        question = st.text_input("Question to ask each person", value="How much does this message make you trust the leader? (1 = not at all, 5 = a lot)", key="ml_q")
        if st.button("Save the test", type="primary", key="ml_save") and all(v.strip() for v in edited):
            t = store.add("message_tests", {"question": question, "variants": [v.strip() for v in edited]})
            st.success(f"Saved. Share this link: add ?poll={t['id']} to the app's address.")
            st.rerun()
    if not tests:
        return
    pick = st.selectbox("Results for", [f"{t['question'][:60]} · {str(t.get('created_at', ''))[:10]}" for t in tests], key="ml_pick")
    t = tests[[f"{x['question'][:60]} · {str(x.get('created_at', ''))[:10]}" for x in tests].index(pick)]
    variants = t["variants"] if isinstance(t["variants"], list) else __import__("json").loads(t["variants"])
    st.code(f"?poll={t['id']}", language=None)
    for i, v in enumerate(variants):
        st.markdown(f"**Version {i + 1}:** {v}")
    resp = [r for r in store.rows("message_responses") if str(r.get("test_id")) == str(t["id"])]
    table, verdict = prep.results(resp, len(variants))
    st.dataframe(pd.DataFrame(table), hide_index=True, width="stretch")
    st.markdown(f"**{verdict}**")
    snap.append(f"Message test '{t['question'][:50]}': {verdict}")


def render_public_poll(test_id):
    """The link respondents open: one randomly chosen version, a rating, nothing else. No password, no personal data."""
    tests = [t for t in store.rows("message_tests") if str(t["id"]) == str(test_id)]
    if not tests:
        st.error("This survey link is not valid.")
        return
    t = tests[0]
    variants = t["variants"] if isinstance(t["variants"], list) else __import__("json").loads(t["variants"])
    if f"poll_v_{test_id}" not in st.session_state:
        st.session_state[f"poll_v_{test_id}"] = prep.pick_variant(len(variants))
    v = st.session_state[f"poll_v_{test_id}"]
    st.markdown("### A short question")
    st.caption("Anonymous: nothing about you is recorded except your answers.")
    st.info(variants[v])
    if st.session_state.get(f"poll_done_{test_id}"):
        st.success("Thank you!")
        return
    with st.form(f"poll_{test_id}"):
        rating = st.radio(t["question"], [1, 2, 3, 4, 5], horizontal=True, index=None)
        share = st.checkbox("I would forward this to others")
        sent = st.form_submit_button("Send", type="primary")
    if sent:
        if rating is None:
            st.warning("Please choose a number first.")
            return
        store.add("message_responses", {"test_id": t["id"], "variant": v, "rating": rating, "would_share": share})
        st.session_state[f"poll_done_{test_id}"] = True
        st.rerun()


def _command(ctx, seat, leader, party, snap):
    st.markdown("Monday, 7 am: everything that matters this week, in one brief you can listen to on the way.")
    if not st.button("Prepare this week's brief", type="primary", key="cc_go"):
        b = st.session_state.get("cc_brief")
        if b:
            _show_brief(b)
        return
    items = []
    with st.spinner("Scanning news speed, seasons, complaints, promises and rivals"):
        # stories speeding up
        places = []
        try:
            places = sorted(ctx.sheets["division_shares"]["Division"].dropna().unique()) if seat == "Jubilee Hills" else []
        except Exception:
            pass
        for term in [f'"{seat}"'] + [f'"{p}"' for p in places[:6]]:
            n = wr.news_velocity(term)
            if n.get("ok") and n["ratio"] >= 1.8 and n["recent"] >= 2:
                items.append(f"News about {term} is running {n['ratio']}x its usual rate ({n['recent']} stories in 3 days). Latest: {(n.get('latest') or [''])[0]}")
        season = wr.seasonal_profile()
        if season["ok"]:
            for x in wr.peaking_now(season["profile"]):
                items.append(f"Seasonal: {x['Issue']} is at its yearly high this month in Telangana searches.")
            for x in wr.coming_up(season["profile"]):
                items.append(f"Seasonal: {x['Issue']} usually climbs to its peak in {x['Month']}; prepare now.")
        tickets = store.rows("voice_tickets")
        if tickets:
            from collections import Counter
            for (cat, area), k in Counter((t.get("category"), t.get("area") or "unnamed area") for t in tickets).most_common(3):
                items.append(f"Complaints: {k} voice complaints about {cat} from {area}.")
        for p in store.rows("promises"):
            if p.get("whose", "Ours") == "Ours" and p.get("status") in ("Late", "In progress", "Confirmed"):
                state = {"Late": "is LATE", "In progress": "is recorded as in progress", "Confirmed": "was made; no progress is recorded yet"}[p["status"]]
                items.append(f"Promise {state}: {p['promise']}" + (f" (said {p['said_on']}" if p.get("said_on") else "") + (f", due {p['due']})" if p.get("due") else (")" if p.get("said_on") else "")))
        for key in ("warroom_snapshot", "proof_snapshot", "ow_snapshot", "voice_snapshot"):
            for line in (st.session_state.get(key) or {}).get("lines", [])[:3]:
                items.append(line)
    if not items:
        st.info("Nothing notable found. Run the Proof, War Room and Opponent Watch checks first; their findings feed the brief.")
        return
    with st.spinner("Writing the brief"):
        b = prep.monday_brief(items[:20], ctx.api_key)
    b["items"] = items
    st.session_state["cc_brief"] = b
    _show_brief(b)


def _show_brief(b):
    if not b.get("ok"):
        st.warning(b.get("error"))
        return
    t1, t2 = st.tabs(["తెలుగు", "English"])
    with t1:
        st.write(b.get("te", ""))
        if st.button("🔊 Listen (AI voice)", key="cc_speak_te"):
            with st.spinner("Recording the brief"):
                a = prep.speak(b.get("te", ""), st.session_state.get("_api_key"))
            st.audio(a["audio"], format="audio/mp3") if a.get("ok") else st.warning(a.get("error"))
    with t2:
        st.write(b.get("en", ""))
        if st.button("🔊 Listen (AI voice)", key="cc_speak_en"):
            with st.spinner("Recording the brief"):
                a = prep.speak(b.get("en", ""), st.session_state.get("_api_key"))
            st.audio(a["audio"], format="audio/mp3") if a.get("ok") else st.warning(a.get("error"))
    with st.expander(f"What it is built from ({len(b.get('items', []))} items)"):
        for x in b.get("items", []):
            st.markdown(f"- {x}")
    st.caption("The voice is AI-generated; label it as such if it is ever shared (ECI rules on AI content).")


def render(ctx, sidebar):
    section("Prep", "Walk in knowing the place, practise against the rival, own the first hour of a crisis, test messages on real people, and start the week with one brief.")
    st.session_state["_api_key"] = ctx.api_key
    if not is_valid_api_key(ctx.api_key):
        st.warning("Most of this page needs OPENAI_API_KEY.")
    seat, leader, party = leader_picker(ctx, "pp")
    snap = []
    tabs = st.tabs(["Monday brief", "Walk-in brief", "Debate sparring", "Crisis playbook", "Message lab"])
    with tabs[0]:
        _command(ctx, seat, leader, party, snap)
    with tabs[1]:
        _walk_in(ctx, seat, leader, party, snap)
    with tabs[2]:
        _debate(ctx, seat, leader, party, snap)
    with tabs[3]:
        _crisis(ctx, seat, leader, party, snap)
    with tabs[4]:
        _lab(ctx, seat, leader, party, snap)
    if snap:
        st.session_state["prep_snapshot"] = {"lines": snap}
    fact_card(
        "Talking points, debate practice, crisis playbooks and the brief are drafted by a language model from the office's own record and public "
        "feeds, and marked where facts must be confirmed. Message tests use real people's answers, never simulated voters.",
        SOURCE_METADATA["prep"]["name"], SOURCE_METADATA["prep"]["type"], "medium",
    )
    ctx.logger.log_analysis("prep", ["prep"], f"prep for {leader} ({party}) in {seat}")
