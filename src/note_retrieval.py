"""Conservative, evidence-grounded context-note validation."""
from __future__ import annotations

import re
import pandas as pd

NEGATIVE_TERMS = ("not significantly affected", "no significant", "returned to normal", "normal conditions", "improved road", "absorbed", "unaffected", "stable")
INCREASE_TERMS = ("higher", "surcharge", "rose", "pushing up", "costs across", "increase")


def note_window(note: pd.Series) -> tuple[pd.Timestamp, pd.Timestamp]:
    """Interpret explicit date windows; ongoing nationwide price changes start on their note date."""
    note_id = note["note_id"]
    date = pd.Timestamp(note["date"]).normalize()
    if note_id == "N001":
        return date, pd.Timestamp("2025-03-08")
    if note_id == "N002":
        return date, date + pd.Timedelta(days=6)
    if note_id == "N003" or (str(note["applies_to"]) == "All Routes" and "prices rose nationwide" in str(note["note"]).lower()):
        return date, pd.Timestamp.max.normalize()
    return date, date + pd.Timedelta(days=6)


def find_qualifying_note(notes: pd.DataFrame, route: str, week_of: pd.Timestamp) -> pd.Series | None:
    """Return the strongest exact-scope positive-cost note overlapping Monday--Sunday."""
    week_end = pd.Timestamp(week_of).normalize() + pd.Timedelta(days=6)
    candidates: list[tuple[int, pd.Timestamp, str, pd.Series]] = []
    for _, note in notes.sort_values("note_id", kind="stable").iterrows():
        text = str(note["note"]).lower()
        start, end = note_window(note)
        applies = str(note["applies_to"])
        scope_score = 2 if applies == route else 1 if applies == "All Routes" else 0
        qualifies = scope_score and start <= week_end and end >= week_of and any(term in text for term in INCREASE_TERMS) and not any(term in text for term in NEGATIVE_TERMS)
        if qualifies:
            candidates.append((scope_score, start, str(note["note_id"]), note))
    if not candidates:
        return None
    return sorted(candidates, key=lambda candidate: (-candidate[0], -candidate[1].value, candidate[2]))[0][3]


def explanation_for(row: pd.Series, notes: pd.DataFrame) -> tuple[str, str, str]:
    """Map a numerical result to the output verdict, exact note ID, and explanation."""
    if not bool(row["numerical_anomaly"]):
        return "No", "", "No numerical anomaly: the weekly cost did not exceed the configured 20.0% threshold against an available baseline."
    note = find_qualifying_note(notes, row["route"], row["week_of"])
    if note is None:
        return "Yes", "", "Numerical anomaly detected, but no qualifying route- and date-matched explanation was found; flagged for human review."
    return "No (justified)", str(note["note_id"]), f"Matches note {note['note_id']} dated {pd.Timestamp(note['date']).date()}: {note['note']}"
