"""Conservative, evidence-grounded context-note retrieval and validation."""
from __future__ import annotations

import re

import pandas as pd

NEGATIVE_TERMS = ("not significantly affected", "no significant", "returned to normal", "normal conditions", "improved road", "absorbed", "unaffected", "stable")
INCREASE_TERMS = ("higher", "surcharge", "rose", "pushing up", "costs across", "increase")
MONTHS = {name: number for number, name in enumerate(("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), start=1)}


def note_window(note: pd.Series) -> tuple[pd.Timestamp, pd.Timestamp]:
    """Derive an effective window from note wording without using note IDs."""
    date = pd.Timestamp(note["date"]).normalize()
    text = str(note["note"]).lower()
    explicit_range = re.search(r"from\s+([a-z]{3,9})\s+(\d{1,2})\s+to\s+([a-z]{3,9})\s+(\d{1,2})", text)
    if explicit_range:
        start_month, start_day, end_month, end_day = explicit_range.groups()
        start = pd.Timestamp(year=date.year, month=MONTHS[start_month[:3]], day=int(start_day))
        end_year = date.year + int(MONTHS[end_month[:3]] < MONTHS[start_month[:3]])
        return start, pd.Timestamp(year=end_year, month=MONTHS[end_month[:3]], day=int(end_day))
    if "starting this week" in text:
        return date, pd.Timestamp.max.normalize()
    return date, date + pd.Timedelta(days=6)


def stated_maximum_impact_percent(note: pd.Series) -> float | None:
    """Return an explicitly stated percentage ceiling, if the note gives one."""
    text = str(note["note"]).lower()
    match = re.search(r"(?:roughly|about|approximately|up to)?\s*(\d+(?:\.\d+)?)\s*(?:-|to)\s*(\d+(?:\.\d+)?)\s*%", text)
    if match:
        return float(match.group(2))
    single = re.search(r"(?:roughly|about|approximately|up to)?\s*(\d+(?:\.\d+)?)\s*%", text)
    return float(single.group(1)) if single else None


def find_plausible_note(notes: pd.DataFrame, route: str, week_of: pd.Timestamp) -> pd.Series | None:
    """Retrieve the strongest note that could be a cost driver for this route-week."""
    week_of = pd.Timestamp(week_of).normalize()
    week_end = week_of + pd.Timedelta(days=6)
    candidates: list[tuple[int, pd.Timestamp, str, pd.Series]] = []
    for _, note in notes.sort_values("note_id", kind="stable").iterrows():
        text = str(note["note"]).lower()
        start, end = note_window(note)
        applies = str(note["applies_to"])
        scope_score = 2 if applies == route else 1 if applies == "All Routes" else 0
        is_positive = any(term in text for term in INCREASE_TERMS)
        is_contradicted = any(term in text for term in NEGATIVE_TERMS)
        if scope_score and start <= week_end and end >= week_of and is_positive and not is_contradicted:
            candidates.append((scope_score, start, str(note["note_id"]), note))
    if not candidates:
        return None
    return sorted(candidates, key=lambda candidate: (-candidate[0], -candidate[1].value, candidate[2]))[0][3]


def has_conflicting_note(notes: pd.DataFrame, route: str, week_of: pd.Timestamp, selected_note_id: str) -> bool:
    """Detect an overlapping applicable note that explicitly contradicts a cost increase."""
    week_of = pd.Timestamp(week_of).normalize()
    week_end = week_of + pd.Timedelta(days=6)
    for _, note in notes.iterrows():
        if str(note["note_id"]) == selected_note_id or str(note["applies_to"]) not in {route, "All Routes"}:
            continue
        start, end = note_window(note)
        if start <= week_end and end >= week_of and any(term in str(note["note"]).lower() for term in NEGATIVE_TERMS):
            return True
    return False


def _positive_changes(row: pd.Series) -> list[float]:
    return [float(value) for value in (row.get("vs_own_history_percent"), row.get("vs_similar_routes_percent")) if value is not None and not pd.isna(value) and value > 0]


def evidence_gap(note: pd.Series, row: pd.Series, notes: pd.DataFrame | None = None) -> str | None:
    """Return why a plausible note cannot prove this anomaly, else ``None``."""
    stated_maximum = stated_maximum_impact_percent(note)
    observed = _positive_changes(row)
    if notes is not None and has_conflicting_note(notes, str(row["route"]), pd.Timestamp(row["week_of"]), str(note["note_id"])):
        return "an overlapping applicable note explicitly says costs were unaffected or normal"
    if str(note["applies_to"]) == "All Routes":
        if stated_maximum is None:
            return "the nationwide note does not quantify an impact large enough to explain this route-specific anomaly"
        observed_maximum = max(observed, default=0.0)
        if observed_maximum > stated_maximum:
            return f"the note states at most about {stated_maximum:g}%, below the observed +{observed_maximum:.1f}% increase"
        return "the nationwide note identifies a general driver but does not establish a route-specific cause"
    if stated_maximum is not None and max(observed, default=0.0) > stated_maximum:
        return f"the note states at most about {stated_maximum:g}%, below the observed +{max(observed):.1f}% increase"
    return None


def find_sufficient_note(notes: pd.DataFrame, row: pd.Series) -> pd.Series | None:
    """Return evidence that is plausible *and* sufficient for a justified verdict."""
    note = find_plausible_note(notes, str(row["route"]), pd.Timestamp(row["week_of"]))
    return note if note is not None and evidence_gap(note, row, notes) is None else None


def explanation_for(row: pd.Series, notes: pd.DataFrame) -> tuple[str, str, str]:
    """Map a numerical anomaly to a deterministic, evidence-bounded output verdict."""
    if not bool(row["numerical_anomaly"]):
        return "No", "", "No numerical anomaly: the weekly cost did not exceed the configured 20.0% threshold against an available baseline."
    plausible = find_plausible_note(notes, str(row["route"]), pd.Timestamp(row["week_of"]))
    sufficient = find_sufficient_note(notes, row)
    if sufficient is not None:
        return "No (justified)", str(sufficient["note_id"]), f"Matches note {sufficient['note_id']} dated {pd.Timestamp(sufficient['date']).date()}: {sufficient['note']}"
    if plausible is not None:
        return "Yes", "", f"Note {plausible['note_id']} is a plausible cost driver, but it is insufficient to justify this anomaly: {evidence_gap(plausible, row, notes)}. Flagged for human review."
    return "Yes", "", "Numerical anomaly detected, but no route- and date-matched explanation was found; flagged for human review."
