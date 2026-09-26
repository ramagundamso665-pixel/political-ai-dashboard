"""Supabase storage for the bot: sessions and ratings, over PostgREST with the service key.
A phone number is only ever kept as a salted hash."""

import hashlib
import os
from datetime import datetime, timezone

import requests

URL = os.environ.get("SUPABASE_URL", "")
KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
SALT = os.environ.get("PHONE_HASH_SALT", "")


def _h(prefer=None):
    h = {"apikey": KEY, "Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}
    if prefer:
        h["Prefer"] = prefer
    return h


def phone_hash(number):
    if not SALT:
        raise RuntimeError("PHONE_HASH_SALT is not set")
    return hashlib.sha256((SALT + str(number)).encode()).hexdigest()


def iso_week(now=None):
    y, w, _ = (now or datetime.now(timezone.utc)).isocalendar()
    return f"{y}-W{w:02d}"


def get_session(ph):
    r = requests.get(f"{URL}/rest/v1/wa_sessions", headers=_h(), params={"phone_hash": f"eq.{ph}", "limit": 1}, timeout=10)
    r.raise_for_status()
    rows = r.json()
    return {k: rows[0].get(k) for k in ("step", "language", "issue", "area")} if rows else None


def save_session(ph, s):
    body = {"phone_hash": ph, "step": s["step"], "language": s.get("language", "en"), "issue": s.get("issue"),
            "area": s.get("area"), "updated_at": datetime.now(timezone.utc).isoformat()}
    r = requests.post(f"{URL}/rest/v1/wa_sessions", headers=_h("resolution=merge-duplicates,return=minimal"), json=body, timeout=10)
    r.raise_for_status()


def save_rating(ph, rating, week=None):
    """One rating per person per week: sending it again replaces the earlier one."""
    body = {"phone_hash": ph, "week": week or iso_week(), "area": rating["area"], "issue": rating["issue"],
            "rating": rating["rating"], "language": rating["language"]}
    r = requests.post(f"{URL}/rest/v1/area_ratings", headers=_h("resolution=merge-duplicates,return=minimal"),
                      params={"on_conflict": "phone_hash,week"}, json=body, timeout=10)
    r.raise_for_status()


def forget(ph):
    for table in ("area_ratings", "wa_sessions"):
        requests.delete(f"{URL}/rest/v1/{table}", headers=_h("return=minimal"), params={"phone_hash": f"eq.{ph}"}, timeout=10).raise_for_status()
