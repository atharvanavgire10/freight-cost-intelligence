# FreightTiger Smart Freight Cost Intelligence

An evidence-grounded Python pipeline for weekly freight-cost anomaly detection. It calculates deterministic route-week benchmarks, identifies material cost increases, and only marks an increase as justified when a supplied context note explicitly supports the route, timing, and positive cost impact.

## Quick start

Requires Python 3.11+ (developed and verified locally with Python 3.14):

```powershell
py -3 -m pip install -r requirements.txt
py -3 -m src.pipeline
py -3 -m src.validate_submission
py -3 -m pytest -q
```

`python -m src.pipeline` works equivalently on environments where `python` resolves to Python 3.11 or newer. Use `--output path/to/file.csv` or `--threshold 25` to override defaults.

## Data flow

`data/shipment_records.csv` and `data/context_notes.csv` → schema/data-quality validation → Monday-based route-week aggregation → own-history and same-week peer comparisons → threshold detection → conservative note retrieval/validation → `outputs/freight_cost_analysis.csv`.

The supplied input CSVs are copied unchanged into `data/`. The source dataset has 2,940 shipments from 2024-01-01 through 2025-12-28 and 10 context notes. It contains no missing fields or invalid quantities, distances, or non-negative cost violations.

## Method

Route identity is `(origin, destination, route_type)`, preserving direction and the supplied `Short`, `Medium`, and `Long` categories. `week_of` is the Monday of the shipment's Monday--Sunday week.

For each route-week:

```text
cost_per_tonne_km = sum(freight_cost_inr) / sum(quantity_tonnes * distance_km)
```

This is a ratio of aggregates, never an unweighted average of shipment ratios. Input is stably sorted before calculations.

The own-history baseline is the mean of up to eight prior observations for the same route. The current week is shifted out first, so there is no look-ahead. Early observations use all available prior weeks; they are not padded or forecast. The similar-route baseline is the same-week mean for all *other* routes with the same `route_type`. A missing, zero, or invalid baseline produces a blank percentage, never zero or infinity.

Percentage comparisons use `100 * (current / baseline - 1)`. The documented implementation assumption is an anomaly threshold of **20% above either available baseline**. This is configurable with `--threshold` and is not represented as an official FreightTiger policy.

## Evidence validation

Retrieval is intentionally lightweight and local. It first finds notes that are plausible cost drivers by validating route scope, effective-window overlap, positive cost-impact wording, and exclusion terms. It then applies a separate sufficiency check before issuing a justified verdict. Route-specific evidence outranks nationwide evidence, then ties resolve by newest effective date and note ID. Effective windows are parsed from note language (explicit date ranges, one-week events, and “starting this week”), not from note IDs.

Notes describing unaffected costs, absorbed costs, stable conditions, improved conditions, or recovery are never evidence for an increase. Therefore toll, maintenance, recovery, and stable-demand notes cannot justify a verdict. Semantic similarity by itself is not evidence. A nationwide note can identify a general driver, but it is not proof of a route-specific premium. When a note states a maximum impact, the pipeline will not use it to justify a larger observed increase; it leaves the residual unexplained instead of inventing a causal allocation.

Verdicts are deliberately separate from numerical detection:

- `No`: no numerical anomaly.
- `No (justified)`: anomaly with qualifying evidence and an exact `matched_note_id`.
- `Yes`: anomaly without qualifying evidence; it remains for human review with a blank `matched_note_id`.

## Output contract

`outputs/freight_cost_analysis.csv` contains exactly these columns, in order:

```text
route,week_of,cost_per_tonne_km,vs_own_history,vs_similar_routes,flagged,matched_note_id,reason
```

Dates are ISO dates; numeric display rounds cost to two decimals and percentages to one decimal only at writing time. Missing comparisons and unsupported note IDs are empty strings. CSV output uses Python/pandas CSV quoting, so comma-containing reasons remain valid.

## Validation results

The checked-in run generated 728 route-week rows, with 20 numerical anomalies. Three rows are justified by direct, in-window route evidence (one Ahmedabad--Mumbai surcharge and two Chennai--Bangalore flood weeks); the 13 Mumbai--Pune N003 rows are flagged for review because its stated 5--7% nationwide effect does not establish their 20.6--38.9% peer premiums. `pytest -q` completed with **9 passed** tests. These cover Monday/Sunday boundaries, ratio-of-sums aggregation, no look-ahead history, early-history behavior, peer exclusion, missing/zero baselines, invalid data, N003 effective date and nationwide scope, the plausible-versus-sufficient distinction, negative/recovery evidence, output mapping, and deterministic output.

`outputs/evaluation_results.json` contains 8 manually reviewed evidence cases, including N003 before its effective date and an N003 plausible-but-insufficient residual. Actual fixture result: **8 passed, 0 failed**. It also audits every justified output row against the current route/date/scope/sufficiency logic.

`python -m src.validate_submission` performed three untouched full pipeline runs. All generated a SHA-256 of `b106515b342a62d23bd2e7b4ae2a5cc5669ed43b9fa486476f2e4a047dbd6073`; the exact comparison result is true for every pair. Full input/output hashes and configuration are in `outputs/reproducibility_report.json`.

## Cost and limitations

No hosted LLM, embedding model, vector database, or paid API is used. The deterministic core has **0 hosted LLM calls, 0 input tokens, 0 output tokens, and USD 0.00** hosted-model cost; this is an actual call count, not an estimate. `outputs/token_cost_log.json` records this explicitly.

The system does not claim causation or fraud. It only identifies large relative increases and classifies whether the limited supplied notes qualify as a plausible documented explanation. Production improvements could add reviewer feedback, source provenance, richer date-window metadata, robust outlier statistics, and authenticated retrieval over a maintained event corpus.

## Repository layout

```text
data/       supplied input CSVs, unchanged
src/        validation, analytics, note validation, CLI, report generation
tests/      automated regression tests
outputs/    final CSV, three runs, evaluation, reproducibility, and token-cost reports
```

## 10-minute walkthrough

1. State the business goal: find unusual route-week cost rises without inventing causes.
2. Show the input contract and the validation policy that rejects bad shipments rather than silently dropping them.
3. Walk through Monday grouping and ratio-of-sums cost calculation.
4. Explain the two exact baselines and demonstrate the `shift(1)` that prevents future leakage.
5. Show the 20% configurable detection threshold and the distinction between anomaly and final verdict.
6. Demonstrate conservative note matching with flood, festival, diesel, maintenance, and recovery examples.
7. Open the final CSV and explain its evidence IDs and blank unsupported IDs.
8. Run tests and point to the seven-case evaluation report.
9. Run the three-run reproducibility command and explain exact SHA-256 matching.
10. Close with trade-offs: transparent deterministic retrieval, zero API cost, and clearly bounded causal claims.
