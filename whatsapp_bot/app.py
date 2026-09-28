"""WhatsApp Cloud API webhook: the "rate my area" survey, clip checks and voice-note complaints. Run with gunicorn (see README.md).

Environment: WHATSAPP_TOKEN, WHATSAPP_PHONE_NUMBER_ID, WHATSAPP_VERIFY_TOKEN, WHATSAPP_APP_SECRET,
SUPABASE_URL, SUPABASE_SERVICE_KEY, PHONE_HASH_SALT, OPENAI_API_KEY (clip checks and voice complaints).
"""

import hashlib
import hmac
import os
import threading

import requests
from flask import Flask, abort, request

import flow
import store

app = Flask(__name__)
GRAPH = "https://graph.facebook.com/v20.0"


def send(to, text):
    r = requests.post(
        f"{GRAPH}/{os.environ['WHATSAPP_PHONE_NUMBER_ID']}/messages",
        headers={"Authorization": f"Bearer {os.environ['WHATSAPP_TOKEN']}"},
        json={"messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": text}},
        timeout=15,
    )
    r.raise_for_status()


def download(media_id):
    """A media file sent to the bot: look up its URL, then fetch it with the same token."""
    auth = {"Authorization": f"Bearer {os.environ['WHATSAPP_TOKEN']}"}
    meta = requests.get(f"{GRAPH}/{media_id}", headers=auth, timeout=15)
    meta.raise_for_status()
    r = requests.get(meta.json()["url"], headers=auth, timeout=60)
    r.raise_for_status()
    return r.content


def process_media(number, media_id, action, lang):
    """Runs after the webhook has answered, since a clip check can take a minute."""
    import media
    try:
        data = download(media_id)
        key = os.environ.get("OPENAI_API_KEY")
        reply = media.reply_for_clip(data, lang, key) if action == "verify" else media.reply_for_complaint(data, lang, key, flow.MEDIA_TEXT[lang])
    except Exception:
        reply = "Sorry, that could not be processed. Please try again later." if lang == "en" else "క్షమించండి, ప్రాసెస్ చేయలేకపోయాం. తర్వాత మళ్లీ ప్రయత్నించండి."
    send(number, reply)


def signature_ok(body, header):
    """Meta signs every webhook call with the app secret; refuse anything that does not check out."""
    secret = os.environ.get("WHATSAPP_APP_SECRET", "")
    if not secret or not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header.split("=", 1)[1])


@app.get("/webhook")
def verify():
    if request.args.get("hub.mode") == "subscribe" and hmac.compare_digest(
        request.args.get("hub.verify_token", ""), os.environ.get("WHATSAPP_VERIFY_TOKEN", "-")
    ):
        return request.args.get("hub.challenge", ""), 200
    abort(403)


@app.post("/webhook")
def incoming():
    if not signature_ok(request.get_data(), request.headers.get("X-Hub-Signature-256")):
        abort(403)
    payload = request.get_json(silent=True) or {}
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            for msg in change.get("value", {}).get("messages", []):
                number = msg["from"]
                ph = store.phone_hash(number)
                kind = msg.get("type")
                if kind in ("audio", "video", "voice"):
                    # a forwarded clip or a voice note: ask what to do with it
                    reply, session = flow.handle_media(store.get_session(ph) or flow.new_session(), msg[kind]["id"], kind)
                    store.save_session(ph, session)
                    send(number, reply)
                    continue
                if kind != "text":
                    continue                      # images, stickers and the like
                reply, session, action = flow.handle(store.get_session(ph) or flow.new_session(), msg["text"]["body"])
                if action == "stop":
                    store.forget(ph)
                else:
                    if action == "save":
                        store.save_rating(ph, session["rating"])
                    store.save_session(ph, session)
                send(number, reply)
                if action in ("verify", "complaint") and session.get("pending_media"):
                    threading.Thread(target=process_media, args=(number, session["pending_media"]["id"], action, session.get("language", "en")),
                                     daemon=True).start()
    return "ok", 200                              # always answer 200, or Meta retries the same message


@app.get("/")
def health():
    return "area survey bot is running", 200
