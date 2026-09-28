"""What the bot does with a forwarded clip or a voice note. Uses the dashboard's own modules (speech, voice_intel,
store), so a clip checked here gets the same verdict as on the Voice & Truth page. No network in `reply_for_*`,
so they can be tested with local files."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import speech        # noqa: E402
import store         # noqa: E402
import voice_intel   # noqa: E402

VERDICT_TE = {
    "Genuine": "✅ నిజమైనది: ఈ క్లిప్ మొత్తం మా అధికారిక రికార్డింగ్‌లోని ఒకే భాగం.",
    "Edited": "❌ ఎడిట్ చేయబడింది: ఈ క్లిప్‌లో వేర్వేరు సమయాల్లో చెప్పిన మాటలు కలిపి అతికించారు.",
    "Partly altered": "❌ కొంత మార్చబడింది: ఈ క్లిప్‌లో కొంత భాగం మాత్రమే మా రికార్డింగ్‌తో సరిపోతుంది.",
    "Check words": "⚠️ శబ్దం సరిపోతుంది కానీ మాటలు తేడాగా ఉన్నాయి: జాగ్రత్తగా వినండి.",
    "Words match, sound does not": "⚠️ ఈ మాటలు నిజంగా చెప్పారు, కానీ ఈ ఆడియో మా రికార్డింగ్ నుండి కాదు (వేరే కెమెరా, మళ్లీ రికార్డింగ్ లేదా కృత్రిమ గొంతు కావచ్చు).",
    "Not in any recording": "❔ మా రికార్డింగ్‌లలో ఇది కనిపించలేదు. ఇది నకిలీ అని కాదు; మా వద్ద ఆ కార్యక్రమం రికార్డింగ్ లేకపోవచ్చు.",
}
VERDICT_EN = {
    "Genuine": "✅ Genuine: the whole clip is one continuous piece of our official recording.",
    "Edited": "❌ Edited: this clip joins words said at different moments.",
    "Partly altered": "❌ Partly altered: only part of this clip matches our recording.",
    "Check words": "⚠️ The sound matches our recording but the words differ: listen carefully.",
    "Words match, sound does not": "⚠️ These words were really said, but this audio is not from our recording (a different camera, a re-recording or a synthetic voice).",
    "Not in any recording": "❔ Not found in our recordings. That does not prove it is fake; we may not have recorded that event.",
}


def _mmss(s):
    s = int(s or 0)
    return f"{s // 60}:{s % 60:02d}"


def reply_for_clip(data, lang, api_key):
    archive = store.rows("speech_archive")
    if not archive:
        return "The office has no recordings to check against yet." if lang == "en" else "తనిఖీ చేయడానికి కార్యాలయం వద్ద ఇంకా రికార్డింగ్‌లు లేవు."
    tr = speech.transcribe(data, api_key, timestamps=False)
    res = speech.check_clip(speech.decode(data), tr.get("text", ""), archive)
    head = (VERDICT_EN if lang == "en" else VERDICT_TE).get(res["verdict"], res["verdict"])
    rec = res.get("recording")
    where = ""
    if rec:
        where = (f"\n\nFrom: {rec['title']}, {rec.get('event_date', '')}, at {_mmss(res['at_s'])}." if lang == "en"
                 else f"\n\nమూలం: {rec['title']}, {rec.get('event_date', '')}, {_mmss(res['at_s'])} వద్ద.")
        if res["verdict"] != "Genuine" and res.get("master_text"):
            where += ("\nWhat was actually said there: " if lang == "en" else "\nఅక్కడ నిజంగా చెప్పింది: ") + res["master_text"][:500]
        if rec.get("link") and "youtu" in rec["link"]:
            where += f"\n{rec['link']}{'&' if '?' in rec['link'] else '?'}t={int(res['at_s'] or 0)}s"
    return head + where


def reply_for_complaint(data, lang, api_key, flow_text):
    tr = speech.transcribe(data, api_key, timestamps=False)
    if not tr.get("ok") or not tr.get("text"):
        return "Sorry, we could not hear any speech in that voice note." if lang == "en" else "క్షమించండి, ఆ వాయిస్ నోట్‌లో మాటలు వినిపించలేదు."
    got = voice_intel.structure_complaint(tr["text"], api_key)
    if not got["ok"]:
        return "Sorry, something went wrong. Please try again." if lang == "en" else "క్షమించండి, సమస్య వచ్చింది. మళ్లీ ప్రయత్నించండి."
    no = voice_intel.ticket_number(tr["text"])
    store.add("voice_tickets", {"ticket_no": no, "transcript": tr["text"], "summary_en": got["summary_en"], "summary_te": got["summary_te"],
                                "category": got["category"], "area": got["area"], "department": got["department"], "urgency": got["urgency"],
                                "consent": True, "language": lang})
    reply = flow_text["filed"].format(no=no, summary=got["summary_en"] if lang == "en" else got["summary_te"])
    if got.get("missing"):
        reply += ("\n\n" + ("Please also tell us: " if lang == "en" else "దయచేసి ఇది కూడా చెప్పండి: ") + got["missing"])
    return reply
