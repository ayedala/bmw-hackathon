# BMW successor decision prototype

> Historical walkthrough. Follow [the current draft decision-support guide](DRAFT_DECISION_SUPPORT.md) for active labels, scoring, raw BEVE handling and reviewer-only decisions. The older automatic scripted approval described below is no longer performed. No historical mapping or example judgement is a verified fact or BMW approval.

This is a working decision-support prototype, not a BMW-approved product plan. It extends the existing local workbench; the previously removed 3D frontend has not been restored.

## Run and demonstrate

From the repository root, with the existing environment:

```powershell
.venv/Scripts/python.exe -m streamlit run ui/app.py
```

Open http://127.0.0.1:8501. The default private database is `data/processed/bmw_pm.db`. No API key is required for the deterministic path. To install from a fresh checkout, use `uv sync --extra data --group dev`; obtain the authorized BMW files through the team's private channel, then follow the ingest/run commands in README. Raw data and processed databases are intentionally excluded from Git.

1. Keep **Decision portfolio scope → G60 · US**. Inspect the ranked portfolio and expand **Priority method and what-if weights**.
2. Select **Controls Usability** in the sidebar. Read the specific successor draft, source anchors, interpretation, future assumption, contrary evidence and proposed customer validation.
3. Inspect `G60-0271` at `Feedback_Explorer!I344`: airflow adjustment is reportedly distracting, and the customer did not know voice could perform that task. The observation is a report; the interpretation is an access/discoverability problem. Physical knobs are one alternative, not an established final answer.
4. Compare `G60-0092` at `I114`, which praises climate performance. It preserves an existing benefit without directly disproving interaction difficulty. In **Evidence**, inspect the broader supporting/preservation signals and independently scoped study/equipment/sales context.
5. Enter a planning reviewer ID and a rationale. **Adopt draft as new requirement revision**, or edit the text, use conditions, assumptions and proposed validation yourself. Content changes require fresh assessment; old scores and decisions remain reconstructable.
6. Set impact/evidence/relevance/uncertainty ratings and **Save priority assessment** with a reason. For example, raise uncertainty from 2 to 3 because better onboarding may solve part of the complaint. At seed weights, that changes the controls priority from 73.75 to 70.00. Change the what-if weights to explore trade-offs across the whole portfolio.
7. In **PM review**, enter a declared reviewer ID and rationale and **Approve**, **Reject**, **Challenge** or **Defer**. A conditional approval should say exactly what is approved, such as concept testing rather than production commitment.
8. In **History** and **All saved priority assessments**, inspect the exact revision, score assessment, actor and rationale. A decision retains its assessment reference even after later ratings change. An edit creates a new revision and does not silently carry priority judgements across revisions.
9. Expand **Export the decision brief**, prepare and download the Markdown snapshot. It contains private evidence excerpts and history. Regenerate it after changes.

An isolated, repeatable illustrative approval story is available:

```powershell
.venv/Scripts/python.exe scripts/demo_successor.py
```

This copies the source database to `data/processed/successor-demo.db`, edits the controls proposal, records two different priority judgements and a clearly labelled **scripted illustrative approval**, then writes `data/processed/successor-demo.md`. It never overwrites an existing database. Use `--output data/processed/successor-demo-2.db` for another rehearsal. Point the workbench's SQLite input at the demo copy to inspect it. This is a demonstration of the human-decision workflow, not an actual human or BMW sign-off. The canonical database receives no scripted approvals.

## Why US 5 Series, and why 2029–2031?

G60 supplies 4,000 unique feedback IDs, including 3,610 US records, across ICE, PHEV and the provisionally mapped BEV category. It supports a coherent demonstration of premium everyday usability, connected functions and electric journeys, with customer-study context and family sales. The 2025 sales sheet totals 296,000 for **G60/G68 combined**, highest among the three supplied sheets, not proof of global BMW leadership. No powertrain sales split is supplied.

G70 has more US records (3,792) but focuses on a different luxury use case. F70 is dominated by GB/JP and is ICE-only in the supplied feedback. Both are already ingested and available under **All available scopes** and the sidebar combined-engine profiles. The seven authored US G60 hypotheses are deliberately not transferred to those vehicles. There are no China verbatims. China study results and German equipment documents retain their own scope.

2029–2031 is the requested three-to-five-year successor scenario from the October 2026 planning date. It is not a BMW launch date. Current undated comments do not establish future demand or an historical trend.

## Customer insights and representative proposals

Observed counts below are **broad-theme keyword-baseline record counts**, with unreviewed semantic entailment. They are neither people nor a verified number needing each proposed feature. Mixed-topic records may appear in several themes; themes cannot be summed into independent customers. The charging denominator is 1,593 eligible US BEV/PHEV records; other themes use 3,610. `BEVE → BEV` remains an explicit mapping assumption.

| Theme | Support / preservation records | Insight and specific successor hypothesis | Counter-signal or unresolved question |
|---|---:|---|---|
| Software | 277 / 76 | Untrustworthy remote-command feedback motivates showing pending, vehicle-confirmed and failed states with recovery | Reported failure is not measured reliability; connectivity and user understanding may explain different cases |
| Controls | 73 / 12 | Persistent access to temperature, fan and demisting, plus optional discoverable voice and confirmation | Existing climate/touchscreen praise; onboarding may address part of the issue without new hardware |
| Assistance | 67 / 13 | Understandable available/active/limited/cancelled states and predictable resume/manual handover | Preserve useful cruise support; potentially severe reports require separate investigation, not majority voting |
| Comfort | 107 / 190 | Guided seat/lumbar setup and clearly confirmed profile save/recall | Many records praise comfort; distinguish setup difficulty from inadequate seat hardware |
| Charging/range | 112 / 26 | Trip energy assumptions and alternatives for changing arrival margins, with a simple commute view | Home-charging commuters can already be satisfied; software cannot itself fix public charging infrastructure |
| Practicality | 86 / 14 | Secure representative bottles/cups without blocking access to a phone | Console styling, other storage and varying object sizes create trade-offs; layout remains to be tested |
| Refinement | 31 / 42 | Preserve the quiet cabin while giving intrusive trim/window noise a clear diagnosis/resolution path | Preservation exceeds complaints in this broad theme; investigate condition-specific causes before redesigning everything |

The actual supplied material reconciles to 10,128 feedback IDs / 13,771 annotation rows, 391 study observations, 36 sales/planning values and 78 equipment pages. Twenty cards across all three vehicles retain 429 cross-channel links; reused links are not independent observations. Every authored draft has resolvable real record anchors in the local database. The draft is shown only when its required anchors are present and the vehicle/market match.

Equipment pages retain original text and locators but are not manually verified availability facts for an individual US trim. Sales supply market context, not customer impact. Studies are not pooled with verbatim recurrence, and respondent counts are absent. Some imported research and competitor context is available in the sidebar but remains unreviewed; keyword alignment alone does not establish support.

## Ranking and PM challenge

The customer-facing priority view complements the original conservative value-range score. The latter has unknown impact/business criteria and all US G60 value comparisons overlap. It must not be presented as a resolved implementation order.

The new view uses a transparent judgement policy:

`priority = 25 × [0.35 × impact + 0.25 × evidence + 0.25 × market relevance + 0.15 × (4 − uncertainty)]`

All ratings are 0–4. Anchors and normalized editable weights are shown in the app. These starting weights and ratings are **illustrative planning assumptions**, not elicited BMW preferences. Evidence is rated 2 throughout the seed because traceability exists but independent interpretation/entailment review is missing. Market relevance is a judgement, not a sales share. Unknown engineering/cost inputs are not fabricated or included in this core ranking.

| Initial rank | Draft | Impact / evidence / relevance / uncertainty | Illustrative priority |
|---:|---|---|---:|
| 1 (tie) | Climate control access | 4 / 2 / 3 / 2 | 73.75 |
| 1 (tie) | Trustworthy remote commands | 4 / 2 / 3 / 2 | 73.75 |
| 3 | Assistance state/handover clarity | 4 / 2 / 3 / 3 | 70.00 |
| 4 | Seat setup and recall | 3 / 2 / 3 / 2 | 65.00 |
| 5 | Trip energy transparency | 3 / 2 / 3 / 3 | 61.25 |
| 6 | Drinks/device access | 2 / 2 / 3 / 1 | 60.00 |
| 7 | Refinement preservation/resolution | 2 / 2 / 3 / 2 | 56.25 |

The ordering is a suggested **research/concept-testing conversation**, not a production commitment. Potentially severe assistance reports warrant attention independently of their position. Reviewers can change ratings and explain each change, or change weights to test sensitivity. Saved assessments retain factors, policy, score, actor, timestamp and rationale. The table compares all ratings under the same current what-if weights; the original saved score and weights remain visible. Other scopes are unranked until a PM supplies ratings.

## External context reviewed

Three primary sources were reopened on 10 October 2026 and appear in the app. They inform questions and scenarios without automatically supplying score ratings:

- [ADAC's BMW i5 test, 30 January 2025](https://www.adac.de/rund-ums-fahrzeug/autokatalog/marken-modelle/bmw/bmw-i5/): condition-specific German review/test context; not a US customer sample or successor target.
- [Mercedes-Benz USA, 2026 EQE 320 4MATIC](https://www.mbusa.com/en/vehicles/model/eqe/sedan/eqe320v4): OEM feature packaging and electric-navigation context for a plausible premium electric-sedan comparator. Manufacturer availability is not customer preference or verified superiority.
- [IEA Global EV Outlook 2026](https://www.iea.org/reports/global-ev-outlook-2026): historical observations and projections are distinct. The overview supports scenario planning around charging and software; no numeric US adoption forecast is imported into the ranking.

These are curated summaries with URLs and access dates, not full archived documents. Prior web seeds and both research pipelines were reviewed. The saved YouTube run contains discovery metadata but zero usable transcript findings; no video claim is invented. The standalone external research pipeline is separate; no paid extraction or unsupported automatic integration is implied.

## Implementation and limits

Python/SQLite/Streamlit keep the existing deterministic ingestion, optional model extraction, citation validation, fusion and immutable PM workflow. `decision/planning.py` adds typed priority judgements and draft selection; `ui/planning_view.py` adds the portfolio, source reasoning, what-if policy, saved assessments and private report. SQLite transactions prevent concurrent stale priority writes. Decisions reference the exact priority assessment used at decision time. Priority rows and requirement revisions are immutable; audit events are hash-linked. Declared local reviewer IDs are not verified identities, and local storage is not tamper-proof against an OS administrator.

The separate evaluation branch's review was considered, including stale-score handling and the need for independent labels. No extraction prompt was tuned, no human labels were invented, and no held-out model accuracy or PM ranking agreement is claimed. Exact spans and data reconciliation are structural checks, not proof that the interpretation is right. The baseline can misclassify mixed sentiment and miss needs; broad-theme praise is preservation context, not necessarily direct counterevidence to a narrower feature.

Open questions: actual US trim/year fitment; customer-study denominators/scales; source dates and ownership; severity and customer segments; representative user-task baselines; BMW strategic preferences; future powertrain/charging scenarios; and qualified investigation of potentially severe reports. Customer-facing proposals can progress to research while these remain explicit.

## Verification

The regression suite, including duplicate invariance, unseen scope, unknown inputs, stale reviews, score invalidation, priority concurrency/idempotency, immutable history and selection retention, passed **38 tests**. Real-data reconciliation validates the 20 cards, 6,462 exact-span signals and 429 cross-channel links. An end-to-end Streamlit AppTest on a copied real database passed adoption/edit, priority save, approve, reject, private export and historical replay with zero UI exceptions. The illustrative demo's audit/priority bindings were also checked. Browser visual verification was unavailable; no claim is made about a manual browser inspection.

```powershell
.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider --basetemp .tmp/pytest-successor-check
.venv/Scripts/python.exe -m bmw_pm.cli --db data/processed/bmw_pm.db validate --expect-supplied-shape
```

Private workflow and validation artifacts are under `data/processed/`. No private source files, database, report excerpts or scripted approvals are published to Git.
