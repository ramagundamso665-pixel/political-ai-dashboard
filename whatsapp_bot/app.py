"""WhatsApp Cloud API webhook for the "rate my area" survey. Run with gunicorn (see README.md).

Environment: WHATSAPP_TOKEN, WHATSAPP_PHONE_NUMBER_ID, WHATSAPP_VERIFY_TOKEN, WHATSAPP_APP_SECRET,
SUPABASE_URL, SUPABASE_SERVICE_KEY, PHONE_HASH_SALT.
"""

import hashlib
import hmac
import os

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
                if msg.get("type") != "text":
                    continue                      # ignore images, voice notes and the like
                number, text = msg["from"], msg["text"]["body"]
                ph = store.phone_hash(number)
                reply, session, action = flow.handle(store.get_session(ph) or flow.new_session(), text)
                if action == "stop":
                    store.forget(ph)
                else:
                    if action == "save":
                        store.save_rating(ph, session["rating"])
                    store.save_session(ph, session)
                send(number, reply)
    return "ok", 200                              # always answer 200, or Meta retries the same message


@app.get("/")
def health():
    return "area survey bot is running", 200
