import pandas as pd

from src.note_retrieval import evidence_gap, find_plausible_note, find_sufficient_note


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
    assert find_plausible_note(data, "Chennai-Bangalore", pd.Timestamp("2025-02-24")).note_id == "N1"
    assert find_plausible_note(data, "Chennai-Bangalore", pd.Timestamp("2025-03-17")) is None


def test_nationwide_note_is_plausible_only_after_its_effective_date_and_recovery_cannot_apply():
    data = notes([
        ["N3", "2025-05-05", "All Routes", "Diesel prices rose nationwide starting this week, pushing up transportation costs."],
        ["N9", "2025-03-17", "Chennai-Bangalore", "Route returned to normal conditions after repairs."],
    ])
    assert find_plausible_note(data, "Mumbai-Pune", pd.Timestamp("2025-05-12")).note_id == "N3"
    assert find_plausible_note(data, "Mumbai-Pune", pd.Timestamp("2025-04-28")) is None
    assert find_plausible_note(data.iloc[[1]], "Chennai-Bangalore", pd.Timestamp("2025-03-17")) is None


def test_nationwide_small_driver_is_not_sufficient_for_large_route_residual():
    data = notes([["N3", "2025-05-05", "All Routes", "Diesel prices rose nationwide starting this week, pushing up transportation costs across all routes by roughly 5-7%."]])
    row = pd.Series({"route": "Mumbai-Pune", "week_of": pd.Timestamp("2025-09-15"), "vs_own_history_percent": 9.2, "vs_similar_routes_percent": 23.6})
    plausible = find_plausible_note(data, row.route, row.week_of)
    assert plausible.note_id == "N3"
    assert find_sufficient_note(data, row) is None
    assert "at most about 7%" in evidence_gap(plausible, row)


def test_nationwide_note_without_an_impact_estimate_is_not_sufficient():
    data = notes([["nationwide", "2025-05-05", "All Routes", "Fuel costs rose nationwide starting this week, pushing up transportation costs."]])
    row = pd.Series({"route": "Mumbai-Pune", "week_of": pd.Timestamp("2025-05-12"), "vs_own_history_percent": 25.0, "vs_similar_routes_percent": 21.0})
    plausible = find_plausible_note(data, row.route, row.week_of)
    assert plausible.note_id == "nationwide"
    assert find_sufficient_note(data, row) is None
    assert "does not quantify" in evidence_gap(plausible, row)


def test_explicit_event_window_includes_end_date_and_excludes_next_day():
    data = notes([["flood", "2025-02-24", "Chennai-Bangalore", "Flooding caused higher costs from Feb 24 to Mar 8."]])
    assert find_plausible_note(data, "Chennai-Bangalore", pd.Timestamp("2025-03-03")).note_id == "flood"
    assert find_plausible_note(data, "Chennai-Bangalore", pd.Timestamp("2025-03-09")) is None


def test_exact_route_surcharge_is_sufficient_when_note_has_no_contradiction():
    data = notes([["N2", "2025-01-20", "Ahmedabad-Mumbai", "A temporary surcharge applied by transporters on the Ahmedabad-Mumbai corridor due to high demand."]])
    row = pd.Series({"route": "Ahmedabad-Mumbai", "week_of": pd.Timestamp("2025-01-20"), "vs_own_history_percent": 29.5, "vs_similar_routes_percent": 22.5})
    assert find_sufficient_note(data, row).note_id == "N2"


def test_conflicting_overlapping_evidence_blocks_justified_verdict():
    data = notes([
        ["positive", "2025-01-20", "A-B", "A surcharge caused higher costs on this corridor."],
        ["negative", "2025-01-20", "A-B", "Costs were not significantly affected during this period."],
    ])
    row = pd.Series({"route": "A-B", "week_of": pd.Timestamp("2025-01-20"), "vs_own_history_percent": 25.0, "vs_similar_routes_percent": 22.0})
    assert find_sufficient_note(data, row) is None
