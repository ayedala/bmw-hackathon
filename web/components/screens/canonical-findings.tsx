"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";

import { DataTable, type Column } from "@/components/app/data-table";
import { EmptyState, PageHeader, Section } from "@/components/app/layout-parts";
import { ArtifactEvidenceList, FindingLinks, NeedLinks, ReasoningSourceNotice } from "@/components/app/reasoning-chain";
import { Button } from "@/components/ui/button";
import { SidePanel } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { humanize } from "@/lib/domain/derive";
import type { ResolvedFinding } from "@/lib/domain/reasoning";
import { useStore } from "@/lib/store";

export function CanonicalFindingsScreen() {
  const { dataset } = useStore();
  const { reasoning } = dataset;
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const [query, setQuery] = useState("");
  const [topic, setTopic] = useState("all");
  const selected = reasoning.findings.find((row) => row.artifact.finding_id === params.get("id"));
  const select = (id?: string) => router.replace(id ? `${pathname}?id=${encodeURIComponent(id)}` : pathname, { scroll: false });
  const rows = reasoning.findings.filter(({ artifact }) =>
    (topic === "all" || artifact.topic === topic) && `${artifact.finding_id} ${artifact.title} ${artifact.summary}`.toLowerCase().includes(query.toLowerCase()),
  );
  const columns: Column<ResolvedFinding>[] = [
    { key: "title", header: "Finding", cell: ({ artifact: f }) => <div className="max-w-xl"><div className="font-medium text-zinc-900">{f.title}</div><div className="mt-1 font-mono text-2xs text-slate-500">{f.finding_id}</div></div>, sortValue: (r) => r.artifact.title },
    { key: "topic", header: "Topic", cell: (r) => humanize(r.artifact.topic), sortValue: (r) => r.artifact.topic },
    { key: "kind", header: "Finding kind", cell: (r) => humanize(r.artifact.finding_kind), sortValue: (r) => r.artifact.finding_kind },
    { key: "markets", header: "Evidence markets", cell: (r) => r.artifact.markets_covered.join(", ") },
    { key: "groups", header: "Independent", cell: (r) => r.independent_groups.length, sortValue: (r) => r.independent_groups.length, align: "right" },
    { key: "contra", header: "Opposing findings", cell: (r) => r.contradicts.length, sortValue: (r) => r.contradicts.length, align: "right" },
    { key: "confidence", header: "Synthesis confidence", cell: (r) => humanize(r.artifact.confidence) },
  ];
  const relatedNeeds = selected ? reasoning.needs.filter((need) => need.artifact.finding_ids.includes(selected.artifact.finding_id)) : [];
  const relatedRequirements = selected ? reasoning.requirements.filter((req) => req.findings.some((f) => f.artifact.finding_id === selected.artifact.finding_id)) : [];
  return (
    <div>
      <PageHeader title="Findings" question="What does the real evidence show, and what disagrees?" actions={<Button asChild><Link href="/needs">Customer needs</Link></Button>} />
      <ReasoningSourceNotice />
      <div className="mb-3 flex flex-wrap gap-2" role="search">
        <Input aria-label="Search canonical findings" placeholder="Search findings" value={query} onChange={(event) => setQuery(event.target.value)} className="max-w-sm" />
        <Select label="Topic" value={topic} onValueChange={setTopic} options={[{ value: "all", label: "All" }, ...[...new Set(reasoning.findings.map((row) => row.artifact.topic))].map((value) => ({ value, label: humanize(value) }))]} />
        <span className="self-center text-xs text-slate-500">{rows.length} of {reasoning.findings.length} findings</span>
      </div>
      <DataTable caption="Canonical findings" rows={rows} columns={columns} getRowId={(row) => row.artifact.finding_id} onRowClick={(row) => select(row.artifact.finding_id)} selectedId={selected?.artifact.finding_id} empty={<EmptyState title="No canonical finding matches." />} />
      {params.get("id") && !selected && <EmptyState title="Finding reference not found." detail="The requested ID is not in the canonical artifacts. No fixture has been substituted." />}
      <SidePanel open={Boolean(selected)} onOpenChange={(open) => !open && select()} title={selected?.artifact.title ?? "Finding"} eyebrow="Canonical finding" width="w-[min(800px,100vw)]">
        {selected && <div className="space-y-5">
          <p className="font-mono text-xs text-slate-500">{selected.artifact.finding_id}</p>
          <p className="text-sm leading-relaxed">{selected.artifact.summary}</p>
          <p className="text-xs text-slate-600">{selected.independent_groups.length} independent groups · {selected.source_families.length} source families · Markets: {selected.artifact.markets_covered.join(", ")} · Vehicles: {selected.artifact.vehicles_covered.join(", ")}</p>
          <Section title="Evidence for this finding" description="These records support the finding; that is distinct from supporting every derived requirement."><ArtifactEvidenceList rows={selected.supporting} empty="No resolved supporting evidence." tone="support" /></Section>
          <Section title="Opposing evidence" description="Evidence from explicitly contradicting findings remains visible."><ArtifactEvidenceList rows={selected.contradicting} empty="No explicit contradiction link. This is a search gap, not proof of consensus." tone="contradict" /></Section>
          {selected.contradicts.length > 0 && <Section title="Contradicting findings"><FindingLinks findings={reasoning.findings.filter((row) => selected.contradicts.includes(row.artifact.finding_id))} /></Section>}
          <Section title="Derived customer needs"><NeedLinks needs={relatedNeeds} /></Section>
          <Section title="Requirements reached through these needs"><ul className="space-y-2">{relatedRequirements.map(({ artifact }) => <li key={artifact.requirement_id}><Link href={`/requirements/${encodeURIComponent(artifact.requirement_id)}`} className="text-xs text-brand hover:underline">{artifact.title}<span className="block font-mono text-2xs text-slate-500">{artifact.requirement_id}</span></Link></li>)}</ul>{!relatedRequirements.length && <p className="text-xs text-slate-500">No requirement has been derived from this finding.</p>}</Section>
          <Section title="Synthesis notes"><p className="text-xs leading-relaxed text-slate-600">{selected.artifact.notes || "No additional synthesis notes."}</p></Section>
          {selected.unresolved_evidence_ids.length > 0 && <EmptyState title="Unresolved evidence references" detail={selected.unresolved_evidence_ids.join(", ")} />}
        </div>}
      </SidePanel>
    </div>
  );
}
