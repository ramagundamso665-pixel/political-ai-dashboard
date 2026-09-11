"""Persistent Ask AI chat history.

Streamlit's session_state dies with the browser tab, so conversations are kept in
a JSON file beside the app. Each stored message carries the sheet and chart the
model picked, which is what lets a resumed conversation redraw its tables and
charts instead of showing bare text.

The file holds campaign questions and answers, so it is gitignored alongside
audit_log.json.
"""

import json
import os
import uuid
from datetime import datetime

STORE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chat_history.json")
MAX_CONVERSATIONS = 100
TITLE_CHARS = 48


def _read():
    if not os.path.exists(STORE):
        return []
    try:
        with open(STORE) as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        # a truncated or hand-edited file should not take the page down
        return []


def _write(conversations):
    trimmed = sorted(conversations, key=lambda c: c["updated_at"], reverse=True)[:MAX_CONVERSATIONS]
    tmp = f"{STORE}.tmp"
    with open(tmp, "w") as f:
        json.dump(trimmed, f, indent=2, default=str)
    os.replace(tmp, STORE)  # atomic, so an interrupted write can't corrupt the store


def _title_from(messages):
    first = next((m["content"] for m in messages if m["role"] == "user"), "")
    first = " ".join(first.split())
    if len(first) <= TITLE_CHARS:
        return first or "Untitled"
    return first[:TITLE_CHARS].rsplit(" ", 1)[0] + "…"


def new_id():
    return uuid.uuid4().hex[:12]


def listing():
    """Conversation summaries, newest first."""
    return [
        {
            "id": c["id"],
            "title": c.get("title") or "Untitled",
            "updated_at": c["updated_at"],
            "turns": sum(1 for m in c.get("messages", []) if m["role"] == "user"),
        }
        for c in sorted(_read(), key=lambda c: c["updated_at"], reverse=True)
    ]


def load(conversation_id):
    return next((c["messages"] for c in _read() if c["id"] == conversation_id), [])


def save(conversation_id, messages, party=None):
    """Insert or update. Empty conversations are never written."""
    if not messages:
        return
    conversations = [c for c in _read() if c["id"] != conversation_id]
    conversations.append(
        {
            "id": conversation_id,
            "title": _title_from(messages),
            "party": party,
            "updated_at": datetime.now().isoformat(),
            "messages": messages,
        }
    )
    _write(conversations)


def delete(conversation_id):
    _write([c for c in _read() if c["id"] != conversation_id])
