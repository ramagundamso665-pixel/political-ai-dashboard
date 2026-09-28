"""Rows for the newer features (speech archive, promises, ledger, contacts, field events, message tests).

Supabase is the home for them (supabase/intel.sql). Until that file has been run, rows go to a JSON
file under data/local_store/ so every feature still works on one machine; the pages say which is in
use, because a local file on a hosted app disappears whenever the host restarts.
"""

import json
import os
import uuid
from datetime import datetime, timezone

import requests

import health

ROOT = os.path.dirname(os.path.abspath(__file__))
LOCAL_DIR = os.path.join(ROOT, "data", "local_store")
TABLES = ("speech_archive", "promises", "ledger", "contacts", "field_events", "message_tests", "message_responses", "voice_tickets")


def _creds():
    return health.supabase_credentials()


def _headers(key, prefer=None):
    h = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    if prefer:
        h["Prefer"] = prefer
    return h


_remote_ok = {}


def remote(table):
    """True when the Supabase table exists and answers."""
    if table in _remote_ok:
        return _remote_ok[table]
    creds = _creds()
    ok = False
    if creds:
        try:
            r = requests.get(f"{creds[0]}/rest/v1/{table}", headers=_headers(creds[1]), params={"limit": 1}, timeout=10)
            ok = r.status_code == 200
        except Exception:
            ok = False
    _remote_ok[table] = ok
    return ok


def where(table):
    return "database" if remote(table) else "this server only (run supabase/intel.sql to keep it)"


def _local_path(table):
    os.makedirs(LOCAL_DIR, exist_ok=True)
    return os.path.join(LOCAL_DIR, f"{table}.json")


def _local_read(table):
    try:
        with open(_local_path(table)) as fh:
            return json.load(fh)
    except Exception:
        return []


def _local_write(table, rows):
    with open(_local_path(table), "w") as fh:
        json.dump(rows, fh, ensure_ascii=False, default=str)


def rows(table, order="created_at.desc", filters=None, limit=2000):
    if remote(table):
        url, key = _creds()
        params = {"order": order, "limit": limit, **(filters or {})}
        r = requests.get(f"{url}/rest/v1/{table}", headers=_headers(key), params=params, timeout=20)
        r.raise_for_status()
        return r.json()
    out = _local_read(table)
    for k, v in (filters or {}).items():
        if v.startswith("eq."):
            out = [r for r in out if str(r.get(k)) == v[3:]]
    field, _, direction = order.partition(".")
    return sorted(out, key=lambda r: str(r.get(field, "")), reverse=direction == "desc")[:limit]


def add(table, row):
    """Insert a row and return it with its id and created_at."""
    row = {k: v for k, v in row.items() if v is not None}
    if remote(table):
        url, key = _creds()
        r = requests.post(f"{url}/rest/v1/{table}", headers=_headers(key, "return=representation"), json=row, timeout=20)
        r.raise_for_status()
        return r.json()[0]
    row.setdefault("id", str(uuid.uuid4()))
    row.setdefault("created_at", datetime.now(timezone.utc).isoformat())
    all_rows = _local_read(table)
    all_rows.append(row)
    _local_write(table, all_rows)
    return row


def update(table, row_id, changes):
    if remote(table):
        url, key = _creds()
        r = requests.patch(f"{url}/rest/v1/{table}", headers=_headers(key, "return=minimal"), params={"id": f"eq.{row_id}"}, json=changes, timeout=20)
        r.raise_for_status()
        return
    all_rows = _local_read(table)
    for r in all_rows:
        if str(r.get("id")) == str(row_id):
            r.update(changes)
    _local_write(table, all_rows)


def delete(table, row_id):
    if remote(table):
        url, key = _creds()
        r = requests.delete(f"{url}/rest/v1/{table}", headers=_headers(key), params={"id": f"eq.{row_id}"}, timeout=20)
        r.raise_for_status()
        return
    _local_write(table, [r for r in _local_read(table) if str(r.get("id")) != str(row_id)])
