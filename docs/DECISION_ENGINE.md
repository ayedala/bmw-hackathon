# Evidence, prioritization and decision logic

This is a proposed implementation contract. Numerical examples and default policies here are illustrative, not BMW decisions or validated predictive models.

## Implemented local slice (10 October 2026)

`src/bmw_pm/decision/requirements.py` groups signals by domain **and customer outcome**, counts unique supporting feedback IDs, keeps praise as preservation evidence, and routes mixed or neutral statements to context. It checks each linked exact span and source hash. Semantic entailment remains `unreviewed`; anonymized Source A–D records retain `author_expertise=unknown`. G60 charging applicability is declared in the vehicle profile for BEV/PHEV, and its denominator uses only that scoped eligible corpus.

The exploratory policy marks each weighted criterion as `customer` or `business`. `src/bmw_pm/decision/scoring.py` reports a separate 0–100 scenario interval for each dimension and the combined value interval. Missing criterion weights remain in the upper bound. Engineering feasibility is a separate status and basis, not an inferred numeric criterion. The displayed list sorts by combined lower bound with a stable ID tie-break; `assess_ranking` counts pairwise comparisons unresolved by overlapping intervals. In the real G60 US run, **only evidence-backed reach has a data-derived criterion input**; customer impact, both business criteria and feasibility are unknown. This is a triage view, not a decision-grade BMW priority order. The baseline and optional live extractor have not been compared against human labels.

## Separate four questions

1. **What does the evidence say?** Atomic claims, context, recurrence, source quality, uncertainty and counterevidence.
2. **What customer outcome could improve?** A solution-neutral need with alternatives and a proposed validation method.
3. **How valuable is the improvement under this strategy?** A reproducible value score or score interval.
4. **Can and should we commit now?** Feasibility, dependencies, effort, risk, lifecycle timing and PM decision.

Never merge these into one LLM-generated `priority: 94`. A value score is a policy-dependent index, not a probability of commercial success or an engineering feasibility certificate.

## Evidence units and claims

One feedback ID may support several distinct signals, but contributes at most once to a given requirement's recurrence in a given scope. A publisher's reposted article is one origin family. An official claim quoted by ten blogs is one underlying claim plus ten repetitions, not ten independent confirmations.

Each evidence link has a role: `supports`, `contradicts`, `context`, `baseline`, or `constraint`. Store an exact span/cell plus an entailment decision and verifier. Shared topic does not establish support. An engineering opinion is a constraint only after scope and authority are checked; otherwise it is a hypothesis for review.

Classify conflicts as: measurement disagreement under matched conditions; preference difference; context difference; feasibility conflict; source-version conflict; or uncertain interpretation. Split contexts before declaring contradiction. Praise for range on a short home-charged commute does not disprove poor cold-weather long-distance experience.

## Source reliability without prestige bias

Store a vector rather than a magic credibility score:

| Field | Values/examples | Use |
|---|---|---|
| Provenance verification | supplied-anonymized, self-reported, verified-document, independently-measured | Distinguish known from asserted authority |
| Claim method | personal experience, instrumented test, specification, survey summary, forecast, opinion | Decide what the source can substantiate |
| Applicability | matched, partial, mismatched, unknown | Vehicle/market/year/trim/powertrain/conditions |
| Specificity | direct observation, quantified observation, broad impression | Weight interpretation effort and confidence |
| Independence | origin-family ID and relationship | Prevent copied evidence inflation |
| Timing | publication/observation time and freshness policy | Assess version applicability, not arbitrary universal decay |

For supplied A–D records use `supplied-anonymized`; owner/expert status is unknown. Explicit “I own…” supports self-reported ownership, not verified purchase. A measured technical test is stronger for that measurement than an unverified guess. A non-owner's purchase objection remains relevant to desirability. Do not suppress accessibility or rare severe reports because they are infrequent.

MVP: use the vector to qualify claims, show evidence tiers and separate known-method sources. Do not multiply frequency by guessed author prestige. If a later version uses numerical reliability weights, calibrate them against adjudicated claim correctness on development data, retain an equal-weight baseline, and evaluate by claim type and source group.

## Customer evidence statistics

For requirement r and scope m, define an eligible corpus before looking at the ranking: vehicle/market/powertrain, ingestion version, inclusion rules and count N. Use unique feedback IDs, not rows or assumed people.

- `support_count`: unique eligible IDs supporting the need after validated extraction.
- `counter_count`: unique eligible IDs opposing the proposed outcome or supporting the status quo. Keep context-specific praise separate when it is not a real contradiction.
- `mention_share = support_count / N`: descriptive share **in the collected corpus**, not population prevalence.
- `extraction_coverage = successfully_processed_eligible_IDs / N`.
- `legacy_label_count`: diagnostic only, never added to AI counts.

If U eligible records are unprocessed/abstained, the possible mention share is `[support_count/N, (support_count+U)/N]`, with an explicit statement that this covers processing uncertainty only, not sampling bias or extraction error. For a partial stratified sample, show stratum counts and use only that sample's denominator unless a documented sampling estimator is implemented. Do not silently use 4,000 as a denominator after extracting 200 records.

Do not add study distributions, comments and expert articles into one numerator. Triangulate them as different evidence channels. Unknown study sample sizes prevent statistical pooling. For review coverage, count every supporting snippet even if it is ineligible for numeric recurrence.

## Requirement generation

Template: **For [user/use case] in [market and vehicle scope], the successor vehicle should enable [customer outcome] under [conditions], assessed by [test method], with [target or target-pending status].**

Keep problem and solution separate. “Restore physical buttons” is an implementation candidate. “Adjust frequently used climate settings with low visual/manual demand” is the customer outcome. Compare physical controls, persistent shortcuts, and improved voice interaction as alternatives; do not presume that one is feasible or preferred in every use case.

Each requirement includes supporting claims, counterclaims, baseline equipment knowledge, alternatives, expected benefit, unresolved assumptions, evidence gaps, and engineering review status. A numeric target needs its source or an explicit `proposed_target` label. No invented cost, battery capacity or charging physics.

## Practical scoring contract

Use a small additive multi-criteria **value** model, conditional on a published policy and scope. The current policy has four criteria in two displayed dimensions, customer and business; keep feasibility and cost outside the value sum.

| Dimension | Anchor 0 | Anchor 4 | Scoring evidence |
|---|---|---|---|
| Customer impact I | No demonstrated improvement in the specified customer task | Material improvement to a repeatedly blocked core use case | Specific task consequence; severity rubric and human examples |
| Evidence-backed reach R | No observed affected eligible records, with sufficient processing coverage | High occurrence within the scoped corpus under a PM-defined saturation point | Unique-ID counts and denominator; corroborating study shown separately |
| Strategic contribution S | No contribution to the agreed product objectives | Strong direct contribution to a stated, approved objective | Versioned objective plus an explicit causal argument |
| Competitive/outlook need O | Verified adequate position for the planning scenario | Material matched gap or well-supported future scenario pressure | Scoped benchmarks, dated trend scenario and uncertainty |

Intermediate anchors 1/2/3 must be written and illustrated in the policy before a decision-grade run. For I: minor inconvenience / repeated workaround / significant task impairment. For S: indirect / partial / direct contribution. For O: small gap / meaningful gap / substantial gap under a documented scenario. These are proposed ordinal rubrics, not yet validated interval scales.

R may use a transparent monotone mapping `R = 4 * min(mention_share / saturation_share, 1)`. `saturation_share` is a policy parameter defined on the same corpus type, never a hidden universal constant. Set it from reviewed development examples and PM judgment; retain raw shares beside it. If coverage is absent, R is unknown rather than zero. For survey-led scopes with no comparable verbatim denominator, use a separately named survey policy after scale review; do not pretend it is the same R metric.

For known dimensions `x in [0,4]`, `V_rm = 100 * sum(w_j * x_j / 4)`, where `w_j >= 0` and `sum(w_j)=1`. Computation is deterministic. LLMs may propose evidence-backed ordinal labels, but may not supply unexplained weights or a final rank. The scoring arithmetic, unknown intervals, dimension views and overlap check are implemented and covered by synthetic tests. Anchored human ratings, PM-approved weights and deterministic sensitivity scenarios remain outstanding.

### Weight elicitation

Show the PM the defined worst-to-best improvement on each dimension. Ask which swing is most valuable and how the others compare, then normalize those ratings into weights. Record the answers, anchors, rationale and approval. This follows the principle of [swing weighting](https://analysisfunction.civilservice.gov.uk/policy-store/an-introductory-guide-to-mcda/); it does not make the resulting weights universal or objective.

For an exploratory demo before PM input, equal weights are an explicit seed policy named `exploratory_equal_v1`. Display `policy_unapproved`. Do not claim it is optimized. A code constant that enforces a documented formula is acceptable; a vehicle-name branch that assigns a desired winner is not.

Check overlap between I/R and S/O. Do not count the same market trend as both strategic and outlook contribution without explaining the distinct value. If criteria interact materially or are not preferentially independent, label additive scoring approximate and retain pairwise review; do not introduce a complex optimizer merely to hide this limitation.

### Missingness and intervals

Do not renormalize remaining weights when a dimension is missing; that can reward poorly documented candidates. Use unknown dimension range [0,4], producing a value interval. A missing dimension contributes 0 to the lower bound and its full policy weight to the upper bound. These are **scenario bounds**, not confidence intervals.

List candidates by lower bound for a conservative exploratory view with a stable ID tie-break. Show overlap and mark unresolved comparisons. Queue high-upper-bound/low-evidence candidates for research; do not quietly bury them. Decision-grade approval requires either filled evidence or a recorded conditional acceptance of the unresolved uncertainty.

### Regions and business exposure

Always show regional scores before a family-level view. Market weights may come from the supplied 2025 shares or 2030 scenario, selected and approved by the PM. A family-level value interval can be `sum(market_weight * regional_value_interval)` only for comparable regional policies. Missing China contributes an unknown interval, not zero and not a redistributed weight.

For G60-only or BEV-only requirements, G60/G68 aggregate sales shares are a labelled proxy at most, because variant and powertrain splits are missing. Prefer regional panels until the PM accepts that approximation. A sensitivity slider is a planning assumption, not a forecast of customer demand.

## Feasibility, cost and portfolios

Use `feasible_reviewed`, `conditional`, `unknown`, `blocked` with reviewer, evidence and scope. Keep effort/cost as unknown or reviewed ordinal ranges, with basis. A feature existing on a competitor demonstrates precedent, not BMW packaging feasibility or cost.

Display customer value against effort and flag dominated alternatives when comparable: A dominates B only if A is no worse on all reviewed benefits/cost dimensions and strictly better on one, with uncertainty handled conservatively. If costs are unknown, dominance cannot be established on cost. Dependencies and mutually exclusive variants must be explicit.

Known hard constraints gate commitment; an LLM may flag a possible safety/regulatory issue for a qualified review but cannot certify compliance. A high-value blocked requirement can remain visible as a research priority. Avoid `value / cost` when cost is an invented number or ordinal category.

## Sensitivity and counterfactuals

Recompute deterministically when the PM changes market mix, scenario, score evidence, feasibility, scope or weights. For an exploratory stability check, vary one weight by ±20%, renormalize, and compare top-five overlap and pairwise reversals. Also test equal-market weights, supplied 2025/2030 shares, source-family removal and disputed-claim removal. The ±20% is a declared test range, not a validated uncertainty distribution.

Explain each change with the affected criterion contribution, altered evidence and remaining unknowns. Treat near ties as near ties. Report stable top groups across scenarios, not a misleadingly precise single order.

Physical counterfactuals such as battery size → range → mass → cost need validated engineering models. The MVP supports **decision scenarios**, not vehicle performance simulation.

## Numerical example, entirely illustrative

Two hypothetical candidates have complete scores A=(3,2,3,1) and B=(2,3,2,3) for (I,R,S,O). Equal weights give A=56.25 and B=62.5. Under a PM policy (0.4,0.1,0.4,0.1), A=67.5 and B=55.0. The order reverses because customer impact and strategy receive more value, not because a model regenerated persuasive prose.

If A's O is unknown, its equal-weight interval is [50,75]. Its rank against B is unresolved; “A=56.25” is no longer valid. This example is a fixture for testing arithmetic and missingness. It must never be presented as a real BMW recommendation.

## Rationale output

Produce a concise argument record: conclusion; strongest supporting evidence; strongest counterevidence; policy contributions; assumptions; alternative rejected and why; confidence limitations; what evidence or preference change would reverse the decision. This is reviewable justification, not a request to expose private chain-of-thought. The displayed explanation must be derived from the actual evidence and score record, not generated independently after sorting.
