# Decision logic review — 10 October 2026

## Result

The prototype reads the database and produces explainable candidate cards, but it is not yet a validated market decision agent. The inspected database has seven draft requirements and one keyword-baseline run over 3,610 G60 US feedback records. All 21 pairwise value comparisons are unresolved. Zero of seven cards passes the new commitment-readiness diagnostic. These are software observations, not measured recommendation accuracy.

## What works

Source hashes and exact locators; grouping annotations into unique feedback records; scoped powertrain denominators; retention of praise/context on complaint-led cards; deterministic score contributions with unknown dimensions kept as intervals; PM decisions with rationale and stale-revision protection; immutable revision history and hash-linked audit replay.

## Gaps against the challenge

- Heterogeneous context is stored, but studies, equipment, sales and external claims do not yet inform requirement synthesis or value criteria. A reviewed, scoped evidence crosswalk is needed; source-topic similarity is insufficient.
- Only reach is populated in the real run. Three of four value criteria are missing. Equal weights and the 5% recurrence saturation point are unapproved proposals. A high position in the display is not a recommendation to implement.
- Exact substrings establish reference validity, not semantic entailment. A human must check that each material argument follows from the quote.
- Outcome-string grouping can fragment equivalent AI-produced needs and combine differing use contexts. Do not tune grouping prompts until the evaluation manifest is frozen.
- Praise-only domains produce no preservation cards; mixed sentiment becomes context rather than separate atomic needs. Rare severe reports have no dedicated review queue. The keyword extractor only examines its first matching sentence per domain. These recall gaps need labelled fixtures and evaluation, not an invented accuracy claim.
- Scope demonstrates generation G60/US, not a confirmed trim/derivative-specific baseline. Feedback dates and verified owner identities are unavailable; no historical trend or owner prevalence can be established.
- PM challenge records the objection but does not itself retrieve new evidence or re-score it. New evidence needs an explicit revised packet and score.
- Audit coverage is not complete for all local reads/exports and failed inference jobs. Hosted workbench/context reads have audit paths, but arbitrary OS access is outside the app's control.

## Corrections in this review

Content, conditions or assumptions edited by a PM no longer inherit the previous revision's score. Title-only edits retain it. Old scores remain reconstructable. The CLI `decision-readiness` and workbench expose unapproved policy, unreviewed support, missing criteria, incomplete processing, absent/stale scores and feasibility gaps. This diagnostic does not prohibit a PM's documented conditional decision or certify that a ready card is correct.

## Improvement loop

1. Freeze grouped development/test/transfer records and evidence hashes before changing prompts. Human reviewers label needs, polarity, exact spans and context, hiding legacy labels. Double-label difficult cases and record adjudication.
2. Record PM edits/challenges with reasons; separately collect explicit criterion ratings and paired preferences (including ties and insufficient evidence). An approval alone is not a severity rating, extraction label or proof of commercial success.
3. Propose a versioned extractor/grouping/policy change on development data. Keep the previous system as a comparator. Never use the agent's own generated decisions as independent truth.
4. Evaluate both versions on frozen independent evidence: extraction precision/recall, human entailment, unsupported claims, preference agreement, scope errors, coverage and latency, with denominators.
5. Promote only after documented human review of measured quality and tradeoffs. Preserve rollback, model/prompt/schema/policy versions, evaluation artifacts and audit events. Scoring preferences remain explicitly approved policy rather than silently learned weights.

No self-training, fine-tuning, automatic policy promotion or quality improvement has been executed. Human labels and PM judgments are missing. The repository's next task remains T04: establish that evaluation foundation. Until then, the honest output is proposed requirements and research priorities for PM review.
