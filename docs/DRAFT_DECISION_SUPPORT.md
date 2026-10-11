# Evidence-grounded successor decision support

This is the current workflow. It supersedes the earlier evidence-only restriction: interpretations and future scenarios are allowed as clearly labelled drafts. Source extraction still cannot convert invented claims into evidence. No model can approve a requirement or confirm a PM priority.

## Run

From the repository root:

```powershell
.venv/Scripts/python.exe -m streamlit run ui/app.py
```

Open http://127.0.0.1:8501. Use the authorized private `data/processed/bmw_pm.db`. No API key is needed for this demonstration. A fresh checkout requires dependencies (`uv sync --extra data --group dev`) and authorized BMW source files; private data, databases and exports are excluded from Git. Existing ingestion and combined-research commands remain documented in README.

## Demonstration choice and evidence

The selected scope is US 5 Series G60, looking at **2029–2031**, three to five years from the October 2026 planning date. This is a scenario, not a BMW launch date. The available corpus has 4,000 G60 feedback IDs, 3,610 US, with customer-study, family-sales and equipment context. The choice gives a coherent premium usability/connected-service/electric-journey demonstration. It is not a claim that this market is more commercially attractive. G70 and F70 remain browsable; G60 proposals are not transferred to them.

Across the supplied files there are 10,128 feedback IDs, 13,771 annotation rows, 391 study observations, 36 sales/planning values and 78 equipment pages. Feedback IDs are not verified people. Broad-theme recurrence is not the number of customers needing a proposed feature. Undated reports do not establish trends. The application resolves exact redacted record text and original hash/row locators; source statements themselves are not independently verified facts.

Additional primary context was checked on 10 October 2026: [ADAC i5 test](https://www.adac.de/rund-ums-fahrzeug/autokatalog/marken-modelle/bmw/bmw-i5/), [Mercedes-Benz US EQE specifications](https://www.mbusa.com/en/vehicles/model/eqe/sedan/eqe320v4), and [IEA Global EV Outlook 2026](https://www.iea.org/reports/global-ev-outlook-2026). Authored summaries are labelled context, not quotations or customer-demand findings. German test conditions and competitor specifications do not establish US BMW customer preference. These sources motivate questions and scenarios; they do not inflate the evidence rating or supply engineering targets.

## Representative draft requirements and ranking

These are assistant-authored, evidence-linked templates, deterministically materialized against matching real records. They are **not live model inference, measured value, approved priorities or BMW decisions**. No draft is generated when required anchors are missing or vehicle/market differs. Each immutable snapshot contains the recipe version, base revision, actual quoted records, context, interpretation, assumption, conflicts, unknowns, validation and priority explanation. Its content hash identifies the snapshot; reviewer adoption references it in a new immutable requirement revision.

Ratings use 0–4. The initial **AI-suggested** weights are impact .35, evidence .25, market relevance .25 and uncertainty .15. Score = 25 × [impact × .35 + evidence × .25 + relevance × .25 + (4 − uncertainty) × .15]. Impact and relevance are scenario judgements, not measured customer impact or demand. Evidence 2 reflects exact records with unreviewed meaning/representativeness. Higher uncertainty reduces priority. Ties use stable requirement IDs rather than fabricated precision.

| Provisional group | Customer-facing draft | Impact / evidence / relevance / uncertainty | AI score | Key conflict or uncertainty |
|---|---|---|---:|---|
| Joint first | Persistent discoverable temperature, fan and demisting access; optional voice and clear confirmation | 4 / 2 / 3 / 2 | 73.75 | Existing climate performance is praised; onboarding may resolve some access difficulty |
| Joint first | Remote commands show pending, vehicle-confirmed or failed status with recovery | 4 / 2 / 3 / 2 | 73.75 | Customer reports do not establish failure rate or connectivity root cause |
| Next | Understandable assistance states and predictable resume/manual handover | 4 / 2 / 3 / 3 | 70.00 | Preserve useful assistance; investigate potentially severe reports separately |
| Next | Guided seat/lumbar setup and confirmed saved-position recovery | 3 / 2 / 3 / 2 | 65.00 | Comfort praise is substantial; distinguish setup from seat hardware |
| Next | Explain arrival-energy assumptions and alternatives, retaining a simple commute view | 3 / 2 / 3 / 3 | 61.25 | Satisfied home-charging commuters; ambiguous BEVE; infrastructure outside product control |
| Next | Keep representative drinks secure without obstructing phone access | 2 / 2 / 3 / 1 | 60.00 | Different containers and console styling create trade-offs |
| Next | Preserve quiet refinement and offer a clear intrusive-noise resolution path | 2 / 2 / 3 / 2 | 56.25 | Preservation feedback exceeds complaints in this broad theme |

The scenario assumes these everyday tasks remain relevant in three to five years because customers report them today; that is plausible continuity, not a forecast established by the data. All implementation choices require customer testing. Validation plans propose matched tasks and baseline measurement; no invented numeric success targets are supplied.

## Evidence → insight → draft → human decision walkthrough

1. In the header select **Vehicle → BMW 5 Series (G60)** and **Market → United States**. On **Decision desk**, select **Adjust everyday climate functions without menu hunting** in the proposal queue. This is the future-facing draft for the stored Controls Usability topic. Expand **Exact source records and observed counts**. `G60-0271`, `Feedback_Explorer!I344`, reports distracting airflow controls and lack of awareness of a voice alternative. Compare `G60-0092`, `I114`, praising climate performance. Inspect the complete exact redacted records in the app; this document paraphrases them.
2. The **AI interpretation** identifies access/discoverability as a possible need. The **future assumption** says easy essential control access may remain valuable in 2029–2031 despite better conversational interfaces. This does not prove physical knobs are the required solution. Persistent shortcuts, tactile access and discoverable voice are alternatives to test.
3. Inspect conflicts, unknowns and the proposed matched-task validation. The draft proposes immediately discoverable temperature/fan/demisting access with optional voice and confirmation. It is still unapproved.
4. Enter **Planning reviewer ID** and **Draft adoption rationale**, then **Adopt draft as reviewable revision**. This records an explicit human edit, not approval. Adjust text, assumptions or validation in **Edit this proposal into a new revision** if needed. Old revisions and decisions remain visible in Audit trail.
5. Inspect the AI provisional 73.75/100. **Use AI suggestion as editable draft inputs** copies ratings and weights into the PM form without saving or confirming. Raise uncertainty to 3 if onboarding may solve part of the problem: at the same weights the score becomes 70.00. Alternatively change weights, enable the custom-criteria table, add/remove/rename criteria, or enter a manual portfolio rank. Explain the judgement.
6. **Save priority assessment** records a PM-entered draft. Only selecting **I explicitly confirm this priority as the reviewer** confirms that assessment. This still does not approve the requirement. Manual ranks sort first; custom policies may not be comparable across cards. A weight preview is labelled unconfirmed and does not change the saved assessment.
7. In **Record a PM decision**, explicitly enter the declared reviewer ID and rationale, then Approve, Reject, Challenge or Defer. Final decisions on a future draft require adoption first; approval additionally requires the explicit uncertainty acknowledgement. A useful rationale might approve concept testing while requiring a baseline usability study before production commitment. That is an example rationale, not an existing BMW approval. The decision references its exact requirement revision and saved assessment; old references stay fixed if a later assessment changes.
8. Use **Data & AI findings** to inspect sources and record human evidence-link assessments. These are revision-scoped and do not silently change counts or scores. Use **Audit trail** for chronological events, priority comparisons and full revision/decision/link-assessment history. On Decision desk expand **Compare portfolio and export a decision brief**, then prepare/download the private Markdown snapshot. It separates evidence/draft layers, locators, assessment origins/statuses and decision rationale. Regenerate after changes; saves invalidate the current download.

## Isolated real-data rehearsal

```powershell
.venv/Scripts/python.exe scripts/demo_successor.py --output data/processed/draft-demo.db
```

This backs up the real database into a new file and generates seven drafts plus a private Markdown brief. It creates **no new decision** by default and refuses to overwrite existing files. Point the workbench SQLite field in sidebar Workspace settings to the copy to review it, or set `BMW_PM_DATABASE` before starting the app. To record an actual explicitly entered CLI decision, supply `--decision`, `--reviewer` and `--rationale`; optionally `--confirm-priority`. Approval also requires `--acknowledge-uncertainty`. Those flags explicitly adopt the selected draft and accept its displayed suggested ratings. For rating or wording changes use the UI. CLI identity is declared, not authenticated. Never label a test actor as BMW approval.

The reproducible automated real-data UI rehearsal is `python scripts/verify_successor_workflow.py`. It explicitly simulates reviewer inputs on a new private copy, tests adoption → editable AI inputs → saved draft priority → explicit priority confirmation → approval, plus rejection/export/replay, and validates all provenance checks. It writes `data/processed/successor-ui-verification.json`, a uniquely named `illustrative-reviewed-draft-*.db` and matching Markdown brief. Every test decision is labelled illustrative; the original database receives no test decisions.

## Safeguards and limitations

- Source extraction stays exact-span constrained. Synthesis is a separate draft layer. No invented source, ownership, sample size, cost, feasibility, launch date or final approval is filled in.
- `BEVE` stays exactly as supplied. Ambiguous mappings are flagged. Historical normalization assumptions remain in history; their presence is not confirmation. Questionable country/generation/trim/test-condition relationships stay scoped or unknown.
- Studies lack respondent counts/scales. Equipment is German July 2026 context, not confirmed US trim availability. Sales combine G60/G68 with no powertrain split. Context links are not independent corroboration.
- The available YouTube discovery run has no usable transcripts/findings. The engine can import validated excerpts when available, but this demo makes no video-derived claims.
- Regeneration preserves any reviewed requirement instead of silently superseding it. New evidence remains inspectable through source context and reruns; incorporating changed evidence into reviewed wording needs a new human edit. Automatic proposal refresh/notifications are not implemented.
- Reviewer IDs are declared local identities. The local audit is append-only/hash-linked within the app, not OS-level access monitoring or enterprise authentication.
- Drafts use seven authored recipes rather than unconstrained live generation. They demonstrate the full decision-support chain without claiming model quality or coverage of every possible requirement. Human-labelled extraction/entailment and ranking validation remain outstanding.
