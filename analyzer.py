"""Layer 3: analysis engine. Every method returns numbers AND registers the
claim + source with the SourceTracker so the UI can show where it came from."""

import pandas as pd

from config import PARTIES, normalize_party
from data_manager import check_conflicting_sources


class PoliticalAnalyzer:
    def __init__(self, sheets, tracker):
        self.sheets = sheets
        self.tracker = tracker

    # ------------------------------------------------------------------
    # Swing divisions
    # ------------------------------------------------------------------
    def swing_divisions(self, top_n=7):
        deltas = self.sheets["division_deltas"].copy()
        shares = self.sheets["division_shares"].copy()

        delta_cols = [c for c in deltas.columns if c.endswith("_Delta")]
        deltas["max_swing"] = deltas[delta_cols].abs().max(axis=1)
        deltas["swinging_party"] = deltas[delta_cols].abs().idxmax(axis=1).str.replace("_Delta", "", regex=False)

        ranked = deltas.sort_values("max_swing", ascending=False).head(top_n)

        latest_year = shares["Year"].max()
        latest_shares = shares[shares["Year"] == latest_year].set_index("Division")

        rows = []
        for _, row in ranked.iterrows():
            division = row["Division"]
            current = latest_shares.loc[division] if division in latest_shares.index else None
            rows.append({
                "division": division,
                "max_swing": round(row["max_swing"], 1),
                "swinging_party": row["swinging_party"],
                "current_shares": current.to_dict() if current is not None else {},
                "deltas": {c.replace("_Delta", ""): row[c] for c in delta_cols},
            })

        self.tracker.add_claim({
            "claim": f"Top {len(rows)} swing divisions identified by 2023->{latest_year} vote share change",
            "source_id": "division_deltas",
            "confidence": "medium",
            "data_point": [r["division"] for r in rows],
        })

        return rows

    # ------------------------------------------------------------------
    # Demographic preferences
    # ------------------------------------------------------------------
    def demographic_preferences(self):
        df = self.sheets["demo_preferences"].copy()

        results = []
        for _, row in df.iterrows():
            party_vals = {p: row[p] for p in PARTIES if p in df.columns}
            leader = max(party_vals, key=party_vals.get)
            runner_up_vals = {p: v for p, v in party_vals.items() if p != leader}
            runner_up = max(runner_up_vals, key=runner_up_vals.get) if runner_up_vals else None
            gap = party_vals[leader] - party_vals[runner_up] if runner_up else None

            results.append({
                "subgroup": row["Subgroup"],
                "shares": party_vals,
                "leader": leader,
                "gap_to_runner_up": round(gap, 1) if gap is not None else None,
                "is_contested": gap is not None and gap < 5,
            })

        contested = [r["subgroup"] for r in results if r["is_contested"]]
        if contested:
            self.tracker.add_claim({
                "claim": f"Tightly contested (<5pt gap) subgroups: {', '.join(contested)}",
                "source_id": "demo_preferences",
                "confidence": "medium",
                "data_point": contested,
            })

        return results

    # ------------------------------------------------------------------
    # Survey landscape + conflict detection
    # ------------------------------------------------------------------
    def survey_landscape(self):
        df = self.sheets["surveys"].copy()

        for p in PARTIES:
            if p in df.columns:
                df[p] = pd.to_numeric(df[p], errors="coerce")

        conflicts = []
        for p in PARTIES:
            if p not in df.columns:
                continue
            values_by_source = dict(zip(df["Survey"], df[p]))
            report = check_conflicting_sources(values_by_source, f"{p} vote share across surveys", tolerance_pct=10.0)
            conflicts.append({"party": p, **report})

        self.tracker.add_claim({
            "claim": f"{len(df)} independent surveys compared for {self.sheets.get('_constituency', 'the constituency')}",
            "source_id": "surveys",
            "confidence": "low" if any(c["conflict_exists"] for c in conflicts) else "medium",
            "data_point": len(df),
        })

        return {"raw": df, "conflicts": conflicts}

    # ------------------------------------------------------------------
    # Social media share of voice
    # ------------------------------------------------------------------
    def social_media_activity(self):
        df = self.sheets["social_media"].copy()
        df["party_norm"] = df["Party"].apply(normalize_party)

        numeric_cols = ["#Posts", "Likes", "Shares", "Comments", "Impressions", "Reach"]
        for c in numeric_cols:
            df[c] = pd.to_numeric(df[c], errors="coerce")

        valid = df.dropna(subset=["party_norm"] + numeric_cols)
        dropped = len(df) - len(valid)

        valid = valid.copy()
        valid["engagement"] = valid["Likes"] + valid["Shares"] + valid["Comments"]

        agg = valid.groupby("party_norm").agg(
            posts=("#Posts", "sum"),
            engagement=("engagement", "sum"),
            reach=("Reach", "sum"),
            impressions=("Impressions", "sum"),
        ).reset_index().rename(columns={"party_norm": "party"})

        total_engagement = agg["engagement"].sum()
        agg["share_of_voice_pct"] = (agg["engagement"] / total_engagement * 100).round(1) if total_engagement else 0

        self.tracker.add_claim({
            "claim": f"Social media share-of-voice computed from {len(valid)} logged posts ({dropped} row(s) excluded as incomplete)",
            "source_id": "social_media",
            "confidence": "low",
            "data_point": agg.to_dict(orient="records"),
        })

        return {"by_party": agg, "excluded_rows": dropped}

    # ------------------------------------------------------------------
    # Ground campaign matrix
    # ------------------------------------------------------------------
    def ground_campaign_matrix(self):
        df = self.sheets["ground_campaign"].copy()
        df["Category"] = df["Category"].ffill()
        cols = [c for c in ["Category", "Subcategory", "Congress", "BRS", "BJP", "Notes"] if c in df.columns]
        return df[cols]

    # ------------------------------------------------------------------
    # Campaign activity timeline
    # ------------------------------------------------------------------
    def campaign_activity_timeline(self):
        df = self.sheets["campaign_activity"].copy()
        df["party_norm"] = df["Party"].apply(normalize_party)
        df = df.sort_values("Date")
        counts = df["party_norm"].value_counts().to_dict()

        self.tracker.add_claim({
            "claim": f"{len(df)} campaign events logged across {df['Date'].nunique()} days",
            "source_id": "campaign_activity",
            "confidence": "high",
            "data_point": counts,
        })

        return {"timeline": df, "event_counts_by_party": counts}

    # ------------------------------------------------------------------
    # Prediction
    # ------------------------------------------------------------------
    def predict_outcome(self):
        historical = self.sheets["historical_results"]
        latest_hist = historical[historical["Year"] == historical["Year"].max()]
        hist_pct = {row["Party"]: float(row["Pct"]) for _, row in latest_hist.iterrows()}

        shares = self.sheets["division_shares"]
        latest_year = shares["Year"].max()
        division_avg = {k: float(v) for k, v in shares[shares["Year"] == latest_year][PARTIES].mean().to_dict().items()}

        surveys = self.sheets["surveys"].copy()
        survey_avgs, survey_stds = {}, {}
        for p in PARTIES:
            if p in surveys.columns:
                vals = pd.to_numeric(surveys[p], errors="coerce").dropna()
                if len(vals):
                    survey_avgs[p] = round(float(vals.mean()), 1)
                    survey_stds[p] = round(float(vals.std(ddof=0)), 1) if len(vals) > 1 else 0.0

        # Weighted blend: internal division tracking is closest to ground truth
        # but small-sample; historical is stale but verified; surveys are
        # noisy (high variance) so they get the least weight.
        weights = {"historical": 0.20, "division": 0.50, "survey": 0.30}
        blended = {}
        for p in PARTIES:
            h = hist_pct.get(p, 0)
            d = division_avg.get(p, 0)
            s = survey_avgs.get(p, d)  # fall back to division estimate if no survey data
            blended[p] = round(h * weights["historical"] + d * weights["division"] + s * weights["survey"], 1)

        leader = max(blended, key=blended.get)
        runner_up = max((p for p in blended if p != leader), key=blended.get)
        margin = round(blended[leader] - blended[runner_up], 1)

        avg_survey_std = round(sum(survey_stds.values()) / len(survey_stds), 1) if survey_stds else 0.0
        # More survey disagreement -> lower confidence. Calibrated so ~5pt avg
        # std -> ~65%, ~15pt avg std -> ~35%.
        confidence = max(30, min(85, round(80 - avg_survey_std * 3)))

        if confidence >= 65:
            confidence_label = "MEDIUM-HIGH"
        elif confidence >= 45:
            confidence_label = "MEDIUM"
        else:
            confidence_label = "LOW"

        self.tracker.add_claim({
            "claim": f"Predicted leader: {leader} by {margin}pt over {runner_up}",
            "source_id": "division_shares",
            "confidence": "medium" if confidence >= 45 else "low",
            "data_point": blended,
        })

        return {
            "blended_shares": blended,
            "predicted_leader": leader,
            "runner_up": runner_up,
            "margin_pct": margin,
            "confidence_pct": confidence,
            "confidence_label": confidence_label,
            "avg_survey_disagreement_pct": avg_survey_std,
            "inputs": {
                "historical_2023_pct": hist_pct,
                "division_avg_2025_pct": {k: round(v, 1) for k, v in division_avg.items()},
                "survey_avg_2025_pct": survey_avgs,
                "survey_std_2025_pct": survey_stds,
            },
            "weights": weights,
        }

    # ------------------------------------------------------------------
    # Recommendations (derived, not hardcoded)
    # ------------------------------------------------------------------
    def recommendations(self):
        recs = []

        swing = self.swing_divisions(top_n=3)
        if swing:
            divisions = ", ".join(r["division"] for r in swing)
            recs.append({
                "priority": 1,
                "action": f"Deploy ground teams to top swing divisions: {divisions}",
                "reasoning": f"These divisions showed the largest 2023->2025 vote share movement (up to {swing[0]['max_swing']}pt swing toward {swing[0]['swinging_party']}).",
                "source": "Internal Division-Level Vote Share Tracking",
                "timeline": "Immediate",
            })

        demo = self.demographic_preferences()
        contested = [r for r in demo if r["is_contested"]]
        if contested:
            names = ", ".join(r["subgroup"] for r in contested[:4])
            recs.append({
                "priority": 2,
                "action": f"Target persuadable subgroups: {names}",
                "reasoning": "These subgroups show a lead-to-runner-up gap under 5 points — most movable with targeted outreach.",
                "source": "Internal Demographic Preference Tracking",
                "timeline": "Next 2 weeks",
            })

        survey = self.survey_landscape()
        flagged = [c for c in survey["conflicts"] if c["conflict_exists"]]
        if flagged:
            parties = ", ".join(c["party"] for c in flagged)
            recs.append({
                "priority": 3,
                "action": f"Commission a fresh internal poll before trusting {parties} numbers",
                "reasoning": f"Third-party surveys disagree by more than 10 points on {parties} — current external polling is not reliable enough to plan around.",
                "source": "Third-Party Opinion Surveys",
                "timeline": "Next 1 week",
            })

        activity = self.campaign_activity_timeline()
        counts = activity["event_counts_by_party"]
        if counts:
            leader_by_activity = max(counts, key=counts.get)
            recs.append({
                "priority": 4,
                "action": f"Match ground event tempo — {leader_by_activity} is currently out-campaigning on visible events ({counts.get(leader_by_activity)} logged)",
                "reasoning": "Event frequency and VIP visibility compound with swing-division targeting.",
                "source": "Campaign Activity Log",
                "timeline": "Ongoing",
            })

        return recs
