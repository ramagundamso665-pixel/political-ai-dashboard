"""Layer 5: audit trail. Every analysis view, prediction, and speech generation
is logged so accuracy can be checked against real outcomes later.

Entries go to Supabase when it's configured (a hosted app's disk doesn't survive
a restart), written on a background thread so logging never slows a page down.
Views log on every rerun, so an identical event repeated within a minute is
dropped instead of filling the table with duplicates.
"""

import json
import os
import threading
import time
from datetime import datetime, timezone

import db
import health

TABLE = "audit_log"
LOCAL_MAX = 500
DEDUPE_SECONDS = 60


class AuditLogger:
    def __init__(self, log_file="audit_log.json"):
        self.log_file = log_file
        self._last_logged = {}
        self._lock = threading.Lock()

    def _read_local(self):
        if not os.path.exists(self.log_file):
            return []
        try:
            with open(self.log_file) as f:
                data = json.load(f)
            return data if isinstance(data, list) else []
        except (json.JSONDecodeError, OSError):
            return []

    def _append_local(self, entry):
        with self._lock:
            logs = self._read_local()
            logs.append(entry)
            with open(self.log_file, "w") as f:
                json.dump(logs[-LOCAL_MAX:], f, indent=2, default=str)

    def _write(self, entry, creds):
        if creds:
            try:
                db.insert_row(*creds, TABLE, {"action_type": entry["action_type"], "details": entry["details"]})
                return
            except Exception:
                pass
        self._append_local(entry)

    def log_event(self, action_type, **details):
        details = json.loads(json.dumps(details, default=str))
        fingerprint = (action_type, json.dumps(details, sort_keys=True))
        now = time.monotonic()
        if now - self._last_logged.get(fingerprint, -DEDUPE_SECONDS) < DEDUPE_SECONDS:
            return
        self._last_logged[fingerprint] = now

        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action_type": action_type,
            "details": details,
        }
        # secrets are read here, on the script thread — st.secrets isn't safe off it
        creds = health.supabase_credentials()
        threading.Thread(target=self._write, args=(entry, creds), daemon=True).start()

    def log_analysis(self, analysis_type, sources_used, summary):
        self.log_event("analysis", analysis_type=analysis_type, sources_used=sources_used, summary=summary)

    def log_speech_generation(self, party, audience, verification_status):
        self.log_event("speech_generation", party=party, audience=audience, verification_status=verification_status)

    def log_prediction(self, prediction_data):
        self.log_event("prediction", prediction=prediction_data)

    def recent(self, n=20):
        creds = health.supabase_credentials()
        if creds:
            try:
                return db.select_rows(*creds, TABLE, {
                    "select": "created_at,action_type,details",
                    "order": "created_at.desc",
                    "limit": n,
                })
            except Exception:
                pass
        return list(reversed(self._read_local()[-n:]))
