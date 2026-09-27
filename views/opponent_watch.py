"""Opponent Watch: one rival at a time — what they're saying, spending and getting, and where they're weak."""

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import date

import pandas as pd
import streamlit as st

import charts
import health
import live_pulse
import opponent_watch as ow
from components import empty_state, fact_card, section
from config import PARTIES, PARTY_COLORS, PARTY_LABELS, SOURCE_METADATA, is_valid_api_key, normalize_party

TITLE = "Opponent Watch"

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
YEARS = (2014, 2018, 2023)
HOME_SEAT = "Jubilee Hills"
BOOTHS_CSV = os.path.join(ROOT, "data", "jubilee_hills_2023_booths.csv")
OTHER = "Someone else…"
TONE_HEADLINES = 40


@st.cache_data(show_spinner=False)
def _years():
    return {y: pd.read_csv(os.path.join(ROOT, "data", f"telangana_{y}_candidates.csv")) for y in YEARS}


@st.cache_data(show_spinner=False)
def _booths():
    return pd.read_csv(BOOTHS_CSV)


@st.cache_data(ttl=12 * 3600, show_spinner=False)
def _google_ads():
    return ow.fetch_google_ads()


@st.cache_data(ttl=1800, show_spinner=False)
def _news(name, name_te, place):
    return ow.fetch_news(name, name_te or None, place)


@st.cache_data(ttl=1800, show_spinner=False)
def _tone(name, heads, api_key):
    return live_pulse.classify_headline_mood(name, list(heads), api_key)


@st.cache_data(ttl=3600, show_spinner=False)
def _meta(token, search, page_ids, days):
    return ow.fetch_meta_ads(token, search=search or None, page_ids=list(page_ids) or None, days=days)


@st.cache_data(ttl=3600, show_spinner=False)
def _channel(text, key):
    found = ow.resolve_channel(text, key)
    if not found["ok"]:
        return found, {"videos": []}
    return found, ow.channel_uploads(found["channel"]["uploads"], key)


@st.cache_data(ttl=3600, show_spinner=False)
def _find_channels(query, key):
    return ow.search_channels(query, key)


@st.cache_data(ttl=3600, show_spinner=False)
def _mentions(query, key):
    return live_pulse.fetch_youtube_mentions(query, key, max_results=10, days=30)


def _rivals(ctx, seat, us):
    """(name, party) of the latest contest in the seat, our own party left out. For the home seat the
    2025 by-election in Historical_Results is newer than the 2023 file."""
    if seat == HOME_SEAT:
        try:
            h = ctx.sheets["historical_results"].copy()
            h["Year"] = pd.to_numeric(h["Year"], errors="coerce")
            latest = h[h["Year"] == h["Year"].max()]
            found = [(r["Candidate"], normalize_party(r["Party"]) or r["Party"]) for _, r in latest.iterrows()]
            if found:
                return [f for f in found if f[1] != us]
        except Exception:
            pass
    c = _years()[2023]
    rows = c[(c["seat"] == seat) & (c["party"] != "NOTA")].sort_values("rank").head(5)
    return [(r["candidate"], r["party"]) for _, r in rows.iterrows() if r["party"] != us]


def _money(rs):
    if rs is None:
        return "–"
    if rs == 0:
        return "Rs 0"
    return f"Rs {rs / 1e7:,.2f} cr" if rs >= 1e7 else f"Rs {rs / 1e5:,.1f} lakh"


# ----------------------------------------------------------------------
# tabs
# ----------------------------------------------------------------------
def _news_tab(w, api_key, snap):
    news = w["news"]
    if not news["ok"]:
        st.warning(f"News search failed: {news['error']}.")
        return
    arts = news["articles"]
    if arts:
        st.caption(f"{len(arts)} stories in the last {news['days']} days · {', '.join(news['languages'])} · searched for "
                   f"{' or '.join(ow.news_names(w['name']))}, together with {w['place'] or 'Telangana'}")
    else:
        empty_state("No news stories name this rival in the last 30 days. For a low-profile candidate that is itself useful: they are not getting coverage.")
        return
    labels = [""] * len(arts)
    if is_valid_api_key(api_key):
        tone = _tone(w["name"], tuple(a["title"] for a in arts[:TONE_HEADLINES]), api_key)
        if tone.get("ok"):
            labels = tone["labels"] + [""] * (len(arts) - len(tone["labels"]))
            left, right = st.columns([1, 1.2])
            left.plotly_chart(charts.headline_tone(tone["counts"]), width="stretch")
            with right:
                st.markdown("**What the coverage keeps coming back to**")
                for t in tone["themes"] or ["No theme appears in two or more headlines."]:
                    st.markdown(f"- {t}")
                if tone["unrelated"]:
                    st.caption(f"{tone['unrelated']} headlines were about someone or something else and are not counted.")
            related = sum(tone["counts"].values())
            if related:
                snap.append(f"News, last {news['days']} days: {related} headlines about them; {tone['counts'].get('negative', 0)} negative, "
                            f"{tone['counts'].get('positive', 0)} positive. Themes: {'; '.join(tone['themes']) or 'none'}")
        else:
            st.caption(f"Headline tone not read: {tone.get('error')}.")
    df = pd.DataFrame({
        "Date": [a["published"].strftime("%d %b") if a["published"] else "" for a in arts],
        "Tone": [lab if lab != "unrelated" else "not about them" for lab in labels],
        "Headline": [a["title"] for a in arts], "Outlet": [a["source"] for a in arts], "Link": [a["url"] for a in arts],
    })
    st.dataframe(df, hide_index=True, width="stretch", column_config={"Link": st.column_config.LinkColumn(display_text="open")})


def _youtube_tab(w, yt_key, snap):
    if not (yt_key and str(yt_key).isascii()):
        st.info("YouTube is off until YOUTUBE_API_KEY is in the secrets.")
        return
    st.markdown("**Their own channel**")
    ckey = f"ow_channel_{w['name']}"
    c1, c2 = st.columns([3, 1])
    text = c1.text_input("Channel link, @handle or ID", key=ckey, placeholder="e.g. https://www.youtube.com/@bharatrashtrasamithiparty")
    if c2.button("Find their channel", key=f"ow_find_{w['name']}"):
        st.session_state[f"ow_found_{w['name']}"] = _find_channels(ow.news_names(w["name"])[-1], yt_key)
    found = st.session_state.get(f"ow_found_{w['name']}")
    if found:
        if not found["ok"] or not found["channels"]:
            st.caption(f"No channels found{': ' + found['error'] if found['error'] else ''}.")
        else:
            st.caption("Copycat and fan channels use the same names. The official one usually has by far the most subscribers. Paste its link above.")
            st.dataframe(pd.DataFrame([{"Channel": c["title"], "Handle": c["handle"], "Subscribers": c["subscribers"],
                                        "Link": f"https://www.youtube.com/channel/{c['id']}"} for c in found["channels"]]),
                         hide_index=True, width="stretch", column_config={"Link": st.column_config.LinkColumn(display_text="open")})
    if text.strip():
        got, uploads = _channel(text.strip(), yt_key)
        if not got["ok"]:
            st.warning(got["error"])
        else:
            ch = got["channel"]
            s = ow.upload_summary(uploads["videos"])
            m = st.columns(4)
            m[0].metric("Subscribers", f"{ch['subscribers']:,}" if ch["subscribers"] is not None else "hidden")
            partial = s.get("partial_30") or s.get("partial_60")
            m[1].metric("Uploads, last 30 days", f"{s.get('uploads_30', 0)}{'+' if s.get('partial_30') else ''}",
                        delta=None if not s or partial else s["uploads_30"] - s["uploads_prev_30"])
            m[2].metric("Typical views, last 30 days", f"{s['median_views_30']:,}" if s.get("median_views_30") is not None else "–",
                        delta=(s["median_views_30"] - s["median_views_prev_30"]) if s.get("median_views_30") is not None and s.get("median_views_prev_30") is not None else None)
            m[3].metric("Channel total views", f"{ch['views']:,}")
            st.caption(f"{ch['title']} · on YouTube since {ch['created']} · deltas compare with the 30 days before. Typical = median, so one viral video doesn't skew it."
                       + (f" Only the latest {len(uploads['videos'])} videos were read, back to {s['oldest_read']}, so counts marked + are at least that many." if s and partial else ""))
            if s:
                snap.append(f"YouTube channel {ch['title']}: {s['uploads_30']} uploads in the last 30 days (previous 30: {s['uploads_prev_30']}), "
                            f"median views {s.get('median_views_30')}; top video: {s['top'][0]['Title']} ({s['top'][0]['Views']:,} views)")
                st.dataframe(pd.DataFrame(uploads["videos"]), hide_index=True, width="stretch",
                             column_config={"Link": st.column_config.LinkColumn(display_text="watch")})
                st.caption("To see what viewers say under any of these, paste its link into Social Voices.")
    st.markdown("**Other channels talking about them (last 30 days)**")
    men = _mentions(f'"{w["name"]}"', yt_key)
    if not men["ok"]:
        st.caption(f"Search failed: {men['error']}.")
    elif not men["videos"]:
        empty_state("No news or politics videos name them in the last 30 days.")
    else:
        st.dataframe(pd.DataFrame(men["videos"]).rename(columns=str.title), hide_index=True, width="stretch",
                     column_config={"Url": st.column_config.LinkColumn("Link", display_text="watch")})


def _google_ads_block(w, snap):
    st.markdown("**Google and YouTube ads** (Google's political ads transparency report)")
    g = _google_ads()
    if not g["ok"]:
        st.warning(f"Google's file could not be read: {g['error']}.")
        return
    adv = g["advertisers"]
    terms = ow.PARTY_AD_NAMES.get(w["party"], []) + [w["name"]]
    matched = ow.match_advertisers(adv, terms)
    extra = st.text_input("Also look for advertisers named (comma-separated)", key=f"ow_gextra_{w['name']}", placeholder="e.g. a PR agency or a supporter page")
    if extra.strip():
        matched = pd.concat([matched, ow.match_advertisers(adv, [t.strip() for t in extra.split(",")])]).drop_duplicates("Advertiser_ID")
    if matched.empty:
        empty_state(f"No election advertiser on Google matches {PARTY_LABELS.get(w['party'], w['party'])} or {w['name']}. They have not run Google election ads, or ran them under another name.")
        return
    labels = {r["Advertiser_ID"]: f"{r['Advertiser']} · {_money(r['Spend_INR'])} all-time" for _, r in matched.iterrows()}
    picked = st.multiselect("Advertisers counted", list(labels), default=list(labels), format_func=labels.get, key=f"ow_gpick_{w['name']}")
    if not picked:
        return
    s = ow.spend_summary(g["weekly"], picked)
    total = int(matched[matched["Advertiser_ID"].isin(picked)]["Spend_INR"].sum())
    m = st.columns(4)
    m[0].metric("All-time", _money(total))
    m[1].metric("Last 30 days", _money(s["last_30"]))
    m[2].metric("Last 90 days", _money(s["last_90"]))
    m[3].metric("Biggest week", _money(s["peak"]), help=f"Week of {s['peak_week']}" if s["peak_week"] else None)
    if not s["weeks"].empty:
        st.plotly_chart(charts.weekly_spend(s["weeks"], "Google election-ad spend per week", PARTY_COLORS.get(w["party"], PARTY_COLORS["Others"])), width="stretch")
        st.caption(f"Last spending week on file: {s['last_seen']}. Biggest week: {s['peak_week']}. Google's file updated {g['updated']}.")
        snap.append(f"Google election ads ({', '.join(labels[p].split(' · ')[0] for p in picked)}): all-time {_money(total)}, "
                    f"last 90 days {_money(s['last_90'])}, biggest week {_money(s['peak'])} (week of {s['peak_week']}), last active week {s['last_seen']}")
    st.caption(
        "This is spend on ads Google counts as election ads in India, for the whole country. Google does not publish a state split "
        "for India in this file, so national parties' totals include every other state."
    )


def _meta_block(w, token, snap):
    st.markdown("**Facebook and Instagram ads** (Meta Ad Library)")
    if not (token and str(token).isascii()):
        st.info(
            "Not connected. Meta publishes every political ad shown in India, with spend, reach by state and the ad text, but its API needs a token "
            "from a person who has confirmed their identity with Meta. One-time setup: (1) confirm your ID at facebook.com/ID; (2) create an app at "
            "developers.facebook.com; (3) copy a user access token from the Graph API Explorer; (4) add it to the app's secrets as META_AD_LIBRARY_TOKEN. "
            "Until then, the same ads can be browsed by hand at facebook.com/ads/library."
        )
        return
    c1, c2, c3 = st.columns([2, 2, 1])
    search = c1.text_input("Search the ad text and page names for", value=w["name"], key=f"ow_msearch_{w['name']}")
    pages = c2.text_input("Or exact Facebook page IDs (comma-separated)", key=f"ow_mpages_{w['name']}",
                          help="The page ID is under 'Page transparency' on the page, or in the Ad Library URL. Exact, unlike word search.")
    days = c3.selectbox("Period", [30, 90, 365], index=1, format_func=lambda d: f"{d} days", key=f"ow_mdays_{w['name']}")
    ids = tuple(p.strip() for p in pages.split(",") if p.strip())
    res = _meta(token, search.strip(), ids, days)
    if not res["ok"]:
        st.warning(f"Meta Ad Library: {res['error']}")
        return
    if res["error"]:
        st.caption(f"Stopped early: {res['error']}")
    if not res["ads"]:
        empty_state("No political ads in India match this in the period.")
        return
    by_page, rows = ow.meta_summary(res["ads"])
    lo = sum(p["Spend min"] for p in by_page)
    hi = sum(p["Spend max"] for p in by_page)
    tlo = sum(p["In region min"] for p in by_page)
    thi = sum(p["In region max"] for p in by_page)
    m = st.columns(3)
    m[0].metric("Ads", len(rows))
    m[1].metric("Spend, all states", f"{_money(lo)} – {_money(hi)}")
    m[2].metric("Spend shown in Telangana", f"{_money(tlo)} – {_money(thi)}")
    snap.append(f"Meta ads matching '{search or ', '.join(ids)}', last {days} days: {len(rows)} ads, {_money(lo)}–{_money(hi)} total, "
                f"{_money(tlo)}–{_money(thi)} shown in Telangana; biggest page: {by_page[0]['Page']}")
    t1, t2, t3 = st.tabs(["By page", "The ads", "By state"])
    t1.dataframe(pd.DataFrame(by_page), hide_index=True, width="stretch")
    t2.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch", column_config={"Link": st.column_config.LinkColumn(display_text="see ad")})
    t3.dataframe(pd.DataFrame(ow.meta_regions(res["ads"])), hide_index=True, width="stretch")
    st.caption("Meta gives spend and reach as ranges, so totals are ranges. Word search also finds ads that only mention the name; use page IDs for exact figures.")


def _record_tab(w, us, snap):
    years = _years()
    rec = ow.electoral_record(w["name"], years)
    st.markdown(f"**{w['name']}'s election record, 2014–2023** (Election Commission results)")
    if rec.empty:
        empty_state("This name is not among the 2014, 2018 or 2023 assembly candidates. Try the spelling used on the ballot.")
    else:
        st.dataframe(rec, hide_index=True, width="stretch")
        st.caption("Matched on name words, so a same-named independent can appear too. Parties sometimes field one to split a rival's vote. Check the party column.")
        snap.append("Election record: " + "; ".join(f"{r['Year']} {r['Seat']} ({r['Party']}) rank {r['Rank']}, {r['Vote %']}%" for _, r in rec.iterrows()))
    if w["seat"]:
        trend = pd.concat([ow.party_trend(years, w["seat"], p).assign(Party=p) for p in {w["party"], us}], ignore_index=True)
        if not trend.empty:
            st.markdown(f"**{w['seat']}: {w['party']} against {us}, vote share by year**")
            st.dataframe(trend.pivot(index="Year", columns="Party", values="Vote %").reset_index(), hide_index=True, width="stretch")

    if w["seat"] == HOME_SEAT and w["party"] in _booths().columns and us in _booths().columns:
        strong, weak, close, n = ow.booth_battleground(_booths(), w["party"], us)
        st.markdown(f"**Booth by booth, 2023: {w['party']} against {us}**")
        m = st.columns(4)
        m[0].metric(f"{w['party']} led", f"{n['rival_leads']} of {n['booths']}")
        m[1].metric(f"{us} led", n["we_lead"])
        m[2].metric("Close booths they led", n["close"], help="Rival ahead by 5 points or less")
        m[3].metric("Votes to flip all of those", f"{n['votes_to_flip_close']:,}")
        snap.append(f"2023 booths, {w['party']} vs {us}: {w['party']} led {n['rival_leads']} of {n['booths']}, {us} led {n['we_lead']}; "
                    f"{n['close']} booths {w['party']} led by 5 points or less, {n['votes_to_flip_close']} votes would flip them all")
        if not close.empty:
            snap.append("Closest booths the rival led (booth: votes to flip): " + ", ".join(f"{r['Booth']}: {r['Votes to flip']}" for _, r in close.head(15).iterrows()))
        t1, t2, t3 = st.tabs(["Close: winnable booths", "Their strongholds", "Where they're weakest"])
        t1.dataframe(close, hide_index=True, width="stretch")
        t1.caption("Votes to flip = voters who'd need to switch from them to you for you to lead the booth. The cheapest wins in the seat.")
        t2.dataframe(strong, hide_index=True, width="stretch")
        t3.dataframe(weak, hide_index=True, width="stretch")
        st.caption("Booth figures are the 2023 general election (Form 20, reconciled to ECI totals). Booth lines may have shifted since the 2025 by-election.")


# ----------------------------------------------------------------------
def _headline(w, us):
    """Plain-language takeaways from what was just read. Deterministic, from the numbers on this page."""
    out = []
    g = _google_ads()
    if g["ok"]:
        matched = ow.match_advertisers(g["advertisers"], ow.PARTY_AD_NAMES.get(w["party"], []) + [w["name"]])
        s = ow.spend_summary(g["weekly"], matched["Advertiser_ID"])
        if s["last_seen"]:
            if s["last_30"]:
                out.append(f"{w['party']} is **spending on Google election ads now**: {_money(s['last_30'])} in the last 30 days (national account, all states).")
            else:
                out.append(f"{w['party']}'s national account has **not run Google election ads since the week of {s['last_seen']}**. A restart is an early signal of a campaign push.")
    if w["seat"] == HOME_SEAT and w["party"] in _booths().columns and us in _booths().columns:
        _, _, _, n = ow.booth_battleground(_booths(), w["party"], us)
        out.append(f"In 2023 {w['party']} led **{n['close']} booths by 5 points or less**. About **{n['votes_to_flip_close']:,} voters** switching would flip all of them.")
    return out


def render(ctx, sidebar):
    section(
        "Opponent watch",
        "Pick a rival. See what the press is saying about them, what they post and spend, and where they can be beaten. Everything here comes from "
        "official public sources: news feeds, YouTube, Google's and Meta's political ad libraries, and Election Commission results.",
    )
    seats = sorted(_years()[2023]["seat"].unique())
    c1, c2, c3 = st.columns([1.2, 1, 1.6])
    seat = c1.selectbox("Seat", seats, index=seats.index(HOME_SEAT) if HOME_SEAT in seats else 0, key="ow_seat")
    us = c2.selectbox("Your party", PARTIES, format_func=lambda p: PARTY_LABELS.get(p, p), key="ow_us")
    rivals = _rivals(ctx, seat, us)
    labels = [f"{n} ({p})" for n, p in rivals] + [OTHER]
    pick = c3.selectbox("Rival", labels, key=f"ow_rival_{seat}_{us}")
    if pick == OTHER:
        d1, d2 = st.columns([2, 1])
        name = d1.text_input("Rival's name, as used in the news", key="ow_other_name")
        party = d2.selectbox("Their party", PARTIES + ["Other"], key="ow_other_party")
        if not name.strip():
            empty_state("Type a name to start.")
            return
        rival = (name.strip(), party)
    else:
        rival = rivals[labels.index(pick)]
    with st.expander("Search options"):
        name_te = st.text_input("Telugu spelling of the name (adds Telugu newspapers)", key=f"ow_te_{rival[0]}", placeholder="e.g. నవీన్ యాదవ్")
        place = st.text_input("News must also mention", value=seat, key=f"ow_place_{rival[0]}",
                              help="Stops namesakes and unrelated stories. Clear it to use 'Telangana' instead, e.g. for a statewide leader.")
    w = {"name": rival[0], "party": rival[1], "seat": seat, "place": place.strip()}

    yt_key = health.secret("YOUTUBE_API_KEY")
    meta_token = health.secret("META_AD_LIBRARY_TOKEN")
    with st.spinner(f"Reading the news, ad libraries and results for {w['name']}"):
        with ThreadPoolExecutor(max_workers=2) as pool:
            news_job = pool.submit(_news, w["name"], name_te.strip(), w["place"] or None)
            ads_job = pool.submit(_google_ads)
            w["news"], _ = news_job.result(), ads_job.result()

    snap = []
    for line in _headline(w, us):
        st.markdown(f"- {line}")

    tabs = st.tabs(["News", "YouTube", "Ads and spending", "Record and booths"])
    with tabs[0]:
        _news_tab(w, ctx.api_key, snap)
    with tabs[1]:
        _youtube_tab(w, yt_key, snap)
    with tabs[2]:
        _google_ads_block(w, snap)
        st.divider()
        _meta_block(w, meta_token, snap)
    with tabs[3]:
        _record_tab(w, us, snap)

    st.session_state["ow_snapshot"] = {"when": date.today().isoformat(), "rival": w["name"], "party": w["party"], "lines": snap}
    st.caption("Ask AI can now use what this page just read. Ask it things like 'what is our rival focusing on this month?'")
    fact_card(
        "News tone is read from headlines by a language model, and ad spend is what the platforms self-report, often as ranges. "
        "Treat both as signals to check, not as measurements of voters.",
        SOURCE_METADATA["opponent_watch"]["name"],
        SOURCE_METADATA["opponent_watch"]["type"],
        "medium",
    )
    ctx.logger.log_analysis("opponent_watch", ["opponent_watch"], f"watched {w['name']} ({w['party']}) in {seat}")
