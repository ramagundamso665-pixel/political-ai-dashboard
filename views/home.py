"""Home: the whole seat on one screen, in plain words. Big numbers, one sentence each, a colour for good or bad,
and three things to do this week. Built from fixed rules over the data (no AI guessing), so the same data
always gives the same page. A Telugu button translates the page in one go."""

import html
import json
import os
from datetime import date

import pandas as pd
import streamlit as st

import live_pulse
import me
from config import ANSWER_MODEL, is_valid_api_key

TITLE = "Home"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GREEN, AMBER, RED, GREY = "#16a34a", "#d97706", "#dc2626", "#64748b"


# ----------------------------------------------------------------------
# facts
# ----------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def _csv(name):
    path = os.path.join(ROOT, "data", name)
    return pd.read_csv(path) if os.path.exists(path) else pd.DataFrame()


def _latest_contest(ctx, seat):
    """[(name, party, votes, pct)] of the latest contest, winner first, and its year."""
    if me.has_campaign_data(seat):
        try:
            h = ctx.sheets["historical_results"].copy()
            h["Year"] = pd.to_numeric(h["Year"], errors="coerce")
            y = int(h["Year"].max())
            rows = h[h["Year"] == y].sort_values("Votes", ascending=False)
            from config import normalize_party
            return [(r["Candidate"], normalize_party(r["Party"]) or r["Party"], int(r["Votes"]), float(r["Pct"])) for _, r in rows.iterrows()], y
        except Exception:
            pass
    c = _csv("telangana_2023_candidates.csv")
    rows = c[(c["seat"] == seat) & (c["party"] != "NOTA")].sort_values("rank")
    return [(r["candidate"], r["party"], int(r["votes_total"]), float(r["pct"])) for _, r in rows.iterrows()], 2023


def _party_history(seat, party):
    out = []
    for y in (2014, 2018, 2023):
        c = _csv(f"telangana_{y}_candidates.csv")
        rows = c[(c["seat"] == seat) & (c["party"] == party)]
        out.append((y, float(rows["pct"].sum()) if not rows.empty else None))
    return out


@st.cache_data(ttl=3 * 3600, show_spinner=False)
def _news(seat):
    res = live_pulse.fetch_google_news(f'"{seat}" Telangana', days=7, max_items=60)
    if not res["ok"]:
        return None
    arts = live_pulse.latest_first(res["articles"])
    # stories that name the seat in the headline first: a search hit can be a story that only mentions it in passing
    named = [a for a in arts if seat.lower().split(" (")[0] in a["title"].lower()]
    rest = [a for a in arts if a not in named]
    return {"count": len(res["articles"]), "named": len(named), "top": [(a["title"], a["url"], a["source"]) for a in (named + rest)[:3]]}


def _pct_change(a, b):
    return (b - a) / a * 100 if a else None


# ----------------------------------------------------------------------
# cards
# ----------------------------------------------------------------------
def build_cards(ctx, who):
    seat, party = who["seat"], who["party"]
    cards, actions = [], []

    # 1. last election
    rows, year = _latest_contest(ctx, seat)
    mine = next((r for r in rows if r[1] == party), None)
    others = [r for r in rows if r[1] != party]
    if rows:
        winner = rows[0]
        if mine and winner[1] == party:
            best_rival = others[0] if others else None
            gap = mine[2] - best_rival[2] if best_rival else 0
            pts = mine[3] - best_rival[3] if best_rival else 0
            cards.append({"title": f"Last election ({year})", "big": f"Won by {gap:,}", "unit": "votes", "colour": GREEN if pts >= 5 else AMBER,
                          "line": f"{mine[0]} got {mine[3]:.1f}%, ahead of {best_rival[0]} ({best_rival[1]}, {best_rival[3]:.1f}%)." if best_rival else ""})
        elif mine:
            gap = winner[2] - mine[2]
            cards.append({"title": f"Last election ({year})", "big": f"Lost by {gap:,}", "unit": "votes", "colour": RED,
                          "line": f"{winner[0]} ({winner[1]}) won with {winner[3]:.1f}%; {me.party_label(party)} got {mine[3]:.1f}%."})
        else:
            cards.append({"title": f"Last election ({year})", "big": f"{winner[1]} won", "unit": "", "colour": GREY,
                          "line": f"{winner[0]} won with {winner[3]:.1f}%. {me.party_label(party)} did not stand here."})
        # 2. safe or close
        if len(rows) >= 2:
            margin = rows[0][3] - rows[1][3]
            if margin < 5:
                label, colour, words = "Close seat", RED, "A small swing changes the result. Every booth matters."
                actions.append(f"This is a close seat (the top two were {margin:.1f} points apart). Visit the areas where the margin was thinnest first.")
            elif margin < 15:
                label, colour, words = "Leaning", AMBER, "Winnable either way with a strong campaign."
            else:
                label, colour, words = "Safe seat", GREEN, "The winner was far ahead. A big upset is needed to change it."
            cards.append({"title": "Safe or close?", "big": label, "unit": f"{margin:.1f} points apart", "colour": colour, "line": words})

    # 3. our party's trend
    hist = [(y, v) for y, v in _party_history(seat, party) if v is not None]
    if mine and year > 2023:
        hist.append((year, mine[3]))       # a by-election newer than the statewide files
    if len(hist) >= 2:
        (y0, v0), (y1, v1) = hist[0], hist[-1]
        up = v1 >= v0
        cards.append({"title": f"{me.party_label(party)} vote share here", "big": f"{v0:.0f}% → {v1:.0f}%", "unit": f"{y0} → {y1}",
                      "colour": GREEN if up else RED, "line": "Rising." if up else "Falling: find out where the votes went."})
        if not up:
            actions.append(f"{me.party_label(party)}'s share here fell from {v0:.0f}% ({y0}) to {v1:.0f}% ({y1}). Ask the Ask page where it went.")

    # 4. from space: water (rural) or trees (city)
    ind = _csv("seat_indicators.csv")
    row = ind[ind["seat"] == seat] if not ind.empty else ind
    if not row.empty:
        r = row.iloc[0]
        city = r["built_2023_ha"] / max(1, r["area_km2"] * 100) > 0.4
        if city:
            ch = _pct_change(r["trees_2017_ha"], r["trees_2023_ha"])
            cards.append({"title": "Trees (from satellite)", "big": f"{r['trees_2017_ha']:,.0f} → {r['trees_2023_ha']:,.0f}", "unit": "hectares, 2017 → 2023",
                          "colour": RED if (ch or 0) < -10 else GREEN, "line": "The city is losing green cover." if (ch or 0) < -10 else "Tree cover is holding."})
            if (ch or 0) < -10:
                actions.append("Tree cover here fell sharply since 2017. A tree-planting drive in the hottest wards is visible and popular (see Proof of Work → Heat).")
        else:
            w0, w1 = r["dry_water_2019_ha"], r["dry_water_2026_ha"]
            clear = min(r.get("dry_cover_2019", 1), r.get("dry_cover_2026", 1)) >= 0.9
            if clear:
                cards.append({"title": "Water in tanks & reservoirs (from satellite)", "big": f"{w0:,.0f} → {w1:,.0f}", "unit": "hectares, Feb–Mar 2019 → 2026",
                              "colour": GREEN if w1 > w0 else RED,
                              "line": "More water held before summer: good for farmers." if w1 > w0 else "Less water held before summer: farmers will feel it."})
                if w1 > w0 * 1.5:
                    actions.append(f"Water in tanks here went from {w0:,.0f} to {w1:,.0f} hectares. Show farmers the before/after satellite picture (Proof of Work page).")
                elif w1 < w0:
                    actions.append("Tanks here held less water this year than in 2019. Expect farmers' anger: meet the irrigation officials first.")

    # 5. power at night
    nl = _csv("night_lights.csv")
    mine_nl = nl[nl["seat"] == seat].sort_values("year") if not nl.empty else nl
    if len(mine_nl) >= 2:
        a, b = mine_nl.iloc[0], mine_nl.iloc[-1]
        ch = _pct_change(a["mean_radiance"], b["mean_radiance"])
        piv = nl.pivot_table(index="seat", columns="year", values="mean_radiance")
        growth = ((piv[piv.columns.max()] - piv[piv.columns.min()]) / piv[piv.columns.min()]).sort_values(ascending=False)
        rank = list(growth.index).index(seat) + 1 if seat in growth.index else None
        cards.append({"title": "Lights at night (from satellite)", "big": f"{ch:+.0f}%", "unit": f"{int(a['year'])} → {int(b['year'])}",
                      "colour": GREEN if ch > 10 else (AMBER if ch > 0 else RED),
                      "line": f"More light means more power, streets and business. {rank} of 119 seats for growth." if rank else
                              "More light means more power, streets and business."})

    # 6. news this week
    n = _news(seat)
    if n is not None:
        cards.append({"title": "In the news this week", "big": str(n["count"]), "unit": f"stories ({n['named']} with {seat} in the headline)",
                      "colour": AMBER if n["named"] >= 5 else GREY,
                      "line": "Latest:" if n["top"] else "A quiet week.", "links": n["top"]})

    # 7. main rival
    if others:
        rv = others[0]
        cards.append({"title": "Main rival", "big": rv[0], "unit": f"{rv[1]} · {rv[3]:.1f}% last time", "colour": GREY,
                      "line": "See what they are saying and spending on the Rivals page."})
        actions.append(f"Check what {rv[0]} ({rv[1]}) said and spent this week (Rivals page) before any press meet.")

    if not me.has_campaign_data(seat):
        actions.append("There are no surveys or booth figures for this seat yet. The office can start collecting them (People & Promises page).")
    return cards, actions[:3]


# ----------------------------------------------------------------------
# Telugu
# ----------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def _telugu(payload, api_key):
    """Translate the page's text in one call. Numbers, names and party names are kept as they are."""
    from openai import OpenAI

    resp = OpenAI(api_key=api_key, timeout=120).chat.completions.create(
        model=ANSWER_MODEL, temperature=0, response_format={"type": "json_object"},
        messages=[{"role": "system", "content": "Translate every string value in this JSON into simple spoken Telugu (Telugu script) for a political "
                                                  "leader. Keep numbers as digits, and keep person names, party names and place names as they are. "
                                                  "Return the same JSON shape."},
                  {"role": "user", "content": payload}],
    )
    return json.loads(resp.choices[0].message.content)


def _card_html(c):
    links = ""
    for title, url, src in c.get("links", [])[:3]:
        links += (f"<div style='font-size:.82rem;margin-top:4px'>• <a href='{html.escape(url)}' target='_blank'>{html.escape(title[:90])}</a> "
                  f"<span style='opacity:.6'>({html.escape(src)})</span></div>")
    return (f"<div style='border-left:6px solid {c['colour']};background:rgba(128,128,128,.07);border-radius:10px;padding:14px 16px;min-height:150px'>"
            f"<div style='font-size:.8rem;opacity:.75;text-transform:uppercase;letter-spacing:.04em'>{html.escape(c['title'])}</div>"
            f"<div style='font-size:1.8rem;font-weight:700;line-height:1.2;margin:4px 0'>{html.escape(c['big'])}</div>"
            f"<div style='font-size:.85rem;opacity:.7'>{html.escape(c['unit'])}</div>"
            f"<div style='margin-top:8px;font-size:.98rem'>{html.escape(c['line'])}</div>{links}</div>")


def render(ctx, sidebar):
    who = me.get()
    c1, c2 = st.columns([4, 1])
    telugu = c2.toggle("తెలుగు", key="home_te", help="Read this page in Telugu")
    with st.spinner("Putting the seat together"):
        cards, actions = build_cards(ctx, who)
    head = f"{who['seat']} this week: summary for {who['leader']}"
    todo_title = "What to do this week"
    if telugu and is_valid_api_key(ctx.api_key):
        payload = json.dumps({"head": head, "todo": todo_title, "actions": actions,
                              "cards": [{k: c[k] for k in ("title", "big", "unit", "line")} for c in cards]}, ensure_ascii=False)
        try:
            t = _telugu(payload, ctx.api_key)
            head, todo_title, actions = t.get("head", head), t.get("todo", todo_title), t.get("actions", actions)
            for c, tc in zip(cards, t.get("cards", [])):
                c.update({k: tc.get(k, c[k]) for k in ("title", "big", "unit", "line")})
        except Exception:
            st.caption("Telugu translation is not available right now.")
    c1.markdown(f"## {html.escape(head)}")
    c1.caption(date.today().strftime("%A, %d %B %Y"))

    for i in range(0, len(cards), 3):
        cols = st.columns(3)
        for col, card in zip(cols, cards[i:i + 3]):
            col.markdown(_card_html(card), unsafe_allow_html=True)
        st.write("")

    if actions:
        st.markdown(f"### ✅ {html.escape(todo_title)}")
        for i, a in enumerate(actions, 1):
            st.markdown(f"**{i}.** {a}")

    with st.expander("Where do these numbers come from?"):
        st.markdown(
            "- **Election results:** Election Commission of India (2014, 2018, 2023); the Jubilee Hills 2025 by-election from the campaign's results sheet.\n"
            "- **Water, trees, building:** free public satellite pictures (Sentinel-2 and yearly land maps), measured the same way for every seat.\n"
            "- **Lights at night:** NASA's night-lights satellite, one reading a year.\n"
            "- **News:** Google News, the last 7 days.\n"
            "- Green = good for you, amber = watch it, red = act now, grey = information."
        )
    ctx.logger.log_analysis("home", ["home"], f"home for {who['leader']} in {who['seat']}")
