# Demonstration and presentation plan

Target a five-minute presentation plus live questions. Adjust to the organizer's actual timing. The currently working G60 US baseline provides seven traceable candidate cards, score ranges, PM review and audit replay. Live AI quality, linked sales/equipment/web facts, sensitivity and the export are still to be completed. Only show a segment as implemented after its recorded acceptance evidence exists.

## Five-minute story

| Time | Show | Point |
|---|---|---|
| 0:00–0:35 | One proposed G60 decision and competing customer needs | Successor planning requires a choice under uncertainty |
| 0:35–1:15 | Supplied data lineage and unique-ID reconciliation | 13,771 annotation rows represent 10,128 feedback IDs, not independent customers |
| 1:15–2:00 | One card with exact feedback spans, study context, verified equipment fact and scoped public claim | Each part of the argument has a locator and applicability limit |
| 2:00–2:45 | Four criterion contributions, unknowns, regional coverage and deterministic sensitivity | Only reach is data-derived today; reviewed PM inputs must drive additional criteria |
| 2:45–3:35 | BMW PM challenges a premise; new revision and score snapshot appear | A consequential human decision changes the recorded argument |
| 3:35–4:15 | Earlier decision replayed beside the revised one | The two-year process retains decision memory |
| 4:15–5:00 | Held-out keyword-versus-AI results, PM judgments and F70/G70 transfer | Quality claims use recorded sample sizes and failures |

The card and challenge sequence above is the **target demonstration**, not a claim that every segment already works. Do not display the standalone YouTube research output as integrated web evidence until an exact, scoped claim is imported and reviewed. If PM weights or ratings have not arrived, show the equal-weight policy as unapproved and the corresponding criteria as unknown.

## Evidence-grounded candidate examples

These are **draft hypotheses for building the demo**, not final ranked requirements. Do not use them as blind evaluation cases after development.

### A. Climate-control interaction

Actual anchor: `G60_feedback_hackathon.xlsx`, `Feedback_Explorer`, row 344, ID `G60-0271`, US/ICE. The record reports distracting touchscreen airflow adjustment, preference for knobs, and an explanation of voice-assistant capability that the customer had not known. This supports both an interaction problem and an alternative explanation involving discoverability.

Draft outcome: drivers can adjust frequently used climate settings with low interaction effort in the defined driving-use scenario. Compare tactile controls, persistent shortcuts and discoverable voice access. Validation method: matched user-task study of task completion and visual/manual demand. Target remains pending a baseline and qualified review.

Counter/context: ID `G60-0092`, row 114, praises climate performance; it does not directly refute control usability. W03 is an external expert critique relevant to interaction. W05 gives assessment context, not a legal command to add particular buttons. Show that the model distinguishes these relationships.

### B. Predictable electric-range information

Actual anchor: ID `G60-0051`, row 59, US/BEVE, contains reported range-estimation and cold-weather concerns alongside other complaints. Atomic extraction must separate them. ID `G60-0078`, row 95, describes a positive daily-commute/home-charging use case; ID `G60-0083`, row 103, JP/BEVE, praises range.

Draft outcome: electric-vehicle drivers can plan journeys with range information that reflects defined operating conditions. Keep range-estimation accuracy, cold-weather energy use, charging-stop duration and maximum battery range as separate needs until evidence links them. W03 is scoped test context, not proof of any individual complaint's cause.

Do not promise 1,000 km or 10-minute charging. Do not turn the three selected examples into prevalence statistics. Show real full-run counts only after the extraction/validation job completes.

### C. Rear-passenger climate access and scope mismatch

Actual anchor: ID `G60-0021`, row 24, US/ICE, requests rear-seat climate control. ID `G60-0236`, row 287, US/BEVE, includes a related complaint. The supplied G60 equipment PDF page 8 is a German-market 2026 matrix with derivative-specific availability.

Draft outcome: rear occupants can achieve comfortable climate conditions in the defined use case. PM challenge: “Is this a missing feature or a trim/market/discoverability issue?” Correct response: current evidence does not identify the feedback vehicle's exact trim/year, so request matching baseline information instead of declaring either source wrong. This is an excellent demonstration of useful abstention.

## What to show from each offered dataset

- Feedback: raw row → canonical ID → atomic signal → requirement.
- Study: scoped category and original distribution/mean → supporting context; no invented sample sizes or pooled scale.
- Equipment: verified cell/symbol and derivative → known baseline or explicit applicability gap.
- Sales: selected 2025 or 2030 scenario → market exposure assumption and rank sensitivity after its adapter is integrated; no invented powertrain sales.
- Web: source method and dated scope → qualified claim with locator; show one incompatible comparison rejected.

## Quality slide

Populate from actual `runs/<run_id>/evaluation.md`: sample sizes, keyword baseline versus AI, extraction F1 and coverage, human-confirmed supported-claim rate, requirement rubric, PM preference agreement, transfer errors, and cold/warm runtime. Separate team proxy labels from BMW PM judgments. The 12 software tests and source-span checks belong on an engineering validation slide, not in place of model accuracy. If a metric was not measured, say “not measured.”

## Judge questions to rehearse

**Why these weights?** Show PM swing choices, anchors and sensitivity; identify seed policies as unapproved.

**Why believe the expert?** Show claim method, conditions and independent origin; contrast technical measurement with lived experience and source anonymity.

**Does it work on other models?** Switch profile, show unchanged logic and held-out results; list the mapping/policy changes and remaining gaps.

**What if evidence changes?** Import a new scoped fact, show affected requirements, review request and replay of the earlier decision.

**Is this an engineering simulator?** Show customer-value scenarios; technical feasibility and quantitative vehicle models require validated engineering inputs.

## Fallback

Prepare a labelled cached replay with the full manifest and a readable Markdown export; neither is implemented yet. If live network/provider access fails during the demo, disclose the failure and use only a previously validated run. Never present cached model output as live or a synthetic constraint as a BMW engineering fact.
