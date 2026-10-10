# First implementation task for Codex

Copy the following task into the coding chat when ready:

> Implement the first vertical slice of BMW Product Decision Lab in this repository. Read internal/AGENTS.md, docs/REPORT.md, docs/DATA_AUDIT.md, docs/DATA_CONTRACTS.md and internal/TASKS.md. We have a 24-hour total build window; prioritize evidence quality and reproducibility. Use the proposed Python/SQLite/Streamlit stack unless the existing environment or my instructions justify changing it.
>
> Start with T01–T03 and a small end-to-end G60 fixture. Keep raw sources immutable. Normalize feedback separately from supplied annotations; preserve stable IDs and exact row references. Reconcile the supplied counts and expose missing metadata. Implement study/sales adapters according to the actual layouts and a clearly labelled verified subset for equipment facts. Do not invent source identities, timestamps, powertrain sales, study sample sizes or engineering estimates.
>
> Define typed contracts, a run manifest and minimal persistence. Create meaningful tests for duplicate invariance, multi-need preservation, missingness, locators and idempotent import. Establish a grouped evaluation split before tuning prompts. Then extend the same path through structured extraction, validated requirements, deterministic policy scoring and PM review, in internal/TASKS.md order. Consult current official provider docs before API integration.
>
> Keep the core independent of the UI. Do not hardcode final recommendations or ranks. Do not build an autonomous-agent framework, vector database, fine-tuning pipeline or elaborate frontend without an evidenced need. Use cached output only with a visible replay label. Record what actually ran, its results and limitations in internal/TASKS.md. Work autonomously on reversible implementation steps already authorized; ask only for missing decisions that materially block progress.

This kickoff authorizes implementation only when the user sends it or otherwise asks to begin coding. The current preparation task itself requests documentation, not a completed application.
