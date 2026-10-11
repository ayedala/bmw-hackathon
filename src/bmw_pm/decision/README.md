# Deterministic requirement decisions

This module contains pure functions. Frozen validated inputs and policy versions reproduce the same customer requirement content and score arithmetic. Generated creation timestamps are metadata and do not make AI inference reproducible.

- `requirements.py` consolidates signals by need and customer outcome, applies vehicle/powertrain scope, preserves supporting and positive evidence, validates exact spans and counts unique feedback records.
- `scoring.py` computes criterion contributions and value intervals under a versioned policy. Missing inputs keep their weight. Ranking uses the lower bound and a stable requirement ID; overlapping intervals remain unresolved.

The application pipeline supplies inputs and persists results; these functions do not fetch sources, invoke a model, write a database or approve requirements. Source-quality classification in the web collector is a separate evidence-processing concern.

Read [the scoring policy explanation](../../../docs/DECISION_ENGINE.md). PM approval is mandatory before treating exploratory scores as an accepted product priority. Engineering feasibility remains a separate unknown/review input; component specifications, regulation and pricing are outside the customer requirement output.
