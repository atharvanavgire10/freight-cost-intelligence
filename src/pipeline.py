"""CLI for FreightTiger Smart Freight Cost Intelligence."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

from .analytics import build_weekly_metrics, validate_threshold
from .load_data import load_inputs
from .note_retrieval import explanation_for

OUTPUT_COLUMNS = ["route", "week_of", "cost_per_tonne_km", "vs_own_history", "vs_similar_routes", "flagged", "matched_note_id", "reason"]
ALLOWED_VERDICTS = {"No", "Yes", "No (justified)"}
PERCENTAGE_PATTERN = re.compile(r"[+-]\d+(?:\.\d+)?%")


def _format_percent(value: float) -> str:
    return "" if pd.isna(value) else f"{value:+.1f}%"


def _parse_threshold(value: str) -> float:
    try:
        return validate_threshold(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(str(error)) from error


def make_output(metrics: pd.DataFrame, notes: pd.DataFrame) -> pd.DataFrame:
    results = metrics.copy()
    explanations = results.apply(lambda row: explanation_for(row, notes), axis=1)
    results[["flagged", "matched_note_id", "reason"]] = pd.DataFrame(explanations.tolist(), index=results.index)
    output = pd.DataFrame({
        "route": results["route"],
        "week_of": results["week_of"].dt.strftime("%Y-%m-%d"),
        "cost_per_tonne_km": results["cost_per_tonne_km"].map(lambda value: f"{value:.2f}"),
        "vs_own_history": results["vs_own_history_percent"].map(_format_percent),
        "vs_similar_routes": results["vs_similar_routes_percent"].map(_format_percent),
        "flagged": results["flagged"],
        "matched_note_id": results["matched_note_id"],
        "reason": results["reason"],
    })
    return output.sort_values(["route", "week_of"], kind="stable").reset_index(drop=True)[OUTPUT_COLUMNS]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_output(output_path: Path, valid_note_ids: set[str] | None = None) -> dict:
    reopened = pd.read_csv(output_path, keep_default_na=False)
    if list(reopened.columns) != OUTPUT_COLUMNS:
        raise ValueError("Output schema does not match the required CSV contract.")
    if reopened.empty:
        raise ValueError("Output is empty.")
    if not reopened["route"].map(lambda value: isinstance(value, str) and bool(value.strip())).all():
        raise ValueError("Output contains blank route values.")
    parsed_dates = pd.to_datetime(reopened["week_of"], format="%Y-%m-%d", errors="coerce")
    if parsed_dates.isna().any() or not (parsed_dates.dt.strftime("%Y-%m-%d") == reopened["week_of"]).all():
        raise ValueError("Output week_of values must be ISO-formatted dates.")
    costs = pd.to_numeric(reopened["cost_per_tonne_km"], errors="coerce")
    if costs.isna().any() or ~np.isfinite(costs).all() or (costs < 0).any():
        raise ValueError("Output cost_per_tonne_km values must be finite non-negative numbers.")
    for column in ("vs_own_history", "vs_similar_routes"):
        invalid_percentages = reopened[column].map(lambda value: bool(value) and PERCENTAGE_PATTERN.fullmatch(value) is None)
        if invalid_percentages.any():
            raise ValueError(f"Output {column} values must be signed percentages or blank.")
    if not reopened["flagged"].isin(ALLOWED_VERDICTS).all():
        raise ValueError(f"Output contains invalid flagged values; expected {sorted(ALLOWED_VERDICTS)}.")
    supported = set(reopened.loc[reopened["flagged"] == "No (justified)", "matched_note_id"])
    if "" in supported:
        raise ValueError("A justified row is missing matched_note_id.")
    if (reopened.loc[reopened["flagged"] != "No (justified)", "matched_note_id"] != "").any():
        raise ValueError("Only justified rows may contain matched_note_id.")
    if valid_note_ids is not None and not supported <= valid_note_ids:
        raise ValueError("Output references note IDs that do not exist in context_notes.csv.")
    return {"output_rows": len(reopened), "columns": list(reopened.columns), "blank_note_ids": int((reopened["matched_note_id"] == "").sum())}


def run(shipment_path: Path, notes_path: Path, output_path: Path, threshold: float = 20.0) -> dict:
    loaded = load_inputs(shipment_path, notes_path)
    metrics = build_weekly_metrics(loaded.shipments, threshold)
    output = make_output(metrics, loaded.notes)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output.to_csv(output_path, index=False, lineterminator="\n")
    return {**loaded.quality_report, **validate_output(output_path, set(loaded.notes["note_id"])), "numerical_anomalies": int(metrics["numerical_anomaly"].sum()), "output_hash": sha256(output_path)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate evidence-grounded weekly freight cost analysis.")
    parser.add_argument("--shipments", type=Path, default=Path("data/shipment_records.csv"))
    parser.add_argument("--notes", type=Path, default=Path("data/context_notes.csv"))
    parser.add_argument("--output", type=Path, default=Path("outputs/freight_cost_analysis.csv"))
    parser.add_argument("--threshold", type=_parse_threshold, default=20.0)
    args = parser.parse_args()
    summary = run(args.shipments, args.notes, args.output, args.threshold)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
