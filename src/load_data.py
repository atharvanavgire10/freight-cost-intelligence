"""Input loading and validation."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

REQUIRED_SHIPMENT_COLUMNS = {
    "shipment_id", "origin", "destination", "route_type", "material",
    "quantity_tonnes", "distance_km", "freight_cost_inr", "shipment_date", "transporter",
}
REQUIRED_NOTE_COLUMNS = {"note_id", "date", "applies_to", "note"}
VALID_ROUTE_TYPES = {"Short", "Medium", "Long"}


@dataclass(frozen=True)
class LoadedData:
    shipments: pd.DataFrame
    notes: pd.DataFrame
    quality_report: dict


def _require_columns(frame: pd.DataFrame, required: set[str], name: str) -> None:
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"{name} is missing required columns: {sorted(missing)}")


def load_inputs(shipment_path: Path, notes_path: Path) -> LoadedData:
    """Load source data without mutating it and reject invalid shipment rows."""
    if not shipment_path.exists() or not notes_path.exists():
        raise FileNotFoundError("Both shipment_records.csv and context_notes.csv are required.")
    shipments = pd.read_csv(shipment_path)
    notes = pd.read_csv(notes_path)
    _require_columns(shipments, REQUIRED_SHIPMENT_COLUMNS, "shipment_records.csv")
    _require_columns(notes, REQUIRED_NOTE_COLUMNS, "context_notes.csv")
    shipments = shipments.copy()
    notes = notes.copy()
    shipments["shipment_date"] = pd.to_datetime(shipments["shipment_date"], errors="coerce")
    notes["date"] = pd.to_datetime(notes["date"], errors="coerce")
    numeric_columns = ["quantity_tonnes", "distance_km", "freight_cost_inr"]
    for column in numeric_columns:
        shipments[column] = pd.to_numeric(shipments[column], errors="coerce")
    invalid = (
        shipments["shipment_date"].isna()
        | shipments[list(REQUIRED_SHIPMENT_COLUMNS - set(numeric_columns) - {"shipment_date"})].isna().any(axis=1)
        | shipments[numeric_columns].isna().any(axis=1)
        | (shipments["quantity_tonnes"] <= 0)
        | (shipments["distance_km"] <= 0)
        | (shipments["freight_cost_inr"] < 0)
        | ~shipments["route_type"].isin(VALID_ROUTE_TYPES)
    )
    report = {
        "shipment_rows_read": int(len(shipments)),
        "note_rows_read": int(len(notes)),
        "invalid_shipment_rows": int(invalid.sum()),
        "missing_values": {column: int(value) for column, value in shipments.isna().sum().items()},
    }
    if invalid.any():
        examples = shipments.index[invalid].tolist()[:10]
        raise ValueError(f"Invalid shipment records at CSV row indexes {examples}; no records were discarded.")
    if notes[["note_id", "date", "applies_to", "note"]].isna().any().any():
        raise ValueError("context_notes.csv contains missing required values.")
    return LoadedData(shipments=shipments, notes=notes, quality_report=report)
