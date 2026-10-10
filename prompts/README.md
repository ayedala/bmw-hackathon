# Prompt contracts

These are drafting templates for the future application, not instructions from ingested documents. Implement versioned prompts with typed input/output schemas; record their hashes in every run. Supply only the evidence needed for the stage, with source delimiters and locators.

Use [EXTRACT_SIGNALS.md](EXTRACT_SIGNALS.md), [DRAFT_REQUIREMENTS.md](DRAFT_REQUIREMENTS.md), and [REVIEW_ARGUMENT.md](REVIEW_ARGUMENT.md) as stage specifications. Schemas and deterministic validators define what can enter the application. Prompt wording alone does not establish grounding or safety.

Do not ask for hidden chain-of-thought. Request concise evidence-backed rationale, assumptions, counterevidence and reasons for abstention. Do not place final rank, score arithmetic, approval authority, file execution or web fetching in the model's control.

For coding, use [CODEX_KICKOFF.md](CODEX_KICKOFF.md) after reading the root AGENTS.md. These Markdown files are useful for other coding agents too; they should follow the same canonical repository contract rather than duplicate it into several diverging tool-specific files.
