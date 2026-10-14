"""Create reproducibility, evaluation, and token-cost deliverables from actual executions."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from .analytics import build_weekly_metrics
from .note_retrieval import find_qualifying_note
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
        ("flood_supported", "Chennai-Bangalore", "2025-02-24", "N001"),
        ("flood_outside_window", "Chennai-Bangalore", "2025-03-10", None),
        ("festival_supported", "Ahmedabad-Mumbai", "2025-01-20", "N002"),
        ("nationwide_supported", "Mumbai-Pune", "2025-05-12", "N003"),
        ("maintenance_negative", "Mumbai-Delhi", "2024-07-29", None),
        ("recovery_negative", "Chennai-Bangalore", "2025-03-17", None),
        ("wrong_route", "Delhi-Jaipur", "2025-02-24", None),
    ]
    details = []
    for name, route, week, expected in cases:
        found = find_qualifying_note(notes, route, pd.Timestamp(week))
        actual = None if found is None else found.note_id
        details.append({"case": name, "expected_note_id": expected, "actual_note_id": actual, "passed": actual == expected})
    evaluation = {"cases_evaluated": len(details), "passed": sum(item["passed"] for item in details), "failed": sum(not item["passed"] for item in details), "details": details}
    (output_dir / "evaluation_results.json").write_text(json.dumps(evaluation, indent=2) + "\n", encoding="utf-8")
    token_log = {"model": None, "provider": None, "hosted_llm_calls": 0, "total_input_tokens": 0, "total_output_tokens": 0, "pricing_source_or_assumption": "No hosted LLM, embedding model, or paid API is used.", "estimated_total_cost": 0.0, "currency": "USD", "measurement_method": "Exact count of hosted calls in deterministic pipeline.", "counts_are": "actual", "local_retrieval": "Deterministic rule-based note filtering; no tokenized inference."}
    (output_dir / "token_cost_log.json").write_text(json.dumps(token_log, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"runs": summaries, "evaluation": evaluation, "reproducible": reproducibility["exact_comparison_results"]["all_identical"]}, indent=2))


if __name__ == "__main__":
    main()
