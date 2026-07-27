"""Layer 5: audit trail. Every analysis view, prediction, and speech
generation is logged so accuracy can be checked against real outcomes later."""

import json
import os
from datetime import datetime


class AuditLogger:
    def __init__(self, log_file="audit_log.json"):
        self.log_file = log_file
        self.logs = self._load()

    def _load(self):
        if os.path.exists(self.log_file):
            try:
                with open(self.log_file) as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                return []
        return []

    def _save(self):
        with open(self.log_file, "w") as f:
            json.dump(self.logs, f, indent=2, default=str)

    def log_event(self, action_type, **details):
        entry = {"timestamp": datetime.now().isoformat(), "action_type": action_type, **details}
        self.logs.append(entry)
        self._save()

    def log_analysis(self, analysis_type, sources_used, summary):
        self.log_event("analysis", analysis_type=analysis_type, sources_used=sources_used, summary=summary)

    def log_speech_generation(self, party, audience, verification_status):
        self.log_event("speech_generation", party=party, audience=audience, verification_status=verification_status)

    def log_prediction(self, prediction_data):
        self.log_event("prediction", prediction=prediction_data)

    def recent(self, n=20):
        return self.logs[-n:]
