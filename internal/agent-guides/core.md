# Core implementation rules

Follow the internal/AGENTS.md. Read `docs/DATA_CONTRACTS.md` for all shared objects.

- Keep parsing, extraction, scoring and approval as distinct responsibilities.
- The scoring module must be pure and independently tested. Never call an LLM to obtain a final numeric rank.
- Every aggregated count uses a declared unique-ID unit and denominator.
- Preserve supplied legacy labels as separate annotations. Keep them out of blind extraction/evaluation inputs.
- Validate source locators and entailment before promoting a claim. A generated source ID is invalid unless it resolves.
- Unknown fields remain unknown. Do not invent timestamps, expertise, study sample sizes or engineering costs.
- Commit revision changes and audit events atomically. Reject stale PM writes.
- Record model-run metadata and failures. Do not silently replace a failed live call with fixture results.
- Fixtures containing BMW private material remain local; commit synthetic fixtures clearly labelled synthetic.
