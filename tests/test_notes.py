import pandas as pd

from src.note_retrieval import find_qualifying_note


def notes(rows):
    frame = pd.DataFrame(rows, columns=["note_id", "date", "applies_to", "note"])
    frame["date"] = pd.to_datetime(frame["date"])
    return frame


def test_route_date_scope_and_negative_evidence_rules():
    data = notes([
        ["N1", "2025-02-24", "Chennai-Bangalore", "Flooding caused higher costs."],
        ["N2", "2025-02-24", "Mumbai-Delhi", "Flooding caused higher costs."],
        ["N3", "2025-02-24", "Chennai-Bangalore", "Costs were not significantly affected."],
    ])
    assert find_qualifying_note(data, "Chennai-Bangalore", pd.Timestamp("2025-02-24")).note_id == "N1"
    assert find_qualifying_note(data, "Chennai-Bangalore", pd.Timestamp("2025-03-17")) is None


def test_nationwide_note_can_apply_but_recovery_cannot():
    data = notes([
        ["N3", "2025-05-05", "All Routes", "Diesel prices rose nationwide, pushing up transportation costs."],
        ["N9", "2025-03-17", "Chennai-Bangalore", "Route returned to normal conditions after repairs."],
    ])
    assert find_qualifying_note(data, "Mumbai-Pune", pd.Timestamp("2025-05-12")).note_id == "N3"
    assert find_qualifying_note(data.iloc[[1]], "Chennai-Bangalore", pd.Timestamp("2025-03-17")) is None
