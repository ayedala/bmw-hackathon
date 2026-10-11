"use client";

import { Search } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { useEffect, useMemo } from "react";

import { MarketTag, ProvenanceBadge, QualityValue, SourceFamilyBadge, StanceBadge } from "@/components/app/badges";
import { DataTable, type Column } from "@/components/app/data-table";
import { EmptyState, FilterBar, PageHeader, type ActiveFilter } from "@/components/app/layout-parts";
import { useEvidencePanel } from "@/components/app/shell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Tooltip } from "@/components/ui/tooltip";
import type { Stance } from "@/lib/domain/contracts";
import { FAMILY_LABEL, formatDate, humanize, PROVENANCE_LABEL, TOPIC_LABEL } from "@/lib/domain/derive";
import { MARKETS, MARKET_LABEL, type EvidenceItem } from "@/lib/domain/model";
import { usePersistentState, useStore } from "@/lib/store";

interface Filters {
  q: string;
  vehicle: string;
  market: string;
  topic: string;
  family: string;
  stance: string;
  date: string;
  provenance: string;
  independentOnly: boolean;
}

const DEFAULTS: Filters = { q: "", vehicle: "all", market: "all", topic: "all", family: "all", stance: "all", date: "all", provenance: "all", independentOnly: true };

const DATE_OPTIONS = [
  { value: "all", label: "Any date" },
  { value: "2026", label: "2026" },
  { value: "2025", label: "2025" },
  { value: "older", label: "Before 2025" },
  { value: "undated", label: "Undated" },
];

interface Row {
  id: string;
  evidence: EvidenceItem;
  stance: Stance | null;
  hypothesis: string | null;
}

export function EvidenceExplorer() {
  const params = useSearchParams();
  const { dataset, requirements } = useStore();
  const panel = useEvidencePanel();
  const [filters, setFilters] = usePersistentState<Filters>("evidence", DEFAULTS);

  useEffect(() => {
    const q = params.get("q");
    const vehicle = params.get("vehicle");
    const id = params.get("id");
    const topic = params.get("topic");
    const market = params.get("market");
    const family = params.get("family");
    if (q || vehicle || topic || market || family) {
      setFilters({ ...DEFAULTS, q: q ?? "", vehicle: vehicle ?? "all", topic: topic ?? "all", market: market ?? "all", family: family ?? "all" });
    }
    if (id) panel.open(id);
    // only react to URL changes
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params]);

  const stanceOf = useMemo(() => {
    const map = new Map<string, { stance: Stance; hypothesis: string }>();
    if (dataset.reasoning.authoritative) {
      for (const bundle of requirements) for (const ref of bundle.revisions.at(-1)?.evidence_references ?? []) {
        const mapped: Stance = ref.role === "opposes" ? "contradicts" : ref.role === "supports" ? "supports" : "neutral";
        const previous = map.get(ref.evidence_id);
        map.set(ref.evidence_id, { stance: previous && previous.stance !== mapped ? "neutral" : mapped,
          hypothesis: previous && previous.stance !== mapped ? "varies by requirement" : bundle.display_id });
      }
      return map;
    }
    for (const h of dataset.hypotheses) {
      for (const l of h.links) if (!map.has(l.evidence_id)) map.set(l.evidence_id, { stance: l.stance, hypothesis: h.id });
    }
    return map;
  }, [dataset.hypotheses, dataset.reasoning.authoritative, requirements]);

  const rows: Row[] = useMemo(
    () =>
      dataset.evidence.map((evidence) => {
        const s = stanceOf.get(evidence.id);
        return { id: evidence.id, evidence, stance: s?.stance ?? null, hypothesis: s?.hypothesis ?? null };
      }),
    [dataset.evidence, stanceOf],
  );

  const brands = useMemo(() => [...new Set(dataset.evidence.map((e) => e.brand))].filter((b) => b && b !== "—").sort(), [dataset.evidence]);
  const families = useMemo(() => [...new Set(dataset.evidence.map((e) => e.source_family))].sort(), [dataset.evidence]);
  const topics = useMemo(() => [...new Set(dataset.evidence.map((e) => e.topic))], [dataset.evidence]);

  const filtered = useMemo(() => {
    const q = filters.q.trim().toLowerCase();
    return rows.filter(({ evidence: e, stance }) => {
      if (filters.independentOnly && e.duplicate_of) return false;
      if (filters.vehicle !== "all" && e.brand !== filters.vehicle) return false;
      if (filters.market !== "all" && e.market !== filters.market) return false;
      if (filters.topic !== "all" && e.topic !== filters.topic) return false;
      if (filters.family !== "all" && e.source_family !== filters.family) return false;
      if (filters.provenance !== "all" && e.provenance !== filters.provenance) return false;
      if (filters.stance !== "all") {
        if (filters.stance === "unlinked" ? stance !== null : stance !== filters.stance) return false;
      }
      if (filters.date !== "all") {
        const year = e.published_at ? Number(e.published_at.slice(0, 4)) : null;
        if (filters.date === "undated" && year !== null) return false;
        if (filters.date === "older" && (year === null || year >= 2025)) return false;
        if ((filters.date === "2026" || filters.date === "2025") && year !== Number(filters.date)) return false;
      }
      if (q) {
        const hay = `${e.id} ${e.claim} ${e.excerpt} ${e.vehicle} ${e.source_name} ${e.subtopic}`.toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
  }, [rows, filters]);

  const set = <K extends keyof Filters>(key: K, value: Filters[K]) => setFilters((f) => ({ ...f, [key]: value }));

  const labels: Record<string, (v: string) => string> = {
    vehicle: (v) => v,
    market: (v) => MARKET_LABEL[v as keyof typeof MARKET_LABEL] ?? v,
    topic: (v) => TOPIC_LABEL[v] ?? v,
    family: (v) => FAMILY_LABEL[v] ?? v,
    stance: (v) => (v === "unlinked" ? "Not linked" : humanize(v)),
    date: (v) => DATE_OPTIONS.find((d) => d.value === v)?.label ?? v,
    provenance: (v) => PROVENANCE_LABEL[v as keyof typeof PROVENANCE_LABEL] ?? v,
  };
  const active: ActiveFilter[] = (Object.keys(labels) as (keyof Filters)[])
    .filter((k) => filters[k] !== "all")
    .map((k) => ({ key: k, label: labels[k]?.(String(filters[k])) ?? String(filters[k]), onClear: () => set(k, "all" as never) }));
  if (filters.q) active.push({ key: "q", label: `“${filters.q}”`, onClear: () => set("q", "") });
  if (!filters.independentOnly) active.push({ key: "dup", label: "Including duplicates", onClear: () => set("independentOnly", true) });

  const emptyDetail = active.length > 0 ? `No evidence matches ${active.map((a) => a.label).join(" + ")}.` : "No evidence records are loaded.";

  const columns: Column<Row>[] = [
    {
      key: "claim",
      header: "Claim",
      cell: ({ evidence: e }) => (
        <div className="min-w-0">
          <div className="line-clamp-2 text-[13px] leading-snug text-zinc-900">
            {e.claim}
            {e.numeric_value !== null && !e.claim.includes(String(e.numeric_value)) && (
              <span className="ml-1 font-medium tabular-nums">
                {e.numeric_value} {e.numeric_unit}
              </span>
            )}
          </div>
          <div className="mt-0.5 flex items-center gap-1.5 text-2xs text-slate-500">
            <ProvenanceBadge provenance={e.provenance} />
            <span className="font-mono">{e.id}</span>
            {e.duplicate_of && <span className="text-amber-700">duplicate of {e.duplicate_of}</span>}
          </div>
        </div>
      ),
      sortValue: (r) => r.evidence.claim,
      className: "min-w-[320px] max-w-[520px]",
    },
    { key: "vehicle", header: "Vehicle", cell: (r) => <span className="text-xs text-zinc-800">{r.evidence.vehicle}</span>, sortValue: (r) => r.evidence.vehicle, className: "w-40" },
    {
      key: "topic",
      header: "Topic",
      cell: (r) => (
        <span className="text-xs text-zinc-800">
          {TOPIC_LABEL[r.evidence.topic]}
          <span className="block text-2xs text-slate-500">{humanize(r.evidence.subtopic)}</span>
        </span>
      ),
      sortValue: (r) => `${r.evidence.topic}${r.evidence.subtopic}`,
      className: "w-36",
    },
    { key: "source", header: "Source", cell: (r) => <span className="line-clamp-1 text-xs text-zinc-800">{r.evidence.source_name}</span>, sortValue: (r) => r.evidence.source_name, className: "max-w-[200px]" },
    { key: "family", header: "Family", cell: (r) => <SourceFamilyBadge family={r.evidence.source_family} />, sortValue: (r) => r.evidence.source_family, className: "w-32" },
    { key: "market", header: "Mkt", cell: (r) => <MarketTag market={r.evidence.market} />, sortValue: (r) => r.evidence.market, className: "w-12" },
    { key: "quality", header: "Quality", cell: (r) => <QualityValue quality={r.evidence.quality} />, sortValue: (r) => r.evidence.quality ?? -1, className: "w-24" },
    {
      key: "published",
      header: "Published",
      cell: (r) => <span className="whitespace-nowrap text-xs tabular-nums text-slate-600">{formatDate(r.evidence.published_at)}</span>,
      sortValue: (r) => r.evidence.published_at ?? "",
      className: "w-28",
    },
    {
      key: "stance",
      header: "Stance",
      cell: (r) =>
        r.stance ? (
          <Tooltip content={`Stance toward ${r.hypothesis}`}>
            <span tabIndex={0} className="focus-visible:outline-none">
              <StanceBadge stance={r.stance} />
            </span>
          </Tooltip>
        ) : (
          <span className="text-2xs text-slate-400">Not linked</span>
        ),
      sortValue: (r) => r.stance ?? "z",
      className: "w-28",
    },
  ];

  return (
    <div>
      <PageHeader
        title="Evidence"
        question="What supports or contradicts our conclusions, and where does it come from?"
        meta={
          <>
            <span>{dataset.evidence.filter((e) => e.provenance === "bmw_record").length} BMW anchor records</span>
            <span>{dataset.evidence.filter((e) => e.provenance === "pipeline").length} pipeline</span>
            <span>{dataset.evidence.filter((e) => e.provenance === "curated_seed").length} curated seeds</span>
            <span>{dataset.evidence.filter((e) => e.provenance === "synthetic").length} synthetic</span>
            <span>{dataset.evidence.filter((e) => e.duplicate_of).length} duplicate</span>
          </>
        }
      />
      <FilterBar
        active={active}
        onClearAll={() => setFilters(DEFAULTS)}
        resultLabel={
          <span className="tabular-nums">
            {filtered.length} of {rows.length} records
          </span>
        }
      >
        <div className="relative">
          <Search aria-hidden className="pointer-events-none absolute left-2 top-1/2 size-3.5 -translate-y-1/2 text-slate-400" />
          <Input value={filters.q} onChange={(e) => set("q", e.target.value)} placeholder="Search claim, excerpt, source" aria-label="Search evidence" className="h-7 w-64 pl-7 text-xs" />
        </div>
        <Select label="Vehicle" value={filters.vehicle} onValueChange={(v) => set("vehicle", v)} options={[{ value: "all", label: "All" }, ...brands.map((b) => ({ value: b, label: b }))]} />
        <Select label="Market" value={filters.market} onValueChange={(v) => set("market", v)} options={[{ value: "all", label: "All" }, ...MARKETS.map((m) => ({ value: m, label: MARKET_LABEL[m] }))]} />
        <Select label="Topic" value={filters.topic} onValueChange={(v) => set("topic", v)} options={[{ value: "all", label: "All" }, ...topics.map((t) => ({ value: t, label: TOPIC_LABEL[t] ?? t }))]} />
        <Select label="Source family" value={filters.family} onValueChange={(v) => set("family", v)} options={[{ value: "all", label: "All" }, ...families.map((f) => ({ value: f, label: FAMILY_LABEL[f] ?? f }))]} />
        <Select
          label="Stance"
          value={filters.stance}
          onValueChange={(v) => set("stance", v)}
          options={[
            { value: "all", label: "All" },
            { value: "supports", label: "Supports" },
            { value: "contradicts", label: "Contradicts" },
            { value: "neutral", label: "Neutral" },
            { value: "unlinked", label: "Not linked" },
          ]}
        />
        <Select label="Published" value={filters.date} onValueChange={(v) => set("date", v)} options={DATE_OPTIONS} />
        <Select
          label="Provenance"
          value={filters.provenance}
          onValueChange={(v) => set("provenance", v)}
          options={[
            { value: "all", label: "All" },
            { value: "bmw_record", label: "BMW record" },
            { value: "pipeline", label: "Pipeline" },
            { value: "curated_seed", label: "Curated seed" },
            { value: "synthetic", label: "Synthetic" },
          ]}
        />
        <label className="ml-1 inline-flex items-center gap-1.5 text-xs text-slate-600">
          <input type="checkbox" className="size-3.5 accent-zinc-900" checked={filters.independentOnly} onChange={(e) => set("independentOnly", e.target.checked)} />
          Hide duplicates
        </label>
      </FilterBar>
      <DataTable
        caption="Evidence records"
        rows={filtered}
        columns={columns}
        getRowId={(r) => r.id}
        onRowClick={(r) => panel.open(r.id)}
        defaultSort={{ key: "quality", direction: "desc" }}
        pageSize={40}
        scrollClassName="max-h-[calc(100vh-230px)]"
        empty={
          <EmptyState
            title="No evidence matches the selected filters."
            detail={emptyDetail}
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
