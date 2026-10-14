"""CLI for FreightTiger Smart Freight Cost Intelligence."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

from .analytics import build_weekly_metrics
from .load_data import load_inputs
from .note_retrieval import explanation_for

OUTPUT_COLUMNS = ["route", "week_of", "cost_per_tonne_km", "vs_own_history", "vs_similar_routes", "flagged", "matched_note_id", "reason"]


def _format_percent(value: float) -> str:
    return "" if pd.isna(value) else f"{value:+.1f}%"


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


def validate_output(output_path: Path) -> dict:
    reopened = pd.read_csv(output_path, keep_default_na=False)
    if list(reopened.columns) != OUTPUT_COLUMNS:
        raise ValueError("Output schema does not match the required CSV contract.")
    if reopened.empty:
        raise ValueError("Output is empty.")
    supported = set(reopened.loc[reopened["flagged"] == "No (justified)", "matched_note_id"])
    if "" in supported:
        raise ValueError("A justified row is missing matched_note_id.")
    return {"output_rows": len(reopened), "columns": list(reopened.columns), "blank_note_ids": int((reopened["matched_note_id"] == "").sum())}


def run(shipment_path: Path, notes_path: Path, output_path: Path, threshold: float = 20.0) -> dict:
    loaded = load_inputs(shipment_path, notes_path)
    metrics = build_weekly_metrics(loaded.shipments, threshold)
    output = make_output(metrics, loaded.notes)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output.to_csv(output_path, index=False, lineterminator="\n")
    return {**loaded.quality_report, **validate_output(output_path), "numerical_anomalies": int(metrics["numerical_anomaly"].sum()), "output_hash": sha256(output_path)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate evidence-grounded weekly freight cost analysis.")
    parser.add_argument("--shipments", type=Path, default=Path("data/shipment_records.csv"))
    parser.add_argument("--notes", type=Path, default=Path("data/context_notes.csv"))
    parser.add_argument("--output", type=Path, default=Path("outputs/freight_cost_analysis.csv"))
    parser.add_argument("--threshold", type=float, default=20.0)
    args = parser.parse_args()
    summary = run(args.shipments, args.notes, args.output, args.threshold)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
