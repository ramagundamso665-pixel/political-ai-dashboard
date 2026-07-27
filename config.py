"""Static configuration: constituency, party normalization, source metadata."""

CONSTITUENCY_NAME = "Jubilee Hills (GHMC)"
DATA_FILE = "Book 13.xlsx"

# Excel sheet name -> internal key used across the app
SHEET_KEY_MAP = {
    "Demographics": "demographics",
    "Division_Shares": "division_shares",
    "Division_Deltas": "division_deltas",
    "Demo_Preferences": "demo_preferences",
    "Surveys": "surveys",
    "Historical_Results": "historical_results",
    "Social_Media": "social_media",
    "Ground_Campaign": "ground_campaign",
    "Campaign_Activity": "campaign_activity",
}

# Canonical party code -> display info
PARTIES = ["BRS", "INC", "BJP", "AIMIM"]

PARTY_LABELS = {
    "BRS": "BRS",
    "INC": "Congress (INC)",
    "BJP": "BJP",
    "AIMIM": "AIMIM",
}

PARTY_COLORS = {
    "BRS": "#E91E63",
    "INC": "#1565C0",
    "BJP": "#F57C00",
    "AIMIM": "#2E7D32",
    "Others": "#9E9E9E",
}

# Different sheets spell party names differently. Map every variant to a canonical code.
PARTY_ALIASES = {
    "BRS": "BRS",
    "INC": "INC",
    "CONG": "INC",
    "CONGRESS": "INC",
    "BJP": "BJP",
    "AIMIM": "AIMIM",
}


def is_valid_api_key(key):
    """Reject missing keys and the placeholder left in secrets.toml.example."""
    return bool(key) and not key.startswith("sk-REPLACE")


def normalize_party(raw):
    """Return canonical party code, or None if unrecognized/placeholder text."""
    if raw is None:
        return None
    key = str(raw).strip().upper()
    return PARTY_ALIASES.get(key)


# Metadata registered with SourceTracker at app start. Confidence/type reflects
# how each sheet was actually produced, not a generic template.
SOURCE_METADATA = {
    "historical_results": {
        "id": "historical_results",
        "name": "Official GHMC/Assembly Election Results (2014-2023)",
        "type": "verified",
        "methodology": "Official declared results, prior election cycles",
    },
    "division_shares": {
        "id": "division_shares",
        "name": "Internal Division-Level Vote Share Tracking",
        "type": "internal",
        "methodology": "Campaign's own division/ward-level estimate, not an official count",
    },
    "division_deltas": {
        "id": "division_deltas",
        "name": "Internal Division-Level Vote Share Tracking",
        "type": "internal",
        "methodology": "Change in campaign's division-level estimate between 2023 and 2025 tracking rounds",
    },
    "demo_preferences": {
        "id": "demo_preferences",
        "name": "Internal Demographic Preference Tracking",
        "type": "internal",
        "methodology": "Campaign's own subgroup-level vote preference estimate",
    },
    "surveys": {
        "id": "surveys",
        "name": "Third-Party Opinion Surveys",
        "type": "external",
        "methodology": "Multiple independent pollsters; sample size and methodology vary by survey and are not independently verified",
    },
    "social_media": {
        "id": "social_media",
        "name": "Social Media Activity Log",
        "type": "internal",
        "methodology": "Manually logged post-level engagement counts, not a sentiment model",
    },
    "ground_campaign": {
        "id": "ground_campaign",
        "name": "Ground Campaign Field Notes",
        "type": "internal",
        "methodology": "Qualitative field intelligence collected by campaign staff",
    },
    "campaign_activity": {
        "id": "campaign_activity",
        "name": "Campaign Activity Log",
        "type": "internal",
        "methodology": "Event-by-event log of rallies, visits, and press activity",
    },
    "demographics": {
        "id": "demographics",
        "name": "Constituency Voter Roll Demographics",
        "type": "internal",
        "methodology": "Voter roll counts by category",
    },
}
