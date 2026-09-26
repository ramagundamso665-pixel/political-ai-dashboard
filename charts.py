"""Plotly figure builders.

Every figure is drawn on a transparent canvas with no Plotly template, so the
page background shows through and the CSS in theme.py can recolor axis, legend
and title text via `fill: currentColor`. One chart therefore reads correctly in
both the light and the dark palette without being rebuilt.
"""

import plotly.graph_objects as go

from config import PARTIES, PARTY_COLORS, PARTY_LABELS

GRID = "rgba(128,128,128,.18)"
ZERO = "rgba(128,128,128,.42)"


def _style(fig, height, *, showlegend=True, margin_t=44):
    fig.update_layout(
        template="none",
        height=height,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, sans-serif", size=12),
        margin=dict(l=8, r=8, t=margin_t, b=8),
        showlegend=showlegend,
        legend=dict(
            orientation="h",
            yanchor="bottom", y=1.02,
            xanchor="left", x=0,
            bgcolor="rgba(0,0,0,0)",
            title_text="",
        ),
        hoverlabel=dict(font_size=12),
        title=dict(font=dict(size=13.5), x=0, xanchor="left", y=.97, yanchor="top"),
    )
    # automargin, or the tick labels get clipped by the tight margins above
    fig.update_xaxes(showgrid=False, zeroline=False, showline=False, ticks="", automargin=True)
    fig.update_yaxes(
        showgrid=True, gridcolor=GRID, zeroline=False, showline=False, ticks="", automargin=True
    )
    return fig


def swing_deltas(swing):
    """Vote-share change per party, one trace per division."""
    fig = go.Figure()
    for row in swing:
        fig.add_trace(
            go.Bar(
                name=row["division"],
                x=[PARTY_LABELS.get(p, p) for p in row["deltas"]],
                y=list(row["deltas"].values()),
                hovertemplate="%{fullData.name}<br>%{x}: %{y:+.1f}pt<extra></extra>",
            )
        )
    fig.add_hline(y=0, line_width=1, line_color=ZERO)
    fig.update_layout(barmode="group", title="Vote share change by party, 2023 to 2025")
    fig.update_yaxes(ticksuffix="pt")
    return _style(fig, 440, margin_t=70)


def demographic_preferences(df):
    """Grouped bars of party share within each demographic subgroup."""
    fig = go.Figure()
    for party in [p for p in PARTIES if p in df.columns]:
        fig.add_trace(
            go.Bar(
                name=PARTY_LABELS.get(party, party),
                x=list(df.index),
                y=df[party].tolist(),
                marker_color=PARTY_COLORS.get(party),
                hovertemplate="%{fullData.name}<br>%{x}: %{y:.1f}%<extra></extra>",
            )
        )
    fig.update_layout(barmode="group", title="Vote share by subgroup")
    fig.update_yaxes(ticksuffix="%")
    return _style(fig, 450, margin_t=70)


def blended_prediction(shares):
    """Final blended share per party, ordered strongest first."""
    ordered = sorted(shares.items(), key=lambda kv: kv[1], reverse=True)
    labels = [PARTY_LABELS.get(p, p) for p, _ in ordered]
    values = [v for _, v in ordered]

    fig = go.Figure(
        go.Bar(
            x=labels,
            y=values,
            marker_color=[PARTY_COLORS.get(p, "#9E9E9E") for p, _ in ordered],
            text=[f"{v:.1f}%" for v in values],
            textposition="outside",
            cliponaxis=False,
            hovertemplate="%{x}: %{y:.1f}%<extra></extra>",
        )
    )
    fig.update_layout(title="Blended vote share")
    fig.update_yaxes(ticksuffix="%", range=[0, max(values) * 1.18])
    return _style(fig, 380, showlegend=False)


def social_share(by_party):
    """Share of engagement volume by party."""
    fig = go.Figure(
        go.Pie(
            labels=[PARTY_LABELS.get(p, p) for p in by_party["party"]],
            values=by_party["engagement"].tolist(),
            hole=.58,
            marker=dict(colors=[PARTY_COLORS.get(p, "#9E9E9E") for p in by_party["party"]]),
            sort=True,
            direction="clockwise",
            textinfo="percent",
            hovertemplate="%{label}: %{value:,} engagements (%{percent})<extra></extra>",
        )
    )
    fig.update_layout(title="Share of engagement volume")
    return _style(fig, 380, margin_t=70)


def pulse_trend(points, value_key, title, ticksuffix=""):
    """A single quiet line for a live signal (search interest, news tone). Grey,
    not a party color — this isn't attributable to any one party."""
    fig = go.Figure(
        go.Scatter(
            x=[p["date"] for p in points],
            y=[p[value_key] for p in points],
            mode="lines",
            line=dict(width=2, color=PARTY_COLORS["Others"]),
            fill="tozeroy",
            fillcolor="rgba(158,158,158,.14)",
            hovertemplate="%{x|%b %d}: %{y:.1f}<extra></extra>",
        )
    )
    fig.add_hline(y=0, line_width=1, line_color=ZERO)
    fig.update_layout(title=title)
    fig.update_yaxes(ticksuffix=ticksuffix)
    return _style(fig, 260, showlegend=False, margin_t=40)


def coverage_volume(per_day, window_days=7):
    """Articles found per day — whether coverage is rising or fading."""
    fig = go.Figure(
        go.Bar(
            x=[d["date"] for d in per_day],
            y=[d["articles"] for d in per_day],
            marker_color=PARTY_COLORS["Others"],
            hovertemplate="%{x|%b %d}: %{y} articles<extra></extra>",
        )
    )
    fig.update_layout(title=f"News articles per day, last {window_days} days")
    fig.update_xaxes(tickformat="%b %d")
    return _style(fig, 260, showlegend=False, margin_t=40)


def event_counts(counts):
    """Campaign events logged per party."""
    ordered = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
    fig = go.Figure(
        go.Bar(
            x=[PARTY_LABELS.get(p, p) for p, _ in ordered],
            y=[v for _, v in ordered],
            marker_color=[PARTY_COLORS.get(p, "#9E9E9E") for p, _ in ordered],
            text=[str(v) for _, v in ordered],
            textposition="outside",
            cliponaxis=False,
            hovertemplate="%{x}: %{y} events<extra></extra>",
        )
    )
    fig.update_layout(title="Logged events by party")
    return _style(fig, 320, showlegend=False)


def what_if(before, after):
    """Average share per party before and after a what-if shift: the original in
    a muted tone, the scenario in the party's own color."""
    parties = [p for p in PARTIES if p in before and p in after]
    labels = [PARTY_LABELS.get(p, p) for p in parties]
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            name="Now",
            x=labels,
            y=[before[p] for p in parties],
            marker_color="rgba(158,158,158,.55)",
            hovertemplate="Now, %{x}: %{y:.1f}%<extra></extra>",
        )
    )
    fig.add_trace(
        go.Bar(
            name="Scenario",
            x=labels,
            y=[after[p] for p in parties],
            marker_color=[PARTY_COLORS.get(p, "#9E9E9E") for p in parties],
            text=[f"{after[p]:.1f}%" for p in parties],
            textposition="outside",
            cliponaxis=False,
            hovertemplate="Scenario, %{x}: %{y:.1f}%<extra></extra>",
        )
    )
    fig.update_layout(barmode="group", title="Average vote share across divisions")
    fig.update_yaxes(ticksuffix="%", range=[0, max(max(before.values()), max(after.values())) * 1.2])
    return _style(fig, 380, margin_t=70)


def backtest_compare(actual, estimated, estimate_label):
    """Official result next to what an estimate said, per party."""
    parties = [p for p in PARTIES if p in actual and p in estimated]
    labels = [PARTY_LABELS.get(p, p) for p in parties]
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            name="Official result",
            x=labels,
            y=[actual[p] for p in parties],
            marker_color=[PARTY_COLORS.get(p, "#9E9E9E") for p in parties],
            hovertemplate="Official, %{x}: %{y:.1f}%<extra></extra>",
        )
    )
    fig.add_trace(
        go.Bar(
            name=estimate_label,
            x=labels,
            y=[estimated[p] for p in parties],
            marker_color="rgba(158,158,158,.55)",
            hovertemplate=estimate_label + ", %{x}: %{y:.1f}%<extra></extra>",
        )
    )
    fig.update_layout(barmode="group", title="Official vote share vs the estimate")
    fig.update_yaxes(ticksuffix="%")
    return _style(fig, 360, margin_t=70)


def margin_distribution(seats):
    """How many seats fell into each winning-margin band, split by who won them."""
    import pandas as pd

    bands = [0, 2, 5, 10, 20, 30, 100]
    labels = ["under 2%", "2-5%", "5-10%", "10-20%", "20-30%", "30%+"]
    banded = pd.cut(seats["margin_pct"], bins=bands, labels=labels, right=False)
    order = ["INC", "BRS", "BJP", "AIMIM"]
    fig = go.Figure()
    for party in order + ["Others"]:
        if party == "Others":
            mask = ~seats["winner_party"].isin(order)
        else:
            mask = seats["winner_party"] == party
        counts = banded[mask].value_counts().reindex(labels, fill_value=0)
        if counts.sum():
            fig.add_trace(
                go.Bar(
                    name=PARTY_LABELS.get(party, party),
                    x=labels,
                    y=counts.tolist(),
                    marker_color=PARTY_COLORS.get(party, "#9E9E9E"),
                    hovertemplate="%{fullData.name}, margin %{x}: %{y} seats<extra></extra>",
                )
            )
    fig.update_layout(barmode="stack", title="Seats by winning margin (share of votes polled)")
    fig.update_yaxes(title_text="Seats")
    return _style(fig, 380, margin_t=70)


def seats_vs_votes(table):
    """Vote share next to seat share for the biggest parties."""
    fig = go.Figure()
    fig.add_trace(go.Bar(name="Share of votes", x=table["Party"], y=table["Vote share %"], marker_color="rgba(158,158,158,.6)",
                         hovertemplate="%{x}: %{y:.1f}% of votes<extra></extra>"))
    fig.add_trace(go.Bar(name="Share of seats", x=table["Party"], y=table["Seat share %"],
                         marker_color=[PARTY_COLORS.get(p, "#9E9E9E") for p in table["Party"]],
                         hovertemplate="%{x}: %{y:.1f}% of seats<extra></extra>"))
    fig.update_layout(barmode="group", title="Votes vs seats, 2023")
    fig.update_yaxes(ticksuffix="%")
    return _style(fig, 360, margin_t=70)


def seat_shares(rows):
    """Vote share of the leading candidates in one seat."""
    top = rows.head(6)
    fig = go.Figure(
        go.Bar(
            x=top["Candidate"] + " (" + top["Party"] + ")",
            y=top["% of votes"],
            marker_color=[PARTY_COLORS.get(p, "#9E9E9E") for p in top["Party"]],
            text=[f"{v:.1f}%" for v in top["% of votes"]],
            textposition="outside",
            cliponaxis=False,
            hovertemplate="%{x}: %{y:.2f}%<extra></extra>",
        )
    )
    fig.update_layout(title="Leading candidates, share of votes polled")
    fig.update_yaxes(ticksuffix="%", range=[0, max(top["% of votes"]) * 1.2])
    return _style(fig, 360, showlegend=False, margin_t=60)


def vote_share_compare(share_then, share_now, parties, then_label="2018", now_label="2023"):
    """Statewide vote share per party at two elections, side by side."""
    labels = [PARTY_LABELS.get(p, p) for p in parties]
    fig = go.Figure()
    fig.add_trace(go.Bar(name=then_label, x=labels, y=[float(share_then.get(p, 0)) for p in parties],
                         marker_color="rgba(158,158,158,.55)", hovertemplate=then_label + ", %{x}: %{y:.1f}%<extra></extra>"))
    fig.add_trace(go.Bar(name=now_label, x=labels, y=[float(share_now.get(p, 0)) for p in parties],
                         marker_color=[PARTY_COLORS.get(p, "#9E9E9E") for p in parties],
                         text=[f"{float(share_now.get(p, 0)):.1f}%" for p in parties], textposition="outside", cliponaxis=False,
                         hovertemplate=now_label + ", %{x}: %{y:.1f}%<extra></extra>"))
    fig.update_layout(barmode="group", title=f"Share of all votes, {then_label} and {now_label}")
    fig.update_yaxes(ticksuffix="%")
    return _style(fig, 360, margin_t=70)


def booth_lead_curve(booths, a="BRS", b="INC"):
    """Every booth in order of how far `a` led `b` (in points of the booth's valid votes).
    Bars above zero are booths `a` won against `b`, below zero booths `b` won."""
    gap = (booths[f"{a}_pct"] - booths[f"{b}_pct"]).sort_values(ascending=False)
    fig = go.Figure(
        go.Bar(
            x=list(range(1, len(gap) + 1)),
            y=gap.values,
            marker_color=[PARTY_COLORS.get(a if v >= 0 else b, "#9E9E9E") for v in gap.values],
            customdata=booths.loc[gap.index, "booth"],
            hovertemplate="Booth %{customdata}: %{y:+.1f} pts<extra></extra>",
        )
    )
    fig.add_hline(y=0, line_color=ZERO, line_width=1)
    fig.update_layout(title=f"Each booth, {PARTY_LABELS.get(a, a)} lead over {PARTY_LABELS.get(b, b)} (points)", bargap=0)
    fig.update_xaxes(title_text="Booths, most favourable to least", showticklabels=False)
    fig.update_yaxes(ticksuffix=" pts")
    return _style(fig, 340, showlegend=False, margin_t=60)


def booth_share_spread(booths, parties):
    """How widely each party's share varies from booth to booth."""
    fig = go.Figure()
    for party in parties:
        fig.add_trace(
            go.Box(
                y=booths[f"{party}_pct"],
                name=PARTY_LABELS.get(party, party),
                marker_color=PARTY_COLORS.get(party, "#9E9E9E"),
                boxpoints=False,
                hovertemplate="%{y:.1f}%<extra>" + PARTY_LABELS.get(party, party) + "</extra>",
            )
        )
    fig.update_layout(title="Share of a booth's votes: the spread across booths")
    fig.update_yaxes(ticksuffix="%")
    return _style(fig, 340, showlegend=False, margin_t=60)


def trend_lines(interest):
    """Search interest over time, one line per term."""
    fig = go.Figure()
    palette = ["#2563eb", "#dc2626", "#16a34a", "#d97706", "#7c3aed"]
    for i, term in enumerate(interest.columns):
        fig.add_trace(go.Scatter(x=interest.index, y=interest[term], name=term, mode="lines",
                                 line=dict(color=palette[i % len(palette)], width=2.2),
                                 hovertemplate="%{x|%d %b}: %{y}<extra>" + term + "</extra>"))
    fig.update_layout(title="Search interest over time (100 = the peak among these terms)")
    fig.update_yaxes(range=[0, 105])
    return _style(fig, 360, margin_t=70)


def organic_split(counts):
    """How many comments fell in each organic-likelihood tier."""
    order = ["Likely organic", "Uncertain", "Flagged"]
    colors = {"Likely organic": "#16a34a", "Uncertain": "#d97706", "Flagged": "#dc2626"}
    fig = go.Figure(go.Bar(x=order, y=[counts.get(t, 0) for t in order], marker_color=[colors[t] for t in order],
                           text=[counts.get(t, 0) for t in order], textposition="outside", cliponaxis=False,
                           hovertemplate="%{x}: %{y} comments<extra></extra>"))
    fig.update_layout(title="Comments by organic likelihood")
    fig.update_yaxes(title_text="Comments")
    return _style(fig, 300, showlegend=False, margin_t=60)


def stance_tone(rows_all, rows_organic):
    """Net tone per party (positive minus negative, as a share of comments about it): all comments next to the organic ones."""
    fig = go.Figure()
    for name, rows, color in (("All comments", rows_all, "rgba(158,158,158,.7)"), ("Likely organic only", rows_organic, "#2563eb")):
        fig.add_trace(go.Bar(name=name, x=[r["Party"] for r in rows], y=[r["Net tone"] for r in rows], marker_color=color,
                             text=[f"{r['Net tone']:+d}" for r in rows], textposition="outside", cliponaxis=False,
                             hovertemplate="%{x}: net %{y:+d} (of %{customdata} comments)<extra>" + name + "</extra>",
                             customdata=[r["Comments"] for r in rows]))
    fig.add_hline(y=0, line_color=ZERO, line_width=1)
    fig.update_layout(barmode="group", title="Net tone toward each party (positive minus negative, % of comments about it)")
    fig.update_yaxes(ticksuffix="")
    return _style(fig, 360, margin_t=70)


def rating_by_area(table):
    """Average rating per area, lowest first, coloured from red (poor) to green (good)."""
    fig = go.Figure(go.Bar(
        y=table["Area"], x=table["Average rating"], orientation="h",
        marker=dict(color=table["Average rating"], colorscale=[[0, "#dc2626"], [0.5, "#d97706"], [1, "#16a34a"]], cmin=1, cmax=5),
        text=[f"{v:.1f}  (n={n})" for v, n in zip(table["Average rating"], table["Answers"])], textposition="outside", cliponaxis=False,
        hovertemplate="%{y}: %{x:.2f} of 5<extra></extra>",
    ))
    fig.update_layout(title="Average rating by area (1 = very poor, 5 = very good)")
    fig.update_xaxes(range=[1, 5.6])
    fig.update_yaxes(autorange="reversed")
    return _style(fig, max(260, 60 + 34 * len(table)), showlegend=False, margin_t=60)
