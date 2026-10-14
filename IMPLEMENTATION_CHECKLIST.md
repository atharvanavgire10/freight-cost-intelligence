# Implementation Checklist

- [x] Validate original shipment and note schemas; reject invalid shipment rows without dropping them.
- [x] Aggregate Monday-based route-weeks using the ratio of total cost to total tonne-kilometres.
- [x] Calculate strictly prior eight-week own history and same-week, route-type peer baselines.
- [x] Detect configurable 20% increases, validate contextual evidence, and emit the required CSV contract.
- [x] Test arithmetic, leakage prevention, data quality, note scope/date/negative evidence, and deterministic output.
- [x] Run evaluation plus three exact reproducibility runs and save their reports.
