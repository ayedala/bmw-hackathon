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
import { DECISION_STATUS_LABEL, formatDate, PRIORITIES, priorityRank, TOPIC_LABEL, type DecisionStatus } from "@/lib/domain/derive";
import { MARKET_LABEL } from "@/lib/domain/model";
import type { ModelCoverageSummary } from "@/lib/domain/model";
import { usePersistentState, useStore } from "@/lib/store";
import { useRequirementRows, type RequirementRow } from "@/lib/view";

interface Filters {
  q: string;
  topic: string;
  priority: string;
  decision: string;
}
const DEFAULTS: Filters = { q: "", topic: "all", priority: "all", decision: "all" };

type ModelChoice = "F70" | "G60" | "G70";
const MODEL_NAME: Record<ModelChoice, string> = { F70: "1 Series", G60: "5 Series", G70: "7 Series" };
const THEME_NAME: Record<string, string> = {
  controls_usability: "Everyday controls and usability",
  software_reliability: "Connected functions and software reliability",
  charging_and_range: "Range and charging confidence",
  ride_and_comfort: "Ride, seating and comfort",
  driver_assistance: "Driver assistance behavior",
  storage_and_practicality: "Storage and practical access",
  noise_and_refinement: "Cabin noise and refinement",
};

function ModelChoiceBar({ selected, onSelect, coverage, g60Count }: {
  selected: ModelChoice;
  onSelect: (model: ModelChoice) => void;
  coverage: ModelCoverageSummary[];
  g60Count: number;
}) {
  return <div className="mb-5 grid gap-2 sm:grid-cols-3" role="group" aria-label="Choose BMW model for requirements">
    {(["F70", "G60", "G70"] as const).map((model) => {
      const summary = coverage.find((item) => item.model_code === model);
      return <button key={model} type="button" aria-pressed={selected === model} onClick={() => onSelect(model)}
        className={`rounded-md border px-4 py-3 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/40 ${selected === model ? "border-brand bg-brand-soft text-zinc-950" : "border-slate-200 bg-white text-slate-700 hover:border-brand-line"}`}>
        <span className="block text-sm font-semibold">BMW {MODEL_NAME[model]} <span className="font-mono text-xs font-normal">{model}</span></span>
        <span className="mt-1 block text-xs text-slate-600">{model === "G60" ? `${g60Count} authored requirement drafts` : summary ? `${summary.themes.length} evidence themes · proposals pending` : "Evidence unavailable"}</span>
      </button>;
    })}
  </div>;
}

function CandidateThemes({ model, summary }: { model: "F70" | "G70"; summary: ModelCoverageSummary | undefined }) {
  if (!summary) return <EmptyState title="Model evidence is unavailable." detail="Connect the private evidence database and reload to inspect model-specific themes." />;
  const markets = summary.signal_markets.map((item) => `${item.country} ${item.signals.toLocaleString()}`).join(" · ");
  return <div className="space-y-5">
    <div className="rounded-md border border-blue-200 bg-blue-50 px-4 py-3 text-sm leading-relaxed text-slate-800">
      <p className="font-semibold text-zinc-950">Evidence themes for the BMW {MODEL_NAME[model]} ({model})</p>
      <p className="mt-1">{summary.feedback_records.toLocaleString()} supplied feedback records across {summary.markets.length} markets; {summary.signal_count.toLocaleString()} extracted spans ({markets}). These are candidate requirement areas, not authored or approved requirements. The G60 proposals and scores do not transfer to this model.</p>
      <p className="mt-1 text-xs text-slate-600">The market control in the workbench header applies to the G60 proposal set. Counts below follow each signal’s own market; feedback IDs are records, not verified unique customers or prevalence estimates.</p>
    </div>
    <div className="grid gap-3 lg:grid-cols-2">
      {summary.themes.map((theme) => <article key={theme.domain} className="rounded-md border border-slate-200 bg-white p-4">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-blue-700">Candidate requirement area</p>
            <h2 className="mt-1 text-base font-semibold text-zinc-950">{THEME_NAME[theme.domain] ?? theme.domain.replaceAll("_", " ")}</h2>
          </div>
          <span className="rounded-full bg-slate-100 px-2 py-1 text-xs text-slate-700">Unreviewed</span>
        </div>
        <p className="mt-2 text-sm text-slate-700">{theme.feedback_count.toLocaleString()} feedback IDs have {theme.signal_count.toLocaleString()} extracted spans in this topic; {theme.concern_count.toLocaleString()} are automatically tagged as complaints or wishes. Topic and polarity labels can be wrong and do not prove support for a specific solution.</p>
        {theme.examples.length > 0 && <div className="mt-3 border-t border-slate-100 pt-3">
          <p className="text-xs font-medium text-slate-600">Source span to review</p>
          <ul className="mt-2 space-y-2">
            {theme.examples.map((example) => <li key={`${example.source_record_id}-${example.locator}`} className="rounded bg-slate-50 px-3 py-2 text-sm text-zinc-800">
              <p className="line-clamp-3">“{example.excerpt}”</p>
              <p className="mt-1 font-mono text-xs text-slate-500">{example.source_record_id} · {example.country}{example.locator ? ` · ${example.locator}` : ""}</p>
            </li>)}
          </ul>
        </div>}
        <p className="mt-3 text-xs text-slate-600">Next: review source relevance, define a model-specific customer outcome, test alternatives, then assess feasibility, cost and framework CRPS.</p>
      </article>)}
    </div>
  </div>;
}

export function requirementColumns(market: string): Column<RequirementRow>[] {
  return [
    { key: "priority", header: "Priority", cell: (r) => <PriorityBadge priority={r.priority} />, sortValue: (r) => -priorityRank(r.priority), className: "w-16" },
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
    { key: "crps", header: "Legacy score", cell: (r) => <ScoreValue score={r.score} basis={r.basis} />, sortValue: (r) => r.score ?? -1, align: "right", className: "w-24" },
    {
      key: "confidence",
      header: "Confidence",
      cell: (r) => <ConfidenceBadge confidence={r.confidence} />,
      sortValue: (r) => ["Low", "Medium", "High"].indexOf(r.confidence),
      className: "w-24",
    },
    {
      key: "evidence",
      header: "Evidence",
      cell: (r) => (
        <Tooltip content={`${r.balance.supporting} same-topic complaint or aspiration spans, ${r.balance.contradicting} reviewed opposing spans, ${r.balance.independent_sources} distinct feedback IDs. Relevance to this requirement is unreviewed.`}>
          <span tabIndex={0} className="whitespace-nowrap text-xs tabular-nums text-zinc-800">
            {r.balance.supporting}
            <span className="text-slate-400"> / </span>
            <span className="text-amber-700">{r.balance.contradicting}</span>
            <span className="ml-1.5 text-slate-500">{r.balance.independent_sources} IDs</span>
          </span>
        </Tooltip>
      ),
      sortValue: (r) => r.balance.independent_sources,
      className: "w-28",
    },
    { key: "market", header: "Mkt", cell: () => <MarketTag market={market} />, className: "w-12" },
    { key: "decision", header: "Decision", cell: (r) => <DecisionBadge status={r.status} />, sortValue: (r) => r.status, className: "w-28" },
    { key: "updated", header: "Updated", cell: (r) => <span className="whitespace-nowrap text-xs text-slate-500">{formatDate(r.updated_at)}</span>, sortValue: (r) => r.updated_at, className: "w-28" },
  ];
}

export function RequirementsScreen() {
  const router = useRouter();
  const { market, dataset } = useStore();
  const [model, setModel] = usePersistentState<ModelChoice>("requirements:model", "G60");
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
        question={model === "G60" ? `Which customer-facing requirements should shape the successor? Legacy planning score under the current weights · ${MARKET_LABEL[market]}.` : `Explore the available ${MODEL_NAME[model]} evidence before defining model-specific requirements.`}
      />
      <ModelChoiceBar selected={model} onSelect={setModel} coverage={dataset.model_coverage} g60Count={rows.length} />
      {model !== "G60" ? <CandidateThemes model={model} summary={dataset.model_coverage.find((item) => item.model_code === model)} /> : <>
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
      </>}
    </div>
  );
}
