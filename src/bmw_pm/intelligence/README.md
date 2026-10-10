# Customer signal extraction

`provider.py` defines the extraction interface and bounded structured model implementation. It validates source-linked text spans and records provider identity. `baseline.py` supplies a deterministic keyword fallback for offline demonstrations; it is explicitly labelled `baseline_no_ai`.

Inputs are redacted, scoped feedback records. Outputs are typed signals for deterministic consolidation in `decision/requirements.py`. Source text is untrusted data. A matching excerpt proves the text exists; human review still needs to verify that it supports the claim.

The current core does not autonomously critique PM challenges or call the requirement drafting prompt. The stage documents in [prompts](../../../prompts/README.md) describe contracts and should not be mistaken for implemented capabilities. External collector extraction adapters are documented within `data_pipeline/`.
