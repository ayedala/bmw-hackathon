"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";

import { ConfidenceBadge, DecisionBadge, PriorityBadge, ScoreValue } from "@/components/app/badges";
import { DataTable, type Column } from "@/components/app/data-table";
import { EmptyState, FilterBar, PageHeader, Section, type ActiveFilter } from "@/components/app/layout-parts";
import { FACTOR_KEYS, WeightControls } from "@/components/app/score";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip } from "@/components/ui/tooltip";
import { DECISION_STATUS_LABEL, FACTOR_LABEL, PRIORITIES, PRIORITY_RULE, priorityRank, TOPIC_LABEL, type DecisionStatus } from "@/lib/domain/derive";
import { MARKET_LABEL } from "@/lib/domain/model";
import { DEFAULT_PRIORITY_POLICY, priorityContributions, priorityScore } from "@/lib/domain/scoring";
import { usePersistentState, useStore } from "@/lib/store";
import { cn } from "@/lib/utils";
import { useRequirementRows, type RequirementRow } from "@/lib/view";

const ScoreDistributionChart = dynamic(() => import("@/components/app/charts").then((m) => m.ScoreDistributionChart), {
  ssr: false,
  loading: () => <Skeleton className="h-36 w-full" />,
});

interface Filters {
  topic: string;
  priority: string;
  decision: string;
}
const DEFAULTS: Filters = { topic: "all", priority: "all", decision: "all" };
const MAX_COMPARE = 4;
/** Two CRPS values closer than this are treated as a tie; ordinal ratings do not support finer distinctions. */
const TIE_MARGIN = 2.5;

function CompareTable({ rows }: { rows: RequirementRow[] }) {
  const { policy } = useStore();
  const pairs: { a: RequirementRow; b: RequirementRow; gap: number }[] = [];
  for (let i = 0; i < rows.length; i += 1)
    for (let j = i + 1; j < rows.length; j += 1) {
      const a = rows[i];
      const b = rows[j];
      if (a && b && a.score !== null && b.score !== null) pairs.push({ a, b, gap: Math.abs(a.score - b.score) });
    }

  const cell = "px-3 py-1.5 text-right tabular-nums";
  return (
    <div className="overflow-x-auto rounded-md border border-slate-200 bg-white">
      <table className="w-full text-[13px]">
        <caption className="sr-only">Side-by-side requirement comparison</caption>
        <thead>
          <tr className="border-b border-slate-200">
            <th scope="col" className="w-56 px-3 py-2 text-left text-2xs font-medium uppercase tracking-wide text-slate-500">
              Dimension
            </th>
            {rows.map((r) => (
              <th key={r.id} scope="col" className="min-w-[180px] px-3 py-2 text-right align-bottom">
                <Link href={`/requirements/${r.id}`} className="block hover:text-brand">
                  <span className="block font-mono text-2xs font-normal text-slate-500">{r.id}</span>
                  <span className="line-clamp-2 text-xs font-medium text-zinc-900">{r.revision.title}</span>
                </Link>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {FACTOR_KEYS.map((k) => (
            <tr key={k} className="border-b border-slate-100">
              <th scope="row" className="px-3 py-1.5 text-left text-xs font-normal text-zinc-800">
                {FACTOR_LABEL[k]} <span className="text-2xs text-slate-400">w {policy[k].toFixed(2)}</span>
                {k === "uncertainty" && <span className="ml-1 text-2xs text-amber-700">against</span>}
              </th>
              {rows.map((r) => (
                <td key={r.id} className={cn(cell, "text-zinc-900")}>
                  {r.factors[k]}
                  <span className="ml-2 text-2xs text-slate-400">{priorityContributions(r.factors, policy)[k].toFixed(1)} pts</span>
                </td>
              ))}
            </tr>
          ))}
          <tr className="border-b border-slate-100 bg-slate-50">
            <th scope="row" className="px-3 py-1.5 text-left text-xs font-semibold text-zinc-900">
              CRPS
            </th>
            {rows.map((r) => (
              <td key={r.id} className={cn(cell, "text-sm")}>
                <ScoreValue score={r.score} basis={r.basis} />
              </td>
            ))}
          </tr>
          <tr className="border-b border-slate-100">
            <th scope="row" className="px-3 py-1.5 text-left text-xs font-normal text-zinc-800">
              Default-weight CRPS
            </th>
            {rows.map((r) => (
              <td key={r.id} className={cn(cell, "text-xs text-slate-600")}>
                {priorityScore(r.factors, DEFAULT_PRIORITY_POLICY).toFixed(1)}
              </td>
            ))}
          </tr>
          <tr className="border-b border-slate-100">
            <th scope="row" className="px-3 py-1.5 text-left text-xs font-normal text-zinc-800">
              Extracted concerns / opposing / feedback IDs
            </th>
            {rows.map((r) => (
              <td key={r.id} className={cn(cell, "text-xs")}>
                {r.balance.supporting} / <span className="text-amber-700">{r.balance.contradicting}</span> / {r.balance.independent_sources}
              </td>
            ))}
          </tr>
          <tr className="border-b border-slate-100">
            <th scope="row" className="px-3 py-1.5 text-left text-xs font-normal text-zinc-800">
              Confidence
            </th>
            {rows.map((r) => (
              <td key={r.id} className={cell}>
                <ConfidenceBadge confidence={r.confidence} />
              </td>
            ))}
          </tr>
          <tr>
            <th scope="row" className="px-3 py-1.5 text-left text-xs font-normal text-zinc-800">
              PM decision
            </th>
            {rows.map((r) => (
              <td key={r.id} className={cell}>
                <DecisionBadge status={r.status} />
              </td>
            ))}
          </tr>
        </tbody>
      </table>
      {pairs.length > 0 && (
        <div className="border-t border-slate-200 px-3 py-2">
          <div className="text-2xs font-medium uppercase tracking-wide text-slate-500">Is the order meaningful?</div>
          <ul className="mt-1 space-y-0.5 text-xs">
            {pairs.map(({ a, b, gap }) => (
              <li key={`${a.id}-${b.id}`} className="text-zinc-800">
                <span className="font-mono text-2xs">{a.id}</span> vs <span className="font-mono text-2xs">{b.id}</span>:{" "}
                {gap < TIE_MARGIN ? (
                  <span className="text-amber-700">near tie ({gap.toFixed(1)} pts) — ordinal ratings cannot separate them; keep both and compare qualitatively.</span>
                ) : (
                  <span>{gap.toFixed(1)} points apart under the current weights.</span>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

export function PrioritizationScreen() {
  const router = useRouter();
  const { market } = useStore();
  const rows = useRequirementRows(market);
  const [filters, setFilters] = usePersistentState<Filters>("prioritization", DEFAULTS);
  const [selected, setSelected] = useState<string[]>([]);
  const set = <K extends keyof Filters>(k: K, v: Filters[K]) => setFilters((f) => ({ ...f, [k]: v }));

  const filtered = useMemo(
    () =>
      rows
        .filter(
          (r) =>
            (filters.topic === "all" || r.bundle.topic === filters.topic) &&
            (filters.priority === "all" || r.priority === filters.priority) &&
            (filters.decision === "all" || r.status === filters.decision),
        )
        .sort((a, b) => priorityRank(a.priority) - priorityRank(b.priority) || (b.score ?? 0) - (a.score ?? 0) || a.id.localeCompare(b.id)),
    [rows, filters],
  );

  const counts = PRIORITIES.map((p) => ({ p, n: rows.filter((r) => r.priority === p && r.status !== "rejected" && r.in_scope).length }));
  const distribution = useMemo(() => {
    const bands = ["<50", "50–60", "60–70", "70–80", "≥80"];
    const bucket = (v: number) => (v < 50 ? 0 : v < 60 ? 1 : v < 70 ? 2 : v < 80 ? 3 : 4);
    const out = bands.map((band) => ({ band, count: 0 }));
    for (const r of rows) if (r.score !== null) out[bucket(r.score)]!.count += 1;
    return out;
  }, [rows]);

  const toggle = (id: string) => setSelected((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : prev.length >= MAX_COMPARE ? prev : [...prev, id]));
  const compareRows = selected.map((id) => rows.find((r) => r.id === id)).filter((r): r is RequirementRow => Boolean(r));

  const topics = [...new Set(rows.map((r) => r.bundle.topic))];
  const active: ActiveFilter[] = [];
  if (filters.topic !== "all") active.push({ key: "topic", label: TOPIC_LABEL[filters.topic] ?? filters.topic, onClear: () => set("topic", "all") });
  if (filters.priority !== "all") active.push({ key: "priority", label: filters.priority, onClear: () => set("priority", "all") });
  if (filters.decision !== "all") active.push({ key: "decision", label: DECISION_STATUS_LABEL[filters.decision as DecisionStatus], onClear: () => set("decision", "all") });

  const columns: Column<RequirementRow>[] = [
    {
      key: "select",
      header: <span className="sr-only">Compare</span>,
      label: "Compare",
      cell: (r) => (
        <input
          type="checkbox"
          className="size-3.5 accent-brand"
          checked={selected.includes(r.id)}
          disabled={!selected.includes(r.id) && selected.length >= MAX_COMPARE}
          onClick={(e) => e.stopPropagation()}
          onChange={() => toggle(r.id)}
          aria-label={`Compare ${r.id}`}
        />
      ),
      className: "w-8",
    },
    { key: "priority", header: "Priority", cell: (r) => <PriorityBadge priority={r.priority} />, className: "w-16" },
    {
      key: "title",
      header: "Requirement",
      cell: (r) => (
        <div className="min-w-0">
          <div className="line-clamp-1 font-medium text-zinc-900">{r.revision.title}</div>
          <div className="font-mono text-2xs text-slate-500">{r.id}</div>
        </div>
      ),
      className: "min-w-[280px] max-w-[460px]",
    },
    { key: "crps", header: "CRPS", cell: (r) => <ScoreValue score={r.score} basis={r.basis} />, align: "right", className: "w-24" },
    ...FACTOR_KEYS.map(
      (k): Column<RequirementRow> => ({
        key: k,
        header: (
          <Tooltip content={k === "uncertainty" ? "Uncertainty 0–4 — counts against priority." : `${FACTOR_LABEL[k]} 0–4`}>
            <span>{k === "relevance" ? "Fit" : k === "uncertainty" ? "Unc." : FACTOR_LABEL[k].split(" ").slice(-1)[0]}</span>
          </Tooltip>
        ),
        label: FACTOR_LABEL[k],
        cell: (r) => <span className={cn("text-xs tabular-nums", k === "uncertainty" && r.factors[k] >= 3 ? "text-amber-700" : "text-zinc-800")}>{r.factors[k]}</span>,
        align: "right",
        className: "w-14",
      }),
    ),
    { key: "confidence", header: "Confidence", cell: (r) => <ConfidenceBadge confidence={r.confidence} />, className: "w-24" },
    { key: "decision", header: "Decision", cell: (r) => <DecisionBadge status={r.status} />, className: "w-28" },
  ];

  return (
    <div className="space-y-6">
      <PageHeader title="Prioritization" question={`What should we do first in ${MARKET_LABEL[market]}?`} meta={<span>{PRIORITY_RULE}</span>} />

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_340px_320px]">
        <div className="grid grid-cols-5 divide-x divide-slate-200 self-start rounded-md border border-slate-200 bg-white">
          {counts.map(({ p, n }) => (
            <button
              key={p}
              type="button"
              onClick={() => set("priority", filters.priority === p ? "all" : p)}
              aria-pressed={filters.priority === p}
              className={cn("px-3 py-2.5 text-left hover:bg-slate-50 focus-visible:bg-slate-50 focus-visible:outline-none", filters.priority === p && "bg-brand-soft")}
            >
              <PriorityBadge priority={p} />
              <div className="mt-1.5 text-xl font-semibold tabular-nums tracking-tight text-zinc-950">{n}</div>
              <div className="text-2xs text-slate-500">active</div>
            </button>
          ))}
        </div>
        <div className="self-start rounded-md border border-slate-200 bg-white p-3">
          <div className="text-2xs font-medium uppercase tracking-wide text-slate-500">CRPS distribution</div>
          <ScoreDistributionChart data={distribution} />
        </div>
        <div className="self-start rounded-md border border-slate-200 bg-white p-3">
          <WeightControls />
        </div>
      </div>

      <div>
        <FilterBar active={active} onClearAll={() => setFilters(DEFAULTS)} resultLabel={`${filtered.length} requirements · select up to ${MAX_COMPARE} to compare`}>
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
          caption="Requirements by priority"
          rows={filtered}
          columns={columns}
          getRowId={(r) => r.id}
          onRowClick={(r) => router.push(`/requirements/${r.id}`)}
          rowClassName={(r) => (selected.includes(r.id) ? "bg-brand-soft/60" : undefined)}
          empty={
            <EmptyState
              title="No requirement matches these filters."
              action={
                <Button size="sm" onClick={() => setFilters(DEFAULTS)}>
                  Clear filters
                </Button>
              }
            />
          }
        />
      </div>

      <Section
        title="Comparison"
        description="Aligned rows. Ties within 2.5 points are flagged — ordinal ratings do not support finer ranking."
        actions={
          selected.length > 0 && (
            <Button size="sm" variant="ghost" onClick={() => setSelected([])}>
              Clear selection
            </Button>
          )
        }
      >
        {compareRows.length < 2 ? (
          <EmptyState title="Select two to four requirements in the table to compare them." detail="Use the checkboxes in the first column." />
        ) : (
          <CompareTable rows={compareRows} />
        )}
      </Section>
    </div>
  );
}
