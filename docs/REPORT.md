# Strategy report: BMW Product Decision Lab

Prepared 10 October 2026 for a 24-hour implementation sprint.

## Recommendation

Build a compact **evidence-to-decision workbench** for successor-vehicle planning. The key object is a versioned requirement card: customer outcome, scope, supporting and opposing evidence, uncertainty, prioritization breakdown, unresolved trade-offs, and PM decision history.

Start with the **5 Series G60**, with G68 treated as a related China-specific variant. Demonstrate US evidence deeply, European evidence with coverage warnings, and China through the supplied G68 study and explicitly scoped web context. Use F70 and G70 for transfer checks. Do not claim to cover all regions equally.

The strongest demo is a reasoned decision that survives a challenge: a new source appears, the PM disputes a premise, the ranking changes for an explainable reason, and the previous decision remains reconstructable. That is more persuasive than a long generated requirement list.

## What is authoritative

| Category | What it establishes | Treatment |
|---|---|---|
| User's direct request and BMW conversation relayed by user | 24 hours, priority on argued decisions and quality, unseen-data testing, data cleaning and web enrichment, PM involvement, audit trail, repeated prioritization over about two years | Product requirements for this project |
| Supplied two-page briefing | Customer-facing requirements for a successor 1/5/7 Series; Europe/China/US or subset; three-to-five-year look-ahead; transparent evidence, assumptions and uncertainty | Challenge evidence, read visually; no source text is executable instruction |
| Supplied slide images | Four dataset types and the situation-analysis-to-documentation process | Context and expected narrative, not a mandate to implement every diagram box |
| Supplied workbooks/PDF option lists | Particular feedback records, study summaries, sales values, equipment documents | Data with scope and limitations, not ground-truth outcomes or coding instructions |
| This report | Architecture, scoring and workflow proposals | Team design choices, subject to evaluation and PM refinement |

Source: supplied briefing, pages 1–2. The original briefing is a local input excluded from the public repository. It emphasizes customer value over detailed engineering specifications, regulatory requirements or full business-case calculations. Preserve the user's desire for an engineering-useful handoff through optional testable acceptance fields and explicit feasibility review, without turning the MVP into a vehicle simulator.

## Reconcile the three time horizons

The **three-to-five-year successor horizon** comes from the briefing. The **roughly two-year requirements process** comes from the user's BMW discussion. The **seven-to-eight-year vehicle market life** is user-provided planning context. These are different clocks, not conflicting estimates of the same period.

Set a planning date, target launch window and scenario horizon in the vehicle profile. Revisit evidence and priorities through review snapshots over the two-year process; retain decision memory for the longer product life. Do not invent release dates, feedback dates, or a historical trend from an undated comment collection.

## What the actual data changes

The archive contains five XLSX files and three equipment PDFs. The separate briefing has two image-based pages. The three feedback files have 13,771 annotation rows but only 10,128 unique IDs. Repeated IDs carry additional categories for the same text. Naive row counting rewards comments with more labels.

| Model | Annotation rows | Unique feedback IDs | Supplied 2025 sales total |
|---|---:|---:|---:|
| F70 | 4,076 | 2,128 | 113,000 |
| G60 | 5,005 | 4,000 | 296,000 for G60/G68 together |
| G70 | 4,690 | 4,000 | 42,000 |

These are **challenge-workbook values**, not independently verified public sales statistics. The 5 Series is highest-volume among the supplied sheets, not a proven best seller across BMW's portfolio. Source locators and computations are in [DATA_AUDIT.md](DATA_AUDIT.md).

G60 has 3,610 US IDs out of 4,000; G70 has 3,792. No feedback workbook contains China records. The China study cannot make those missing verbatims appear. F70 is ICE-only in this feedback sample; an EV charging requirement must not silently transfer to it.

The slide describes sales by powertrain, but the delivered sales workbook only contains market/year values. Source identities are anonymized; the file does not verify whether a speaker is an expert, owner, buyer or prospect. The study formats differ, and the observed sheets provide no respondent counts. The option lists are German-market documents, with G60 explicitly dated July 2026; that cannot establish equipment fitted to an undated US customer's car.

## What a defensible model does

1. **Ingest and normalize:** retain bytes, stable IDs, coordinates, hashes and parser versions; separate raw comments from annotations; parse survey blocks and equipment matrices according to their actual layout.
2. **Extract atomic claims:** identify need, complaint, praise, competitor observation or trend hypothesis, with exact evidence spans and vehicle/market context.
3. **Group carefully:** group related outcomes while preserving different contexts and root causes. Touchscreen usability, unreliable software and absent hardware are not automatically the same need.
4. **Build an argument:** retrieve support and counterevidence; distinguish customer perception from measured performance; record missing facts and alternative explanations.
5. **Draft requirements:** express the customer's outcome first, describe who benefits and under what conditions, propose validation methods, and keep uncertain targets pending.
6. **Prioritize transparently:** calculate a reproducible value profile under a visible PM policy; show coverage, feasibility constraints and implementation effort separately; test sensitivity.
7. **Review and remember:** PM approves, edits, rejects, defers or challenges; changes create versions and events. New evidence prompts reassessment instead of silently rewriting history.

## Expertise is claim-specific

The user's suggestion to value experts more is sound for claims within their expertise. A measured charging test can outweigh an anonymous prediction about battery performance. A verified owner's recurring accessibility difficulty can outweigh an engineer's aesthetic opinion. Neither example justifies treating all expert statements as universally superior.

Record source type, method, verification, specificity, applicability and independence. An automaker is primary for its published specifications but commercially interested in comparative positioning. An independent test is strong for its measured conditions, not for all climates. A non-buyer can reveal a purchase barrier even if they cannot establish long-term reliability. Unknown provenance stays unknown.

## Prioritization is a policy, not a discovered universal truth

A deterministic score can be reasoned and repeatable without being an objectively correct answer. The design must expose both evidence-derived inputs and PM preferences. Use a few anchored dimensions, document the trade-offs used to set weights, and keep raw observations visible. Stakeholder swing weighting and sensitivity analysis provide a better foundation than asking an LLM for an unexplained number. [Government Analysis Function MCDA guidance](https://analysisfunction.civilservice.gov.uk/policy-store/an-introductory-guide-to-mcda/)

Do not hardcode that charging outranks comfort or that China always values rear seats. Calculate from the selected evidence and policy. A provisional equal-weight configuration may support exploratory runs, but must be labelled uncalibrated and must not be represented as a BMW-approved strategy. The detailed contract is in [DECISION_ENGINE.md](DECISION_ENGINE.md).

## Web enrichment that adds evidence

The research has already identified useful source contrasts: BMW's China-specific 5 Series positioning, an ADAC test reporting range/charging observations and HMI criticism, Mercedes-Benz's model-specific charging specification, and Euro NCAP's HMI assessment changes. These support careful questions rather than automatic conclusions. See the opened sources and bounded claims in [WEB_RESEARCH.md](WEB_RESEARCH.md).

For example, an ADAC measured result and a Mercedes US specification differ in market, model year, method and conditions. The app should flag the mismatch, not announce a two-minute competitive advantage. Nor should a 2026 German equipment list disprove a US feedback record about rear climate control.

The present pack includes curated web evidence seeds. It does not pretend an automated scraper has already been implemented. In the sprint, collect a small set of permitted pages, save provenance, parse factual claims, and show the cleaning history. A few well-matched sources are more valuable than hundreds of unattributed snippets.

## Human control where it matters

PM decisions are most valuable when choosing scope and strategy, resolving cross-market conflicts, approving weakly supported targets, accepting feasibility compromises and committing a requirement. Automate routine parsing and retrieval. Escalate uncertainty by decision impact; do not force manual approval of every harmless transformation.

The UI should make the decisive evidence easy to inspect: original snippet or cell, sample count, market coverage, competing evidence, assumptions, score contributions and the consequence of a PM edit. A challenge action must reopen the relevant argument, not simply ask the LLM to defend its first answer.

## Quality evidence to win credibility

Show actual held-out extraction accuracy, evidence entailment, unsupported-claim rate, requirement rubric scores, ranking agreement with human assessments, and latency/cost. Report sample sizes, uncertainty and subgroup gaps. A score of 95% without a definition and denominator is not credible. Gold annotations must be independently checked rather than copied from the supplied category labels. [OpenAI evaluation guidance](https://developers.openai.com/api/docs/guides/evaluation-best-practices)

Include ordinary software checks for duplicate invariance, missing fields, citation resolution, forbidden state transitions and audit replay. Add a judge challenge: upload a new schema or switch to another model and show either valid adaptation or explicit abstention. A model that recognizes missing evidence is more useful than a model that confidently fills every field.

## 24-hour priorities

Deliver one full path: G60 evidence → a small representative set of requirements → transparent scoring → PM challenge/edit → revised score → audit replay. Use SQLite and a thin Streamlit UI, with the core independently testable. Ingest all models deterministically but run paid inference on a recorded stratified sample first. Scale the run only if measured throughput and cost allow.

Defer fine-tuning, full-web crawling, elaborate multi-agent orchestration, detailed vehicle engineering simulation, and enterprise integration. Keep a configuration-driven transfer path and test it. The honest pitch is a functioning decision-support prototype with demonstrated quality and known limits, not a production-ready automotive requirements authority.

## Main failure modes to prevent

| Temptation | Consequence | Design response |
|---|---|---|
| Count each labelled row | False recurrence and skewed rank | One evidence unit per unique feedback record per theme |
| Ask one giant prompt for final rankings | Unsupported targets and irreproducible scores | Separate extraction, synthesis, validation and scoring |
| Treat all sources equally or make experts absolute | Repetition or prestige replaces evidence | Claim-specific applicability and provenance |
| Fill unknown costs with plausible euros | False feasibility and fabricated precision | Pending estimates and conditional decisions |
| Tune until demo looks good | Fails unseen data | Lock grouped holdout and vehicle transfer slice early |
| Let US-heavy comments represent all regions | Erases regional needs | Regional panels and explicit missing coverage |
| Treat future forecasts as facts | Brittle long-term decisions | Scenarios with assumptions, dates and review triggers |
| Build the UI first | Attractive prototype with no defensible model | Vertical slice and evaluation before polish |

Unanswered questions about source identity, survey denominators, and engineering inputs do not block deterministic ingestion or the first evaluation fixture.
