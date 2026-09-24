import time

import pandas as pd
import streamlit as st

import charts
import scoring
from components import empty_state, fact_card, section
from config import PARTIES, PARTY_LABELS, SOURCE_METADATA

TITLE = "Backtest"


def _when(event):
    stamp = event.get("timestamp") or event.get("created_at")
    return pd.to_datetime(stamp, utc=True, errors="coerce")


def _events(ctx, kind):
    out = []
    for event in ctx.logger.recent(500):
        details = event.get("details")
        if event.get("action_type") == kind and isinstance(details, dict) and pd.notna(_when(event)):
            out.append({"at": _when(event), "details": details})
    return out


def _distinct_predictions(events):
    """The same prediction is logged every time a page loads. Keep the first time
    each distinct one appeared, which is the honest time to hold it to."""
    seen, out = set(), []
    for event in sorted(events, key=lambda e: e["at"]):
        pred = event["details"].get("prediction") or {}
        shares = pred.get("blended_shares")
        if not shares:
            continue
        key = tuple(sorted((p, round(v, 1)) for p, v in shares.items()))
        if key not in seen:
            seen.add(key)
            out.append({"at": event["at"], "prediction": pred})
    return out


def _calibration(ctx):
    section(
        "1. Is the base data consistent with the official result?",
        "The 2023 division figures, averaged, against the official 2023 result.",
    )
    entries = scoring.calibration(ctx.sheets)
    if not entries:
        empty_state("No election appears in both the official results and the division tracking.")
        return

    for entry in entries:
        year = entry["year"]
        c1, c2, c3 = st.columns(3)
        c1.metric(f"Average gap, {year}", f"{entry['mae']} pt")
        c2.metric("Winner matches", "Yes" if entry["winner_actual"] == entry["winner_tracked"] else "No")
        c3.metric("Parties compared", len(entry["actual"]))
        st.plotly_chart(
            charts.backtest_compare(entry["actual"], entry["tracked"], "Division tracking"),
            width="stretch",
        )
        for party, carry in entry["carry_forward"].items():
            name = PARTY_LABELS.get(party, party)
            st.caption(
                f"For comparison, assuming {name} simply repeats its {carry['from_year']} share "
                f"({carry['prior']}%) would have been off by {abs(carry['error'])} pt."
            )

    fact_card(
        "This shows the division table adds up to the official count, so it is a sound base to build on. "
        "It does not show the model can forecast: these are past figures. Forecast accuracy can only be "
        "measured against a result the model didn't know, which is what the next section does.",
        SOURCE_METADATA["historical_results"]["name"],
        SOURCE_METADATA["historical_results"]["type"],
        "high",
    )


def _record_form(ctx):
    with st.expander("Record a real result"):
        with st.form("record_actual"):
            label = st.text_input("Election", placeholder="e.g. Jubilee Hills by-election")
            declared = st.date_input("Result declared on")
            cols = st.columns(len(PARTIES))
            shares = {
                party: col.number_input(
                    f"{PARTY_LABELS.get(party, party)} %", 0.0, 100.0, 0.0, 0.01, key=f"actual_{party}"
                )
                for col, party in zip(cols, PARTIES)
            }
            submitted = st.form_submit_button("Save result")

        if not submitted:
            return
        entered = {p: v for p, v in shares.items() if v > 0}
        if not label.strip():
            st.error("Give the election a name.")
        elif len(entered) < 2 or sum(entered.values()) > 100.5:
            st.error("Enter at least two parties' shares, adding up to no more than 100.")
        else:
            winner = max(entered, key=entered.get)
            ctx.logger.log_event(
                "actual_result", label=label.strip(), result_date=str(declared), shares=entered, winner=winner
            )
            time.sleep(1)  # logging runs on a background thread; give it a moment before re-reading
            st.rerun()


def _score(ctx):
    section(
        "2. Score a prediction against a real result",
        "Predictions are logged automatically when the prediction pages load. Record the real result once it is out.",
    )

    results = _events(ctx, "actual_result")
    predictions = _distinct_predictions(_events(ctx, "prediction"))
    _record_form(ctx)

    if not results:
        empty_state("No real result recorded yet.")
        return
    if not predictions:
        empty_state("No prediction has been logged yet. Open Overview or Survey Reliability once.")
        return

    latest_first = sorted(results, key=lambda e: e["at"], reverse=True)
    result = st.selectbox(
        "Result", latest_first,
        format_func=lambda e: f"{e['details'].get('label', 'Election')} · declared {e['details'].get('result_date', '?')}",
    )
    preds_first = sorted(predictions, key=lambda e: e["at"], reverse=True)
    chosen = st.selectbox(
        "Prediction to score", preds_first,
        format_func=lambda e: (
            f"first logged {e['at']:%d %b %Y %H:%M} · "
            f"{PARTY_LABELS.get(e['prediction'].get('predicted_leader'), e['prediction'].get('predicted_leader'))} "
            f"by {e['prediction'].get('margin_pct')}pt"
        ),
    )

    declared = pd.to_datetime(result["details"].get("result_date"), utc=True, errors="coerce")
    if pd.notna(declared) and chosen["at"] >= declared + pd.Timedelta(days=1):
        st.error(
            "This prediction was first logged after the result was declared, so it can't count. "
            "Only a prediction made beforehand is a fair test."
        )
        return

    scored = scoring.score_prediction(chosen["prediction"]["blended_shares"], result["details"]["shares"])
    if not scored:
        st.warning("The prediction and the result share no party to compare.")
        return

    c1, c2, c3 = st.columns(3)
    c1.metric("Winner called", "Correct" if scored["winner_correct"] else "Wrong")
    c2.metric("Called", PARTY_LABELS.get(scored["winner_called"], scored["winner_called"]))
    c3.metric("Actual winner", PARTY_LABELS.get(scored["winner_actual"], scored["winner_actual"]))
    st.metric("Average gap per party", f"{scored['mae']} pt")

    st.plotly_chart(
        charts.backtest_compare(
            {p: result["details"]["shares"][p] for p in scored["compared"]},
            {p: chosen["prediction"]["blended_shares"][p] for p in scored["compared"]},
            "Model",
        ),
        width="stretch",
    )
    st.dataframe(
        pd.DataFrame(
            {
                "Party": [PARTY_LABELS.get(p, p) for p in scored["compared"]],
                "Predicted %": [round(chosen["prediction"]["blended_shares"][p], 1) for p in scored["compared"]],
                "Actual %": [result["details"]["shares"][p] for p in scored["compared"]],
                "Gap (pt)": [scored["errors"][p] for p in scored["compared"]],
            }
        ),
        hide_index=True,
        width="stretch",
    )
    if not scored["winner_correct"]:
        st.info(
            "A wrong call is useful: it says which input to fix. Compare the gaps above with the survey "
            "conflicts on the Survey Reliability page."
        )


def render(ctx, sidebar):
    section("Backtest", "How close have the numbers been to what actually happened?")
    _calibration(ctx)
    _score(ctx)
