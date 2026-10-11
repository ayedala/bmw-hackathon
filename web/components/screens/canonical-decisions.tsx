"use client";

import Link from "next/link";
import { ChallengeResult } from "@/components/app/canonical-review-controls";
import { CrpsInterval } from "@/components/app/canonical-crps";
import { DecisionBadge } from "@/components/app/badges";
import { EmptyState, PageHeader, Section } from "@/components/app/layout-parts";
import { ReasoningSourceNotice } from "@/components/app/reasoning-chain";
import { formatDateTime, humanize } from "@/lib/domain/derive";
import { useStore } from "@/lib/store";
import { useRequirementRows } from "@/lib/view";

export function CanonicalDecisionsScreen() {
  const { market, canonicalChallenges, auditVerification } = useStore();
  const rows = useRequirementRows(market);
  const pending = canonicalChallenges.filter((challenge) => !challenge.resolution);
  return <div className="space-y-6"><PageHeader title="PM decisions" question="Who reviewed each real requirement, and which challenges still need a decision?" /><ReasoningSourceNotice />
    <p className="rounded border border-slate-200 bg-white p-3 text-xs">Every decision below is from the review database. {auditVerification ? auditVerification.valid ? "The backend hash chain verifies." : `The backend reports a broken chain: ${auditVerification.checkpoint}.` : "Audit verification is unavailable."} Each action names an exact requirement revision and request ID.</p>
    <Section title={`Open reassessments (${pending.length})`} description="A challenge proposal changes no authoritative CRPS until accepted by a PM.">{pending.length ? <div className="space-y-4">{pending.map((challenge) => <ChallengeResult key={challenge.challenge_id} challenge={challenge} />)}</div> : <EmptyState title="No unresolved challenge proposal." />}</Section>
    <Section title="Requirement decisions" description="Approval, rejection, deferral and edits are recorded against immutable revisions."><ul className="divide-y divide-slate-100 rounded border border-slate-200 bg-white">{rows.map((row) => <li key={row.id} className="space-y-2 p-3 text-xs"><div className="flex flex-wrap items-center gap-2"><Link href={`/requirements/${row.id}`} className="min-w-0 flex-1 font-medium text-brand hover:underline"><span className="font-mono">{row.id}</span> · {row.revision.title}</Link>{row.bundle.crps ? <CrpsInterval score={row.bundle.crps} /> : <span>Score unavailable</span>}<DecisionBadge status={row.status} /></div>
      {row.bundle.decisions.length ? <ol className="space-y-1">{row.bundle.decisions.slice().reverse().map((decision) => <li key={decision.decision_id} className="rounded bg-slate-50 p-2"><span className="font-medium">{humanize(decision.action)}</span> · r{decision.requirement_revision} · {decision.actor_id} · {formatDateTime(decision.recorded_at)}<span className="block">{decision.rationale}</span><span className="block break-all font-mono text-2xs text-slate-500">{decision.request_id}</span></li>)}</ol> : <p className="text-slate-500">No PM decision recorded.</p>}
    </li>)}</ul></Section>
  </div>;
}
