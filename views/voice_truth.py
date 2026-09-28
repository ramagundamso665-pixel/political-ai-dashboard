"""Voice & Truth: citizens speak complaints; the leader's own recordings become the reference that settles
what was really said, what was promised, and a public record nobody can quietly edit."""

import json
from collections import Counter
from datetime import date

import pandas as pd
import streamlit as st

import health
import registers
import speech
import store
import voice_intel as vi
from components import empty_state, fact_card, section
from config import SOURCE_METADATA, is_valid_api_key

TITLE = "Voice & Truth"

PROMISE_STATUSES = ["Suggested", "Confirmed", "In progress", "Done", "Late", "Dropped", "Rejected"]
LEDGER_KINDS = ["Meeting", "Spending", "Work sanctioned", "Work completed", "Statement", "Other"]


def _where(table):
    st.caption(f"Saved to: {store.where(table)}")


def _jump(rec, at_s):
    """A link that opens the published video at the moment, for YouTube links."""
    link = (rec or {}).get("link") or ""
    if not link or at_s is None:
        return None
    if "youtu" in link:
        return f"{link}{'&' if '?' in link else '?'}t={int(at_s)}s"
    return link


def _mmss(s):
    s = int(s or 0)
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"


# ----------------------------------------------------------------------
# Janavani
# ----------------------------------------------------------------------
def _janavani(api_key, snap):
    st.markdown(
        "Any resident speaks a complaint in Telugu, Urdu, Dakhni, Hindi or English. It becomes a written ticket with the area, the department "
        "and a Telugu read-back, and goes into Local Issues. Nobody needs to read or type."
    )
    consent = st.checkbox(
        "The resident has heard this notice and agrees: \"Your voice will be turned into text by a computer service to register your complaint with "
        "the MLA's office. Your recording is not kept; the text is.\"", key="jv_consent")
    c1, c2 = st.columns(2)
    rec = c1.audio_input("Record here", key="jv_rec", disabled=not consent)
    up = c2.file_uploader("Or a WhatsApp voice note / audio file", type=["ogg", "opus", "mp3", "m4a", "wav", "aac", "amr", "webm"], key="jv_up",
                          disabled=not consent)
    audio = rec or up
    if audio and st.button("Turn into a ticket", type="primary", key="jv_go"):
        with st.spinner("Listening and writing it down"):
            tr = speech.transcribe(audio.getvalue(), api_key, timestamps=False)
            got = vi.structure_complaint(tr["text"], api_key) if tr.get("ok") and tr["text"] else {"ok": False, "error": tr.get("error") or "no speech heard"}
        st.session_state["jv_result"] = {"transcript": tr.get("text", ""), **got}
    r = st.session_state.get("jv_result")
    if r:
        if not r["ok"]:
            st.warning(r["error"])
        else:
            st.markdown(f"**What was said:** {r['transcript']}")
            m = st.columns(4)
            m[0].metric("Category", r["category"])
            m[1].metric("Area", r["area"] or "not said")
            m[2].metric("Department", r["department"] or "?")
            m[3].metric("Urgency", r["urgency"])
            st.markdown(f"**Summary:** {r['summary_en']}  \n**తెలుగులో:** {r['summary_te']}")
            st.info(f"**Read back to the caller:** {r['readback_te']}")
            if r["missing"]:
                st.warning(f"Ask the caller: {r['missing']}")
            if st.button("File it", key="jv_file"):
                no = vi.ticket_number(r["transcript"])
                issue_id = None
                creds = health.supabase_credentials()
                if creds:
                    try:
                        registers.add(*creds, "local_issues", {"title": r["summary_en"][:200], "category": r["category"], "location": r["area"],
                                                                "severity": r["urgency"], "status": "Open", "source": f"Janavani voice {no}",
                                                                "details": r["transcript"], "reported_on": date.today().isoformat()})
                    except Exception:
                        pass
                store.add("voice_tickets", {"ticket_no": no, "transcript": r["transcript"], "summary_en": r["summary_en"], "summary_te": r["summary_te"],
                                            "category": r["category"], "area": r["area"], "department": r["department"], "urgency": r["urgency"],
                                            "consent": True, "issue_id": issue_id})
                st.success(f"Filed as **{no}**. Give the caller this number.")
                st.session_state.pop("jv_result", None)
    tickets = store.rows("voice_tickets")
    if tickets:
        df = pd.DataFrame(tickets)
        st.markdown(f"**{len(df)} voice tickets**")
        by = df.groupby(["area", "category"]).size().reset_index(name="Tickets").sort_values("Tickets", ascending=False)
        st.dataframe(by.head(12), hide_index=True, width="stretch")
        st.dataframe(df[[c for c in ("ticket_no", "created_at", "category", "area", "department", "urgency", "status", "summary_en") if c in df]],
                     hide_index=True, width="stretch")
        top = by.iloc[0]
        snap.append(f"Voice tickets: {len(df)}; most from {top['area'] or 'unnamed area'} about {top['category']} ({top['Tickets']})")
    _where("voice_tickets")
    st.caption("A phone number anyone can call needs a telephony account (Exotel or Plivo, about ₹1–2 a minute) connected to this same step; "
               "WhatsApp voice notes work through the WhatsApp bot once it is deployed.")


# ----------------------------------------------------------------------
# Speech archive
# ----------------------------------------------------------------------
def _archive(api_key):
    st.markdown(
        "The team records every public appearance in full, start to finish, on a phone. Each recording added here is written out with times and "
        "fingerprinted, so any clip that later goes around can be checked against what was actually said."
    )
    with st.form("arch_form", clear_on_submit=True):
        c1, c2, c3 = st.columns([2, 1, 1])
        title = c1.text_input("What was it", placeholder="e.g. Borabanda public meeting")
        when = c2.date_input("Date", value=date.today())
        place = c3.text_input("Place")
        c4, c5 = st.columns(2)
        speaker = c4.text_input("Main speaker", placeholder="e.g. the MLA")
        link = c5.text_input("Video link, if published (YouTube etc.)")
        up = st.file_uploader("The full recording (video or audio)", type=["mp4", "mov", "m4a", "mp3", "wav", "ogg", "opus", "aac", "webm", "mkv"])
        go = st.form_submit_button("Add to the archive", type="primary")
    if go and up and title:
        data = up.getvalue()
        with st.spinner("Writing it out and fingerprinting it (about a minute per 10 minutes of speech)"):
            tr = speech.transcribe(data, api_key)
            if not tr["ok"]:
                st.warning(tr["error"])
                return
            fp = speech.pack(speech.hashes(speech.decode(data)))
        store.add("speech_archive", {"title": title, "event_date": when.isoformat(), "place": place, "speaker": speaker, "file_sha256": speech.sha256(data),
                                     "duration_s": tr["duration"], "segments": tr["segments"], "fingerprint": fp,
                                     "link": link or None})
        st.success(f"Added: {title} ({_mmss(tr['duration'])}, {len(tr['segments'])} pieces).")
    arch = store.rows("speech_archive", order="event_date.desc")
    if not arch:
        empty_state("No recordings yet. Add the first full recording of a speech or press meet.")
    else:
        st.dataframe(pd.DataFrame([{"Date": a.get("event_date"), "Title": a["title"], "Place": a.get("place"), "Length": _mmss(a.get("duration_s")),
                                    "Pieces": len(a.get("segments") or [])} for a in arch]), hide_index=True, width="stretch")
        pick = st.selectbox("Read a transcript", [a["title"] for a in arch], key="arch_pick")
        rec = next(a for a in arch if a["title"] == pick)
        segs = rec.get("segments") or []
        if isinstance(segs, str):
            segs = json.loads(segs)
        st.dataframe(pd.DataFrame([{"At": _mmss(s["start"]), "Said": s["text"]} for s in segs]), hide_index=True, width="stretch")
    _where("speech_archive")


# ----------------------------------------------------------------------
# Clip check
# ----------------------------------------------------------------------
VERDICT_STYLE = {"Genuine": st.success, "Edited": st.error, "Partly altered": st.error, "Check words": st.warning,
                 "Words match, sound does not": st.warning, "Not in any recording": st.info}


def _clip_check(api_key, snap):
    st.markdown("Got a clip from TV, YouTube or WhatsApp? It is checked against every full recording in the archive: by its sound, then by its words.")
    arch = store.rows("speech_archive")
    if not arch:
        st.info("The archive is empty, so there is nothing to check against. Add full recordings under Speech archive first.")
        return
    up = st.file_uploader("The clip (video or audio)", type=["mp4", "mov", "m4a", "mp3", "wav", "ogg", "opus", "aac", "webm", "3gp"], key="cc_up")
    if up and st.button("Check it", type="primary", key="cc_go"):
        data = up.getvalue()
        with st.spinner("Comparing sound and words with the archive"):
            tr = speech.transcribe(data, api_key, timestamps=False)
            res = speech.check_clip(speech.decode(data), tr.get("text", ""), arch)
        res["clip_text"] = tr.get("text", "")
        st.session_state["cc_result"] = res
    res = st.session_state.get("cc_result")
    if not res:
        return
    VERDICT_STYLE.get(res["verdict"], st.info)(f"**{res['verdict']}.** {res['why']}")
    rec = res.get("recording")
    if rec:
        st.markdown(f"**Recording:** {rec['title']} · {rec.get('event_date', '')} · {rec.get('place', '')} · from {_mmss(res['at_s'])}")
    c1, c2 = st.columns(2)
    c1.markdown("**The clip says**")
    c1.write(res.get("clip_text") or "(no speech heard)")
    c2.markdown("**The recording says there**")
    c2.write(res.get("master_text") or "–")
    if res.get("context_text"):
        with st.expander("A minute either side, for context"):
            st.write(res["context_text"])
    st.markdown("**Piece by piece** (each 5 seconds of the clip, and where it sits in the recording)")
    st.dataframe(pd.DataFrame([{"Clip from": _mmss(w["clip_from_s"]), "Recording": w["recording"] or "no match", "At": _mmss(w["at_s"]) if w["at_s"] is not None else "–",
                                "Sound match": w["match"]} for w in res["windows"]]), hide_index=True, width="stretch")
    snap.append(f"Clip check: {res['verdict']}" + (f" (recording '{rec['title']}' at {_mmss(res['at_s'])})" if rec else ""))
    st.caption("Tested on known clips: a cut from a recording (re-compressed like WhatsApp) was found at the right second; two joined pieces "
               "were caught as edited; the same words in another voice were caught as not from the recording. The check only knows what the team recorded.")


# ----------------------------------------------------------------------
# Promise Catcher
# ----------------------------------------------------------------------
def _promises(api_key, snap):
    st.markdown("Promises are found only in the archive's own recordings, never in general news, and a person confirms each one before it counts.")
    arch = store.rows("speech_archive", order="event_date.desc")
    if arch:
        c1, c2 = st.columns([3, 1])
        pick = c1.selectbox("Find promises in", [a["title"] for a in arch], key="pc_pick")
        whose = c2.selectbox("Whose", ["Ours", "Rival"], key="pc_whose")
        if st.button("Find promises", key="pc_go"):
            rec = next(a for a in arch if a["title"] == pick)
            segs = rec.get("segments") or []
            if isinstance(segs, str):
                segs = json.loads(segs)
            with st.spinner("Reading the speech"):
                got = vi.find_promises(segs, api_key)
            existing = {p["quote"] for p in store.rows("promises")}
            n = 0
            for p in got["promises"]:
                if p["quote"] in existing:
                    continue
                store.add("promises", {"archive_id": rec["id"], "said_on": rec.get("event_date"), "said_at_s": p["at_s"], "quote": p["quote"],
                                       "promise": p["promise"], "area": p["area"], "due": p["due"], "status": "Suggested", "whose": whose})
                n += 1
            st.success(f"{n} new possible promises. Confirm or reject each below.") if n else st.info("No new promises found in this recording.")
    else:
        st.info("Add recordings under Speech archive; promises are found in them.")

    rows = store.rows("promises")
    if not rows:
        return
    df = pd.DataFrame(rows)
    for col in ("area", "due", "evidence", "whose", "said_on", "said_at_s", "archive_id"):
        if col not in df:
            df[col] = None       # empty fields are left out of stored rows
    df["whose"] = df["whose"].fillna("Ours")
    sugg = df[df["status"] == "Suggested"]
    if not sugg.empty:
        st.markdown(f"**{len(sugg)} waiting for a person to confirm**")
        for _, p in sugg.head(10).iterrows():
            with st.container(border=True):
                st.markdown(f"“{p['quote']}”  \n→ {p['promise']}" + (f" · **{p['area']}**" if p.get("area") else "") + (f" · due: {p['due']}" if p.get("due") else ""))
                src = next((a for a in arch if a["id"] == p.get("archive_id")), None) if arch else None
                jump = _jump(src, p.get("said_at_s"))
                st.caption(f"{p.get('said_on', '')} at {_mmss(p.get('said_at_s'))} · {p.get('whose', 'Ours')}" + (f" · [play the moment]({jump})" if jump else ""))
                a, b = st.columns(2)
                if a.button("✅ A real promise", key=f"pc_ok_{p['id']}"):
                    store.update("promises", p["id"], {"status": "Confirmed"})
                    st.rerun()
                if b.button("❌ Not a promise", key=f"pc_no_{p['id']}"):
                    store.update("promises", p["id"], {"status": "Rejected"})
                    st.rerun()
    real = df[~df["status"].isin(["Suggested", "Rejected"])]
    if not real.empty:
        counts = Counter(real["status"])
        m = st.columns(5)
        for col, s in zip(m, ["Confirmed", "In progress", "Done", "Late", "Dropped"]):
            col.metric(s, counts.get(s, 0))
        edit = st.data_editor(real[["id", "whose", "said_on", "promise", "area", "due", "status", "evidence"]], hide_index=True, width="stretch",
                              column_config={"id": None, "status": st.column_config.SelectboxColumn(options=PROMISE_STATUSES)}, key="pc_edit",
                              disabled=["whose", "said_on", "promise", "area", "due"])
        if st.button("Save changes", key="pc_save"):
            for _, r in edit.iterrows():
                orig = real[real["id"] == r["id"]].iloc[0]
                if r["status"] != orig["status"] or (r["evidence"] or "") != (orig["evidence"] if isinstance(orig["evidence"], str) else ""):
                    store.update("promises", r["id"], {"status": r["status"], "evidence": r["evidence"]})
            st.success("Saved.")
        ours = real[real["whose"] == "Ours"]
        done = (ours["status"] == "Done").sum()
        snap.append(f"Promises (ours): {len(ours)} confirmed, {done} done, {(ours['status'] == 'Late').sum()} late")
    _where("promises")


# ----------------------------------------------------------------------
# Open Office Ledger
# ----------------------------------------------------------------------
def _ledger(snap):
    st.markdown(
        "Meetings, spending and works, recorded so that no one (the office included) can quietly change or delete an entry later. "
        "Each entry carries a fingerprint of everything before it; publish the latest fingerprint and anyone can check the record against it."
    )
    entries = store.rows("ledger", order="seq.asc")
    with st.form("led_form", clear_on_submit=True):
        c1, c2, c3 = st.columns([1, 2, 1])
        kind = c1.selectbox("Kind", LEDGER_KINDS)
        what = c2.text_input("What", placeholder="e.g. Met HMWSSB GM on Rahmath Nagar water supply")
        amount = c3.number_input("Amount (₹), if any", min_value=0, step=1000)
        c4, c5 = st.columns(2)
        place = c4.text_input("Place or ward")
        ref = c5.text_input("Reference (sanction no., letter no., link)")
        if st.form_submit_button("Record it", type="primary") and what:
            e = vi.new_entry(entries, kind, {"what": what, "amount_rs": int(amount) or None, "place": place or None, "ref": ref or None})
            store.add("ledger", e)
            st.success(f"Recorded as entry {e['seq']}.")
            entries = store.rows("ledger", order="seq.asc")
    if not entries:
        empty_state("Nothing recorded yet.")
        _where("ledger")
        return
    ok, bad, why = vi.verify(entries)
    (st.success if ok else st.error)(f"Check: {why}" + (f" (entry {bad})" if bad else ""))
    last = max(entries, key=lambda e: int(e["seq"]))
    st.markdown(f"**Today's fingerprint to publish** (newspaper notice, website, X post):  \n`{last['hash']}` · entry {last['seq']}")
    df = pd.DataFrame([{"No.": e["seq"], "Kind": e["kind"], "What": (e["body"] if isinstance(e["body"], dict) else json.loads(e["body"])).get("what"),
                        "₹": (e["body"] if isinstance(e["body"], dict) else json.loads(e["body"])).get("amount_rs"),
                        "When": (e["body"] if isinstance(e["body"], dict) else json.loads(e["body"])).get("_at"), "Fingerprint": e["hash"][:16] + "…"} for e in entries])
    st.dataframe(df.sort_values("No.", ascending=False), hide_index=True, width="stretch")
    st.caption("Public view (no password): add ?public=ledger to the app's address. Anyone can recompute the fingerprints and compare with a published one.")
    snap.append(f"Open ledger: {len(entries)} entries, chain {'intact' if ok else 'BROKEN'}")
    _where("ledger")


def render_public_ledger():
    """Read-only ledger for anyone, no password: entries and the recomputed check."""
    section("Open office ledger", "The MLA office's public record. Every entry is chained to the one before it, so a change or deletion shows up.")
    entries = store.rows("ledger", order="seq.asc")
    if not entries:
        empty_state("Nothing recorded yet.")
        return
    ok, bad, why = vi.verify(entries)
    (st.success if ok else st.error)(why + (f" (entry {bad})" if bad else ""))
    last = max(entries, key=lambda e: int(e["seq"]))
    st.markdown(f"Latest fingerprint: `{last['hash']}` (entry {last['seq']}). Compare it with the one the office published.")
    names = {"what": "What", "amount_rs": "Amount (₹)", "place": "Place", "ref": "Reference", "_at": "Recorded (UTC)"}
    rows = []
    for e in entries:
        body = e["body"] if isinstance(e["body"], dict) else json.loads(e["body"])
        rows.append({"No.": e["seq"], "Kind": e["kind"], **{names.get(k, k): v for k, v in body.items()}, "Fingerprint": e["hash"]})
    st.dataframe(pd.DataFrame(rows).sort_values("No.", ascending=False), hide_index=True, width="stretch")
    st.caption("How to check: each fingerprint is SHA-256 of the entry's number, kind, contents and the previous fingerprint. Anyone can recompute them.")


def render(ctx, sidebar):
    section(
        "Voice & truth",
        "Citizens speak their problems; the leader's own full recordings settle what was really said and promised; and a public record that "
        "cannot be quietly edited shows what the office did.",
    )
    if not is_valid_api_key(ctx.api_key):
        st.warning("Speech and language steps need OPENAI_API_KEY. The ledger works without it.")
    snap = []
    tabs = st.tabs(["Janavani (voice complaints)", "Speech archive", "Clip check", "Promise catcher", "Open office ledger"])
    with tabs[0]:
        _janavani(ctx.api_key, snap)
    with tabs[1]:
        _archive(ctx.api_key)
    with tabs[2]:
        _clip_check(ctx.api_key, snap)
    with tabs[3]:
        _promises(ctx.api_key, snap)
    with tabs[4]:
        _ledger(snap)
    if snap:
        st.session_state["voice_snapshot"] = {"lines": snap}
    fact_card(
        "Speech is written out by OpenAI's transcription model and checked by audio fingerprint; complaints and promises are drafted by a language "
        "model and confirmed by a person before they count. Recordings of residents are not kept.",
        SOURCE_METADATA["voice_truth"]["name"], SOURCE_METADATA["voice_truth"]["type"], "medium",
    )
    ctx.logger.log_analysis("voice_truth", ["voice_truth"], "voice & truth page")
