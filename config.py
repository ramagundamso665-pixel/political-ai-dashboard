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

# The 17 Telangana Lok Sabha constituencies.
TELANGANA_LOK_SABHA = [
    "Adilabad", "Bhongir", "Chevella", "Hyderabad", "Karimnagar", "Khammam",
    "Mahabubabad", "Mahbubnagar", "Malkajgiri", "Medak", "Nagarkurnool",
    "Nalgonda", "Nizamabad", "Peddapalle", "Secunderabad", "Warangal", "Zahirabad",
]

# Display name -> the form headlines actually use ("KCR", not the full name).
# Deliberately no party tags: affiliations change, and a stale tag on a
# politician is exactly the kind of wrong claim this dashboard must not make.
KEY_LEADERS = {
    "A. Revanth Reddy": "Revanth Reddy",
    "Akbaruddin Owaisi": "Akbaruddin Owaisi",
    "Asaduddin Owaisi": "Asaduddin Owaisi",
    "Bandi Sanjay Kumar": "Bandi Sanjay",
    "Bhatti Vikramarka": "Bhatti Vikramarka",
    "Etela Rajender": "Etela Rajender",
    "G. Kishan Reddy": "Kishan Reddy",
    # Low-coverage names get a full spec: Google News matches a name anywhere in
    # an article body, so a bare name search mostly returns stories where the
    # person is a passing mention. The role in the label is verified against
    # current headlines — Peddapalli MP, not an MLA.
    "Gaddam Vamsi Krishna (MP, Peddapalli)": {
        "term": "Gaddam Vamsi Krishna",
        "news": '"Gaddam Vamsi Krishna" OR "Peddapalli MP"',
        "headline_terms": ["vamsi krishna", "vamshi krishna", "vamsikrishna", "peddapalli mp", "peddapalle mp"],
        # Telugu media is where he is actually covered — English news only
        # mentions him in passing
        "news_te": '"గడ్డం వంశీకృష్ణ"',
        "headline_terms_te": ["వంశీకృష్ణ", "ఎంపీ వంశీ"],
        # Chikkudu Vamshi Krishna is the Achampet MLA — a different person
        "exclude_terms": ["mla vamsi", "mla vamshi", "achampet", "chikkudu", "అచ్చంపేట", "చిక్కుడు"],
    },
    "Gaddam Vivek Venkatswamy (Labour Minister)": {
        "term": "Vivek Venkatswamy",
        # headlines mostly say just "Vivek" — this found 8 about him vs 4 for his full name
        "news": '"Vivek" Telangana minister',
        "headline_terms": ["venkatswamy", "venkataswamy", "gaddam vivek", "minister vivek", "vivek"],
        "news_te": '"మంత్రి వివేక్"',
        "headline_terms_te": ["వివేక్"],
        # other Viveks the bare name pulls in; the AI relevance check catches any new ones
        "exclude_terms": ["rawat", "athreya", "ramaswamy", "oberoi", "agnihotri", "bindra"],
    },
    "K. Chandrashekar Rao (KCR)": "KCR",
    "K. T. Rama Rao (KTR)": "KTR",
    "Komatireddy Venkat Reddy": "Komatireddy Venkat Reddy",
    "N. Uttam Kumar Reddy": "Uttam Kumar Reddy",
    "Ponguleti Srinivas Reddy": "Ponguleti Srinivas Reddy",
    "Seethakka": "Seethakka",
    "T. Harish Rao": "Harish Rao",
}

PARTY_SEARCH_TERMS = {
    "BRS": "BRS Telangana",
    "INC": "Telangana Congress",
    "BJP": "Telangana BJP",
    "AIMIM": "AIMIM",
}

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
    """Reject missing keys, the placeholder left in secrets.toml.example, and keys
    pasted from a masked display — those carry • characters, which are never
    part of a real key and would otherwise fail later as an opaque HTTP 400."""
    if not key:
        return False
    key = str(key)
    return key.isascii() and " " not in key.strip() and not key.startswith(placeholder_prefix)


# The model that answers questions about the data (Ask AI, Rebuttal Builder). Chosen by
# testing seven known-answer questions: gpt-4o-mini misread the numeric tables (4/7),
# gpt-4o was dearer and no better (5/7), gpt-4.1-mini got them right for about
# Rs 0.2 a question. Speeches and headline mood stay on gpt-4o-mini: they don't
# read numbers out of tables.
ANSWER_MODEL = "gpt-4.1-mini"


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
        "name": "Official GHMC/Assembly Election Results (2014-2025)",
        "type": "verified",
        "refresh": "Fixed per election cycle",
        "basis": "Public official record (Election Commission results)",
        "methodology": "Official declared results. The 2025 by-election rows were taken from Wikipedia's results "
                        "table and cross-checked against news reports, not from the ECI file itself; replace "
                        "them with ECI's own figures when downloaded",
    },
    "eci_2018": {
        "id": "eci_2018",
        "name": "Election Commission of India: Telangana 2018 Detailed Results",
        "type": "verified",
        "refresh": "Fixed per election cycle",
        "basis": "Public official record (Election Commission of India statistical report)",
        "methodology": "Candidate-wise results for all 119 constituencies, read from the ECI's published report "
                        "(hosted on its old site). Every constituency is checked against its own turnout line. "
                        "The party then called TRS is shown as BRS, its later name.",
    },
    "eci_2023": {
        "id": "eci_2023",
        "name": "Election Commission of India: Telangana 2023 Detailed Results",
        "type": "verified",
        "refresh": "Fixed per election cycle",
        "basis": "Public official record (Election Commission of India statistical report)",
        "methodology": "Candidate-wise results for all 119 constituencies, read from the ECI's published report. "
                        "Every constituency is checked against its own turnout line: the candidates' votes add up exactly.",
    },
    "ceo_form20_2023": {
        "id": "ceo_form20_2023",
        "name": "CEO Telangana: Form 20 booth results, Jubilee Hills 2023",
        "type": "verified",
        "refresh": "Fixed per election cycle",
        "basis": "Public official record (Form 20 final result sheet, scanned), read by hand and reconciled",
        "methodology": "One line per polling station, read off the scanned sheet. Each candidate's column adds up "
                        "exactly to that candidate's EVM votes in the ECI Detailed Results report. Postal votes are "
                        "not attributed to any booth.",
    },
    "division_shares": {
        "id": "division_shares",
        "name": "Internal Division-Level Vote Share Tracking",
        "type": "internal",
        "refresh": "Per tracking round (2023, 2025), updated by staff",
        "basis": "Campaign's own aggregate estimate; no individual voter is identified",
        "methodology": "Campaign's own division/ward-level estimate, not an official count",
    },
    "division_deltas": {
        "id": "division_deltas",
        "name": "Internal Division-Level Vote Share Tracking",
        "type": "internal",
        "refresh": "Recomputed when a tracking round is added",
        "basis": "Derived from the aggregate tracking rounds; no individual voter is identified",
        "methodology": "Change in campaign's division-level estimate between 2023 and 2025 tracking rounds",
    },
    "demo_preferences": {
        "id": "demo_preferences",
        "name": "Internal Demographic Preference Tracking",
        "type": "internal",
        "refresh": "Per tracking round, updated by staff",
        "basis": "Campaign's own aggregate estimate by group; no individual voter is identified",
        "methodology": "Campaign's own subgroup-level vote preference estimate",
    },
    "surveys": {
        "id": "surveys",
        "name": "Third-Party Opinion Surveys",
        "type": "external",
        "refresh": "As each poll is published",
        "basis": "Published third-party polls; aggregate figures only",
        "methodology": "Multiple independent pollsters; sample size and methodology vary by survey and are not independently verified",
    },
    "social_media": {
        "id": "social_media",
        "name": "Social Media Activity Log",
        "type": "internal",
        "refresh": "Logged by staff, post by post",
        "basis": "Public post engagement counts; no individual profiles kept",
        "methodology": "Manually logged post-level engagement counts, not a sentiment model",
    },
    "ground_campaign": {
        "id": "ground_campaign",
        "name": "Ground Campaign Field Notes",
        "type": "internal",
        "refresh": "Updated when staff file field notes",
        "basis": "Staff observations about parties and issues; no personal data recorded",
        "methodology": "Qualitative field intelligence collected by campaign staff",
    },
    "campaign_activity": {
        "id": "campaign_activity",
        "name": "Campaign Activity Log",
        "type": "internal",
        "refresh": "Logged event by event",
        "basis": "Public campaign events reported by staff",
        "methodology": "Event-by-event log of rallies, visits, and press activity",
    },
    "demographics": {
        "id": "demographics",
        "name": "Constituency Voter Roll Demographics",
        "type": "internal",
        "refresh": "Updated when the electoral roll is revised",
        "basis": "Aggregate counts from the public electoral roll; no individual is identified",
        "methodology": "Voter roll counts by category",
    },
    "field_reports": {
        "id": "field_reports",
        "name": "Public Field Report Intake",
        "type": "internal",
        "refresh": "As reports arrive, reviewed by staff",
        "basis": "Submitted voluntarily by the person filing the report; free text, so it can contain personal details",
        "methodology": "Unverified reports submitted directly by field workers/the public "
                        "through the open intake form — reviewed by staff before acting on them",
    },
    "live_pulse": {
        "id": "live_pulse",
        "name": "Live Search & News Pulse (Google Trends / GDELT / YouTube)",
        "type": "external",
        "refresh": "Fetched live, cached for 15 minutes",
        "basis": "Public search trends, news headlines and video details from free APIs and feeds; no individual profiles collected",
        "methodology": "Automated free-tier pull of public search interest, news tone, "
                        "and video activity — a sampled proxy for public mood, not a "
                        "measured survey",
    },
}
