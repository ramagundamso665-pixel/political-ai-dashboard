"""Parse the Election Commission's "10 - Detailed Results" statistical report.

The PDF lists, for every constituency: its number, name and total electors; then one
row per candidate (rank, name, sex, age, category, party, symbol, general / postal /
total votes, share of votes polled); then the turnout line. Candidate names and party
symbols wrap onto neighbouring lines, so rows are rebuilt from word positions rather
than from plain text.

Every constituency is checked against its own turnout line, so a misread row cannot
slip through silently: candidate votes must add up to the valid votes polled, and each
share must match its votes.

Source file: https://www.eci.gov.in/eci-backend/public/all_files/full-statistical-reports/telangana/2023/Detailed_Results.pdf
"""

import re
from dataclasses import dataclass, field

import pdfplumber

LINE_TOLERANCE = 3.0


@dataclass(frozen=True)
class Era:
    """How one edition of the ECI report is laid out. The columns are the same in every
    edition; the labels, codes and font sizes are not."""
    fonts: tuple                 # point sizes used for data (footers and titles use others)
    constituency: str            # regex: number, name, electors
    turnout: str                 # regex: general, postal, total, percent
    sex: frozenset
    categories: frozenset
    parties: dict                # code as printed -> the code this app uses
    strip_sex_words: bool        # whether a sex word can spill into the name column
    title_names: bool            # names are printed in capitals


ERAS = {
    2023: Era(
        fonts=(7.1,),
        constituency=r"Constituency (\d+) - (.+?) TOTAL ELECTORS (\d+)",
        turnout=r"TURN OUT TOTAL:\s*([\d,]+)\s+([\d,]+)\s+([\d,]+)\s+([\d.]+)",
        sex=frozenset({"MALE", "FEMALE", "THIRD", "OTHER"}),
        categories=frozenset({"GENERAL", "SC", "ST"}),
        parties={"BHRS": "BRS"},                # the ECI abbreviates Bharat Rashtra Samithi as BHRS
        strip_sex_words=True,
        title_names=False,
    ),
    2018: Era(
        fonts=(8.8, 8.9, 9.0, 10.5, 10.8),      # column heading, rows, then the constituency line and its electors
        constituency=r"Constituency (\d+)\. (.+?) TOTAL ELECTORS : (\d+)",
        turnout=r"TURNOUT TOTAL:\s*([\d,]+)\s+([\d,]+)\s+([\d,]+)\s+([\d.]+)",
        sex=frozenset({"M", "F", "O", "T"}),
        categories=frozenset({"GEN", "SC", "ST"}),
        parties={"TRS": "BRS"},                 # Telangana Rashtra Samithi, renamed BRS in October 2022
        strip_sex_words=False,
        title_names=True,
    ),
}

@dataclass
class Candidate:
    rank: int
    name: str
    sex: str
    age: int | None
    category: str
    party: str
    votes_general: int
    votes_postal: int
    votes_total: int
    pct: float


@dataclass
class Seat:
    number: int
    name: str
    reservation: str          # "GENERAL", "SC" or "ST"
    electors: int
    candidates: list[Candidate] = field(default_factory=list)
    turnout_general: int = 0
    turnout_postal: int = 0
    turnout_total: int = 0
    turnout_pct: float = 0.0
    problems: list[str] = field(default_factory=list)


def _number(text):
    return float(text.replace(",", "")) if "." in text else int(text.replace(",", ""))


def _lines(words):
    """Group a page's words into visual lines, top to bottom, left to right."""
    lines, current, current_top = [], [], None
    for word in sorted(words, key=lambda w: (w["top"], w["x0"])):
        if current_top is None or abs(word["top"] - current_top) <= LINE_TOLERANCE:
            current.append(word)
            current_top = word["top"] if current_top is None else current_top
        else:
            lines.append(sorted(current, key=lambda w: w["x0"]))
            current, current_top = [word], word["top"]
    if current:
        lines.append(sorted(current, key=lambda w: w["x0"]))
    return lines


def _text(line):
    return " ".join(w["text"] for w in line)


def _looks_like_main_line(line, era):
    """The line carrying the vote figures: it ends in three integers and a decimal."""
    texts = [w["text"] for w in line]
    if len(texts) < 5:
        return False
    tail = texts[-4:]
    return (
        all(t.replace(",", "").isdigit() for t in tail[:3])
        and re.fullmatch(r"\d+\.\d+|\d+", tail[3]) is not None
        and (any(t in era.sex for t in texts) or "NOTA" in texts)
    )


def _sex_index(tokens, era):
    """Where the sex column is on a vote line: a sex code followed by an age and a category.
    (A bare 'M' can also be an initial inside a name.)"""
    for i in range(len(tokens) - 2):
        if tokens[i] in era.sex and tokens[i + 1].isdigit() and tokens[i + 2] in era.categories:
            return i
    return None


def _clean_name(name, era):
    name = re.sub(r"\s+", " ", name).strip()
    return name.title() if era.title_names else name


def _build_candidate(lines, sex_x0, era):
    """One candidate from the lines between two rank numbers."""
    words = [w for line in lines for w in line]
    main = next((line for line in lines if _looks_like_main_line(line, era)), None)
    if main is None:
        raise ValueError("no vote line: " + " / ".join(_text(l) for l in lines))

    tail = [w["text"] for w in main[-4:]]
    general, postal, total = (int(t.replace(",", "")) for t in tail[:3])
    pct = float(tail[3])

    rank_word = lines[0][0]
    rank = int(rank_word["text"])
    # the sex column starts a couple of points left of its heading, so stop the name column short of it
    dropped = era.sex | {"GENDER"} if era.strip_sex_words else set()
    name_words = [w for w in words if w is not rank_word and w["x0"] < sex_x0 - 5 and w["text"] not in dropped]
    name_words.sort(key=lambda w: (round(w["top"] / LINE_TOLERANCE), w["x0"]))
    name = _clean_name(" ".join(w["text"] for w in name_words), era)

    tokens = [w["text"] for w in main]
    i = _sex_index(tokens, era)
    if i is None:
        if "NOTA" in tokens:
            return Candidate(rank, name or "Nota", "", None, "", "NOTA", general, postal, total, pct)
        raise ValueError("no sex/age/category on vote line: " + " ".join(tokens))
    sex = tokens[i]
    age = int(tokens[i + 1])
    category = tokens[i + 2]
    party = era.parties.get(tokens[i + 3], tokens[i + 3])
    return Candidate(rank, name, sex, age, category, party, general, postal, total, pct)


def parse(pdf_path, year=2023):
    """Seats from an ECI Detailed Results PDF. `year` selects the layout (see ERAS)."""
    era = ERAS[year]
    seats, seat, group = [], None, []
    sex_x0 = name_x0 = None

    def flush():
        nonlocal group
        if group and seat is not None:
            try:
                seat.candidates.append(_build_candidate(group, sex_x0, era))
            except (ValueError, StopIteration, IndexError) as exc:
                seat.problems.append(f"unreadable candidate row ({exc})")
        group = []

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            # the page footer is printed in a different size and, on a full page, right on top of the
            # last row's percentage, so only the data font is kept before words are read
            body = page.filter(
                lambda o: o.get("object_type") != "char" or any(abs(o.get("size", 0) - f) < 0.25 for f in era.fonts)
            )
            for line in _lines(body.extract_words(x_tolerance=1.5, y_tolerance=2)):
                text = _text(line)

                if "CANDIDATE" in text and "SEX" in text:
                    header = {w["text"]: w["x0"] for w in line}
                    name_x0, sex_x0 = header["CANDIDATE"], header["SEX"]
                    continue

                m = re.match(era.constituency, text)
                if m:
                    flush()
                    number, name, electors = int(m.group(1)), m.group(2).strip(), int(m.group(3))
                    reservation = "GENERAL"
                    r = re.search(r"\((SC|ST)\)\s*$", name)
                    if r:
                        reservation, name = r.group(1), name[: r.start()].strip()
                    seat = Seat(number, name, reservation, electors)
                    seats.append(seat)
                    continue

                m = re.match(era.turnout, text)
                if m:
                    flush()
                    seat.turnout_general, seat.turnout_postal, seat.turnout_total = (int(m.group(i).replace(",", "")) for i in (1, 2, 3))
                    seat.turnout_pct = float(m.group(4))
                    continue

                if seat is None or name_x0 is None or text.startswith(("VALID VOTES", "VOTES", "Election Commission", "10 - DETAILED", "DETAILED")):
                    continue

                first = line[0]
                # a rank is a short number at, or just left of, the name column (ages and votes sit far to the right)
                if first["text"].isdigit() and first["x0"] < name_x0 + 3 and first["x1"] - first["x0"] < 14:
                    flush()
                    group = [line]
                elif group:
                    group.append(line)
        flush()

    for s in seats:
        _validate(s)
    return seats


def _validate(seat):
    got = sum(c.votes_total for c in seat.candidates)
    if seat.turnout_total and got != seat.turnout_total:
        seat.problems.append(f"candidate votes add up to {got:,}, turnout line says {seat.turnout_total:,}")
    for c in seat.candidates:
        if seat.turnout_total and abs(c.votes_total / seat.turnout_total * 100 - c.pct) > 0.06:
            seat.problems.append(f"{c.name}: {c.votes_total:,} votes is {c.votes_total / seat.turnout_total * 100:.2f}%, sheet says {c.pct}")
    ranks = [c.rank for c in seat.candidates]
    if ranks != list(range(1, len(ranks) + 1)):
        seat.problems.append(f"candidate ranks are not 1..n: {ranks}")
    winner = max((c for c in seat.candidates if c.party != "NOTA"), key=lambda c: c.votes_total, default=None)
    if winner and seat.candidates and seat.candidates[0].votes_total != winner.votes_total:
        seat.problems.append("first-listed candidate is not the highest vote-getter")
