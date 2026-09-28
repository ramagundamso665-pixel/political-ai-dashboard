"""War Room: the next attack, the next story and the rival's next target, seen before they arrive."""

from datetime import date

import pandas as pd
import streamlit as st

import charts
import evidence
import health
import store
import warroom as wr
from components import empty_state, fact_card, section
from config import PARTIES, PARTY_LABELS, SOURCE_METADATA, is_valid_api_key, normalize_party
from views.opponent_watch import _rivals, _years

TITLE = "War Room"
HOME = "Jubilee Hills"


def leader_picker(ctx, prefix):
    """Seat, leader and party, shared by War Room and Prep. Defaults to the latest winner of the seat."""
    seats = sorted(_years()[2023]["seat"].unique())
    c1, c2, c3 = st.columns([1.2, 1.6, 1])
    seat = c1.selectbox("Seat", seats, index=seats.index(HOME) if HOME in seats else 0, key=f"{prefix}_seat")
    winner, wparty = None, None
    if seat == HOME:
        try:
            h = ctx.sheets["historical_results"].copy()
            h["Year"] = pd.to_numeric(h["Year"], errors="coerce")
            top = h[h["Year"] == h["Year"].max()].sort_values("Votes", ascending=False).iloc[0]
            winner, wparty = top["Candidate"], normalize_party(top["Party"]) or top["Party"]
        except Exception:
            pass
    if not winner:
        c = _years()[2023]
        top = c[(c["seat"] == seat) & (c["rank"] == 1)].iloc[0]
        winner, wparty = top["candidate"], top["party"]
    leader = c2.text_input("Your leader", value=winner, key=f"{prefix}_leader_{seat}")
    opts = PARTIES + ["Other"]
    party = c3.selectbox("Party", opts, index=opts.index(wparty) if wparty in opts else len(opts) - 1, key=f"{prefix}_party_{seat}")
    return seat, leader.strip(), party


def _places(ctx, seat):
    if seat == HOME:
        try:
            return sorted(ctx.sheets["division_shares"]["Division"].dropna().unique())
        except Exception:
            pass
    return [seat]


@st.cache_data(ttl=1800, show_spinner=False)
def _news_vel(term):
    return wr.news_velocity(term)


@st.cache_data(ttl=3 * 3600, show_spinner=False)
def _yt_vel(term, key):
    return wr.youtube_velocity(term, key)


@st.cache_data(ttl=7 * 24 * 3600, show_spinner=False)
def _season():
    return wr.seasonal_profile()


@st.cache_data(ttl=3600, show_spinner=False)
def _place_news(party, places):
    return wr.news_place_mentions(party, list(places))


@st.cache_data(ttl=3600, show_spinner=False)
def _rally(event_date, place, others, leader):
    return wr.rally_impact(event_date, place, list(others), leader)


def _events(ctx):
    """The campaign's event log (Campaign_Activity sheet) plus staff-logged field events."""
    rows = []
    try:
        ca = ctx.sheets["campaign_activity"]
        for _, r in ca.iterrows():
            rows.append({"date": r.get("Date"), "party": r.get("Party"), "place": r.get("Area / Division"), "kind": r.get("Event Type"),
                         "who": r.get("Leader(s) / VIP"), "source": "Campaign_Activity sheet"})
    except Exception:
        pass
    for e in store.rows("field_events"):
        rows.append({"date": e.get("event_date"), "party": e.get("who"), "place": e.get("place"), "kind": e.get("kind"), "who": e.get("notes"), "source": "Field event log"})
    return pd.DataFrame(rows)


# ----------------------------------------------------------------------
def _attack(ctx, seat, leader, party, snap):
    st.markdown(f"The opposition's research desk, turned on **{leader}** first. Every attack cites the evidence it rests on; the defence is only what is on record.")
    if st.button("Forecast the attacks", type="primary", key="wr_attack_go"):
        with st.spinner("Gathering the record and thinking like the rivals"):
            lines = evidence.build(ctx, seat, leader, party)
            st.session_state["wr_attack"] = {"lines": lines, "res": wr.attack_forecast(lines, ctx.api_key)}
    got = st.session_state.get("wr_attack")
    if not got:
        return
    res, lines = got["res"], got["lines"]
    if not res["ok"]:
        st.warning(res["error"])
        return
    for i, a in enumerate(res["attacks"], 1):
        colour = {"High": "🔴", "Medium": "🟠", "Low": "🟡"}.get(a.get("damage"), "⚪")
        with st.container(border=True):
            st.markdown(f"**{i}. {colour} {a['attack']}**")
            st.caption(f"Most likely from: {a.get('who', '?')} · likelihood {a.get('likelihood', '?')} · damage {a.get('damage', '?')} · rests on {', '.join(a.get('evidence', []))}")
            if a.get("defence"):
                st.success("**On record:** " + " ".join(a["defence"]))
            else:
                st.error("**No answer on record yet.**")
            st.markdown(f"**Do now:** {a.get('todo', '')}")
    snap.append(f"Attack forecast: top risk '{res['attacks'][0]['attack']}'" if res["attacks"] else "Attack forecast: none found")
    with st.expander(f"The evidence pack ({len(lines)} lines)"):
        for i, line in enumerate(lines, 1):
            st.markdown(f"**E{i}** {line}")


def _radar(ctx, seat, leader, party, snap):
    st.markdown("Stories accelerate before they explode. Each topic's last 3 days are compared with its usual rate for the month before.")
    places = _places(ctx, seat)
    default = [f'"{seat}"', f'"{leader}"'] + [f'"{p}"' for p in places[:5] if p != seat]
    terms_text = st.text_area("Topics to watch (one per line; quotes keep words together)", "\n".join(default), height=140, key=f"wr_radar_terms_{seat}")
    terms = [t.strip() for t in terms_text.splitlines() if t.strip()][:12]
    use_yt = st.checkbox("Also check YouTube (uses 200 of the 10,000 daily quota units per topic)", key="wr_radar_yt")
    if st.button("Scan now", type="primary", key="wr_radar_go"):
        yt = health.secret("YOUTUBE_API_KEY")
        rows = []
        with st.spinner("Scanning"):
            for t in terms:
                n = _news_vel(t)
                row = {"Topic": t, "News, last 3 days": n.get("recent"), "Usual for 3 days": n.get("baseline"), "News speed-up": n.get("ratio"),
                       "Latest headline": (n.get("latest") or [""])[0]}
                if use_yt and yt:
                    y = _yt_vel(t, yt)
                    row.update({"Videos, last 3 days": y.get("recent"), "YouTube speed-up": y.get("ratio")})
                best = max(r for r in (row.get("News speed-up") or 0, row.get("YouTube speed-up") or 0))
                row["Signal"] = wr.radar_level(best, max(row.get("News, last 3 days") or 0, row.get("Videos, last 3 days") or 0))
                rows.append(row)
        st.session_state["wr_radar"] = rows
    rows = st.session_state.get("wr_radar")
    if rows:
        df = pd.DataFrame(rows).sort_values(["Signal", "News speed-up"], ascending=[True, False])
        st.dataframe(df, hide_index=True, width="stretch")
        hot = [r for r in rows if not r["Signal"].startswith("⚪")]
        st.session_state["radar_snapshot"] = {"lines": [f"{r['Topic']}: {r['Signal']} ({r['News, last 3 days']} stories in 3 days vs usual {r['Usual for 3 days']}); latest: {r['Latest headline']}" for r in hot]}
        snap.extend(st.session_state["radar_snapshot"]["lines"][:3])
    tickets = pd.DataFrame(store.rows("voice_tickets"))
    if not tickets.empty:
        st.markdown("**Complaints speeding up** (voice tickets, last 7 days against the 4 weeks before)")
        lv = wr.local_velocity(tickets, "created_at", ["area", "category"])
        st.dataframe(lv.head(10), hide_index=True, width="stretch") if not lv.empty else st.caption("No complaints in the last 7 days.")
    st.caption("Google News lists at most 100 stories per search, and only reaches back about a month. A speed-up is a smoke alarm, not a forecast: check the headline.")


def _targets(ctx, seat, party, snap):
    st.markdown("Where rivals are putting their effort. Heavy activity in one area usually means they think it is winnable.")
    places = _places(ctx, seat)
    ev = _events(ctx)
    if ev.empty:
        st.info("No events logged yet. Log rival and own events under Event log.")
    else:
        act = wr.rival_activity(ev, places)
        st.markdown("**Events in the last 45 days of the log, by area and party**")
        st.dataframe(act, hide_index=True, width="stretch")
    if seat == HOME:
        try:
            d = ctx.sheets["division_shares"].copy()
            d["Year"] = pd.to_numeric(d["Year"], errors="coerce")
            latest = d[d["Year"] == d["Year"].max()].set_index("Division")
            rivals = [p for p in ("BRS", "INC", "BJP") if p != party and p in latest]
            if party in latest:
                latest["Your margin"] = latest[party] - latest[rivals].max(axis=1)
                st.markdown(f"**Your margin by division, {int(d['Year'].max())} estimate** (the thinnest are where a rival push matters most)")
                st.dataframe(latest[[party] + rivals + ["Your margin"]].sort_values("Your margin").reset_index(), hide_index=True, width="stretch")
        except Exception:
            pass
    rival = st.selectbox("Also count news pairing a rival party with each area", [p for p in ("BRS", "INC", "BJP", "AIMIM") if p != party], key="wr_tgt_party")
    if st.button("Count news mentions (last 30 days)", key="wr_tgt_news"):
        with st.spinner("Searching news for each area"):
            m = _place_news(rival, tuple(places))
        mdf = pd.DataFrame([{"Area": k, f"{rival} stories": v} for k, v in m.items()]).sort_values(f"{rival} stories", ascending=False)
        st.dataframe(mdf, hide_index=True, width="stretch")
        top = mdf.iloc[0]
        snap.append(f"Rival target: news pairs {rival} most with {top['Area']} ({top[f'{rival} stories']} stories in 30 days)")


def _counter(ctx, seat, leader, party, snap):
    st.markdown("Paste what a rival said. Each factual part is checked against the record; a reply is drafted only from what the record can prove.")
    claim = st.text_area("The rival's claim", placeholder="e.g. KTR: 'Not one drain has been built in Jubilee Hills since Congress came to power.'", key="wr_claim")
    if st.button("Check it and draft a reply", type="primary", key="wr_claim_go") and claim.strip():
        with st.spinner("Checking against the record"):
            lines = evidence.build(ctx, seat, leader, party)
            st.session_state["wr_counter"] = {"lines": lines, "res": wr.counter_proof(claim, lines, ctx.api_key)}
    got = st.session_state.get("wr_counter")
    if not got:
        st.caption("Tip: run the relevant check on the Proof page first (for example land use or irrigation). Its numbers then join the record here.")
        return
    res = got["res"]
    if not res["ok"]:
        st.warning(res["error"])
        return
    for a in res.get("assertions", []):
        icon = {"Supports rival": "⚠️", "Contradicts rival": "✅", "No evidence": "❔"}.get(a.get("verdict"), "❔")
        st.markdown(f"{icon} **{a.get('assertion')}** — {a.get('verdict')} ({', '.join(a.get('evidence', [])) or 'no lines'}). {a.get('why', '')}")
    if res.get("advice"):
        st.warning(f"**Before replying:** {res['advice']}")
    c1, c2 = st.columns(2)
    c1.markdown("**తెలుగు reply**")
    c1.write(res.get("reply_te", ""))
    c2.markdown("**English reply**")
    c2.write(res.get("reply_en", ""))
    snap.append(f"Counter-proof drafted for claim: {st.session_state.get('wr_claim', '')[:80]}")
    with st.expander(f"The evidence pack ({len(got['lines'])} lines)"):
        for i, line in enumerate(got["lines"], 1):
            st.markdown(f"**E{i}** {line}")


def _rally_tab(ctx, seat, leader, party, snap):
    st.markdown("Did an event change anything? News about the place in the week after, against the week before, next to other places over the same dates.")
    ev = _events(ctx)
    ours = ev[ev["party"].astype(str).str.upper().map(lambda p: wr.PARTY_ALIASES.get(p.strip(), p.strip())) == party] if not ev.empty else ev
    if ours.empty:
        st.info("No events of yours in the log. Add them under Event log (date, place, kind).")
        return
    ours = ours.assign(label=ours["date"].astype(str).str[:10] + " · " + ours["place"].astype(str) + " · " + ours["kind"].astype(str))
    pick = st.selectbox("Event", ours["label"].tolist(), key="wr_rally_pick")
    row = ours[ours["label"] == pick].iloc[0]
    others = tuple(p for p in _places(ctx, seat) if p != row["place"])
    if st.button("Measure", key="wr_rally_go"):
        if (date.today() - pd.Timestamp(row["date"]).date()).days > 23:
            st.warning("Google News only reaches back about 30 days, so events older than about 3 weeks cannot be measured this way.")
            return
        with st.spinner("Counting stories before and after"):
            r = _rally(str(row["date"])[:10], str(row["place"]), others, leader)
        m = st.columns(3)
        m[0].metric("Stories the week before", r["before"])
        m[1].metric("Stories the week after", r["after"], f"×{r['change']}")
        m[2].metric("Other areas, same dates", f"×{r['control_change']}" if r["control_change"] else "–")
        verdict = "moved coverage" if r["change"] and r["control_change"] and r["change"] > r["control_change"] * 1.5 else "did not clearly move coverage"
        st.markdown(f"**This event {verdict}** compared with the other areas.")
        snap.append(f"Rally impact: {pick} {verdict} (×{r['change']} vs ×{r['control_change']} elsewhere)")
    st.caption("News coverage is one signal; complaints and social comments can be added the same way. A single event against a handful of places is noisy.")


def _money(ctx, seat, party, snap):
    st.markdown("Which spending was followed by votes? Money spent per division against the change in your share there between two tracking rounds.")
    if seat != HOME:
        st.info("Division-level vote estimates exist for the home seat only.")
        return
    up = st.file_uploader("Spending CSV: division, amount (one row per work; RTI or fund records)", type=["csv"], key="wr_money_up")
    if not up:
        st.caption("Division names must match the division list: " + ", ".join(_places(ctx, seat)))
        return
    spend = pd.read_csv(up)
    spend.columns = [c.lower().strip() for c in spend.columns]
    d = ctx.sheets["division_shares"]
    years = sorted(pd.to_numeric(d["Year"], errors="coerce").dropna().unique())
    table, corr = wr.money_to_votes(spend, d, party, years[0], years[-1])
    st.dataframe(table, hide_index=True, width="stretch")
    if corr is not None:
        st.metric("Link between spending and vote change", corr, help="-1 to 1. With seven divisions this is a hint, not proof.")
        snap.append(f"Money-to-votes: correlation {corr} between spending and {party} share change {int(years[0])}→{int(years[-1])}")
    st.caption("Seven divisions is far too few to prove anything, and the vote shares are the campaign's own estimates. Use it to ask questions, not to decide budgets.")


def _calendar(snap):
    st.markdown("Problems come in seasons. Five years of Telangana search interest, folded into months, shows what is coming next.")
    with st.spinner("Reading five years of Google Trends"):
        p = _season()
    if not p["ok"]:
        st.warning(p["error"])
        return
    now = wr.peaking_now(p["profile"])
    soon = wr.coming_up(p["profile"])
    c1, c2 = st.columns(2)
    c1.markdown("**At its yearly high now**")
    for x in now:
        c1.markdown(f"- {x['Issue']} ({x['Level now']})")
    if not now:
        c1.caption("Nothing at its peak this month.")
    c2.markdown("**Rising in the next six weeks**")
    for x in soon:
        c2.markdown(f"- {x['Issue']}: {x['Now']} now → {x['Peak soon']} in {x['Month']}")
    if not soon:
        c2.caption("Nothing climbing sharply in the next six weeks.")
    st.dataframe(p["profile"], hide_index=True, width="stretch")
    snap.append("Season: peaking now " + (", ".join(x["Issue"] for x in now) or "nothing") + "; rising soon " + (", ".join(x["Issue"] for x in soon) or "nothing"))
    st.caption("Each row is 0–100 within that issue (100 = its busiest month). Search interest is statewide, not constituency-level.")


def _log(ctx):
    st.markdown("Log events as they happen, yours and rivals'. Opponent Targets and Rally Impact read from here and from the Campaign_Activity sheet.")
    with st.form("wr_log", clear_on_submit=True):
        c1, c2, c3, c4 = st.columns(4)
        when = c1.date_input("Date", value=date.today())
        who = c2.selectbox("Party", PARTIES + ["Other"])
        kind = c3.selectbox("Kind", ["Rally", "Padayatra", "Press meet", "Door to door", "Inspection", "Meeting", "Other"])
        place = c4.text_input("Area / division")
        notes = st.text_input("Leaders present, notes")
        if st.form_submit_button("Log it") and place:
            store.add("field_events", {"event_date": when.isoformat(), "who": who, "kind": kind, "place": place, "notes": notes})
            st.success("Logged.")
    ev = _events(ctx)
    if not ev.empty:
        st.dataframe(ev.sort_values("date", ascending=False), hide_index=True, width="stretch")
    st.caption(f"Saved to: {store.where('field_events')}")


def render(ctx, sidebar):
    section("War room", "The next attack, the next story, and the rival's next target, seen before they arrive.")
    if not is_valid_api_key(ctx.api_key):
        st.warning("Attack Forecast and Counter-Proof need OPENAI_API_KEY.")
    seat, leader, party = leader_picker(ctx, "wr")
    snap = []
    tabs = st.tabs(["Attack forecast", "Pre-viral radar", "Opponent targets", "Counter-proof", "Rally impact", "Money to votes", "Grievance calendar", "Event log"])
    with tabs[0]:
        _attack(ctx, seat, leader, party, snap)
    with tabs[1]:
        _radar(ctx, seat, leader, party, snap)
    with tabs[2]:
        _targets(ctx, seat, party, snap)
    with tabs[3]:
        _counter(ctx, seat, leader, party, snap)
    with tabs[4]:
        _rally_tab(ctx, seat, leader, party, snap)
    with tabs[5]:
        _money(ctx, seat, party, snap)
    with tabs[6]:
        _calendar(snap)
    with tabs[7]:
        _log(ctx)
    if snap:
        st.session_state["warroom_snapshot"] = {"lines": snap}
    fact_card(
        "Built from public news and video searches, Google Trends, and the campaign's own records. Language-model steps may only cite the evidence "
        "pack, and defences are only what is on record.",
        SOURCE_METADATA["war_room"]["name"], SOURCE_METADATA["war_room"]["type"], "medium",
    )
    ctx.logger.log_analysis("war_room", ["war_room"], f"war room for {leader} ({party}) in {seat}")
