"""Proof: what satellites show changed in a seat, by sector, with the limits said plainly."""

import os

import numpy as np
import pandas as pd
import streamlit as st

import charts
import geo
import mla_history
import orbit
import proof
from components import empty_state, fact_card, section
from config import SOURCE_METADATA

TITLE = "Proof"

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEAT_INDICATORS = os.path.join(ROOT, "data", "seat_indicators.csv")
HOME = "Jubilee Hills"
DAY = 24 * 3600


# ----------------------------------------------------------------------
# cached readers (satellite reads take seconds to a minute; results change slowly)
# ----------------------------------------------------------------------
@st.cache_data(ttl=30 * DAY, show_spinner=False, persist="disk")
def _landcover(seat, wards, area_id):
    return proof.landcover_series(geo.area(seat, wards))


@st.cache_data(ttl=7 * DAY, show_spinner=False, persist="disk")
def _season(seat, wards, area_id, years, which):
    return proof.season_series(geo.area(seat, wards), list(years), which)


@st.cache_data(ttl=30 * DAY, show_spinner=False, persist="disk")
def _picture(seat, wards, area_id, year):
    return proof.picture(geo.area(seat, wards), year)


@st.cache_data(ttl=30 * DAY, show_spinner=False, persist="disk")
def _new_built(seat, wards, area_id, y0, y1):
    return proof.new_built(geo.area(seat, wards), y0, y1)


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def _crop_loss(seat, wards, area_id):
    return proof.crop_loss(geo.area(seat, wards))


@st.cache_data(ttl=30 * DAY, show_spinner=False, persist="disk")
def _heat(seat, wards, area_id, year):
    return proof.heat(geo.area(seat, wards), year)


@st.cache_data(ttl=7 * DAY, show_spinner=False, persist="disk")
def _lakes(seat, wards, area_id):
    return proof.lake_watch(geo.area(seat, wards))


@st.cache_data(ttl=30 * DAY, show_spinner=False, persist="disk")
def _work(lat, lon, year, radius):
    return proof.work_check(lat, lon, year, radius)


@st.cache_data(ttl=30 * DAY, show_spinner=False, persist="disk")
def _ward_growth(seat, area_id):
    return proof.ward_growth(seat)


def _terms(seat, ctx):
    """Who was MLA in which years, for labelling the time machine. The home seat's 2025 by-election winner
    comes from Historical_Results, since the statewide files stop at 2023."""
    try:
        t = mla_history.table().set_index("seat").loc[seat]
    except Exception:
        return {}
    out = {}
    for y in range(2014, orbit.this_year() + 1):
        term = 2014 if y < 2019 else (2018 if y < 2024 else 2023)
        out[y] = f"{t[f'mla_{term}']} ({t[f'party_{term}']})"
    if seat == HOME:
        try:
            h = ctx.sheets["historical_results"].copy()
            h["Year"] = pd.to_numeric(h["Year"], errors="coerce")
            latest = h[h["Year"] == h["Year"].max()].sort_values("Votes", ascending=False).iloc[0]
            if int(latest["Year"]) > 2023:
                for y in range(int(latest["Year"]) + 1, orbit.this_year() + 1):
                    out[y] = f"{latest['Candidate']} ({latest['Party']}, by-election {int(latest['Year'])})"
        except Exception:
            pass
    return out


def _pct(a, b):
    if not a:
        return "none before" if b else "none"
    return f"{(b - a) / a * 100:+.0f}%"


# ----------------------------------------------------------------------
# tabs
# ----------------------------------------------------------------------
def _sectors(seat, wards, snap):
    st.markdown("**What satellites can settle, sector by sector, and what they can't**")
    st.dataframe(pd.DataFrame(proof.SECTORS, columns=["Sector", "Satellites show", "Official records that fill the gap", "Neither can prove"]),
                 hide_index=True, width="stretch")
    c1, c2 = st.columns(2)
    run_lc = c1.button("Measure land use 2017–2023", key="pf_lc")
    run_dry = c2.button("Measure irrigation and tanks (dry season, 2019–now)", key="pf_dry")
    if run_lc or st.session_state.get("pf_lc_done") == seat:
        with st.spinner("Reading seven years of land-cover maps (about 20–40 seconds the first time)"):
            df, errs = _landcover(seat, wards, st.session_state["pf_area_id"])
        st.session_state["pf_lc_done"] = seat
        if df.empty:
            st.warning("No land-cover reading: " + "; ".join(errs))
        else:
            first, last = df.iloc[0], df.iloc[-1]
            m = st.columns(4)
            for col, name in zip(m, ("Built area", "Trees", "Crops", "Water")):
                col.metric(f"{name}, {int(last['Year'])}", f"{last[name]:,.0f} ha", _pct(first[name], last[name]) + f" since {int(first['Year'])}")
            st.plotly_chart(charts.series_lines(df, "Year", ["Built area", "Trees", "Crops", "Water"], "Land use by year (hectares)", " ha"), width="stretch")
            snap.append(f"Land cover {int(first['Year'])}→{int(last['Year'])}: built {first['Built area']:.0f}→{last['Built area']:.0f} ha, trees {first['Trees']:.0f}→{last['Trees']:.0f} ha, "
                        f"crops {first['Crops']:.0f}→{last['Crops']:.0f} ha, water {first['Water']:.0f}→{last['Water']:.0f} ha")
            st.caption("Esri / Impact Observatory annual land cover, 10 m. Its own accuracy is about 75–85%, so read small year-to-year wiggles as noise and trust the direction over several years.")
    if run_dry or st.session_state.get("pf_dry_done") == seat:
        years = tuple(range(2019, orbit.this_year() + 1))
        with st.spinner("Reading Sentinel-2 for every dry season since 2019 (about a minute the first time)"):
            df, errs = _season(seat, wards, st.session_state["pf_area_id"], years, "dry")
        st.session_state["pf_dry_done"] = seat
        if df.empty:
            st.warning("No dry-season reading: " + "; ".join(errs))
        else:
            first, last = df.iloc[0], df.iloc[-1]
            m = st.columns(2)
            m[0].metric(f"Green in the dry season, {int(last['Year'])}", f"{last['Green (ha)']:,.0f} ha", _pct(first["Green (ha)"], last["Green (ha)"]) + f" since {int(first['Year'])}")
            m[1].metric(f"Tanks and reservoirs holding water, {int(last['Year'])}", f"{last['Open water (ha)']:,.0f} ha", _pct(first["Open water (ha)"], last["Open water (ha)"]) + f" since {int(first['Year'])}")
            st.plotly_chart(charts.series_lines(df, "Year", ["Green (ha)", "Open water (ha)"], "February–March each year (hectares)", " ha"), width="stretch")
            st.dataframe(df, hide_index=True, width="stretch")
            snap.append(f"Dry season (Feb–Mar) {int(first['Year'])}→{int(last['Year'])}: green {first['Green (ha)']:.0f}→{last['Green (ha)']:.0f} ha, "
                        f"open water {first['Open water (ha)']:.0f}→{last['Open water (ha)']:.0f} ha")
            st.caption(
                "Green in February–March outside forests is mostly irrigated rabi crops, so it is the best free measure of irrigation reaching fields. "
                "Water then is what tanks and reservoirs still hold before summer. A year with more rain gives both a lift, so compare against rainfall "
                "before crediting a scheme."
            )


def _time_machine(seat, wards, snap, ctx):
    terms = _terms(seat, ctx)
    years = list(range(2017, orbit.this_year() + 1))
    year = st.select_slider("Year (February–March, clearest days)", years, value=years[-1], key="pf_tm_year")
    with st.spinner(f"Assembling the {year} picture"):
        pic = _picture(seat, wards, st.session_state["pf_area_id"], year)
    if not pic["ok"]:
        st.warning(pic["error"])
    else:
        st.image(np.clip(pic["rgb"], 0, 1), caption=f"{seat}, {year} · scenes {', '.join(pic['dates'])} · MLA then: {terms.get(year, '?')}", width="stretch")
    st.markdown("**What was built between two years** (red = land that became built-up)")
    c1, c2 = st.columns(2)
    y0 = c1.selectbox("From", orbit.LULC_YEARS[:-1], index=0, key="pf_tm_y0")
    y1 = c2.selectbox("To", [y for y in orbit.LULC_YEARS if y > y0], index=len([y for y in orbit.LULC_YEARS if y > y0]) - 1, key="pf_tm_y1")
    if st.button("Show new construction", key="pf_tm_go"):
        with st.spinner("Comparing land-cover maps"):
            nb = _new_built(seat, wards, st.session_state["pf_area_id"], y0, y1)
        if not nb["ok"]:
            st.warning(nb["error"])
        else:
            m = st.columns(4)
            m[0].metric("Newly built", f"{nb['new_built_ha']:,.0f} ha")
            m[1].metric("From farmland", f"{nb['crops_lost_ha']:,.0f} ha")
            m[2].metric("From trees", f"{nb['trees_lost_ha']:,.0f} ha")
            m[3].metric("From water", f"{nb['water_lost_ha']:,.0f} ha")
            st.image(np.clip(nb["rgb"], 0, 1), caption=f"Red: built-up in {y1} but not in {y0}", width="stretch")
            snap.append(f"New construction {y0}→{y1}: {nb['new_built_ha']} ha, of which {nb['water_lost_ha']} ha was water and {nb['trees_lost_ha']} ha trees")
    st.caption("MLA by year: " + " · ".join(f"{y}: {v}" for y, v in terms.items() if y in (2015, 2019, 2024)) if terms else "")


def _crop_tab(seat, wards, snap):
    st.caption("Compares the two latest clear satellite passes over cropland. In the monsoon, clouds hide much of the seat; the page says how much it could compare.")
    if not st.button("Check for crop damage now", key="pf_crop_go"):
        return
    with st.spinner("Reading the two latest clear passes (about 15 seconds)"):
        r = _crop_loss(seat, wards, st.session_state["pf_area_id"])
    if not r["ok"]:
        st.warning(r["error"])
        return
    m = st.columns(4)
    m[0].metric("Passes compared", f"{r['before']} → {r['after']}")
    m[1].metric("Cropland seen clearly", f"{r['compared_acres']:,} acres", help=f"of {r['crop_acres']:,} acres of cropland")
    m[2].metric("Damaged crop", f"{r['damaged_acres']:,} acres")
    m[3].metric("Hotspots", len(r["cells"]))
    if r["cells"]:
        st.dataframe(pd.DataFrame(r["cells"]), hide_index=True, width="stretch")
        st.map(pd.DataFrame(r["cells"]), latitude="lat", longitude="lon", size=300)
        snap.append(f"Crop damage {r['before']}→{r['after']}: {r['damaged_acres']} acres, hotspots near {', '.join(c['Near'] for c in r['cells'][:5])}")
    else:
        empty_state("No concentrated crop damage between these passes. Hotspots are 1 km cells where at least 30% of the crop's greenness fell sharply.")
    st.caption("Damage = plant greenness (NDVI) falling by more than 0.15 on cropland that was green before. Harvest also causes a fall, so check the season before calling it damage.")


def _heat_tab(seat, wards, snap):
    year = st.selectbox("Summer of", list(range(orbit.this_year(), 2017, -1)), key="pf_heat_year")
    if not st.button("Map the heat", key="pf_heat_go"):
        return
    with st.spinner("Reading the clearest April–May Landsat day"):
        h = _heat(seat, wards, st.session_state["pf_area_id"], year)
    if not h["ok"]:
        st.warning(h["error"])
        return
    m = st.columns(3)
    m[0].metric("Average ground temperature", f"{h['mean']} °C")
    m[1].metric("Coolest 5%", f"{h['p5']} °C")
    m[2].metric("Hottest 5%", f"{h['p95']} °C")
    st.plotly_chart(charts.heat_grid(h["celsius"], h["inside"], f"Ground temperature on {h['date']}"), width="stretch")
    if h["wards"]:
        st.markdown("**By ward**")
        st.dataframe(pd.DataFrame(h["wards"]), hide_index=True, width="stretch")
    if h["hottest"]:
        st.markdown("**Hottest places** (where to put shade, water points and trees first)")
        st.dataframe(pd.DataFrame(h["hottest"]), hide_index=True, width="stretch")
    snap.append(f"Heat on {h['date']}: average {h['mean']}°C, hottest 5% {h['p95']}°C" + (f"; hottest ward {h['wards'][0]['Ward']} ({h['wards'][0]['Average °C']}°C)" if h["wards"] else ""))
    st.caption("Ground surface temperature from Landsat's thermal band on one clear afternoon, not air temperature: roofs and bare ground read hotter than the air. The ranking between places is what matters.")


def _lakes_tab(seat, wards, snap):
    st.caption("Each named lake's historical water extent (how often it held water, 1984–2020) against what holds water now and what is now built on it.")
    if not st.button("Check the lakes", key="pf_lake_go"):
        return
    with st.spinner("Reading lake outlines and three satellite layers (about 30 seconds)"):
        r = _lakes(seat, wards, st.session_state["pf_area_id"])
    if not r["ok"]:
        st.warning(r["error"])
        return
    if not r["lakes"]:
        empty_state("No named lake or tank on OpenStreetMap inside this area.")
        return
    df = pd.DataFrame(r["lakes"])
    st.dataframe(df, hide_index=True, width="stretch")
    built_col = [c for c in df.columns if c.startswith("Built on it")][0]
    worst = df.iloc[0]
    if worst[built_col] > 0:
        snap.append(f"Lakes: most built-over is {worst['Lake']} with {worst[built_col]} ha of its historical water area now built area")
    st.caption(
        "Historical water = the pixels that held water at least a quarter of the time in 1984–2020 (JRC Global Surface Water). "
        "Built on it = those pixels now classed as built area. 0% water now can mean dry, or covered by weed or hyacinth: check the picture before "
        "calling it encroachment. The official full-tank-level boundaries (HYDRAA / irrigation department) are the legal reference."
    )


def _ghost_tab(snap):
    st.caption("Upload the works list (MGNREGA, MPLADS, MLA fund, or the rival's claims). Each work is checked for visible change on the ground around its location.")
    up = st.file_uploader("Works CSV with columns: work, lat, lon, year_completed", type=["csv"], key="pf_ghost_up")
    if not up:
        st.info("MGNREGA works with geotags are on Bhuvan's NREGA portal; MPLADS works on eSAKSHI; MLA fund works come by RTI. Keep one row per work.")
        return
    df = pd.read_csv(up)
    need = {"work", "lat", "lon", "year_completed"}
    if not need <= set(map(str.lower, df.columns)):
        st.warning(f"The file needs columns {', '.join(sorted(need))}.")
        return
    df.columns = [c.lower() for c in df.columns]
    radius = st.slider("Look within (metres)", 50, 500, 120, key="pf_ghost_r")
    rows = []
    prog = st.progress(0.0)
    for i, r in df.head(40).iterrows():
        got = _work(float(r["lat"]), float(r["lon"]), int(r["year_completed"]), radius)
        rows.append({"Work": r["work"], "Year": int(r["year_completed"]), "Verdict": got.get("verdict", got.get("error")), "Change score": got.get("score"),
                     "_got": got})
        prog.progress((i + 1) / min(40, len(df)))
    table = pd.DataFrame([{k: v for k, v in r.items() if k != "_got"} for r in rows])
    st.dataframe(table, hide_index=True, width="stretch")
    none = table[table["Verdict"] == "No visible change"]
    snap.append(f"Works check: {len(none)} of {len(table)} works show no visible change on the ground")
    pick = st.selectbox("See before and after", [r["Work"] for r in rows], key="pf_ghost_pick")
    got = next(r["_got"] for r in rows if r["Work"] == pick)
    if got.get("ok"):
        c1, c2 = st.columns(2)
        c1.image(np.clip(got["before"], 0, 1), caption=f"Before · {', '.join(got['before_dates'])}", width="stretch")
        c2.image(np.clip(got["after"], 0, 1), caption=f"After · {', '.join(got['after_dates'])}", width="stretch")
    st.caption("No visible change is a reason to go and look, not proof of a fake work: drains, pipes, resurfacing and anything under about 10 m wide cannot be seen at this resolution.")


def _reach_tab(snap):
    st.caption("Beneficiaries per area against households per area. The places far below the typical coverage are where eligible families are most likely missed: hold an enrolment camp there.")
    up = st.file_uploader("CSV with columns: area, households, beneficiaries (one scheme per file)", type=["csv"], key="pf_reach_up")
    if not up:
        st.info("Households: Census 2011 ward and village tables (Hyderabad's are on data.opencity.in), grown by each ward's built-area growth on the Roll vs Roof tab. "
                "Beneficiaries: scheme dashboards (PM-KISAN, ration cards per shop), or an RTI reply.")
        return
    df = pd.read_csv(up)
    df.columns = [c.lower().strip() for c in df.columns]
    if not {"area", "households", "beneficiaries"} <= set(df.columns):
        st.warning("The file needs columns area, households, beneficiaries.")
        return
    table, median = proof.reach_gap(df)
    st.metric("Typical coverage", f"{median:.0f}% of households")
    st.dataframe(table, hide_index=True, width="stretch")
    top = table.iloc[0]
    snap.append(f"Scheme reach: {top['area']} is furthest below typical coverage, about {int(top['Gap vs typical area'])} households short")


def _roll_tab(seat, snap):
    st.caption(
        "Telangana's special revision removed about 73 lakh names from the draft roll, 1.79 lakh of them in Jubilee Hills. Where a booth lost far more "
        "names than the seat as a whole while its ward kept growing, genuine voters are more likely to have been dropped. Claims (Form 6) close on 7 October."
    )
    growth = pd.DataFrame()
    if geo.wards_in(seat):
        if st.button("Measure building growth per ward", key="pf_roll_growth") or st.session_state.get("pf_roll_growth_done") == seat:
            with st.spinner("Comparing 2017 and 2023 land cover per ward"):
                growth = _ward_growth(seat, st.session_state["pf_area_id"])
            st.session_state["pf_roll_growth_done"] = seat
            st.dataframe(growth, hide_index=True, width="stretch")
    else:
        st.caption("Per-ward growth is available for Hyderabad seats; elsewhere the booth deletions alone are ranked.")
    up = st.file_uploader("Booth deletions CSV: booth, ward, electors_before, deleted", type=["csv"], key="pf_roll_up")
    if not up:
        st.info("The absent/shifted/dead lists are displayed booth by booth on the CEO Telangana site. Count each booth's names into this sheet "
                "(counts only: never copy names or details into the app).")
        return
    b = pd.read_csv(up)
    b.columns = [c.lower().strip() for c in b.columns]
    if not {"booth", "ward", "electors_before", "deleted"} <= set(b.columns):
        st.warning("The file needs columns booth, ward, electors_before, deleted.")
        return
    table, rate = proof.roll_vs_roof(b, growth)
    st.metric("Seat-wide deletion rate", f"{rate}%")
    st.dataframe(table, hide_index=True, width="stretch")
    high = table[table["Priority"] == "High"]
    snap.append(f"Roll vs roof: {len(high)} booths are high priority for Form 6 help desks (deletions far above the seat's {rate}% while the ward grew)")
    st.caption("This ranks where to put help desks. It never says a particular person was wrongly removed; each case is settled on Form 6 with proof of residence.")


def _rank_tab(seat, snap):
    if not os.path.exists(SEAT_INDICATORS):
        st.info("The statewide satellite indicators are still being computed (pipeline/seat_indicators.py).")
        return
    d = pd.read_csv(SEAT_INDICATORS)
    y0, y1 = 2017, orbit.LULC_YEARS[-1]
    d["Built growth %"] = ((d[f"built_{y1}_ha"] - d[f"built_{y0}_ha"]) / d[f"built_{y0}_ha"].replace(0, np.nan) * 100).round(1)
    d["Tree cover change %"] = ((d[f"trees_{y1}_ha"] - d[f"trees_{y0}_ha"]) / d[f"trees_{y0}_ha"].replace(0, np.nan) * 100).round(1)
    dry = sorted(int(c.split("_")[2]) for c in d.columns if c.startswith("dry_green_"))
    if len(dry) >= 2:
        a, b = dry[0], dry[-1]
        d["Irrigated (dry-season green) change %"] = ((d[f"dry_green_{b}_ha"] - d[f"dry_green_{a}_ha"]) / d[f"dry_green_{a}_ha"].replace(0, np.nan) * 100).round(1)
        d["Tank water change %"] = ((d[f"dry_water_{b}_ha"] - d[f"dry_water_{a}_ha"]) / d[f"dry_water_{a}_ha"].replace(0, np.nan) * 100).round(1)
    metrics = [c for c in d.columns if c.endswith("%")]
    metric = st.selectbox("Rank all seats by", metrics, key="pf_rank_metric")
    d = d.sort_values(metric, ascending=False).reset_index(drop=True)
    d["Rank"] = d.index + 1
    st.caption(f"{len(d)} of 119 seats computed so far.")
    if seat in set(d["seat"]):
        me = d[d["seat"] == seat].iloc[0]
        st.metric(f"{seat}: rank on {metric}", f"{int(me['Rank'])} of {len(d)}", f"{me[metric]}")
        snap.append(f"Seat rank: {seat} is {int(me['Rank'])} of {len(d)} on {metric} ({me[metric]})")
    st.dataframe(d[["Rank", "seat", metric, "area_km2"]].rename(columns={"seat": "Seat", "area_km2": "Area km²"}), hide_index=True, width="stretch")
    st.caption("Seat outlines are the OpenCity 2018 map at about 60 m per pixel. Percentages on tiny starting values (a city seat's few hectares of trees) swing wildly, so read them with the hectares.")


def render(ctx, sidebar):
    section(
        "Proof",
        "What changed on the ground, measured from free satellite data anyone can re-check: building, farming, irrigation, lakes, heat and crop damage. "
        "Where a satellite can't see something, this page says so.",
    )
    c1, c2 = st.columns([2, 1])
    seats = geo.seats()
    seat = c1.selectbox("Seat", seats, index=seats.index(HOME) if HOME in seats else 0, key="pf_seat")
    wards = bool(geo.SEAT_WARDS.get(seat)) and c2.toggle("Use GHMC wards (more precise)", value=True, key="pf_wards")
    feat = geo.area(seat, wards)
    # part of every cache key, so a change to how an area is drawn is never served stale results
    st.session_state["pf_area_id"] = feat["properties"]["basis"]
    st.caption(f"Area analysed: {feat['properties']['basis']} · about {geo.km2(feat):,.0f} km²")

    snap = []
    tabs = st.tabs(["By sector", "Time machine", "Crop-loss radar", "Heat", "Lakes", "Ghost works", "Scheme reach", "Roll vs roof", "Seat rank"])
    with tabs[0]:
        _sectors(seat, wards, snap)
    with tabs[1]:
        _time_machine(seat, wards, snap, ctx)
    with tabs[2]:
        _crop_tab(seat, wards, snap)
    with tabs[3]:
        _heat_tab(seat, wards, snap)
    with tabs[4]:
        _lakes_tab(seat, wards, snap)
    with tabs[5]:
        _ghost_tab(snap)
    with tabs[6]:
        _reach_tab(snap)
    with tabs[7]:
        _roll_tab(seat, snap)
    with tabs[8]:
        _rank_tab(seat, snap)

    if snap:
        st.session_state["proof_snapshot"] = {"seat": seat, "lines": snap}
    fact_card(
        "Measured from Sentinel-2, Landsat, the Esri annual land-cover maps and JRC Global Surface Water through Microsoft's Planetary Computer, "
        "with lake and place names from OpenStreetMap. Satellites show the ground, not people: they cannot see payments, teachers or a road's surface.",
        SOURCE_METADATA["satellite"]["name"], SOURCE_METADATA["satellite"]["type"], "medium",
    )
    ctx.logger.log_analysis("proof", ["satellite"], f"proof page for {seat}")
