"use client";

import Link from "next/link";

import { DecisionBadge, PriorityBadge } from "@/components/app/badges";
import { CanonicalScoreBreakdown, CrpsInterval, RequirementQualityPanel } from "@/components/app/canonical-crps";
import { CanonicalReviewControls } from "@/components/app/canonical-review-controls";
import { EvidenceList, type EvidenceListEntry } from "@/components/app/evidence-list";
import { EmptyState, KeyValue, PageHeader, Section } from "@/components/app/layout-parts";
import { FindingLinks, NeedLinks, ReasoningSourceNotice } from "@/components/app/reasoning-chain";
import { RecordingTarget } from "@/components/app/review-authority";
import { decisionStatus, formatDateTime, humanize, latestRevision } from "@/lib/domain/derive";
import { judgmentsFor, useStore } from "@/lib/store";

export function CanonicalRequirementWorkspace({ displayId }: { displayId: string }) {
  const { dataset, requirementByDisplayId, evidenceById, audit, judgments } = useStore();
  const resolved = dataset.reasoning.requirements.find((row) => row.artifact.requirement_id === displayId);
  const bundle = requirementByDisplayId.get(displayId);
  if (!resolved) return <EmptyState title="Requirement is not in the canonical research artifacts." detail={`No real requirement resolves to ${displayId}. No demo record is substituted.`} action={<Link href="/requirements" className="text-xs text-brand underline">Back to requirements</Link>} />;
  if (!bundle) return <div><PageHeader title={resolved.artifact.title} question={resolved.artifact.requirement} /><ReasoningSourceNotice /><EmptyState title="Authoritative review state is unavailable." detail="The canonical artifact exists, but no reviewable requirement revision was loaded. Review actions and scores are unavailable until the backend import succeeds." /><div className="mt-5 space-y-5"><Section title="Customer needs"><NeedLinks needs={resolved.needs} /></Section><Section title="Findings"><FindingLinks findings={resolved.findings} /></Section></div></div>;

  const rev = latestRevision(bundle);
  const artifact = resolved.artifact;
  const refs = rev.evidence_references ?? [];
  const supporting: EvidenceListEntry[] = [];
  const opposing: EvidenceListEntry[] = [];
  const context: EvidenceListEntry[] = [];
  const unresolvedReferences = refs.filter((reference) => !evidenceById.has(reference.evidence_id));
  for (const reference of refs) {
    const evidence = evidenceById.get(reference.evidence_id);
    if (!evidence) continue;
    const entry = { evidence, note: `${reference.evidence_id} · ${reference.evidence_kind} · source market ${reference.market || "unspecified"}${reference.market !== "DE" ? "; Germany applicability requires review" : ""}` };
    if (reference.role === "supports") supporting.push(entry);
    else if (reference.role === "opposes") opposing.push(entry);
    else context.push(entry);
  }
  const missingRoles = refs.length === 0;
  if (missingRoles) {
    for (const row of resolved.evidence) {
      const evidence = evidenceById.get(row.evidence_id);
      if (evidence) context.push({ evidence, note: "Cited by synthesis; requirement-relative stance has not been imported." });
    }
  }
  const independent = new Set(refs.filter((ref) => !ref.duplicate_of).map((ref) => ref.independence_group || ref.source_url || ref.evidence_id));
  const families = new Set(refs.filter((ref) => !ref.duplicate_of).map((ref) => ref.source_family || "unspecified"));
  const linkJudgments = judgmentsFor(judgments, rev.requirement_id, rev.revision);
  const assess = { displayId, judgments: linkJudgments };
  const assessed = refs.filter((ref) => linkJudgments.has(ref.evidence_id)).length;
  const events = audit.filter((event) => event.object_id === rev.requirement_id || event.object_id === bundle.display_id).slice().reverse();
  const status = decisionStatus(rev, bundle.decisions);
  const unresolvedIssues = dataset.reasoning.issues.filter((issue) => issue.from_id === displayId || resolved.needs.some((need) => need.artifact.need_id === issue.from_id) || resolved.findings.some((finding) => finding.artifact.finding_id === issue.from_id));

  return (
    <div>
      <nav aria-label="Breadcrumb" className="mb-3 text-xs text-slate-500"><Link href="/requirements" className="hover:text-brand">Requirements</Link><span className="mx-2">/</span><span className="font-mono">{displayId}</span></nav>
      <PageHeader title={rev.title} question={`${dataset.vehicle.successor_label} · ${rev.scope.countries.join(", ")} · planning horizon ${dataset.vehicle.horizon}`} meta={<><span className="font-mono">{displayId}</span><span>Revision {rev.revision}</span><span>{humanize(bundle.topic)}</span><span>{rev.scope.models.join(", ")}</span><span>{rev.scope.powertrains.join(" / ")}</span></>} />
      <ReasoningSourceNotice />
      <div className="grid grid-cols-2 gap-px overflow-hidden rounded-md border border-slate-200 bg-slate-200 md:grid-cols-5">
        <div className="bg-white p-3"><span className="block text-2xs uppercase tracking-wide text-slate-500">CRPS interval</span><div className="mt-1 text-lg">{bundle.crps ? <CrpsInterval score={bundle.crps} /> : "Unknown"}</div></div>
        <div className="bg-white p-3"><span className="block text-2xs uppercase tracking-wide text-slate-500">Decision Confidence</span><div className="mt-1 text-lg font-medium tabular-nums">{bundle.crps ? `${bundle.crps.confidence.value_0_to_100.toFixed(1)}/100` : "Unknown"}</div></div>
        <div className="bg-white p-3"><span className="mb-2 block text-2xs uppercase tracking-wide text-slate-500">Priority band</span>{bundle.crps ? <><PriorityBadge priority={bundle.crps.result.band} hint={bundle.crps.result.band_basis} /><span className="ml-2 text-xs">{bundle.crps.result.band_label}</span></> : <span className="text-xs">Not assessed</span>}</div>
        <div className="bg-white p-3"><span className="mb-2 block text-2xs uppercase tracking-wide text-slate-500">Human review</span><DecisionBadge status={status} /></div>
        <div className="bg-white p-3"><span className="block text-2xs uppercase tracking-wide text-slate-500">Feasibility</span><div className="mt-1 text-xs font-medium">{humanize(rev.feasibility)}</div><p className="mt-1 text-2xs text-slate-500">Separate from priority</p></div>
      </div>
      <nav aria-label="Requirement reasoning chain" className="my-4 flex flex-wrap items-center gap-2 text-xs text-brand"><a href="#canonical-outcome" className="hover:underline">Requirement r{rev.revision}</a><span aria-hidden>←</span><a href="#canonical-needs" className="hover:underline">{resolved.needs.length} customer needs</a><span aria-hidden>←</span><a href="#canonical-findings" className="hover:underline">{resolved.findings.length} findings</a><span aria-hidden>←</span><a href="#canonical-evidence" className="hover:underline">{refs.length || resolved.evidence.length} evidence references</a></nav>
      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_310px]">
        <div className="min-w-0 space-y-6">
          <div id="canonical-outcome" className="scroll-mt-20"><Section title="Customer outcome" description="The accepted scope is Germany 2030; evidence from other markets is contextual unless its applicability is justified.">
            <div className="rounded-md border border-slate-200 bg-white p-4"><p className="text-sm leading-relaxed text-zinc-900">{rev.customer_outcome}</p><dl className="mt-4 grid gap-4 md:grid-cols-2"><KeyValue label="Customer value"><span className="text-xs">{artifact.customer_value}</span></KeyValue><KeyValue label="Differentiation"><span className="text-xs">{artifact.differentiation}</span></KeyValue><KeyValue label="Validation method"><span className="text-xs">{rev.acceptance_proposal.method}</span></KeyValue><KeyValue label="Acceptance target"><span className="text-xs">{rev.acceptance_proposal.target === null ? "Unresolved; requires a declared baseline and engineering review" : `${rev.acceptance_proposal.target} ${rev.acceptance_proposal.unit || ""}`}</span></KeyValue><KeyValue label="Implementation cost"><span className="text-xs">{rev.implementation_cost_missing_reason}</span></KeyValue><KeyValue label="Target status"><span className="text-xs">{humanize(rev.target_status)}</span></KeyValue></dl></div>
          </Section></div>
          <CanonicalScoreBreakdown score={bundle.crps} />
          <div id="canonical-needs" className="scroll-mt-20"><Section title="Linked customer needs" description="Each need links back to the actual findings used to derive it."><NeedLinks needs={resolved.needs} /></Section></div>
          <div id="canonical-findings" className="scroll-mt-20"><Section title="Linked findings" description="Follow a finding to its precise evidence rows, source families and contradictory findings."><FindingLinks findings={resolved.findings} /></Section></div>
          <div id="canonical-evidence" className="scroll-mt-20 space-y-4">
            <Section title="Evidence balance" description="Roles are requirement-relative; source sentiment is not automatically a vote for or against the proposed outcome."><div className="grid grid-cols-2 gap-2 rounded-md border border-slate-200 bg-white p-3 text-xs md:grid-cols-3">{[["Supporting", supporting.length], ["Opposing", opposing.length], ["Neutral / context", context.length], ["Independent groups", independent.size], ["Source families", families.size], ["Human judgments", `${assessed}/${refs.length}`]].map(([label, value]) => <div key={label}><span className="block text-2xs text-slate-500">{label}</span><span className="tabular-nums">{value}</span></div>)}</div><p className="mt-2 text-2xs text-slate-500">Duplicates remain visible but are excluded from independent confirmation. Evidence volume is not customer prevalence. Source families: {[...families].join(", ") || "not imported"}.</p>{bundle.crps && <p className="mt-1 text-2xs text-slate-500">Last score used {bundle.crps.evidence_strength.supporting_groups} supporting / {bundle.crps.evidence_strength.contradicting_groups} opposing groups and excluded {bundle.crps.evidence_strength.duplicate_rows_excluded} duplicate rows. A changed judgment requires reassessment.</p>}</Section>
            {missingRoles && <EmptyState title="Requirement-level evidence roles are unavailable." detail="Synthesis citations are shown as context; no supporting or opposing relation is invented." />}
            <Section title="Supporting evidence"><EvidenceList entries={supporting} empty="No imported supporting references." tone="support" assess={assess} /></Section>
            <Section title="Opposing evidence"><EvidenceList entries={opposing} empty="No imported opposing references. This is a gap to challenge, not proof of consensus." tone="contradict" assess={assess} /></Section>
            <Section title="Neutral / context evidence"><EvidenceList entries={context} empty="No neutral or contextual references are linked." assess={missingRoles ? undefined : assess} /></Section>
            {unresolvedReferences.length > 0 && <Section title="References missing from the evidence browser" description="Their exact backend provenance is preserved below; they have not been replaced with demo evidence."><ul className="space-y-2">{unresolvedReferences.map((reference) => <li key={reference.evidence_id} className="rounded-md border border-amber-200 bg-white p-3 text-xs"><div className="font-mono">{reference.evidence_id}</div><p className="mt-1">{reference.claim}</p><blockquote className="mt-2 border-l-2 border-slate-200 pl-2 text-slate-600">{reference.exact_text}</blockquote><details className="mt-2"><summary className="cursor-pointer text-brand">Exact provenance</summary><pre className="mt-2 overflow-auto text-2xs">{JSON.stringify(reference, null, 2)}</pre></details></li>)}</ul></Section>}
          </div>
          <div className="grid gap-4 md:grid-cols-2"><Section title="Assumptions">{rev.assumptions.length ? <ul className="list-disc space-y-2 pl-4 text-xs leading-relaxed text-slate-600">{rev.assumptions.map((item) => <li key={item}>{item}</li>)}</ul> : <p className="text-xs text-slate-500">No assumptions declared in this revision.</p>}</Section><Section title="Missing evidence">{rev.missing_evidence.length ? <ul className="list-disc space-y-2 pl-4 text-xs leading-relaxed text-slate-600">{rev.missing_evidence.map((item) => <li key={item}>{item}</li>)}</ul> : <p className="text-xs text-slate-500">No gap declared in the source artifact; unknown score factors and opposing-evidence gaps still require review.</p>}</Section></div>
          <RequirementQualityPanel quality={bundle.quality} />
          {unresolvedIssues.length > 0 && <Section title="Traceability gaps"><ul className="space-y-2 text-xs text-amber-800">{unresolvedIssues.map((issue, index) => <li key={`${issue.from_id}-${index}`}>{issue.severity}: {issue.from_id} / {issue.field} — {issue.detail} {issue.missing_ids.join(", ")}</li>)}</ul></Section>}
          <Section title="Immutable revision history" description="Edits create a new revision; approval and evidence judgments belong to an exact revision."><ol className="divide-y divide-slate-100 rounded-md border border-slate-200 bg-white">{bundle.revisions.slice().reverse().map((revision) => <li key={revision.revision} className="p-3"><details><summary className="cursor-pointer text-xs font-medium">r{revision.revision} · {revision.title}<span className="mt-1 block text-2xs font-normal text-slate-500">{formatDateTime(revision.created_at)} · {revision.created_by}{revision.supersedes_revision ? ` · supersedes r${revision.supersedes_revision}` : " · original import"}</span></summary><p className="mt-2 text-xs leading-relaxed">{revision.customer_outcome}</p><pre className="mt-3 max-h-80 overflow-auto rounded bg-slate-50 p-2 text-2xs">{JSON.stringify(revision, null, 2)}</pre></details></li>)}</ol></Section>
          <Section title="Backend audit history" actions={<Link href="/audit" className="text-xs text-brand hover:underline">Full hash-verified audit</Link>}>
            {events.length ? <ol className="divide-y divide-slate-100 rounded-md border border-slate-200 bg-white">{events.map((event) => <li key={event.event_id} className="p-3"><details><summary className="cursor-pointer text-xs"><span className="font-medium">{humanize(event.action)}</span><span className="ml-2 text-slate-500">{formatDateTime(event.recorded_at)} · {event.actor_id} · r{event.object_revision ?? "—"} · {event.result}</span></summary><p className="mt-2 text-xs leading-relaxed">{event.reason}</p><dl className="mt-2 space-y-1 break-all font-mono text-2xs text-slate-500"><div>Object: {event.object_id}</div><div>Request: {event.request_id}</div><div>Old hash: {event.before_hash ?? "—"}</div><div>New hash: {event.after_hash ?? "—"}</div><div>Event hash: {event.event_hash}</div></dl></details></li>)}</ol> : <EmptyState title="No backend audit events have been loaded for this requirement." detail="A local browser action is not presented as an authoritative audit event." />}
          </Section>
        </div>
        <aside className="space-y-4 xl:sticky xl:top-20 xl:self-start" aria-label="Authoritative PM review">
          <div className="rounded-md border border-slate-200 bg-white p-4"><RecordingTarget displayId={displayId} /><div className="mt-4"><CanonicalReviewControls bundle={bundle} revision={rev} /></div></div>
          <div className="rounded-md border border-slate-200 bg-white p-4 text-xs"><h2 className="font-semibold text-zinc-900">Review state</h2><dl className="mt-3 space-y-2"><KeyValue label="Requirement"><span className="break-all font-mono text-2xs">{rev.requirement_id}</span></KeyValue><KeyValue label="Revision"><span>r{rev.revision}</span></KeyValue><KeyValue label="Lifecycle"><span>{humanize(rev.lifecycle_status)}</span></KeyValue><KeyValue label="Evidence judgment"><span>{assessed} of {refs.length} links reviewed</span></KeyValue><KeyValue label="Content validation"><span>{bundle.quality ? bundle.quality.passed ? "No blocking content checks" : "Blocking checks remain" : "Unavailable"}</span></KeyValue><KeyValue label="Score policy"><span>{bundle.crps ? `${bundle.crps.result.policy_id} r${bundle.crps.result.policy_revision}` : "Unavailable"}</span></KeyValue></dl></div>
        </aside>
      </div>
    </div>
  );
}
