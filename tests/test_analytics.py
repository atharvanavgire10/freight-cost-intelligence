import pandas as pd
import pytest

from src.analytics import build_weekly_metrics, monday_of_week, percentage_change
from src.load_data import load_inputs


def shipments(rows):
    columns = ["shipment_id", "origin", "destination", "route_type", "material", "quantity_tonnes", "distance_km", "freight_cost_inr", "shipment_date", "transporter"]
    return pd.DataFrame(rows, columns=columns)


def test_monday_grouping_and_ratio_of_sums():
    data = shipments([["a", "A", "B", "Short", "x", 1, 10, 100, "2024-01-07", "t"], ["b", "A", "B", "Short", "x", 10, 10, 500, "2024-01-08", "t"], ["c", "A", "B", "Short", "x", 10, 10, 1000, "2024-01-08", "t"]])
    result = build_weekly_metrics(data)
    assert result.week_of.dt.strftime("%Y-%m-%d").tolist() == ["2024-01-01", "2024-01-08"]
    assert result.loc[1, "cost_per_tonne_km"] == pytest.approx(7.5)


def test_own_history_has_no_lookahead_and_uses_early_history():
    data = shipments([[str(index), "A", "B", "Short", "x", 1, 1, cost, f"2024-01-{1 + index * 7:02d}", "t"] for index, cost in enumerate([1, 2, 100])])
    result = build_weekly_metrics(data)
    assert pd.isna(result.loc[0, "own_history_baseline"])
    assert result.loc[1, "own_history_baseline"] == 1
    assert result.loc[2, "own_history_baseline"] == 1.5


def test_peer_excludes_current_route_and_missing_or_zero_baselines_are_blank():
    data = shipments([["a", "A", "B", "Short", "x", 1, 1, 10, "2024-01-01", "t"], ["b", "C", "D", "Short", "x", 1, 1, 20, "2024-01-01", "t"], ["c", "E", "F", "Long", "x", 1, 1, 20, "2024-01-01", "t"]])
    result = build_weekly_metrics(data)
    assert result.loc[result.route == "A-B", "similar_route_baseline"].iloc[0] == 20
    assert pd.isna(result.loc[result.route == "E-F", "similar_route_baseline"].iloc[0])
    assert pd.isna(percentage_change(10, 0))


def test_invalid_input_is_rejected_and_reported(tmp_path):
    shipment = tmp_path / "shipment.csv"
    notes = tmp_path / "notes.csv"
    shipments([["a", "A", "B", "Short", "x", 0, 1, 1, "2024-01-01", "t"]]).to_csv(shipment, index=False)
    pd.DataFrame([["N", "2024-01-01", "All Routes", "costs rose"]], columns=["note_id", "date", "applies_to", "note"]).to_csv(notes, index=False)
    with pytest.raises(ValueError, match="Invalid shipment"):
        load_inputs(shipment, notes)
