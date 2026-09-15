"""Persistent Ask AI chat history.

Stored in Supabase when it's configured, because a hosted app's disk is wiped on
every restart and redeploy — a JSON file there silently loses every
conversation. The local JSON file stays as the fallback so the app still runs
before the database is set up. Each stored message keeps the sheet and chart
the model picked, which is what lets a resumed conversation redraw its tables
and charts instead of showing bare text.
"""

import json
import os
import uuid
from datetime import datetime, timezone

import db
import health

STORE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chat_history.json")
TABLE = "conversations"
MAX_CONVERSATIONS = 100
LIST_LIMIT = 50
TITLE_CHARS = 48


def backend():
    return "supabase" if health.supabase_credentials() else "local"


def _read_local():
    if not os.path.exists(STORE):
        return []
    try:
        with open(STORE) as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        # a truncated or hand-edited file should not take the page down
        return []


def _write_local(conversations):
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


def _summary(c):
    return {
        "id": c["id"],
        "title": c.get("title") or "Untitled",
        "updated_at": c["updated_at"],
        "turns": sum(1 for m in c.get("messages") or [] if m.get("role") == "user"),
    }


def new_id():
    return uuid.uuid4().hex[:12]


def listing():
    """Conversation summaries, newest first."""
    creds = health.supabase_credentials()
    if creds:
        try:
            rows = db.select_rows(*creds, TABLE, {
                "select": "id,title,updated_at,messages",
                "order": "updated_at.desc",
                "limit": LIST_LIMIT,
            })
            return [_summary(r) for r in rows]
        except Exception:
            pass
    return [_summary(c) for c in sorted(_read_local(), key=lambda c: c["updated_at"], reverse=True)]


def load(conversation_id):
    creds = health.supabase_credentials()
    if creds:
        try:
            rows = db.select_rows(*creds, TABLE, {"select": "messages", "id": f"eq.{conversation_id}"})
            return rows[0]["messages"] if rows else []
        except Exception:
            pass
    return next((c["messages"] for c in _read_local() if c["id"] == conversation_id), [])


def save(conversation_id, messages, party=None):
    """Insert or update; empty conversations are never written. Returns where it
    was actually stored, so the caller can warn when the database was missed."""
    if not messages:
        return None
    record = {
        "id": conversation_id,
        "title": _title_from(messages),
        "party": party,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "messages": messages,
    }
    creds = health.supabase_credentials()
    if creds:
        try:
            db.upsert_row(*creds, TABLE, record)
            return "supabase"
        except Exception:
            pass
    conversations = [c for c in _read_local() if c["id"] != conversation_id]
    conversations.append(record)
    _write_local(conversations)
    return "local"


def delete(conversation_id):
    creds = health.supabase_credentials()
    if creds:
        try:
            db.delete_rows(*creds, TABLE, {"id": f"eq.{conversation_id}"})
            return
        except Exception:
            pass
    _write_local([c for c in _read_local() if c["id"] != conversation_id])
