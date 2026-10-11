# Requirement intelligence: the reasoning chain

How this repository answers one question — *what should the next BMW 5 Series
offer in Germany in 2030?* — and, more importantly, how it shows its work.

The claim this document has to support is not "here are fourteen
requirements". It is that every requirement can be walked back to the sentence
on the web page it came from, and walked forward to the score, the confidence
and the human decision attached to it. Anything that cannot be walked is
labelled as such rather than quietly presented alongside the things that can.

## Scope

| | |
|---|---|
| Vehicle | BMW 5 Series, G60 successor |
| Market | Germany |
| Horizon | 2030 |
| Profile | [`configs/g60_de_2030.json`](../configs/g60_de_2030.json) |

The profile is the single place the scope is declared. The web data layer reads
the planning market and the horizon from it rather than restating them, so
changing the profile changes the scenario instead of leaving parts of the UI on
a stale market.

`configs/g60.json` is a different, still-current profile: the US
customer-feedback MVP slice that the feedback pipeline and `tests/test_fusion.py`
are built on. The two coexist on purpose.

## The chain

```text
SOURCE          public web page, with URL, retrieval date and a content hash
  ↓
EVIDENCE        one atomic claim + the verbatim span it came from
  ↓
FINDING         independent evidence on one topic, with its stance and spread
  ↓
CUSTOMER NEED   what the customer is trying to do, in their terms
  ↓
REQUIREMENT     the outcome the vehicle should deliver
  ↓
SCORE           CRPS interval + Decision Confidence, separately
  ↓
PM DECISION     approve / reject / defer / edit, by a named reviewer
  ↓
AUDIT TRAIL     append-only, hash-chained, including refused attempts
```

Each link stores the ids of the one before it, so the chain is traversable in
both directions:

- **Backwards** — `requirement → need_ids → finding_ids → evidence_ids → source URL and verbatim span`.
- **Forwards** — `requirement → CRPS → Decision Confidence → challenge or edit → decision → audit event`.

### What is canonical and what is a fixture

This matters more than anything else in this document, because the two look the
same on screen.

**Canonical** — produced by the pipeline from real collected sources, in
`src/bmw_pm/data_pipeline/web_research/data/processed/`:

| File | Rows |
|---|---|
| `external_evidence.jsonl` | 979 |
| `findings.jsonl` | 20 |
| `customer_needs.jsonl` | 15 |
| `requirements.jsonl` | 14 |
| `requirement_scores.jsonl` | 14 |

`cache_reprocess_evidence.jsonl` is a QA artifact from re-running extraction
over the local page cache. It is not canonical and nothing reads it as truth.

**Fixtures** — illustrative data in `web/lib/data/fixtures/`, used when a
canonical artifact is missing and for the parts of the UI that have no canonical
equivalent yet. The loader prepends a note to `data_notes` saying which of the
two is in use, so the distinction is visible in the running app rather than
only in the repository.

`web/lib/domain/reasoning.ts` builds the traversable graph from the canonical
artifacts. Resolution is one-directional and never repairs: a reference to an
id that does not exist becomes a `TraceabilityIssue`, not a silently dropped
link. `blockers()` returns the issues that should stop a requirement being
presented as evidence-backed.

## Scoring

Two numbers, deliberately never combined. Priority answers *how much does this
matter*; confidence answers *how sure are we*. A high-priority requirement with
weak evidence must display high priority **and** low confidence, because
averaging the two produces a middling number that hides both facts.

### CRPS v1

Defined in [`configs/crps_v1.json`](../configs/crps_v1.json), implemented in
[`src/bmw_pm/decision/crps.py`](../src/bmw_pm/decision/crps.py). Seven factors
on a 0–4 scale:

| Factor | Weight | Source |
|---|---|---|
| Customer impact | 0.25 | PM judgement or evidence |
| Evidence strength | 0.20 | deterministic subscore |
| Frequency | 0.15 | requires a population denominator |
| Market relevance | 0.15 | deterministic, from evidence market |
| Competitive gap | 0.10 | matched BMW-vs-competitor evidence only |
| Future relevance | 0.10 | trend evidence actually present |
| Strategic fit | 0.05 | approved objectives or explicit PM input |

`CRPS_100 = weighted_0_to_4 / 4 × 100`.

Several of these are routinely **unknown**, and that is the honest answer rather
than a gap to be filled:

- **Frequency** needs a denominator of unique eligible records. Public web pages
  cannot establish population prevalence, so counting pages would be inventing
  a statistic. It is reported unknown.
- **Strategic fit** needs approved product objectives. `objectives` is empty in
  the profile because none exist for this exercise, so it stays unknown. An
  assumption about what the business probably values is not a strategic fact.
- **Competitive gap** is scored only from matched evidence on the same
  dimension. An unmatched dimension is reported missing, not assumed adequate.

### Unknown as an interval

An unknown factor **keeps its full weight** and contributes the interval
`[0, 4]`. It is not dropped and the remaining weights are not renormalised.
The result is therefore an interval, not a point, and a midpoint is never
substituted for a missing factor.

Renormalising away an unknown silently inflates confidence in whatever is left:
a requirement scored on two of seven factors would come out looking as
well-understood as one scored on all seven. Keeping the weight and widening the
interval makes the ignorance visible in the number itself.

Two consequences follow:

- **Bands come from the lower bound.** P1 ≥ 80, P2 ≥ 65, P3 ≥ 50, P4 ≥ 0, all
  assigned from the pessimistic end, so an incomplete score cannot be promoted
  by its optimistic one. These thresholds are a display convention for this
  exercise, not a BMW policy.
- **Ranking is conservative.** Two requirements are ordered only when their
  intervals do not overlap. Overlapping intervals are reported as unresolved
  rather than given a false ordinal position.

### Evidence Strength

A deterministic subscore, not a judgement:

| Component | Weight |
|---|---|
| Source quality | 0.30 |
| Source diversity | 0.25 |
| Consistency | 0.20 |
| Evidence volume | 0.15 |
| Recency | 0.10 |

Confirmation is counted by **independence group**, so ten rows scraped from one
page count once, and rows marked `duplicate_of` never count as independent
confirmation. Diversity saturates at 6 groups and volume at 8, chosen so a
handful of strong independent sources is not beaten by a large number of
same-source rows.

Contradicting evidence reduces **Consistency only**. It does not reduce Customer
Impact, because the fact that reviewers disagree about something does not make
the underlying customer problem smaller.

### Decision Confidence

Evidence strength 0.45, consistency 0.25, diversity 0.20, recency 0.10. Reported
beside CRPS and never folded into it.

## Requirement quality, and why it is not readiness

Two different checks, both needed:

- [`assess_readiness()`](../src/bmw_pm/decision/readiness.py) gates **process**.
  Is the policy approved, has entailment been reviewed, is feasibility
  documented, is the score current for this revision.
- [`validate_requirement_quality()`](../src/bmw_pm/decision/requirement_quality.py)
  gates **content**. Is this a customer-facing outcome rather than an
  implementation, one outcome rather than three, traceable to a need and
  evidence, free of numeric targets no source supports, not a restated
  regulation or business case, scoped to a vehicle and a market.

A requirement can pass every process gate and still be unusable, which is why
neither replaces the other. Every check reports its own basis so a reviewer sees
why something was flagged, and blockers are separated from warnings so advisory
findings do not gate a card.

The numeric-target check is the one with teeth: a number in the requirement text
must appear in the linked evidence, in either decimal spelling, since German
sources write `17,5` where the requirement writes `17.5`. Measurement-window
conventions such as the 10–80 % state-of-charge window are allowed but named in
the check detail, so the allowance is visible rather than silent.

All 14 shipped requirements pass. The tests assert that against the real
artifacts, not only against fixtures.

## PM workflow and where decisions are recorded

`ReviewService` owns the review rules — editable fields, the requirement that
approval carries an explicit uncertainty acknowledgement, revision conflicts,
idempotency. The web app reaches it through
[`bmw_pm.review.bridge`](../src/bmw_pm/review/bridge.py), spawned by
`web/lib/review/server.ts` behind `/api/review`, following the existing
`bmw_pm.advisor.bridge` pattern.

The bridge is transport only and holds no review logic; tests assert it never
constructs a `Decision`, `RequirementRevision` or judgement itself, so the rules
cannot drift into a second implementation in TypeScript.

What the backend enforces, and the web app therefore cannot talk its way around:

- **Stale-review protection.** Deciding against a revision that is no longer the
  latest is refused, and the refusal is itself written to the audit chain as a
  failure event.
- **Idempotency.** Replaying a `request_id` returns the original decision rather
  than deciding twice. Reusing one with a different payload is refused.
- **Immutable revisions.** An edit creates a new revision; the previous one stays
  readable, and the saved priority and any approval of it do not carry over.

Failures come back as typed codes — `backend_unavailable`,
`requirement_not_found`, `stale_revision`, `request_conflict`,
`invalid_request`, `internal` — mapped to HTTP status. None of them is
permission to treat browser state as authoritative.

**When the backend has no revision for a card**, the action still works for the
demo but is recorded in the browser session only, and says so: the audit entry
carries an explicit note, and the approve, reject, defer and edit dialogs show
where the decision will land before it is taken. This is the current state for
the shipped requirement cards — see *Known gaps*.

## Audit trail

Append-only and hash-chained, in SQLite or Postgres. Every event carries actor,
action, object, revision, reason, `request_id`, a monotonic sequence and the
previous event's hash. `verify-audit` recomputes the chain.

Refused attempts are recorded, not just successful ones. An audit trail that
only contains what worked cannot show that a control fired.

## Known gaps

Stated here because a demo that hides these is worth less than one that does
not.

1. **No shipped requirement card is backend-backed yet.** The cards use fixture
   display ids (`REQ-CTL-01`), while the review database is populated by the
   feedback pipeline. Every PM action in the shipped app therefore takes the
   session-only path. Closing this needs a decision about how external web
   evidence maps onto `RequirementEvidenceLink`, whose `provenance` is
   restricted to `supplied_anonymized` — the contract is feedback-shaped and the
   canonical chain's evidence is not. That is a change to a shared contract, so
   it is not made unilaterally here.
2. **Four canonical evidence rows carry a wrong unit.** Three vehicle lengths
   and one radar distance were recorded as minutes, from a bare `m` that was
   hardwired to minutes before `normalization.py` learned to resolve it from the
   quote. The code is fixed and tested; the stored rows are not rewritten,
   because correcting them is a cache reprocess that rewrites canonical evidence
   and should be a deliberate step rather than a silent historical edit.
3. **The CRPS policy is unapproved.** `approved: false`, and the weights come
   from the exercise definition rather than a weight-elicitation session with
   accountable stakeholders. It must not be presented as a BMW standard. The
   priority bands are likewise a display convention introduced here.
4. **Frequency and strategic fit are unknown throughout.** See *Scoring*. They
   are intervals, not zeros, and not gaps waiting to be filled with plausible
   numbers.

## Running the checks

Commands assume the repository Python environment (see the main README);
`pyproject.toml` already puts `src` on the path, so no `PYTHONPATH` is needed.

```bash
# Core suite: 281 passed, 6 skipped
python -m pytest tests

# Traceability of the canonical chain; runs from the repository root
python src/bmw_pm/data_pipeline/web_research/validate_traceability.py

# Collector and synthesis suites, which are unittest and live beside their code
cd src/bmw_pm/data_pipeline/web_research
python -m unittest test_pipeline   # 141 tests
python -m unittest test_synthesis  #  22 tests

# Web app: there is no test runner, so these three are the checks
cd web && npm run typecheck && npm run lint && npm run build
```

`validate_traceability.py` is the one that matters for this document: it fails
if any finding, need, requirement or score references an id that does not exist.
