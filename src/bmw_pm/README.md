# Application modules

The application is organized by responsibility. Start with `pipeline.py` for the end-to-end flow and `contracts.py` for the shared data shapes.

| Module | Responsibility | Boundary |
|---|---|---|
| [data_pipeline](data_pipeline/README.md) | Search, retrieve, parse, clean and preserve evidence | Never approves or prioritizes requirements |
| [intelligence](intelligence/README.md) | Extract customer signals using a bounded model or a labelled baseline | Never supplies trusted score arithmetic |
| [decision](decision/README.md) | Consolidate validated signals and calculate explainable priorities | Pure functions; no network or database writes |
| [review](review/README.md) | PM approval, rejection, edits and challenges | Human rationale and expected revision required |
| [storage](storage/README.md) | Persist sources, revisions, scores, decisions and audit events | Transactions and immutable history |

`cli.py` exposes these services. `pipeline.py` coordinates them. `validation.py` checks stored invariants. `hosting.py` provides bounded deployment helpers. `utils.py` holds core hashing, timestamps and text redaction. Shared contracts remain at package level to avoid making one module own another module's schema.

AI performs extraction only in the current core implementation. Requirement consolidation and prioritization are deterministic. The optional collectors are independent source-checkout tools with their own dependencies; they are excluded from the core wheel and Docker image.
