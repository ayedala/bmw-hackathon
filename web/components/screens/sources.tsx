"use client";

import { useRouter } from "next/navigation";
import { useMemo } from "react";

import { MarketTag, ProvenanceBadge, QualityValue, SourceFamilyBadge } from "@/components/app/badges";
import { DataTable, type Column } from "@/components/app/data-table";
import { EmptyState, PageHeader, Section } from "@/components/app/layout-parts";
import { SOURCE_FAMILIES, type ResearchRun } from "@/lib/domain/contracts";
import { FAMILY_LABEL, formatDateTime } from "@/lib/domain/derive";
import type { Provenance, UiSourceFamily } from "@/lib/domain/model";
import { useStore } from "@/lib/store";
import { cn } from "@/lib/utils";

interface SourceRow {
  id: string;
  name: string;
  family: UiSourceFamily;
  markets: string[];
  records: number;
  duplicates: number;
  quality: number | null;
  last: string;
  provenance: Provenance;
  groups: number;
}

export function SourcesScreen() {
  const router = useRouter();
  const { dataset } = useStore();

  const rows = useMemo<SourceRow[]>(() => {
    const map = new Map<string, SourceRow & { qualities: number[]; groupSet: Set<string> }>();
    for (const e of dataset.evidence) {
      const key = e.source_name;
      const row =
        map.get(key) ??
        ({ id: key, name: key, family: e.source_family, markets: [], records: 0, duplicates: 0, quality: null, last: e.retrieved_at, provenance: e.provenance, groups: 0, qualities: [], groupSet: new Set() } as SourceRow & {
          qualities: number[];
          groupSet: Set<string>;
        });
      row.records += 1;
      if (e.duplicate_of) row.duplicates += 1;
      if (!row.markets.includes(e.market)) row.markets.push(e.market);
      if (e.quality !== null) row.qualities.push(e.quality);
      if (e.retrieved_at > row.last) row.last = e.retrieved_at;
      row.groupSet.add(e.independence_group);
      map.set(key, row);
    }
    return [...map.values()].map(({ qualities, groupSet, ...r }) => ({
      ...r,
      quality: qualities.length ? Math.round(qualities.reduce((a, b) => a + b, 0) / qualities.length) : null,
      groups: groupSet.size,
    }));
  }, [dataset.evidence]);

  const familyCounts = useMemo(() => {
    const all: UiSourceFamily[] = [...SOURCE_FAMILIES, "supplied_feedback"];
    return all.map((f) => ({ family: f, records: dataset.evidence.filter((e) => e.source_family === f && !e.duplicate_of).length }));
  }, [dataset.evidence]);

  const columns: Column<SourceRow>[] = [
    {
      key: "name",
      header: "Source",
      cell: (r) => (
        <div className="flex items-center gap-2">
          <span className="text-[13px] font-medium text-zinc-900">{r.name}</span>
          <ProvenanceBadge provenance={r.provenance} />
        </div>
      ),
      sortValue: (r) => r.name,
      className: "min-w-[260px]",
    },
    { key: "family", header: "Family", cell: (r) => <SourceFamilyBadge family={r.family} />, sortValue: (r) => r.family, className: "w-36" },
    { key: "market", header: "Market", cell: (r) => <span className="flex gap-1.5">{r.markets.map((m) => <MarketTag key={m} market={m} />)}</span>, className: "w-28" },
    { key: "records", header: "Evidence records", cell: (r) => <span className="text-xs tabular-nums">{r.records}{r.duplicates > 0 && <span className="ml-1 text-amber-700">({r.duplicates} dup)</span>}</span>, sortValue: (r) => r.records, align: "right", className: "w-32" },
    { key: "groups", header: "Indep. groups", cell: (r) => <span className="text-xs tabular-nums">{r.groups}</span>, sortValue: (r) => r.groups, align: "right", className: "w-24" },
    { key: "quality", header: "Quality", cell: (r) => <QualityValue quality={r.quality} />, sortValue: (r) => r.quality ?? -1, className: "w-24" },
    { key: "last", header: "Last collected", cell: (r) => <span className="whitespace-nowrap text-xs tabular-nums text-slate-600">{formatDateTime(r.last)}</span>, sortValue: (r) => r.last, className: "w-32" },
  ];

  const runColumns: Column<ResearchRun>[] = [
    { key: "run", header: "Run", cell: (r) => <span className="font-mono text-2xs text-zinc-800">{r.run_id}</span>, className: "w-60" },
    { key: "mode", header: "Mode", cell: (r) => <span className="text-xs text-slate-600">{r.mode ?? "search"}</span>, className: "w-28" },
    { key: "topic", header: "Topic", cell: (r) => <span className="text-xs">{r.topic}</span>, className: "w-24" },
    { key: "started", header: "Started", cell: (r) => <span className="whitespace-nowrap text-xs tabular-nums text-slate-600">{formatDateTime(r.started_at)}</span>, sortValue: (r) => r.started_at, className: "w-32" },
    { key: "results", header: "Search hits", cell: (r) => <span className="text-xs tabular-nums">{r.search_results_found}</span>, align: "right", className: "w-24" },
    { key: "scraped", header: "Pages", cell: (r) => <span className="text-xs tabular-nums">{r.pages_scraped + (r.pages_loaded_from_cache ?? 0)}</span>, align: "right", className: "w-16" },
    { key: "evidence", header: "Evidence", cell: (r) => <span className={cn("text-xs tabular-nums", r.evidence_records_created > 0 ? "font-medium text-zinc-900" : "text-slate-400")}>{r.evidence_records_created}</span>, sortValue: (r) => r.evidence_records_created, align: "right", className: "w-20" },
    { key: "calls", header: "Firecrawl / LLM", cell: (r) => <span className="text-xs tabular-nums text-slate-600">{r.firecrawl_search_calls + r.firecrawl_scrape_calls} / {r.llm_calls}</span>, align: "right", className: "w-28" },
  ];

  return (
    <div className="space-y-6">
      <PageHeader title="Sources" question="Is the evidence base diverse and independent enough to trust?" />

      <Section title="Coverage by source family" description="Families with no records are gaps in the evidence base. Duplicates excluded.">
        <div className="grid grid-cols-3 gap-px overflow-hidden rounded-md border border-slate-200/60 bg-slate-200/60 md:grid-cols-6">
          {familyCounts.map(({ family, records }) => (
            <button
              key={family}
              type="button"
              onClick={() => router.push(`/evidence?family=${family}`)}
              className={cn("bg-white px-3 py-2 text-left", records === 0 && "bg-slate-50")}
              aria-label={`${FAMILY_LABEL[family]}: ${records} records`}
              disabled={records === 0}
            >
              <div className="truncate text-2xs uppercase tracking-wide text-slate-500">{FAMILY_LABEL[family]}</div>
              <div className={cn("mt-0.5 text-base font-semibold tabular-nums", records === 0 ? "text-slate-300" : "text-zinc-950")}>{records}</div>
            </button>
          ))}
        </div>
      </Section>

      <Section title="Sources" description="Click a source to see its evidence.">
        <DataTable
          caption="Evidence sources"
          rows={rows}
          columns={columns}
          getRowId={(r) => r.id}
          onRowClick={(r) => router.push(`/evidence?q=${encodeURIComponent(r.name)}`)}
          defaultSort={{ key: "quality", direction: "desc" }}
          empty={<EmptyState title="No sources are loaded." detail="Run the external research pipeline or check Settings → Data sources." />}
        />
      </Section>

      <Section title="Research pipeline runs" description="Read from external_research_pipeline/data/metadata/research_runs.jsonl.">
        <DataTable
          caption="Research pipeline runs"
          rows={[...dataset.research_runs].reverse()}
          columns={runColumns}
          getRowId={(r) => r.run_id}
          pageSize={10}
          empty={<EmptyState title="No research runs recorded." detail="research_runs.jsonl is missing or empty." />}
        />
      </Section>
    </div>
  );
}
