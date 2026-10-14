"""Create reproducibility, evaluation, and token-cost deliverables from actual executions."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from .analytics import build_weekly_metrics
from .load_data import load_inputs
from .note_retrieval import find_plausible_note, find_sufficient_note
from .pipeline import run, sha256


def main() -> None:
    root = Path.cwd()
    data_dir, output_dir = root / "data", root / "outputs"
    output_dir.mkdir(exist_ok=True)
    shipment_path, note_path = data_dir / "shipment_records.csv", data_dir / "context_notes.csv"
    run_paths = [output_dir / f"run{number}.csv" for number in range(1, 4)]
    summaries = [run(shipment_path, note_path, path) for path in run_paths]
    (output_dir / "freight_cost_analysis.csv").write_bytes(run_paths[0].read_bytes())
    hashes = [sha256(path) for path in run_paths]
    reproducibility = {
        "input_hashes": {"shipment_records.csv": sha256(shipment_path), "context_notes.csv": sha256(note_path)},
        "configuration": {"threshold_percent": 20.0, "own_history_weeks": 8, "week_start": "Monday", "hosted_llm": False},
        "run_status": ["success" for _ in run_paths],
        "output_hashes": dict(zip([path.name for path in run_paths], hashes)),
        "exact_comparison_results": {"run1_equals_run2": hashes[0] == hashes[1], "run2_equals_run3": hashes[1] == hashes[2], "all_identical": len(set(hashes)) == 1},
        "differences": [] if len(set(hashes)) == 1 else ["Output hashes differed; inspect run CSVs."],
    }
    (output_dir / "reproducibility_report.json").write_text(json.dumps(reproducibility, indent=2) + "\n", encoding="utf-8")
    notes = pd.read_csv(note_path, parse_dates=["date"])
    cases = [
        ("flood_supported", "Chennai-Bangalore", "2025-02-24", 31.5, 38.7, "N001", "N001"),
        ("flood_outside_window", "Chennai-Bangalore", "2025-03-10", 25.0, 30.0, None, None),
        ("festival_supported", "Ahmedabad-Mumbai", "2025-01-20", 29.5, 22.5, "N002", "N002"),
        ("diesel_before_effective_date", "Mumbai-Pune", "2025-04-28", 25.0, 25.0, None, None),
        ("diesel_plausible_but_insufficient_residual", "Mumbai-Pune", "2025-09-15", 9.2, 23.6, "N003", None),
        ("maintenance_negative", "Mumbai-Delhi", "2024-07-29", 25.0, 30.0, None, None),
        ("recovery_negative", "Chennai-Bangalore", "2025-03-17", 25.0, 30.0, None, None),
        ("wrong_route", "Delhi-Jaipur", "2025-02-24", 25.0, 30.0, None, None),
    ]
    details = []
    for name, route, week, own_change, peer_change, expected_plausible, expected_sufficient in cases:
        row = pd.Series({"route": route, "week_of": pd.Timestamp(week), "vs_own_history_percent": own_change, "vs_similar_routes_percent": peer_change})
        plausible = find_plausible_note(notes, route, pd.Timestamp(week))
        sufficient = find_sufficient_note(notes, row)
        actual_plausible = None if plausible is None else plausible.note_id
        actual_sufficient = None if sufficient is None else sufficient.note_id
        details.append({"case": name, "expected_plausible_note_id": expected_plausible, "actual_plausible_note_id": actual_plausible, "expected_sufficient_note_id": expected_sufficient, "actual_sufficient_note_id": actual_sufficient, "passed": actual_plausible == expected_plausible and actual_sufficient == expected_sufficient})
    evaluation = {"cases_evaluated": len(details), "passed": sum(item["passed"] for item in details), "failed": sum(not item["passed"] for item in details), "details": details}
    loaded = load_inputs(shipment_path, note_path)
    metrics = build_weekly_metrics(loaded.shipments)
    written_output = pd.read_csv(output_dir / "freight_cost_analysis.csv", keep_default_na=False)
    justified_audit = []
    for _, output_row in written_output.loc[written_output["flagged"] == "No (justified)"].iterrows():
        metric = metrics.loc[(metrics["route"] == output_row["route"]) & (metrics["week_of"].dt.strftime("%Y-%m-%d") == output_row["week_of"])].iloc[0]
        sufficient = find_sufficient_note(notes, metric)
        expected_note_id = None if sufficient is None else sufficient.note_id
        justified_audit.append({"route": output_row["route"], "week_of": output_row["week_of"], "matched_note_id": output_row["matched_note_id"], "expected_sufficient_note_id": expected_note_id, "passed": output_row["matched_note_id"] == expected_note_id})
    evaluation["justified_output_audit"] = {"rows_audited": len(justified_audit), "passed": sum(item["passed"] for item in justified_audit), "failed": sum(not item["passed"] for item in justified_audit), "details": justified_audit}
    (output_dir / "evaluation_results.json").write_text(json.dumps(evaluation, indent=2) + "\n", encoding="utf-8")
    token_log = {"model": None, "provider": None, "hosted_llm_calls": 0, "total_input_tokens": 0, "total_output_tokens": 0, "pricing_source_or_assumption": "No hosted LLM, embedding model, or paid API is used.", "estimated_total_cost": 0.0, "currency": "USD", "measurement_method": "Exact count of hosted calls in deterministic pipeline.", "counts_are": "actual", "local_retrieval": "Deterministic rule-based note filtering; no tokenized inference."}
    (output_dir / "token_cost_log.json").write_text(json.dumps(token_log, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"runs": summaries, "evaluation": evaluation, "reproducible": reproducibility["exact_comparison_results"]["all_identical"]}, indent=2))


if __name__ == "__main__":
    main()
