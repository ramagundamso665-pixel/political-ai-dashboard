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
