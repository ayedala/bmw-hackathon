/**
 * Markdown decision brief — a frontend counterpart of
 * bmw_pm.decision.planning.decision_brief. Contains proposal text, PM
 * judgements and decisions; no verbatim customer text is included.
 */
import type { EvidenceLinkJudgment, PriorityPolicy } from "@/lib/domain/contracts";
import { DECISION_STATUS_LABEL, FACTOR_LABEL } from "@/lib/domain/derive";
import type { Dataset } from "@/lib/domain/model";
import { PRIORITY_FORMULA } from "@/lib/domain/scoring";
import type { RequirementRow } from "@/lib/view";

export function buildDecisionBrief(dataset: Dataset, rows: RequirementRow[], policy: PriorityPolicy, judgments: EvidenceLinkJudgment[], actorId: string): string {
  const now = new Date().toISOString();
  const weights = (Object.keys(policy) as (keyof PriorityPolicy)[]).map((k) => `${FACTOR_LABEL[k]} ${policy[k].toFixed(2)}`).join(", ");
  const lines: string[] = [
    "# BMW successor decision brief",
    "",
    `Vehicle: ${dataset.vehicle.family} (${dataset.vehicle.generation}) · Market: United States · Proposal set: ${dataset.planning.version}`,
    `Planning window: ${dataset.planning.window} (assumed horizon, not a BMW launch commitment).`,
    `Prepared ${now} by ${actorId} in BMW Product Decision Lab. Internal.`,
    "",
    `Priority (CRPS) = ${PRIORITY_FORMULA}. Weights: ${weights}. Declared preferences, not an approved BMW policy.`,
    "Ratings are PM judgements, not measured prevalence. Seed ratings are illustrative. Engineering feasibility is a separate review.",
    "",
  ];
  const ordered = [...rows].sort((a, b) => (b.score ?? -1) - (a.score ?? -1));
  for (const r of ordered) {
    const p = r.bundle.proposal;
    const lastDecision = r.bundle.decisions[r.bundle.decisions.length - 1];
    const linkJudgments = judgments.filter((j) => j.requirement_id === r.revision.requirement_id && j.requirement_revision === r.revision.revision);
    lines.push(
      `## ${r.id} · ${r.revision.title} · r${r.revision.revision}`,
      "",
      r.revision.customer_outcome,
      "",
      `- **Priority:** ${r.priority} · CRPS ${r.score?.toFixed(1) ?? "—"} (${r.basis === "saved" ? "saved PM assessment" : "illustrative seed"}) · factors ${(Object.keys(r.factors) as (keyof typeof r.factors)[]).map((k) => `${FACTOR_LABEL[k]} ${r.factors[k]}`).join(", ")}`,
      `- **Confidence:** ${r.confidence} · evidence ${r.balance.supporting} supporting / ${r.balance.contradicting} contradicting / ${r.balance.independent_sources} independent sources`,
      `- **PM decision:** ${DECISION_STATUS_LABEL[r.status]}${lastDecision ? ` — ${lastDecision.actor_id}, ${lastDecision.recorded_at}: ${lastDecision.rationale}` : ""}`,
      `- **Customer value:** ${p.value}`,
      `- **Interpretation:** ${p.interpretation}`,
      `- **Future assumption:** ${p.future_assumption}`,
      `- **Contrary evidence / trade-off:** ${p.contrary}`,
      `- **Validation:** ${p.validation}`,
      `- **Revisit when:** ${p.review_trigger}`,
      `- **Anchor records:** ${p.anchor_ids.join(", ")} (verbatim text in the private database)`,
      `- **Evidence links assessed:** ${linkJudgments.length}${linkJudgments.length ? ` (${linkJudgments.map((j) => `${j.signal_id}: ${j.verdict.replace(/_/g, " ")}`).join("; ")})` : ""}`,
      "",
    );
  }
  return lines.join("\n");
}
