# PM review, audit and decision memory

## Human involvement by decision impact

| Point | Why a human adds value | Required action |
|---|---|---|
| Vehicle, market and planning scope | Sets the business question and eligible population | PM confirms profile and exclusions |
| Scoring policy and trade-offs | Weights encode strategy, not model facts | PM reviews anchors, swing choices and policy version |
| Ambiguous data mapping | A wrong market/unit/variant changes interpretation | Data owner or PM resolves only material ambiguity |
| Requirement commitment | Balances value, uncertainty, cost and feasibility | PM approves, conditionally approves, rejects or defers |
| High-risk or unresolved technical target | Requires expertise absent from customer comments | Engineering reviewer supplies evidence or leaves pending |
| Changed evidence/constraints | Prior approvals may no longer fit | PM reviews affected requirement revisions |

Routine parsing, clear normalization, candidate extraction and deterministic score recalculation do not need repeated human approval. Escalate material ambiguity, conflicting evidence and commitments. This product's PM gates are application behavior, not permission gates for the coding agent's routine implementation work.

## Requirement card

Show customer outcome and status first. Then scope/use case; support and strongest counterevidence; original source link/row/page; counts with denominator; survey context; equipment baseline; proposed acceptance method and pending targets; criterion contributions; uncertainty interval; feasibility and effort; alternative solutions; and what would change the conclusion.

Actions:

- **Approve:** commit the exact requirement revision under the visible policy. If assumptions remain, require explicit conditional acceptance and an owner/review trigger.
- **Reject:** reason plus optional correction; keep the record and evidence available.
- **Edit:** create a new draft revision, show a diff and recalculate affected scores. An old approval does not transfer automatically.
- **Challenge:** record the disputed claim or preference, request targeted counterevidence/reanalysis, and create a response with changed/unchanged conclusions and unresolved gaps.
- **Defer:** reason, missing input, owner, and review date/trigger. Absence of evidence can create a research task rather than a permanent rejection.

## State machine

`draft → needs_review → approved | conditionally_approved | rejected | deferred`.

A challenge creates a linked `challenge_open` review item while preserving the requirement's previous decision. Resolving it creates a new revision or a recorded decision that no change is warranted. Significant new evidence creates `needs_review` for the new revision; the historical approved revision remains frozen. `superseded` denotes a version replaced by a later one; it is not deletion.

Actor permissions: pipeline may create drafts, quality findings and review requests; PM may make product decisions; engineering reviewer may record technical constraints and validation. An LLM output cannot grant itself a role. For the local prototype, role selection is demonstrative, not authenticated authorization; label it accordingly.

Use `expected_revision` and idempotency keys. Two reviewers editing revision 2 cannot silently overwrite each other. The second write receives a conflict and an explicit diff/rebase choice. Persist decisions independently of Streamlit session state.

## Chronological audit

Log in-app source imports, data transformations, model jobs, validation failures, evidence reads, requirement views, policy changes, score runs, challenges, edits, decisions, exports and access-denied attempts. Use server-side monotonic sequence plus UTC time; retain source observation time separately.

Each event includes actor, action, object and revision, before/after hashes, reason, request/run ID and outcome. Sensitive raw text and secrets do not belong in the event payload. Logs reference protected evidence instead. Read events record accessed scope, not unnecessary copies of all content. Deduplicate repeated delivery of the **same request ID**, not independent access events.

In one database transaction: validate expected revision → write new immutable revision/decision → write audit event → commit. A partial failure must roll back both. Score recalculations create new snapshots and link their causes; a user can inspect why a value changed.

Append-only application rules plus a hash chain make unauthorized alteration detectable against a trusted checkpoint, not impossible. A database owner can rewrite an unanchored chain. For the demo, test replay and tamper detection, export a checkpoint outside the mutable event table, and describe the limitation. Do not claim coverage of OS-level file reads or third-party systems. The user's “complete audit” is implemented within a declared application boundary.

## Two-year iteration

Each review cycle stores a snapshot: data available then, model/prompt/policy/profile versions, active requirement revisions, PM decisions and unresolved assumptions. New input is processed as a delta; unchanged evidence is reused, affected requirements are re-evaluated.

Distinguish **when evidence was true/observed** from **when the team learned it**. A late-arriving old review is not a new customer trend. Supplied comments have no dates, so the demo may stage a new import batch but must call it an ingestion sequence, not a historical longitudinal study.

Review triggers: new independent counterevidence; updated equipment/competitor specification; changed scope or market mix; new engineering constraint; expired source validity; shifted top group across accepted scenarios; scheduled milestone. Trigger thresholds are policy settings with an owner, not hidden model behavior.

The MVP demonstrates two cycles immediately: original evidence and review; then one real newly imported public source or clearly labelled synthetic constraint, revised argument, PM decision and replay. No background automation is required to simulate a two-year process. Future scheduling belongs to deployment work.

## Acceptance scenarios

1. Approve revision 1, edit the target → revision 2 requires review; revision 1 remains reproducible.
2. Import unchanged file twice → no extra support, but both import attempts have audit outcomes.
3. Challenge source applicability → contested claim is excluded or explicitly retained with justification; score diff matches the changed inputs.
4. Read restricted evidence or export → audit event exists with actor and scope; raw personal data remains protected.
5. Stale review write → conflict, no silent overwrite and no false success event.
6. Tamper with a prior event in a disposable test database → checkpoint verification fails.
