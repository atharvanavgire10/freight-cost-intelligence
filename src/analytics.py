"""Deterministic weekly freight-cost analytics."""
from __future__ import annotations

import numpy as np
import pandas as pd

ROUTE_KEYS = ["origin", "destination", "route_type"]


def validate_threshold(threshold_percent: float) -> float:
    """Validate the configurable increase threshold before calculations begin."""
    try:
        threshold = float(threshold_percent)
    except (TypeError, ValueError) as error:
        raise ValueError("threshold must be a finite non-negative percentage") from error
    if not np.isfinite(threshold) or threshold < 0:
        raise ValueError("threshold must be a finite non-negative percentage")
    return threshold


def monday_of_week(dates: pd.Series) -> pd.Series:
    normalized = pd.to_datetime(dates, errors="raise").dt.normalize()
    return normalized - pd.to_timedelta(normalized.dt.weekday, unit="D")


def percentage_change(current: float, baseline: float | None) -> float:
    if baseline is None or pd.isna(baseline) or baseline <= 0 or pd.isna(current):
        return np.nan
    return 100.0 * (current / baseline - 1.0)


def build_weekly_metrics(shipments: pd.DataFrame, threshold_percent: float = 20.0) -> pd.DataFrame:
    """Aggregate weekly costs and calculate no-look-ahead own and peer comparisons."""
    threshold_percent = validate_threshold(threshold_percent)
    data = shipments.copy()
    data["week_of"] = monday_of_week(data["shipment_date"])
    data["tonne_km"] = data["quantity_tonnes"] * data["distance_km"]
    data = data.sort_values(ROUTE_KEYS + ["week_of", "shipment_date", "shipment_id"], kind="stable")
    weekly = data.groupby(ROUTE_KEYS + ["week_of"], as_index=False, sort=True).agg(
        freight_cost=("freight_cost_inr", "sum"), tonne_km=("tonne_km", "sum")
    )
    weekly["cost_per_tonne_km"] = weekly["freight_cost"] / weekly["tonne_km"]
    weekly["route"] = weekly["origin"] + "-" + weekly["destination"]
    weekly = weekly.sort_values(ROUTE_KEYS + ["week_of"], kind="stable").reset_index(drop=True)
    weekly["own_history_baseline"] = weekly.groupby(ROUTE_KEYS, sort=False)["cost_per_tonne_km"].transform(
        lambda values: values.shift(1).rolling(window=8, min_periods=1).mean()
    )
    peer_sum = weekly.groupby(["route_type", "week_of"])["cost_per_tonne_km"].transform("sum") - weekly["cost_per_tonne_km"]
    peer_count = weekly.groupby(["route_type", "week_of"])["cost_per_tonne_km"].transform("count") - 1
    weekly["similar_route_baseline"] = peer_sum / peer_count.where(peer_count > 0)
    weekly["vs_own_history_percent"] = [percentage_change(current, baseline) for current, baseline in zip(weekly["cost_per_tonne_km"], weekly["own_history_baseline"])]
    weekly["vs_similar_routes_percent"] = [percentage_change(current, baseline) for current, baseline in zip(weekly["cost_per_tonne_km"], weekly["similar_route_baseline"])]
    weekly["numerical_anomaly"] = (weekly["vs_own_history_percent"] >= threshold_percent) | (weekly["vs_similar_routes_percent"] >= threshold_percent)
    return weekly
