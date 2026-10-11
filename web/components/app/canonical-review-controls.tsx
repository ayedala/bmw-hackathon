"use client";

import { useState } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Input, Label, Textarea } from "@/components/ui/input";
import { RecordingTarget, ReviewErrorNotice } from "./review-authority";
import { CrpsInterval } from "./canonical-crps";
import type { RequirementRevision } from "@/lib/domain/contracts";
import type { RequirementBundle } from "@/lib/domain/model";
import type { CanonicalChallenge } from "@/lib/review/contracts";
import { useStore } from "@/lib/store";

/** A proposed score has no authority until a PM accepts its immutable reassessment. */
export function ChallengeResult({ challenge }: { challenge: CanonicalChallenge }) {
  const { resolveChallenge, actorId } = useStore();
  const [rationale, setRationale] = useState("");
  const [busy, setBusy] = useState(false);
  async function resolve(accept: boolean) {
    setBusy(true);
    try { if (await resolveChallenge(challenge, accept, rationale)) setRationale(""); }
    finally { setBusy(false); }
  }
  return <article className="space-y-3 rounded-md border border-slate-200 bg-white p-4 text-xs">
    <h3 className="font-medium text-zinc-900">{challenge.hypothesis}</h3>
    <p className="text-2xs text-slate-500">{challenge.challenge_id} · r{challenge.requirement_revision} · {challenge.actor_id} · {challenge.created_at}</p>
    <div className="grid grid-cols-2 gap-4 rounded bg-slate-50 p-3">
      <div>Before: <CrpsInterval score={challenge.before} /><p>Decision Confidence {challenge.before.confidence.value_0_to_100}/100</p></div>
      <div>Proposed: <CrpsInterval score={challenge.after} /><p>Decision Confidence {challenge.after.confidence.value_0_to_100}/100</p></div>
    </div>
    <ul className="list-disc space-y-1 pl-4">{challenge.explanation.map((reason, i) => <li key={i}>{reason}</li>)}</ul>
    <p className="text-2xs text-slate-500">Affected factors: {challenge.factor_changes.map((c) => c.factor.replaceAll("_", " ")).join(", ") || "None; deterministic inputs unchanged"}. Other factors are carried forward without alteration.</p>
    {challenge.factor_changes.map((change) => <details key={change.factor}><summary className="cursor-pointer">{change.factor.replaceAll("_", " ")}: input change and exact IDs</summary><p>{change.reason}</p><pre className="max-h-48 overflow-auto whitespace-pre-wrap text-2xs">{JSON.stringify({ before: change.before, after: change.after, evidence_ids: change.evidence_ids }, null, 2)}</pre></details>)}
    <p className="text-2xs text-slate-500">{challenge.retrieval.method}</p>
    <details><summary className="cursor-pointer">Corpus coverage</summary><pre className="text-2xs">{JSON.stringify(challenge.retrieval.searched_counts, null, 2)}</pre></details>
    {(["supporting", "opposing", "context"] as const).map((role) => <details key={role}><summary className="cursor-pointer font-medium capitalize">{role} ({challenge.retrieval[role].length})</summary>
      <ul className="mt-2 space-y-2">{challenge.retrieval[role].map((item) => <li key={`${item.kind}:${item.item_id}`} className="rounded border border-slate-100 p-2">
        <Link className="font-mono text-brand underline" href={item.kind === "findings" ? `/findings?id=${encodeURIComponent(item.item_id)}` : item.kind === "needs" ? `/needs?id=${encodeURIComponent(item.item_id)}` : item.kind === "requirements" ? `/requirements/${encodeURIComponent(item.item_id)}` : `/evidence?id=${encodeURIComponent(item.item_id)}`}>{item.item_id}</Link> · {item.kind} · {item.applicability}
        <p>{String(item.payload.claim ?? item.payload.statement ?? item.payload.title ?? "")}</p>
        <p className="text-2xs text-slate-500">{item.relevance_basis}</p>
        <details><summary className="cursor-pointer text-2xs">Exact retrieved payload / provenance</summary><pre className="max-h-64 overflow-auto whitespace-pre-wrap text-2xs">{JSON.stringify(item.payload, null, 2)}</pre></details>
      </li>)}</ul></details>)}
    <div className="rounded bg-amber-50 p-3"><p className="font-medium">Unresolved evidence gaps</p><ul className="mt-1 list-disc pl-4">{challenge.gaps.map((gap, i) => <li key={i}>{gap}</li>)}</ul></div>
    <details><summary className="cursor-pointer">All exact evidence IDs used ({challenge.evidence_ids.length})</summary><p className="break-all font-mono text-2xs">{challenge.evidence_ids.join(", ")}</p><p>Excluded: {challenge.retrieval.excluded_evidence_ids.join(", ") || "none"}</p></details>
    {challenge.resolution ? <p className="rounded bg-slate-50 p-3">{challenge.resolution.accepted ? "Accepted" : "Rejected"} by {challenge.resolution.actor_id} · {challenge.resolution.recorded_at}. {challenge.resolution.rationale}</p> : <div className="space-y-2">
      <Label htmlFor={`resolution-${challenge.challenge_id}`}>Reassessment rationale</Label>
      <Textarea id={`resolution-${challenge.challenge_id}`} value={rationale} onChange={(e) => setRationale(e.target.value)} />
      <div className="flex gap-2"><Button disabled={busy || !actorId.trim() || rationale.trim().length < 5} onClick={() => resolve(true)}>Accept reassessment</Button><Button disabled={busy || !actorId.trim() || rationale.trim().length < 5} onClick={() => resolve(false)}>Reject reassessment</Button></div>
      <p className="text-2xs text-slate-500">Accept records the deterministic score snapshot, not requirement approval. A changed revision, evidence judgment or baseline score is rejected as stale.</p>
    </div>}
  </article>;
}

export function CanonicalReviewControls({ bundle, revision }: { bundle: RequirementBundle; revision: RequirementRevision }) {
  const store = useStore();
  const [rationale, setRationale] = useState("");
  const [hypothesis, setHypothesis] = useState("");
  const [acknowledged, setAcknowledged] = useState(false);
  const [title, setTitle] = useState(revision.title);
  const [outcome, setOutcome] = useState(revision.customer_outcome);
  const [busy, setBusy] = useState(false);
  const backed = store.isBackendBacked(bundle.display_id) && store.backend.reachable;
  const valid = !busy && store.actorId.trim().length > 0 && rationale.trim().length >= 5;
  async function run(action: () => Promise<boolean>) {
    setBusy(true);
    try { if (await action()) setRationale(""); } finally { setBusy(false); }
  }
  const challenges = store.canonicalChallenges.filter((c) => c.requirement_id === revision.requirement_id);
  return <section className="space-y-3 rounded-md border border-slate-200 bg-white p-4">
    <h2 className="text-sm font-semibold">PM review · r{revision.revision} · {revision.scope.countries.join(", ")} · {revision.planning_horizon ?? "2030"}</h2>
    <RecordingTarget displayId={bundle.display_id} /><ReviewErrorNotice />
    <Label htmlFor="canonical-reviewer">Reviewer ID</Label><Input id="canonical-reviewer" value={store.actorId} onChange={(e) => store.setActorId(e.target.value)} />
    <Label htmlFor="canonical-rationale">Rationale (required for every action)</Label><Textarea id="canonical-rationale" value={rationale} onChange={(e) => setRationale(e.target.value)} />
    {!backed ? <div className="space-y-2"><Button disabled={!valid} onClick={() => run(() => store.importCanonicalRequirements(rationale))}>Import canonical corpus for audited review</Button><p className="text-xs text-slate-500">Idempotently imports the real corpus and 14 requirements with provenance. Existing PM revisions are preserved. Preview alone is not a persisted decision.</p></div> : <>
      <label className="flex gap-2 text-xs"><input type="checkbox" checked={acknowledged} onChange={(e) => setAcknowledged(e.target.checked)} />I acknowledge unknown factors, unreviewed links, unapproved policy and separate engineering feasibility.</label>
      <div className="flex flex-wrap gap-2"><Button variant="primary" disabled={!valid || !acknowledged} onClick={() => run(() => store.recordDecision(bundle.display_id, "approve", rationale))}>Approve</Button><Button disabled={!valid} onClick={() => run(() => store.recordDecision(bundle.display_id, "defer", rationale))}>Defer</Button><Button variant="destructive" disabled={!valid} onClick={() => run(() => store.recordDecision(bundle.display_id, "reject", rationale))}>Reject</Button></div>
      <details className="space-y-2"><summary className="cursor-pointer text-xs font-medium">Edit outcome (creates an immutable new revision)</summary><Label htmlFor="canonical-title">Title</Label><Input id="canonical-title" value={title} onChange={(e) => setTitle(e.target.value)} /><Label htmlFor="canonical-outcome">Customer outcome</Label><Textarea id="canonical-outcome" value={outcome} onChange={(e) => setOutcome(e.target.value)} /><Button disabled={!valid || !title.trim() || !outcome.trim() || (title === revision.title && outcome === revision.customer_outcome)} onClick={() => run(() => store.editRequirement(bundle.display_id, { title, customer_outcome: outcome, acceptance_proposal: revision.acceptance_proposal }, rationale))}>Save new revision</Button></details>
      <div className="space-y-2 border-t border-slate-200 pt-3"><Label htmlFor="canonical-hypothesis">Challenge hypothesis / reassessment question</Label><Textarea id="canonical-hypothesis" placeholder="What would change this conclusion?" value={hypothesis} onChange={(e) => setHypothesis(e.target.value)} /><Button disabled={!valid || hypothesis.trim().length < 5} onClick={() => run(() => store.createChallenge(bundle.display_id, hypothesis, rationale))}>Challenge / retrieve and reassess</Button><p className="text-2xs text-slate-500">Searches the existing corpus only. No live scrape or LLM score changes. The resulting proposal needs a separate PM acceptance.</p></div>
    </>}
    <div className="space-y-3">{challenges.map((c) => <ChallengeResult key={c.challenge_id} challenge={c} />)}</div>
  </section>;
}
