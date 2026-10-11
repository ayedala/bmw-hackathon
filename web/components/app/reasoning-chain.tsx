"use client";

import Link from "next/link";

import { EvidenceList } from "@/components/app/evidence-list";
import { EmptyState } from "@/components/app/layout-parts";
import type { ProcessedEvidence } from "@/lib/domain/contracts";
import type { ResolvedFinding, ResolvedNeed } from "@/lib/domain/reasoning";
import { useStore } from "@/lib/store";

/** A fallback is a different dataset, not an invisible supplement to real data. */
export function ReasoningSourceNotice() {
  const { dataset } = useStore();
  const graph = dataset.reasoning;
  return (
    <div role="status" className={`mb-4 rounded-md border px-3 py-2 text-xs ${graph.authoritative ? "border-slate-200 bg-white text-slate-600" : "border-amber-200 bg-amber-50 text-amber-900"}`}>
      {graph.authoritative
        ? `Canonical research corpus · ${graph.counts.evidence} evidence records → ${graph.counts.findings} findings → ${graph.counts.needs} customer needs → ${graph.counts.requirements} requirements. Germany · BMW 5 Series successor · 2030.`
        : dataset.mode === "demo" ? "Explicit demo fallback: canonical reasoning artifacts are unavailable. These illustrative records are not the real Germany 2030 requirement set." : "Canonical reasoning artifacts are unavailable or incomplete. No illustrative records have been substituted."}
      {graph.issues.length > 0 && <span className="mt-1 block text-amber-800">{graph.issues.length} traceability issue(s) require review; unresolved references are not repaired automatically.</span>}
    </div>
  );
}

export function FindingLinks({ findings }: { findings: ResolvedFinding[] }) {
  if (!findings.length) return <EmptyState title="No linked finding." detail="This is a traceability gap, not evidence that the need is validated." />;
  return (
    <ul className="divide-y divide-slate-100 rounded-md border border-slate-200 bg-white">
      {findings.map(({ artifact, independent_groups, source_families }) => (
        <li key={artifact.finding_id} className="px-3 py-3">
          <Link href={`/findings?id=${encodeURIComponent(artifact.finding_id)}`} className="text-[13px] font-medium text-zinc-900 hover:text-brand">
            <span className="mb-1 block font-mono text-2xs font-normal text-slate-500">{artifact.finding_id}</span>{artifact.title}
          </Link>
          <p className="mt-1 text-xs leading-relaxed text-slate-600">{artifact.summary}</p>
          <p className="mt-1 text-2xs text-slate-500">{independent_groups.length} independent groups · {source_families.length} source families · {artifact.markets_covered.join(", ") || "market unspecified"}</p>
        </li>
      ))}
    </ul>
  );
}

export function NeedLinks({ needs }: { needs: ResolvedNeed[] }) {
  if (!needs.length) return <EmptyState title="No linked customer need." detail="A requirement needs a traceable customer motivation." />;
  return (
    <ul className="divide-y divide-slate-100 rounded-md border border-slate-200 bg-white">
      {needs.map(({ artifact }) => (
        <li key={artifact.need_id} className="px-3 py-3">
          <Link href={`/needs?id=${encodeURIComponent(artifact.need_id)}`} className="text-[13px] font-medium text-zinc-900 hover:text-brand">
            <span className="mb-1 block font-mono text-2xs font-normal text-slate-500">{artifact.need_id}</span>{artifact.statement}
          </Link>
          <p className="mt-1 text-xs leading-relaxed text-slate-600">{artifact.rationale}</p>
          <p className="mt-1 text-2xs text-slate-500">{artifact.target_market} · {artifact.customer_context} · Importance: {artifact.importance}</p>
        </li>
      ))}
    </ul>
  );
}

/** Resolve only actual canonical IDs; unavailable records stay visibly missing. */
export function ArtifactEvidenceList({ rows, empty, tone = "neutral" }: { rows: ProcessedEvidence[]; empty: string; tone?: "support" | "contradict" | "neutral" }) {
  const { evidenceById } = useStore();
  const unique = [...new Map(rows.map((row) => [row.evidence_id, row])).values()];
  const entries = unique.flatMap((row) => {
    const evidence = evidenceById.get(row.evidence_id);
    return evidence ? [{ evidence, note: `${row.evidence_id} · ${row.market} evidence; Germany applicability requires review` }] : [];
  });
  const unresolved = unique.filter((row) => !evidenceById.has(row.evidence_id));
  return (
    <>
      <EvidenceList entries={entries} initial={5} empty={empty} tone={tone} />
      {unresolved.length > 0 && <p className="mt-2 text-xs text-amber-800">Unavailable evidence IDs: {unresolved.map((row) => row.evidence_id).join(", ")}</p>}
    </>
  );
}
