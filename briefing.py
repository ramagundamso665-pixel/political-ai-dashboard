"""The one-page daily brief: built from the analysis engine only, no model call,
so it costs nothing and cannot contain a number that isn't in the data."""

import html
from datetime import date

import pandas as pd

from config import CONSTITUENCY_NAME, PARTY_LABELS
from validation import validate_workbook

CSS = """
html{background:#fff}body{background:#fff;font-family:-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:#1c1c1e;max-width:820px;margin:0 auto;padding:32px 28px;line-height:1.5}
h1{font-size:24px;margin:0 0 2px}h2{font-size:15px;text-transform:uppercase;letter-spacing:.06em;color:#555;margin:26px 0 8px;border-bottom:1px solid #ddd;padding-bottom:4px}
.sub{color:#666;font-size:13px}.headline{background:#f4f4f6;border-radius:8px;padding:14px 16px;font-size:16px;margin:16px 0}
table{border-collapse:collapse;width:100%;font-size:13.5px}th,td{text-align:left;padding:6px 8px;border-bottom:1px solid #eee}th{color:#666;font-weight:600}
.note{font-size:12.5px;color:#666}.warn{color:#8a5a00}li{margin:3px 0}
@media print{body{padding:0}}
"""


def _e(value):
    return html.escape(str(value))


def _label(party):
    return PARTY_LABELS.get(party, party)


def _table(headers, rows):
    head = "".join(f"<th>{_e(h)}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{_e(c)}</td>" for c in row) + "</tr>" for row in rows)
    return f"<table><tr>{head}</tr>{body}</table>"


def _own_points(ctx, party):
    """This party's own ground-campaign notes, split the way the sheet splits them."""
    tag = "[Congress (INC)]" if party == "INC" else f"[{party}]"
    return [f.replace(tag, "", 1).strip() for f in ctx.analyzer.ground_campaign_facts() if f.startswith(tag)]


def build_brief_html(ctx, party, today=None):
    today = today or date.today()
    analyzer = ctx.analyzer

    pred = analyzer.predict_outcome()
    survey = analyzer.survey_landscape()
    swing = analyzer.swing_divisions(top_n=3)
    subgroups = analyzer.demographic_preferences()
    recs = analyzer.recommendations()
    issues = validate_workbook(ctx.sheets)

    leader, runner_up = _label(pred["predicted_leader"]), _label(pred["runner_up"])
    blended = pred["blended_shares"]
    ours = blended.get(party)
    rank = sorted(blended, key=blended.get, reverse=True).index(party) + 1 if party in blended else None
    conflicted = [c for c in survey["conflicts"] if c["conflict_exists"]]
    widest = max((c["spread"] for c in survey["conflicts"]), default=0)

    parts = [
        f"<h1>Daily brief — {_e(CONSTITUENCY_NAME)}</h1>",
        f'<div class="sub">{today:%A, %d %B %Y} · prepared for the {_e(_label(party))} campaign</div>',
        f'<div class="headline"><strong>{_e(leader)}</strong> leads {_e(runner_up)} by '
        f'<strong>{pred["margin_pct"]} points</strong> on the blended estimate. '
        f'Confidence: <strong>{_e(pred["confidence_label"].title())} ({pred["confidence_pct"]}%)</strong>.</div>',
    ]
    if conflicted:
        parts.append(
            f'<p class="warn">Third-party surveys disagree by up to {widest:.0f} points on this seat, so treat '
            "the estimate as a direction, not a forecast.</p>"
        )

    if ours is not None:
        gap = blended[pred["predicted_leader"]] - ours
        where = "leading" if rank == 1 else f"{gap:.1f} points behind the leader, ranked {rank}"
        parts.append(f"<h2>Where {_e(_label(party))} stands</h2><p>Blended share <strong>{ours:.1f}%</strong> — {where}.</p>")
        strengths, weaknesses, campaigning = [], [], []
        for point in _own_points(ctx, party):
            category, _, note = point.partition(" > ")
            bucket = strengths if category == "Observed Pluses" else weaknesses if category == "Observed Minuses" else campaigning
            bucket.append(note)
        for title, items in (("Noted strengths", strengths), ("Noted weaknesses", weaknesses), ("Campaigning on", campaigning)):
            if items:
                parts.append(f"<p><strong>{title}</strong></p><ul>" + "".join(f"<li>{_e(i)}</li>" for i in items[:6]) + "</ul>")

    if swing:
        rows = [
            [s["division"], _label(s["swinging_party"]), f"{s['max_swing']} pt"] for s in swing
        ]
        parts.append("<h2>Divisions that moved most, 2023 to 2025</h2>" + _table(["Division", "Moved toward", "Swing"], rows))

    contested = [g for g in subgroups if g["is_contested"]]
    if contested:
        rows = [[g["subgroup"], _label(g["leader"]), f"{g['gap_to_runner_up']} pt"] for g in contested]
        parts.append("<h2>Groups still up for grabs (under 5 points apart)</h2>" + _table(["Group", "Ahead", "Lead"], rows))

    if recs:
        items = "".join(
            f"<li><strong>{_e(r['action'])}</strong> <span class='note'>({_e(r['timeline'])})</span><br>"
            f"<span class='note'>{_e(r['reasoning'])}</span></li>"
            for r in recs
        )
        parts.append(f"<h2>Suggested actions</h2><ol>{items}</ol>")

    timeline = analyzer.campaign_activity_timeline()["timeline"]
    if not timeline.empty:
        recent = timeline.sort_values("Date", ascending=False).head(5)
        rows = [
            [pd.to_datetime(r["Date"]).strftime("%d %b"), _label(r["party_norm"]) if r["party_norm"] else r["Party"],
             r["Event Type"], r["Area / Division"], r["Attendance"]]
            for _, r in recent.iterrows()
        ]
        parts.append("<h2>Latest campaign activity</h2>" + _table(["Date", "Party", "Event", "Area", "Crowd"], rows))

    scores = [r["data_quality_score"] for r in ctx.quality_reports.values()]
    quality = round(sum(scores) / len(scores)) if scores else 0
    flagged = [i for i in issues if i["severity"] in ("error", "warning")]
    parts.append(f"<h2>How far to trust this</h2><p class='note'>Data quality score {quality}%. Data loaded from {_e(ctx.data_source)}. ")
    parts.append(f"{len(flagged)} open data question(s).</p>" if flagged else "No open data questions.</p>")
    if flagged:
        parts.append("<ul class='note'>" + "".join(f"<li>{_e(i['message'])}</li>" for i in flagged[:5]) + "</ul>")

    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>Daily brief — {_e(CONSTITUENCY_NAME)} — {today:%d %b %Y}</title><style>{CSS}</style></head>"
        f"<body>{''.join(parts)}</body></html>"
    )
