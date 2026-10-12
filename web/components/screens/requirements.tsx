"use client";

import { Search } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

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
import { MARKET_LABEL, type ModelCoverageSummary } from "@/lib/domain/model";
import { VEHICLES, type Vehicle } from "@/lib/advisor/contracts";
import { useReviewDrafts } from "@/lib/advisor/review-drafts";
import { usePersistentState, useStore } from "@/lib/store";
import { useRequirementRows, type RequirementRow } from "@/lib/view";

interface Filters {
  q: string;
  topic: string;
  priority: string;
  decision: string;
}
const DEFAULTS: Filters = { q: "", topic: "all", priority: "all", decision: "all" };
const THEME_NAME: Record<string, string> = {
  controls_usability: "Everyday controls and usability",
  software_reliability: "Connected functions and software reliability",
  charging_and_range: "Range and charging confidence",
  ride_and_comfort: "Ride, seating and comfort",
  driver_assistance: "Driver assistance behavior",
  storage_and_practicality: "Storage and practical access",
  noise_and_refinement: "Cabin noise and refinement",
};

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
  const [model, setModel] = usePersistentState<Vehicle>("requirements:model", "G60");
  const drafts = useReviewDrafts();
  const rows = useRequirementRows(market);
  const modelDrafts = drafts.filter((draft) => draft.model_code === model);
  const [coverage, setCoverage] = useState<ModelCoverageSummary[]>([]);
  const [coverageLoaded, setCoverageLoaded] = useState(false);
  const [coverageReason, setCoverageReason] = useState<string | null>(null);
  useEffect(() => {
    if (model === "G60" || coverageLoaded) return;
    const controller = new AbortController();
    fetch("/api/model-coverage", { signal: controller.signal })
      .then((response) => response.json())
      .then((data: { available: boolean; reason: string | null; coverage: ModelCoverageSummary[] }) => {
        setCoverage(data.coverage);
        setCoverageReason(data.available ? null : data.reason || "Evidence database unavailable.");
        setCoverageLoaded(true);
      })
      .catch(() => { if (!controller.signal.aborted) { setCoverageReason("Model evidence could not be loaded."); setCoverageLoaded(true); } });
    return () => controller.abort();
  }, [model, coverageLoaded]);
  const modelCoverage = coverage.find((item) => item.model_code === model);
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
        question={model === "G60" ? `Which customer-facing requirements should shape the BMW 5 Series successor? Canonical seven-factor CRPS · ${MARKET_LABEL[market]} · 2030.` : `Review suggested requirements for the ${VEHICLES[model]}. Authored canonical requirements are currently available only for the 5 Series.`}
        actions={<Button asChild><Link href="/needs">Trace customer needs</Link></Button>}
      />
      <div className="mb-5 grid gap-2 sm:grid-cols-3" role="group" aria-label="Choose BMW model for requirements">
        {(["F70", "G60", "G70"] as const).map((code) => <button key={code} type="button" aria-pressed={model === code} onClick={() => setModel(code)} className={`rounded-md border px-4 py-3 text-left text-sm font-semibold ${model === code ? "border-brand bg-brand-soft" : "border-slate-200 bg-white hover:border-brand-line"}`}>{VEHICLES[code]} <span className="font-mono text-xs font-normal">{code}</span><span className="mt-1 block text-xs font-normal text-slate-600">{code === "G60" ? `${rows.length} canonical requirements · ` : ""}{drafts.filter((draft) => draft.model_code === code).length} Studio suggestions</span></button>)}
      </div>
      {modelDrafts.length > 0 && <section className="mb-5 space-y-2"><h2 className="text-sm font-semibold">Studio suggestions awaiting PM review or decision</h2><p className="text-xs text-slate-500">These suggestions and decisions are saved in this browser, separate from audited canonical requirements.</p><div className="grid gap-2 md:grid-cols-2">{modelDrafts.map((draft) => <Link key={draft.id} href={`/requirements/suggestions/${encodeURIComponent(draft.id)}`} className="rounded-md border border-slate-200 bg-white p-3 hover:border-brand"><span className="block text-sm font-medium">{draft.title}</span><span className="mt-1 block text-xs capitalize text-slate-500">{draft.status} · {draft.market} · {draft.powertrain}</span></Link>)}</div></section>}
      {model !== "G60" ? <div className="space-y-4">
        <div className="rounded-md border border-slate-200 bg-white p-5"><h2 className="text-sm font-semibold">Model-specific requirement areas</h2><p className="mt-2 text-xs text-slate-600">These are evidence themes, not authored or PM-approved requirements. Studio suggestions for this car appear above when sent for review.</p>
          {!coverageLoaded && <p className="mt-3 text-xs">Loading model evidence…</p>}
          {coverageReason && <p className="mt-3 text-xs text-amber-700">{coverageReason}</p>}
          {modelCoverage && <p className="mt-3 text-xs text-slate-600">{modelCoverage.feedback_records.toLocaleString()} feedback records · {modelCoverage.signal_count.toLocaleString()} extracted spans · {modelCoverage.themes.length} candidate areas</p>}
          <Button asChild className="mt-3"><Link href="/studio">Open Decision Studio</Link></Button>
        </div>
        {modelCoverage && <div className="grid gap-3 md:grid-cols-2">{modelCoverage.themes.map((theme) => <article key={theme.domain} className="rounded-md border border-slate-200 bg-white p-4"><p className="text-2xs font-semibold uppercase text-brand">Candidate requirement area · unreviewed</p><h3 className="mt-1 text-sm font-semibold">{THEME_NAME[theme.domain] ?? theme.domain.replaceAll("_", " ")}</h3><p className="mt-2 text-xs text-slate-600">{theme.feedback_count.toLocaleString()} feedback IDs · {theme.signal_count.toLocaleString()} extracted spans · {theme.concern_count.toLocaleString()} tagged concerns. Counts do not measure customer prevalence.</p>{theme.examples.slice(0, 2).map((example) => <blockquote key={`${example.source_record_id}-${example.locator}`} className="mt-3 border-l-2 border-slate-200 pl-3 text-xs text-slate-700">“{example.excerpt}”<span className="mt-1 block font-mono text-2xs text-slate-500">{example.source_record_id} · {example.country}</span></blockquote>)}</article>)}</div>}
      </div> : <>
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
      </>}
    </div>
  );
}
