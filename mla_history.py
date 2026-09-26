"""Who held each seat after the 2014, 2018 and 2023 assembly elections.

Built from the three statewide results files (2014 from the open Lok Dhaba extract, 2018 and 2023 from
the Election Commission's reports). The party shown is the party the winner stood for. It does not
follow anyone who changed party after the election, and by-elections since 2023 are not in here.
"""

import difflib
import re

import pandas as pd

import statewide

YEARS = (2014, 2018, 2023)
# name parts shared by very many people, which prove nothing on their own
COMMON = {"rao", "reddy", "kumar", "goud", "yadav", "naik", "singh", "raju", "babu", "chandra", "krishna", "venkata",
          "shri", "sri", "smt", "dr", "mohd", "md", "mohammed", "mohammad", "syed", "kumari", "devi", "rama", "narayana",
          "srinivas", "lakshmi", "anil", "ramesh", "prasad", "raj", "das", "naidu", "chary", "sagar", "ali", "khan", "ahmed", "ahmad", "hussain", "hussein", "akbar", "shaik", "begum"}
# a successor from the same family is not the same person (the daughter of a late MLA winning the seat, say)
NOT_THE_SAME = {("Secunderabad Cantt.", 2018, 2023)}
_TITLES = re.compile(r"\b(dr|sri|smt|mr|mrs|md|mohd)\b\.?")


def _tokens(name):
    name = _TITLES.sub(" ", name.lower())
    return [t for t in re.sub(r"[^a-z ]", " ", name).split() if t]


def same_person(a, b):
    """Two spellings of a winner's name, judged as the same person. Errs towards 'different'."""
    ta, tb = _tokens(a), _tokens(b)
    if len(ta) >= 2 and sorted(ta) == sorted(tb):
        return True  # same words in a different order, e.g. "Srinivas Goud V" and "V Srinivas Goud"
    strong_a = [t for t in ta if len(t) >= 4 and t not in COMMON]
    strong_b = [t for t in tb if len(t) >= 4 and t not in COMMON]
    for x in strong_a:
        for y in strong_b:
            if x == y or (len(x) >= 5 and "".join(tb).startswith(x)) or (len(y) >= 5 and "".join(ta).startswith(y)) or (len(x) >= 5 and len(y) >= 5 and difflib.SequenceMatcher(None, x, y).ratio() >= 0.85):
                return True
    return False


def table():
    """One row per seat: the winner and party in each of the three terms, and how many terms in a row the same person won."""
    seats = {y: statewide.load_year(y)[0].set_index("seat_no") for y in YEARS}
    rows = []
    for no in seats[2023].index:
        row = {"seat_no": no, "seat": seats[2023].loc[no, "seat"], "reservation": seats[2023].loc[no, "reservation"]}
        for y in YEARS:
            row[f"mla_{y}"] = seats[y].loc[no, "winner"]
            row[f"party_{y}"] = seats[y].loc[no, "winner_party"]
        row["kept_2018"] = same_person(row["mla_2014"], row["mla_2018"]) and (row["seat"], 2014, 2018) not in NOT_THE_SAME
        row["kept_2023"] = same_person(row["mla_2018"], row["mla_2023"]) and (row["seat"], 2018, 2023) not in NOT_THE_SAME
        row["terms_in_a_row"] = 1 + row["kept_2023"] + (row["kept_2023"] and row["kept_2018"])
        rows.append(row)
    return pd.DataFrame(rows)


def party_switch(df):
    """Seats where the same person won again but for a different party than last time."""
    out = []
    for a, b, flag in ((2014, 2018, "kept_2018"), (2018, 2023, "kept_2023")):
        for _, r in df[df[flag] & (df[f"party_{a}"] != df[f"party_{b}"])].iterrows():
            out.append({"Seat": r["seat"], "MLA": r[f"mla_{b}"], "From": r[f"party_{a}"], "To": r[f"party_{b}"], "Between": f"{a} and {b}"})
    return pd.DataFrame(out)
