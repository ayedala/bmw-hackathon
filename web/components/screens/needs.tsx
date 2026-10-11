"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";

import { DataTable, type Column } from "@/components/app/data-table";
import { EmptyState, PageHeader, Section } from "@/components/app/layout-parts";
import { ArtifactEvidenceList, FindingLinks, ReasoningSourceNotice } from "@/components/app/reasoning-chain";
import { Button } from "@/components/ui/button";
import { SidePanel } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { humanize } from "@/lib/domain/derive";
import type { ResolvedNeed } from "@/lib/domain/reasoning";
import { useStore } from "@/lib/store";

export function NeedsScreen() {
  const { dataset } = useStore();
  const { reasoning } = dataset;
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const [query, setQuery] = useState("");
  const selected = reasoning.needs.find((row) => row.artifact.need_id === params.get("id"));
  const select = (id?: string) => router.replace(id ? `${pathname}?id=${encodeURIComponent(id)}` : pathname, { scroll: false });
  const rows = reasoning.needs.filter(({ artifact }) => `${artifact.need_id} ${artifact.statement} ${artifact.rationale}`.toLowerCase().includes(query.toLowerCase()));
  const columns: Column<ResolvedNeed>[] = [
    { key: "need", header: "Customer need", cell: ({ artifact }) => <div className="max-w-2xl"><p className="font-medium">{artifact.statement}</p><p className="mt-1 font-mono text-2xs text-slate-500">{artifact.need_id}</p></div>, sortValue: (row) => row.artifact.statement },
    { key: "topic", header: "Topic", cell: (row) => humanize(row.artifact.topic), sortValue: (row) => row.artifact.topic },
    { key: "market", header: "Target market", cell: (row) => row.artifact.target_market },
    { key: "importance", header: "Importance", cell: (row) => humanize(row.artifact.importance) },
    { key: "findings", header: "Findings", cell: (row) => row.findings.length, sortValue: (row) => row.findings.length, align: "right" },
    { key: "requirements", header: "Requirements", cell: (row) => reasoning.requirements.filter((req) => req.artifact.need_ids.includes(row.artifact.need_id)).length, align: "right" },
  ];
  const requirements = selected ? reasoning.requirements.filter((req) => req.artifact.need_ids.includes(selected.artifact.need_id)) : [];
  return (
    <div>
      <PageHeader title="Customer needs" question="Which customer outcomes connect the findings to the Germany 2030 requirements?" actions={<Button asChild><Link href="/requirements">Requirements</Link></Button>} />
      <ReasoningSourceNotice />
      {!reasoning.authoritative ? <EmptyState title="No canonical customer needs loaded." detail="Demo requirements are not substituted into the real reasoning chain." /> : <>
        <div className="mb-3 flex items-center gap-3" role="search"><Input aria-label="Search customer needs" placeholder="Search customer needs" value={query} onChange={(event) => setQuery(event.target.value)} className="max-w-sm" /><span className="text-xs text-slate-500">{rows.length} of {reasoning.needs.length} needs</span></div>
        <DataTable caption="Canonical customer needs" rows={rows} columns={columns} getRowId={(row) => row.artifact.need_id} onRowClick={(row) => select(row.artifact.need_id)} selectedId={selected?.artifact.need_id} empty={<EmptyState title="No customer need matches." />} />
      </>}
      {params.get("id") && !selected && <EmptyState title="Customer need reference not found." detail="The ID does not exist in the loaded canonical graph." />}
      <SidePanel open={Boolean(selected)} onOpenChange={(open) => !open && select()} title={selected?.artifact.statement ?? "Customer need"} eyebrow="Customer need" width="w-[min(800px,100vw)]">
        {selected && <div className="space-y-5">
          <p className="font-mono text-xs text-slate-500">{selected.artifact.need_id}</p>
          <p className="text-sm leading-relaxed">{selected.artifact.rationale}</p>
          <p className="text-xs text-slate-600">Target: {selected.artifact.target_market} · {selected.artifact.customer_context} · Importance: {selected.artifact.importance} · Synthesis confidence: {selected.artifact.confidence}</p>
          <Section title="Derived from findings"><FindingLinks findings={selected.findings} /></Section>
          <Section title="Supporting evidence reached through findings"><ArtifactEvidenceList rows={selected.findings.flatMap((finding) => finding.supporting)} empty="No evidence is reachable through the findings." tone="support" /></Section>
          <Section title="Opposing evidence reached through findings"><ArtifactEvidenceList rows={selected.findings.flatMap((finding) => finding.contradicting)} empty="No explicit contradiction link; further opposing-evidence retrieval remains necessary." tone="contradict" /></Section>
          <Section title="Derived requirements"><ul className="space-y-3">{requirements.map(({ artifact }) => <li key={artifact.requirement_id}><Link href={`/requirements/${encodeURIComponent(artifact.requirement_id)}`} className="text-[13px] font-medium text-brand hover:underline">{artifact.title}<span className="block font-mono text-2xs text-slate-500">{artifact.requirement_id}</span></Link><p className="mt-1 text-xs text-slate-600">{artifact.customer_value}</p></li>)}</ul>{!requirements.length && <EmptyState title="No derived requirement yet." />}</Section>
          {selected.unresolved_finding_ids.length > 0 && <EmptyState title="Unresolved finding references" detail={selected.unresolved_finding_ids.join(", ")} />}
        </div>}
      </SidePanel>
    </div>
  );
}
