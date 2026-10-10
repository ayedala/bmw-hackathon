"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useMemo } from "react";

import { BalanceBar, ConfidenceBadge, HypothesisStatusBadge, MarketTag } from "@/components/app/badges";
import { DataTable, type Column } from "@/components/app/data-table";
import { EvidenceList } from "@/components/app/evidence-list";
import { EmptyState, FilterBar, PageHeader, SubHeading, type ActiveFilter } from "@/components/app/layout-parts";
import { Button } from "@/components/ui/button";
import { SidePanel } from "@/components/ui/dialog";
import { Select } from "@/components/ui/select";
import { Tooltip } from "@/components/ui/tooltip";
import { EVIDENCE_STRENGTH_RULE, HYPOTHESIS_STATUS_LABEL, TOPIC_LABEL } from "@/lib/domain/derive";
import type { HypothesisStatus } from "@/lib/domain/model";
import { usePersistentState, useStore } from "@/lib/store";
import { useHypothesisRows, type HypothesisRow } from "@/lib/view";

interface Filters {
  topic: string;
  status: string;
}
const DEFAULTS: Filters = { topic: "all", status: "all" };

function HypothesisDetail({ row }: { row: HypothesisRow }) {
  const { dataset } = useStore();
  const entries = (stance: string) =>
    row.links.filter((l) => l.stance === stance && l.evidence).map((l) => ({ evidence: l.evidence!, note: l.note }));
  const findings = dataset.findings.filter((f) => f.hypothesis_ids.includes(row.id));
  const missing = row.links.filter((l) => !l.evidence).length;
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-3">
        <HypothesisStatusBadge status={row.status} />
        <ConfidenceBadge confidence={row.confidence} />
        <Tooltip content={EVIDENCE_STRENGTH_RULE}>
          <span tabIndex={0} className="text-xs text-slate-600">
            Strength <span className="font-medium tabular-nums text-zinc-900">{row.strength}</span>
          </span>
        </Tooltip>
        <BalanceBar balance={row.balance} />
      </div>
      {missing > 0 && <p className="text-2xs text-amber-700">{missing} linked record(s) are not loaded; counts exclude them.</p>}
      <div>
        <SubHeading count={entries("supports").length}>Supporting</SubHeading>
        <EvidenceList entries={entries("supports")} initial={5} empty="No supporting evidence." />
      </div>
      <div>
        <SubHeading count={entries("contradicts").length}>Contradicting</SubHeading>
        <EvidenceList entries={entries("contradicts")} initial={5} tone="contradict" empty="No contradicting evidence linked — an evidence gap, not consensus." />
      </div>
      {entries("neutral").length > 0 && (
        <div>
          <SubHeading count={entries("neutral").length}>Neutral / context</SubHeading>
          <EvidenceList entries={entries("neutral")} initial={3} empty="" />
        </div>
      )}
      <div>
        <SubHeading count={findings.length}>Feeds findings</SubHeading>
        <ul className="space-y-1 text-xs">
          {findings.map((f) => (
            <li key={f.id}>
              <Link href={`/findings?id=${f.id}`} className="text-zinc-900 hover:underline">
                <span className="mr-1.5 font-mono text-2xs text-slate-500">{f.id}</span>
                {f.title}
              </Link>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

export function HypothesesScreen() {
  const rows = useHypothesisRows();
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const selectedId = params.get("id");
  const selected = rows.find((r) => r.id === selectedId) ?? null;
  const [filters, setFilters] = usePersistentState<Filters>("hypotheses", DEFAULTS);
  const select = (id: string | null) => router.replace(id ? `${pathname}?id=${id}` : pathname, { scroll: false });

  const filtered = useMemo(
    () => rows.filter((r) => (filters.topic === "all" || r.hypothesis.topic === filters.topic) && (filters.status === "all" || r.status === filters.status)),
    [rows, filters],
  );
  const topics = [...new Set(rows.map((r) => r.hypothesis.topic))];
  const active: ActiveFilter[] = [];
  if (filters.topic !== "all") active.push({ key: "topic", label: TOPIC_LABEL[filters.topic] ?? filters.topic, onClear: () => setFilters((f) => ({ ...f, topic: "all" })) });
  if (filters.status !== "all") active.push({ key: "status", label: HYPOTHESIS_STATUS_LABEL[filters.status as HypothesisStatus], onClear: () => setFilters((f) => ({ ...f, status: "all" })) });

  const columns: Column<HypothesisRow>[] = [
    {
      key: "statement",
      header: "Hypothesis",
      cell: (r) => (
        <div className="min-w-0">
          <div className="font-mono text-2xs text-slate-500">{r.id}</div>
          <div className="line-clamp-2 text-[13px] text-zinc-900">{r.hypothesis.statement}</div>
        </div>
      ),
      sortValue: (r) => r.id,
      className: "min-w-[340px] max-w-[560px]",
    },
    { key: "status", header: "Status", cell: (r) => <HypothesisStatusBadge status={r.status} />, sortValue: (r) => r.status, className: "w-32" },
    { key: "strength", header: "Strength", cell: (r) => <span className="text-xs tabular-nums text-zinc-900">{r.strength}</span>, sortValue: (r) => r.strength, align: "right", className: "w-20" },
    { key: "support", header: "Support", cell: (r) => <span className="text-xs tabular-nums">{r.balance.supporting}</span>, sortValue: (r) => r.balance.supporting, align: "right", className: "w-16" },
    {
      key: "contra",
      header: "Contradict",
      cell: (r) => <span className={r.balance.contradicting ? "text-xs tabular-nums text-amber-700" : "text-xs tabular-nums text-slate-400"}>{r.balance.contradicting}</span>,
      sortValue: (r) => r.balance.contradicting,
      align: "right",
      className: "w-20",
    },
    { key: "sources", header: "Indep. sources", cell: (r) => <span className="text-xs tabular-nums">{r.balance.independent_sources}</span>, sortValue: (r) => r.balance.independent_sources, align: "right", className: "w-24" },
    { key: "balance", header: "Balance", cell: (r) => <BalanceBar balance={r.balance} showCounts={false} />, className: "w-24" },
    { key: "market", header: "Mkt", cell: (r) => <MarketTag market={r.hypothesis.market} />, className: "w-12" },
  ];

  return (
    <div>
      <PageHeader title="Hypotheses" question="Which premises behind our findings hold up against the evidence?" />
      <FilterBar active={active} onClearAll={() => setFilters(DEFAULTS)} resultLabel={`${filtered.length} of ${rows.length} hypotheses`}>
        <Select label="Topic" value={filters.topic} onValueChange={(v) => setFilters((f) => ({ ...f, topic: v }))} options={[{ value: "all", label: "All" }, ...topics.map((t) => ({ value: t, label: TOPIC_LABEL[t] ?? t }))]} />
        <Select
          label="Status"
          value={filters.status}
          onValueChange={(v) => setFilters((f) => ({ ...f, status: v }))}
          options={[{ value: "all", label: "All" }, ...Object.entries(HYPOTHESIS_STATUS_LABEL).map(([value, label]) => ({ value, label }))]}
        />
      </FilterBar>
      <DataTable
        caption="Hypotheses"
        rows={filtered}
        columns={columns}
        getRowId={(r) => r.id}
        selectedId={selectedId}
        onRowClick={(r) => select(r.id)}
        defaultSort={{ key: "strength", direction: "desc" }}
        empty={<EmptyState title="No hypothesis matches these filters." action={<Button size="sm" onClick={() => setFilters(DEFAULTS)}>Clear filters</Button>} />}
      />
      <SidePanel open={Boolean(selected)} onOpenChange={(o) => !o && select(null)} title={selected?.hypothesis.statement ?? ""} eyebrow={selected?.id} width="w-[min(600px,100vw)]">
        {selected && <HypothesisDetail row={selected} />}
      </SidePanel>
    </div>
  );
}
