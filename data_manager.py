"""Layer 1 (data validation) and Layer 2 (source attribution) of the dashboard."""

import pandas as pd

from config import SOURCE_METADATA


def validate_sheet(df, sheet_key):
    """Validate a single sheet and return a quality report.

    Flags missing values, non-numeric placeholder cells (e.g. the
    "(enter)" row left in Social_Media), and gives a 0-100 quality score.
    """
    meta = SOURCE_METADATA.get(sheet_key, {})
    total_cells = df.shape[0] * df.shape[1] if df.size else 1

    missing = int(df.isnull().sum().sum())

    placeholder_rows = 0
    for col in df.columns:
        placeholder_rows += df[col].astype(str).str.strip().isin(
            ["(enter)", "(party)", "-", "—", "NaN", "nan"]
        ).sum()

    warnings = []
    if missing:
        warnings.append(f"{missing} missing cell(s) detected")
    if placeholder_rows:
        warnings.append(f"{placeholder_rows} unfilled placeholder cell(s) detected (e.g. '(enter)')")

    quality_score = max(0, 100 - int((missing + placeholder_rows) / total_cells * 100))

    return {
        "sheet": sheet_key,
        "source_name": meta.get("name", sheet_key),
        "source_type": meta.get("type", "internal"),
        "rows_count": len(df),
        "missing_values": missing,
        "placeholder_cells": int(placeholder_rows),
        "data_quality_score": quality_score,
        "warnings": warnings,
        "is_valid": quality_score >= 50,
    }


def validate_all(sheets):
    """Run validate_sheet across every loaded sheet, keyed by sheet_key."""
    reports = {}
    for key in sheets:
        reports[key] = validate_sheet(sheets[key], key)
    return reports


def check_conflicting_sources(values_by_source, metric_name, tolerance_pct=5.0):
    """Compare a metric reported by multiple sources and flag disagreement.

    values_by_source: dict of {source_label: numeric_value}
    Never hides conflicts - always returns the full spread.
    """
    clean = {k: v for k, v in values_by_source.items() if v is not None}
    if len(clean) < 2:
        return {
            "metric": metric_name,
            "values": clean,
            "conflict_exists": False,
            "spread": 0.0,
        }

    vals = list(clean.values())
    spread = max(vals) - min(vals)
    mean_val = sum(vals) / len(vals)

    return {
        "metric": metric_name,
        "values": clean,
        "mean": round(mean_val, 1),
        "min": round(min(vals), 1),
        "max": round(max(vals), 1),
        "spread": round(spread, 1),
        "conflict_exists": spread > tolerance_pct,
    }


class SourceTracker:
    """Registers every source and every claim so each analysis result can be
    traced back to where the number came from."""

    def __init__(self):
        self.sources = {}
        self.claims = []

    def add_source(self, source_info):
        self.sources[source_info["id"]] = source_info

    def add_claim(self, claim_info):
        self.claims.append(claim_info)
        return len(self.claims) - 1

    def get_source(self, source_id):
        return self.sources.get(source_id)

    def get_claim(self, index):
        claim = self.claims[index]
        source = self.get_source(claim["source_id"])
        return {**claim, "source": source}

    def recent_claims(self, n=10):
        return self.claims[-n:]
