"""The "rate my area" conversation, with no network in it so it can be tested by typing.

    hi -> language (1 English, 2 Telugu) -> the issue that bothers you most this week (menu)
       -> which area or colony (free text) -> rate the area 1 to 5 -> thanks

`handle(session, text)` takes the person's saved state and their message, and returns the reply and the new
state. When the conversation reaches its end, the state carries a finished rating for the caller to store.
STOP at any time asks the caller to delete that person's answers.
"""

ISSUES = ["Water supply", "Roads", "Electricity", "Drainage", "Garbage", "Price rise", "Other"]
ISSUES_TE = ["తాగునీరు", "రోడ్లు", "కరెంటు", "డ్రైనేజీ", "చెత్త", "ధరల పెరుగుదల", "ఇతర"]

TEXT = {
    "en": {
        "menu": "What bothers you most in your area this week? Reply with a number:\n" + "\n".join(f"{i + 1}. {n}" for i, n in enumerate(ISSUES)),
        "area": "Which area or colony is this about? (for example: Shaikpet, Road No. 45)",
        "rate": "How would you rate your area this week?\n1 = very poor, 2 = poor, 3 = okay, 4 = good, 5 = very good",
        "thanks": "Thank you. Your answer has been recorded. You can send Hi again next week. Send STOP to delete your answers and stop messages.",
        "bad_choice": "Please reply with just one of the numbers shown.",
        "bad_area": "Please type the name of your area or colony (2 to 60 letters).",
        "stopped": "Done. Your answers have been deleted and you will get no more messages. Send Hi if you ever want to start again.",
    },
    "te": {
        "menu": "ఈ వారం మీ ప్రాంతంలో మిమ్మల్ని ఎక్కువగా ఇబ్బంది పెడుతున్న సమస్య ఏది? ఒక సంఖ్యతో జవాబు ఇవ్వండి:\n" + "\n".join(f"{i + 1}. {n}" for i, n in enumerate(ISSUES_TE)),
        "area": "ఇది ఏ ప్రాంతం లేదా కాలనీ గురించి? (ఉదా: షేక్‌పేట్, రోడ్డు నంబర్ 45)",
        "rate": "ఈ వారం మీ ప్రాంతానికి ఎన్ని మార్కులు ఇస్తారు?\n1 = చాలా చెడ్డ, 2 = చెడ్డ, 3 = పర్వాలేదు, 4 = బాగుంది, 5 = చాలా బాగుంది",
        "thanks": "ధన్యవాదాలు. మీ జవాబు నమోదైంది. వచ్చే వారం మళ్లీ Hi పంపండి. మీ జవాబులు తొలగించి సందేశాలు ఆపడానికి STOP పంపండి.",
        "bad_choice": "దయచేసి చూపిన సంఖ్యలలో ఒకదానితో మాత్రమే జవాబు ఇవ్వండి.",
        "bad_area": "దయచేసి మీ ప్రాంతం లేదా కాలనీ పేరు రాయండి (2 నుండి 60 అక్షరాలు).",
        "stopped": "సరే. మీ జవాబులు తొలగించబడ్డాయి, ఇక సందేశాలు రావు. మళ్లీ మొదలుపెట్టాలంటే Hi పంపండి.",
    },
}

WELCOME = (
    "Hello! This is the People's Mandate area survey. It takes under a minute and is voluntary. "
    "Your number is not stored; only a scrambled code, so we can count you once a week.\n\n"
    "Reply 1 for English\nతెలుగు కోసం 2 అని జవాబు ఇవ్వండి\n\nSend STOP any time to leave and delete your answers."
)


def new_session():
    return {"step": "start", "language": "en", "issue": None, "area": None}


def handle(session, text):
    """(reply, session, action). action is None, 'save' (a finished rating is in session['rating']) or 'stop'."""
    session = dict(session or new_session())
    said = (text or "").strip()
    word = said.lower()
    lang = session.get("language", "en")

    if word in {"stop", "unsubscribe", "ఆపు"}:
        return TEXT[lang]["stopped"], new_session(), "stop"
    if word in {"hi", "hello", "hai", "start", "నమస్తే", "హాయ్"} or session["step"] == "start":
        session.update(step="language", issue=None, area=None)
        return WELCOME, session, None

    step = session["step"]
    if step == "language":
        if word not in {"1", "2"}:
            return WELCOME, session, None
        session.update(language="en" if word == "1" else "te", step="issue")
        return TEXT[session["language"]]["menu"], session, None
    if step == "issue":
        if not (word.isdigit() and 1 <= int(word) <= len(ISSUES)):
            return TEXT[lang]["bad_choice"] + "\n\n" + TEXT[lang]["menu"], session, None
        session.update(issue=ISSUES[int(word) - 1], step="area")
        return TEXT[lang]["area"], session, None
    if step == "area":
        area = " ".join(said.split())
        if not (2 <= len(area) <= 60) or area.isdigit():
            return TEXT[lang]["bad_area"], session, None
        session.update(area=area.title() if area.isascii() else area, step="rate")
        return TEXT[lang]["rate"], session, None
    if step == "rate":
        if word not in {"1", "2", "3", "4", "5"}:
            return TEXT[lang]["bad_choice"] + "\n\n" + TEXT[lang]["rate"], session, None
        session["rating"] = {"issue": session["issue"], "area": session["area"], "rating": int(word), "language": lang}
        session["step"] = "done"
        return TEXT[lang]["thanks"], session, "save"
    return TEXT[lang]["thanks"], session, None      # anything after the end: remind them how to go again
