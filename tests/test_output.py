import pandas as pd

from src.pipeline import OUTPUT_COLUMNS, make_output, run


def test_output_schema_reason_and_determinism(tmp_path):
    shipments = tmp_path / "shipments.csv"
    notes = tmp_path / "notes.csv"
    pd.DataFrame([
        ["a", "A", "B", "Short", "x", 1, 1, 1, "2024-01-01", "t"],
        ["b", "A", "B", "Short", "x", 1, 1, 2, "2024-01-08", "t"],
        ["c", "C", "D", "Short", "x", 1, 1, 1, "2024-01-08", "t"],
    ], columns=["shipment_id", "origin", "destination", "route_type", "material", "quantity_tonnes", "distance_km", "freight_cost_inr", "shipment_date", "transporter"]).to_csv(shipments, index=False)
    pd.DataFrame([["N", "2024-01-08", "A-B", "A surcharge caused higher costs."]], columns=["note_id", "date", "applies_to", "note"]).to_csv(notes, index=False)
    first, second = tmp_path / "first.csv", tmp_path / "second.csv"
    run(shipments, notes, first)
    run(shipments, notes, second)
    result = pd.read_csv(first, keep_default_na=False)
    assert list(result.columns) == OUTPUT_COLUMNS
    assert result.loc[result.week_of == "2024-01-08", "flagged"].iloc[0] == "No (justified)"
    assert first.read_bytes() == second.read_bytes()
