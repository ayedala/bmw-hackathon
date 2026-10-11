"use client";

import { Search } from "lucide-react";
import { useRouter } from "next/navigation";
import { useMemo } from "react";

import { ConfidenceBadge, DecisionBadge, MarketTag, PriorityBadge, ScoreValue } from "@/components/app/badges";
import { DataTable, type Column } from "@/components/app/data-table";
import { EmptyState, FilterBar, PageHeader, type ActiveFilter } from "@/components/app/layout-parts";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Tooltip } from "@/components/ui/tooltip";
import Link from "next/link";
import { CrpsInterval } from "@/components/app/canonical-crps";
import { ReasoningSourceNotice } from "@/components/app/reasoning-chain";
import { DECISION_STATUS_LABEL, formatDate, PRIORITIES, priorityRank, TOPIC_LABEL, type DecisionStatus } from "@/lib/domain/derive";
import { MARKET_LABEL } from "@/lib/domain/model";
import { usePersistentState, useStore } from "@/lib/store";
import { useRequirementRows, type RequirementRow } from "@/lib/view";

interface Filters {
  q: string;
  topic: string;
  priority: string;
  decision: string;
}
const DEFAULTS: Filters = { q: "", topic: "all", priority: "all", decision: "all" };

export function requirementColumns(market: string): Column<RequirementRow>[] {
  return [
    { key: "priority", header: "Priority", cell: (r) => <PriorityBadge priority={r.priority} hint={r.bundle.crps?.result.band_basis} />, sortValue: (r) => -priorityRank(r.priority), className: "w-16" },
    {
      key: "title",
      header: "Requirement",
      cell: (r) => (
        <div className="min-w-0">
          <div className="line-clamp-1 font-medium text-zinc-900">{r.revision.title}</div>
          <div className="flex gap-2 font-mono text-2xs text-slate-500">
            {r.id}
            <span>r{r.revision.revision}</span>
            <span className="truncate font-sans">{r.revision.customer_outcome}</span>
          </div>
        </div>
      ),
      sortValue: (r) => r.revision.title,
      className: "min-w-[320px] max-w-[520px]",
    },
    { key: "topic", header: "Topic", cell: (r) => <span className="text-xs text-slate-700">{TOPIC_LABEL[r.bundle.topic]}</span>, sortValue: (r) => r.bundle.topic, className: "w-24" },
    { key: "crps", header: "CRPS", cell: (r) => r.bundle.canonical ? r.in_scope && r.bundle.crps ? <CrpsInterval score={r.bundle.crps} /> : <span className="text-xs text-slate-500">Not assessed</span> : <ScoreValue score={r.score} basis={r.basis} />, sortValue: (r) => r.score ?? -1, align: "right", className: "w-32" },
    {
      key: "confidence",
      header: "Confidence",
      cell: (r) => r.bundle.canonical ? <span className="tabular-nums">{r.bundle.crps ? `${r.bundle.crps.confidence.value_0_to_100.toFixed(1)}/100` : "Unknown"}</span> : <ConfidenceBadge confidence={r.confidence} />,
      sortValue: (r) => r.bundle.canonical ? r.bundle.crps?.confidence.value_0_to_100 ?? -1 : ["Low", "Medium", "High"].indexOf(r.confidence),
      className: "w-24",
    },
    {
      key: "evidence",
      header: "Evidence",
      cell: (r) => (
        <Tooltip content={`${r.balance.supporting} supporting, ${r.balance.contradicting} contradicting, ${r.balance.independent_sources} independent sources linked through findings.`}>
          <span tabIndex={0} className="whitespace-nowrap text-xs tabular-nums text-zinc-800">
            {r.balance.supporting}
            <span className="text-slate-400"> / </span>
            <span className="text-amber-700">{r.balance.contradicting}</span>
            <span className="ml-1.5 text-slate-500">{r.balance.independent_sources} src</span>
          </span>
        </Tooltip>
      ),
      sortValue: (r) => r.balance.independent_sources,
      className: "w-28",
    },
    { key: "market", header: "Scope", cell: (r) => <div><MarketTag market={r.bundle.canonical ? r.revision.scope.countries.join(", ") : market} />{r.bundle.canonical && <span className="ml-1 text-2xs text-slate-500">2030</span>}</div>, className: "w-24" },
    { key: "feasibility", header: "Feasibility", cell: (r) => <span className="text-xs text-slate-600">{r.revision.feasibility.replaceAll("_", " ")}</span>, className: "w-24" },
    { key: "decision", header: "Decision", cell: (r) => <DecisionBadge status={r.status} />, sortValue: (r) => r.status, className: "w-28" },
    { key: "updated", header: "Updated", cell: (r) => <span className="whitespace-nowrap text-xs text-slate-500">{formatDate(r.updated_at)}</span>, sortValue: (r) => r.updated_at, className: "w-28" },
  ];
}

export function RequirementsScreen() {
  const router = useRouter();
  const { market } = useStore();
  const rows = useRequirementRows(market);
  const [filters, setFilters] = usePersistentState<Filters>("requirements", DEFAULTS);
  const set = <K extends keyof Filters>(k: K, v: Filters[K]) => setFilters((f) => ({ ...f, [k]: v }));

  const filtered = useMemo(() => {
    const q = filters.q.trim().toLowerCase();
    return rows.filter((r) => {
      if (filters.topic !== "all" && r.bundle.topic !== filters.topic) return false;
      if (filters.priority !== "all" && r.priority !== filters.priority) return false;
      if (filters.decision !== "all" && r.status !== filters.decision) return false;
      if (q && !`${r.id} ${r.revision.title} ${r.revision.customer_outcome}`.toLowerCase().includes(q)) return false;
      return true;
    });
  }, [rows, filters]);

  const topics = [...new Set(rows.map((r) => r.bundle.topic))];
  const active: ActiveFilter[] = [];
  if (filters.q) active.push({ key: "q", label: `“${filters.q}”`, onClear: () => set("q", "") });
  if (filters.topic !== "all") active.push({ key: "topic", label: TOPIC_LABEL[filters.topic] ?? filters.topic, onClear: () => set("topic", "all") });
  if (filters.priority !== "all") active.push({ key: "priority", label: filters.priority, onClear: () => set("priority", "all") });
  if (filters.decision !== "all")
    active.push({ key: "decision", label: DECISION_STATUS_LABEL[filters.decision as DecisionStatus], onClear: () => set("decision", "all") });

  return (
    <div>
      <PageHeader
        title="Requirements"
        question={`Which customer-facing requirements should shape the BMW 5 Series successor? Canonical seven-factor CRPS · ${MARKET_LABEL[market]} · 2030.`}
        actions={<Button asChild><Link href="/needs">Trace customer needs</Link></Button>}
      />
      <ReasoningSourceNotice />
      <FilterBar active={active} onClearAll={() => setFilters(DEFAULTS)} resultLabel={`${filtered.length} of ${rows.length} requirements`}>
        <div className="relative">
          <Search aria-hidden className="pointer-events-none absolute left-2 top-1/2 size-3.5 -translate-y-1/2 text-slate-400" />
          <Input value={filters.q} onChange={(e) => set("q", e.target.value)} placeholder="Search requirements" aria-label="Search requirements" className="h-7 w-56 pl-7 text-xs" />
        </div>
        <Select label="Topic" value={filters.topic} onValueChange={(v) => set("topic", v)} options={[{ value: "all", label: "All" }, ...topics.map((t) => ({ value: t, label: TOPIC_LABEL[t] ?? t }))]} />
        <Select label="Priority" value={filters.priority} onValueChange={(v) => set("priority", v)} options={[{ value: "all", label: "All" }, ...PRIORITIES.map((p) => ({ value: p, label: p }))]} />
        <Select
          label="Decision"
          value={filters.decision}
          onValueChange={(v) => set("decision", v)}
          options={[{ value: "all", label: "All" }, ...Object.entries(DECISION_STATUS_LABEL).map(([value, label]) => ({ value, label }))]}
        />
      </FilterBar>
      <DataTable
        caption="Requirements"
        rows={filtered}
        columns={requirementColumns(market)}
        getRowId={(r) => r.id}
        onRowClick={(r) => router.push(`/requirements/${r.id}`)}
        defaultSort={{ key: "crps", direction: "desc" }}
        empty={
          <EmptyState
            title="No requirement matches these filters."
            detail={`${active.map((a) => a.label).join(" + ")} in ${MARKET_LABEL[market]}.`}
            action={
              <Button size="sm" onClick={() => setFilters(DEFAULTS)}>
                Clear filters
              </Button>
            }
          />
        }
      />
    </div>
  );
}
