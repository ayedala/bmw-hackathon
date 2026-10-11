# CRPS framework assessment

The supplied *BMW CRPS Scoring Framework* defines a seven-factor customer priority score. The application implements its proposed weights in a separate, versioned assessment (`crps-framework-v1`):

`0.25 impact + 0.20 evidence strength + 0.15 frequency + 0.15 market relevance + 0.10 competitive gap + 0.10 future relevance + 0.05 strategic fit`.

Evidence strength is calculated from `0.30 source quality + 0.25 independent source families + 0.20 consistency + 0.15 relevant volume + 0.10 recency`. All inputs are 0–100. The calculation is deterministic in Python (`src/bmw_pm/decision/crps.py`) and the web app (`web/lib/domain/crps.ts`); an LLM cannot set the final score by writing prose. The framework's worked example produces 88.35, P1 Critical. Bands are P1 ≥80, P2 ≥65, P3 ≥50, P4 ≥35, and P5 Watch below 35.

## Evidence rules

- Each rated input needs a reviewer explanation. Ratings based on source review also need source IDs or URLs.
- Unknown inputs retain their full weight as a 0–100 interval. A band is assigned only when every required input is rated. A partial result is a possible range, not a point estimate.
- Frequency requires a representative eligible population, requirement-matched count, source reference and explanation. Raw counts in the feedback corpus are not a prevalence estimate. The Python helper refuses to score frequency without the sampling conditions, and the web form requires a source-reviewed frequency rating.
- Source diversity counts independent source families, not pages or repeated comments. Contradiction is scored under consistency and does not automatically negate customer impact.
- Feasibility is recorded separately from customer priority. The suggested feasibility multiplier is omitted because it is not calibrated. The suggested decision-confidence percentage is also omitted because it reuses evidence-strength inputs and is not calibrated.
- The PDF's impact, market, future and competitive sub-rubrics are guidance for reviewer notes. Their underlying measurements are not available as validated inputs here, so no automatic values are synthesized from the present dataset.

The Next.js requirement workspace allows a reviewer to enter the factor vector, notes and references, preview the range, and save a versioned snapshot with an audit event. These assessments are stored in the browser-local overlay on that device; they are **not** shared through Supabase yet. A new requirement revision requires a new assessment. Existing four-factor scores and priority bands remain as **legacy planning estimates** for historical decisions; their weight controls do not change the framework assessments. The prioritization list displays both scores and continues to order by the legacy score until comparable framework assessments are available.

This score is an ordering aid. It does not measure revenue, guarantee shippability, or establish a release decision. A stronger result requires representative customer sampling, verified competitor comparisons, market and segment data, calibrated scoring rubrics, and validation against later decisions and outcomes.
