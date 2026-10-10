# Frozen evaluation and human labeling

Run from the repository root:

```powershell
$env:PYTHONPATH = 'src'
python -m bmw_pm.cli freeze-evaluation
```

The private output is `runs/evaluation-v1/`, excluded from Git. The manifest and four split packets are frozen inputs, with a hash receipt. A repeat verifies them without rewriting human work; changed content requires a new version. Preserve old versions. The export is recorded in the application's audit trail.

## Splits

| Packet | Records | Use |
|---|---:|---|
| development.jsonl | 60 G60 | Review examples and later tuning |
| heldout_g60.jsonl | 30 G60 | Independent evaluation, never prompt tuning |
| transfer_f70.jsonl | 15 F70 | Transfer diagnostics |
| transfer_g70.jsonl | 15 G70 | Transfer diagnostics |

Selection rotates through source/country/powertrain strata, with seeded content hashes ordering each stratum. Identical case-folded whitespace-normalized texts are one group; a group spanning vehicle models is excluded. Only one representative is annotated; all member IDs are reserved with it. Labels or model-generated signals do not influence selection. This deliberately enriches sparse strata and is not a population-representative sample. Grouped annotation rows already belong to one feedback record.

Near-duplicates, reposts, difficult examples and severe cases still require human screening. The 30 double-label flags are provisional assignments (15 development, 7 G60 holdout, 4 F70, 4 G70), not evidence that those records are difficult. If screening requires replacement, retain the version and create an explicitly documented new one before tuning. Prior baseline processing means these splits cannot be claimed completely unseen.

## Human worksheet

Use `human_labels.jsonl`, matching `record_id` to its split packet. Packets contain redacted text, known scope and original locators, without legacy labels or extracted model signals. An annotator must not inspect model predictions or supplied categories first. Review text remains untrusted evidence.

Fill `reviewer_id`, `difficulty` and `review_status` (`labelled` after inspection). Each `signals` item should contain:

```json
{
  "need_domain": "reviewer-chosen topic",
  "atomic_claim": "What the speaker actually establishes",
  "customer_outcome": "The customer task or outcome",
  "polarity": "complaint",
  "evidence_text": "Exact contiguous substring copied from packet text",
  "evidence_start": 0,
  "evidence_end": 10,
  "use_context": null,
  "uncertainties": []
}
```

Offsets are Python Unicode character indices into packet `text`, with an exclusive end. `text[start:end]` must equal `evidence_text`. The numbers above illustrate the schema; they are not a valid gold annotation. Polarity options are complaint, praise, aspiration, observation, mixed. Separate atomic praise and complaints when warranted. Keep unsupported ownership, dates, severity, engineering targets and market claims unknown. If no justified signal exists, use `signals: []` and explain `abstention_reason`.

For a flagged second review, give an independent reviewer the packet and an empty worksheet, without the first review. Retain both worksheets under distinct names. A human adjudicator records disagreement and the resolved labels in `adjudication`; do not silently replace either independent review. Additional difficult records may need a second reviewer.

The second worksheet is a separate JSONL file with the same row shape as `human_labels.jsonl`, containing only `double_label: true` records. Its `reviewer_id` must differ from the primary reviewer and `adjudication` stays `null`. Once both reviewers finish, keep both entries and add this object to the primary row:

```json
{
  "reviewer_id": "adjudicator-id",
  "reason": "How the two reviews were resolved, including agreement",
  "signals": [],
  "abstention_reason": "Reason when the resolved label has no signals"
}
```

Replace `signals` and `abstention_reason` with the resolved values. The adjudicator's exact spans are validated against the same frozen text. A singly reviewed record is ready for scoring when labelled; a flagged record stays provisional until independent review and adjudication are complete.

## Local validation and extraction comparison

Run from the repository root with `PYTHONPATH=src`:

```powershell
$env:PYTHONPATH = 'src'
python scripts/evaluation_workflow.py validate-labels
python scripts/evaluation_workflow.py validate-labels --second-review runs/evaluation-v1/second_review.jsonl
python scripts/evaluation_workflow.py run-extraction --provider baseline --split development --output runs/evaluation-v1/baseline-development-v2
python scripts/evaluation_workflow.py score-extraction --run runs/evaluation-v1/baseline-development-v2 --second-review runs/evaluation-v1/second_review.jsonl
```

Use a new output directory for a changed taxonomy, prompt, model or frozen split. A repeated run reuses completed per-record results; `--retry-failures` retries only failed records. Run the optional live provider on the **same split** with a separate output directory and configured `OPENAI_API_KEY` / `BMW_PM_OPENAI_MODEL`, then use `compare-extraction --first <baseline-run> --second <live-run>` with the same second-review file. Live calls transmit the redacted packet text; check authorization and the packet before invoking them. No live model call occurs during validation, baseline extraction, scoring or comparison.

The scorer counts one-to-one matches requiring the same normalized topic, polarity and overlapping evidence span. It reports this as a **proxy**, with true/false counts and denominators, rather than semantic accuracy or citation entailment. Reviewers must separately assess whether a quoted span actually supports an atomic claim. The output remains `metrics: null` when no adjudicated labels are ready; partial labels produce explicitly partial metrics.

## Current boundary

Freezing inputs does not label them, train a model, establish correctness or approve a policy. The validator checks hashes, coverage, independent reviewer IDs, abstentions and exact spans; it cannot establish semantic correctness or the quality of an adjudication. The baseline can run before labels, but no measured accuracy exists until reviewers finish. No automatic policy promotion is enabled.
