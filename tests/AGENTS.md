# Test and evaluation instructions

Follow root instructions and `docs/EVALUATION.md`.

- Keep software correctness tests separate from model-quality evaluations.
- Test meaningful domain invariants: deduplication, evidence validity, missingness, scope, score arithmetic, revision and replay.
- Keep all annotations/duplicates of one source record in a single split.
- Never tune prompts or weights to improve the sealed test results. Freeze changes after a final evaluation, or create a genuinely new holdout.
- Label synthetic fixtures. Never report synthetic fixture scores as customer-data accuracy.
- Report skipped checks, sample sizes, abstentions and subgroup gaps.
- A single LLM judge is advisory; human-adjudicated examples anchor the quality evaluation.
- Do not turn proposed targets in the plan into fabricated passing metrics.
