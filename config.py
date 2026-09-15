"""Static configuration: constituency, party normalization, source metadata."""

CONSTITUENCY_NAME = "Jubilee Hills (GHMC)"
DATA_FILE = "Book 13.xlsx"

# Search term used for the free-tier Live Pulse signals (Google Trends / GDELT /
# YouTube) — kept separate from CONSTITUENCY_NAME since that string carries the
# "(GHMC)" suffix, which is not what anyone actually searches or writes about.
PULSE_KEYWORD = "Jubilee Hills"

# 2023 candidates, from Historical_Results — lets Live Pulse search on names
# that actually appear on this seat's ballot instead of a guessed keyword.
# AIMIM has no entry: no candidate contested this seat for them in 2023.
CANDIDATES = {
    "BRS": "Maganti Gopinath",
    "INC": "Mohammed Azharuddin",
    "BJP": "Lankala Deepak Reddy",
}

# All 119 Telangana Legislative Assembly constituencies, so Live Pulse can
# track search/news/social signal for any seat in the state, not only this
# campaign's own. Source: Wikipedia's list of Telangana Assembly
# constituencies (delimitation in force since 2014).
TELANGANA_CONSTITUENCIES = [
    "Achampet", "Adilabad", "Alair", "Alampur", "Amberpet", "Andole",
    "Armur", "Asifabad", "Aswaraopeta", "Bahadurpura", "Balkonda",
    "Banswada", "Bellampalli", "Bhadrachalam", "Bhongir", "Bhupalpalle",
    "Boath", "Bodhan", "Chandrayangutta", "Charminar", "Chennur",
    "Chevella", "Choppadandi", "Devarakonda", "Devarkadra", "Dharmapuri",
    "Dornakal", "Dubbak", "Gadwal", "Gajwel", "Ghanpur Station",
    "Goshamahal", "Huzurabad", "Huzurnagar", "Husnabad", "Ibrahimpatnam",
    "Jadcherla", "Jagtial", "Jangaon", "Jubilee Hills", "Jukkal",
    "Kalwakurthy", "Kamareddy", "Karimnagar", "Karwan", "Khairatabad",
    "Khammam", "Khanapur", "Kodad", "Kodangal", "Kollapur", "Koratla",
    "Kothagudem", "Kukatpally", "Lal Bahadur Nagar", "Madhira", "Maheshwaram",
    "Mahabubabad", "Mahbubnagar", "Makthal", "Malakpet", "Malkajgiri",
    "Manakondur", "Mancherial", "Manthani", "Medak", "Medchal",
    "Miryalaguda", "Mudhole", "Mulug", "Munugode", "Musheerabad",
    "Nagarjuna Sagar", "Nagarkurnool", "Nakrekal", "Nalgonda", "Nampally",
    "Narayankhed", "Narayanpet", "Narsampet", "Narsapur", "Nirmal",
    "Nizamabad Rural", "Nizamabad Urban", "Palair", "Palakurthi", "Pargi",
    "Parkal", "Patancheru", "Peddapalle", "Pinapaka", "Quthbullapur",
    "Rajendranagar", "Ramagundam", "Sanathnagar", "Sangareddy", "Sathupalli",
    "Secunderabad", "Secunderabad Cantonment", "Serilingampally", "Shadnagar",
    "Siddipet", "Sircilla", "Sirpur", "Suryapet", "Tandur", "Thungathurthi",
    "Uppal", "Vemulawada", "Vikarabad", "Wanaparthy", "Waradhanapet",
    "Warangal East", "Warangal West", "Wyra", "Yakutpura", "Yellandu",
    "Yellareddy", "Zahirabad",
]

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


def is_valid_api_key(key, placeholder_prefix="sk-REPLACE"):
    """Reject missing keys and the placeholder left in secrets.toml.example."""
    return bool(key) and not str(key).startswith(placeholder_prefix)


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
    "field_reports": {
        "id": "field_reports",
        "name": "Public Field Report Intake",
        "type": "internal",
        "methodology": "Unverified reports submitted directly by field workers/the public "
                        "through the open intake form — reviewed by staff before acting on them",
    },
    "live_pulse": {
        "id": "live_pulse",
        "name": "Live Search & News Pulse (Google Trends / GDELT / YouTube)",
        "type": "external",
        "methodology": "Automated free-tier pull of public search interest, news tone, "
                        "and video activity — a sampled proxy for public mood, not a "
                        "measured survey",
    },
}
