# Demonstration and presentation plan

Target a five-minute presentation plus live questions. Adjust to the organizer's actual timing. Do not claim that a winning outcome is guaranteed; the strategy is to make the evidence and decision quality easy to assess.

## Five-minute story

| Time | Show | Point |
|---|---|---|
| 0:00–0:35 | One PM decision and two competing needs | Successor planning combines current experience, uncertainty and strategy |
| 0:35–1:15 | Data lineage and before/after cleaning counts | We used the supplied four data types and avoided annotation inflation |
| 1:15–2:00 | Requirement card with support, counterevidence and a web fact | AI turns evidence into a scoped customer outcome |
| 2:00–2:45 | Criteria contributions, region coverage, policy sensitivity | Ranking follows evidence and explicit preferences |
| 2:45–3:35 | PM challenge/edit, changed score and revision diff | Human judgment changes the result at a consequential point |
| 3:35–4:15 | New batch and historical replay | The process supports repeated decisions over two years |
| 4:15–5:00 | Measured baseline comparison and transfer test | Quality and generalization are tested, with limitations visible |

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
- Sales: selected 2025 or 2030 scenario → market exposure assumption and rank sensitivity; no invented powertrain sales.
- Web: source method and dated scope → qualified claim with locator; show one incompatible comparison rejected.

## Quality slide

Populate from actual `runs/<run_id>/evaluation.md`: sample sizes, baseline versus system, extraction F1, supported-claim rate, requirement rubric, transfer errors, and cold/warm runtime. If ranking labels are team proxies, say so. If no valid metric was measured, say “not measured” rather than replacing it with a persuasive anecdote.

## Judge questions to rehearse

**Why these weights?** Show PM swing choices, anchors and sensitivity; identify seed policies as unapproved.

**Why believe the expert?** Show claim method, conditions and independent origin; contrast technical measurement with lived experience and source anonymity.

**Does it work on other models?** Switch profile, show unchanged logic and held-out results; list the mapping/policy changes and remaining gaps.

**What if evidence changes?** Import a new scoped fact, show affected requirements, review request and replay of the earlier decision.

**Is this an engineering simulator?** Show customer-value scenarios; technical feasibility and quantitative vehicle models require validated engineering inputs.

## Fallback

Keep a labelled cached replay with full manifest. If live network/provider access fails, display the failure and switch explicitly to that replay. Never present cached model output as live or a synthetic constraint as a BMW engineering fact. Preserve a readable Markdown export for a reliable evidence walkthrough.
