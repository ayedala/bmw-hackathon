"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useMemo } from "react";

import { BalanceBar, ConfidenceBadge, DecisionBadge, HypothesisStatusBadge, MarketTag, PriorityBadge, ScoreValue } from "@/components/app/badges";
import { DataTable, type Column } from "@/components/app/data-table";
import { EvidenceList } from "@/components/app/evidence-list";
import { EmptyState, FilterBar, PageHeader, SubHeading, type ActiveFilter } from "@/components/app/layout-parts";
import { Button } from "@/components/ui/button";
import { SidePanel } from "@/components/ui/dialog";
import { Select } from "@/components/ui/select";
import { balanceOf, currentFactors, decisionStatus, inScope, formatDate, hypothesisStatus, latestRevision, priorityOf, TOPIC_LABEL } from "@/lib/domain/derive";
import { MARKETS, MARKET_LABEL } from "@/lib/domain/model";
import { priorityScore } from "@/lib/domain/scoring";
import { usePersistentState, useStore } from "@/lib/store";
import { useFindingRows, type FindingRow } from "@/lib/view";

interface Filters {
  topic: string;
  market: string;
}
const DEFAULTS: Filters = { topic: "all", market: "all" };

function FindingDetail({ row }: { row: FindingRow }) {
  const { hypothesesById, evidenceById, requirementByDisplayId, market, policy } = useStore();
  const f = row.finding;
  const supporting = row.links.filter((l) => l.stance === "supports" && l.evidence).map((l) => ({ evidence: l.evidence!, note: l.note || l.hypothesis_id }));
  const contradicting = row.links.filter((l) => l.stance === "contradicts" && l.evidence).map((l) => ({ evidence: l.evidence!, note: l.note || l.hypothesis_id }));
  const anchors = f.requirement_ids.flatMap((rid) => requirementByDisplayId.get(rid)?.proposal.anchor_ids ?? [])
    .map((id) => evidenceById.get(id))
    .filter((e): e is NonNullable<typeof e> => Boolean(e))
    .map((evidence) => ({ evidence, note: "Source anchor cited by the proposal; interpretation requires review." }));
  const b = row.balance;

  return (
    <div className="space-y-5">
      <div>
        <div className="flex flex-wrap items-center gap-2 text-2xs text-slate-500">
          <span className="font-mono">{f.id}</span>
          <span>{TOPIC_LABEL[f.topic]}</span>
          <MarketTag market={f.market} />
          <span>Updated {formatDate(f.updated_at)}</span>
        </div>
        <p className="mt-2 text-[13px] leading-relaxed text-zinc-800">{f.summary}</p>
        <div className="mt-3 flex items-center gap-4">
          <ConfidenceBadge confidence={row.confidence} />
        </div>
      </div>

      <div className="grid grid-cols-4 gap-px overflow-hidden rounded-md border border-slate-200/60 bg-slate-200/60">
        {[
          ["Topic complaints / wishes", b.supporting],
          ["Opposing", b.contradicting],
          ["Praise / other", b.neutral],
          ["Feedback IDs", b.independent_sources],
        ].map(([label, value]) => (
          <div key={label} className="bg-white px-2.5 py-2">
            <div className="text-2xs uppercase tracking-wide text-slate-500">{label}</div>
            <div className={label === "Opposing" ? "text-base font-semibold tabular-nums text-amber-700" : "text-base font-semibold tabular-nums text-zinc-950"}>{value}</div>
          </div>
        ))}
      </div>

      {anchors.length > 0 && <div>
        <SubHeading count={anchors.length}>Proposal anchor records</SubHeading>
        <p className="mb-2 text-xs leading-relaxed text-slate-600">Start with these cited records, then inspect the wider same-topic signals below.</p>
        <EvidenceList entries={anchors} initial={3} empty="No proposal anchors available." />
      </div>}

      <div>
        <SubHeading count={supporting.length}>Same-topic complaints and wishes</SubHeading>
        <p className="mb-2 text-xs leading-relaxed text-slate-600">These spans share a broad topic with this proposal. They have not been checked for relevance to the specific customer outcome, and the count is not a failure rate.</p>
        <EvidenceList entries={supporting} initial={3} empty="No same-topic complaints or wishes." />
      </div>
      <div>
        <SubHeading count={contradicting.length}>Opposing evidence</SubHeading>
        <EvidenceList entries={contradicting} initial={3} tone="contradict" empty="No opposing evidence has been reviewed. Praise remains visible as context." />
      </div>

      <div>
        <SubHeading count={f.hypothesis_ids.length}>Related hypotheses</SubHeading>
        <ul className="space-y-1">
          {f.hypothesis_ids.map((hid) => {
            const h = hypothesesById.get(hid);
            if (!h) return null;
            const hb = balanceOf(h.links.map((l) => ({ stance: l.stance, evidence: evidenceById.get(l.evidence_id) })));
            return (
              <li key={hid} className="flex items-center gap-2 text-xs">
                <Link href={`/hypotheses?id=${hid}`} className="min-w-0 flex-1 hover:underline">
                  <span className="mr-1.5 font-mono text-2xs text-slate-500">{hid}</span>
                  <span className="text-zinc-900">{h.statement}</span>
                </Link>
                <HypothesisStatusBadge status={hypothesisStatus(hb)} />
              </li>
            );
          })}
        </ul>
      </div>

      <div>
        <SubHeading>Proposed customer outcome</SubHeading>
        <p className="text-xs text-zinc-900">{f.customer_need}</p>
      </div>

      <div>
        <SubHeading count={f.requirement_ids.length}>Related requirements</SubHeading>
        <ul className="divide-y divide-slate-100 rounded-md border border-slate-200/60">
          {f.requirement_ids.map((rid) => {
            const bundle = requirementByDisplayId.get(rid);
            if (!bundle) return null;
            const rev = latestRevision(bundle);
            const { factors, basis } = currentFactors(bundle);
            const scoped = inScope(bundle, market);
            const s = scoped ? priorityScore(factors, policy) : null;
            return (
              <li key={rid}>
                <Link href={`/requirements/${rid}`} className="flex items-center gap-2 px-2.5 py-1.5 text-xs hover:bg-slate-50">
                  <PriorityBadge priority={priorityOf(s, scoped ? factors : null)} />
                  <span className="min-w-0 flex-1 truncate text-zinc-900">{rev.title}</span>
                  <ScoreValue score={s} basis={basis} />
                  <DecisionBadge status={decisionStatus(rev, bundle.decisions)} />
                </Link>
              </li>
            );
          })}
        </ul>
      </div>
    </div>
  );
}

export function FindingsScreen() {
  const rows = useFindingRows();
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const selectedId = params.get("id");
  const [filters, setFilters] = usePersistentState<Filters>("findings", DEFAULTS);
  const selected = rows.find((r) => r.id === selectedId) ?? null;

  const select = (id: string | null) => router.replace(id ? `${pathname}?id=${id}` : pathname, { scroll: false });

  const filtered = useMemo(
    () =>
      rows.filter((r) => {
        if (filters.topic !== "all" && r.finding.topic !== filters.topic) return false;
        if (filters.market !== "all" && r.finding.market !== filters.market) return false;
        return true;
      }),
    [rows, filters],
  );

  const active: ActiveFilter[] = [];
  if (filters.topic !== "all") active.push({ key: "topic", label: TOPIC_LABEL[filters.topic] ?? filters.topic, onClear: () => setFilters((f) => ({ ...f, topic: "all" })) });
  if (filters.market !== "all") active.push({ key: "market", label: MARKET_LABEL[filters.market as keyof typeof MARKET_LABEL], onClear: () => setFilters((f) => ({ ...f, market: "all" })) });

  const topics = [...new Set(rows.map((r) => r.finding.topic))];

  const columns: Column<FindingRow>[] = [
    {
      key: "finding",
      header: "Finding",
      cell: (r) => (
        <div className="min-w-0">
          <div className="line-clamp-1 font-medium text-zinc-900">{r.finding.title}</div>
          <div className="font-mono text-2xs text-slate-500">{r.id}</div>
        </div>
      ),
      sortValue: (r) => r.finding.title,
      className: "min-w-[300px] max-w-[460px]",
    },
    { key: "topic", header: "Topic", cell: (r) => <span className="text-xs text-slate-700">{TOPIC_LABEL[r.finding.topic]}</span>, sortValue: (r) => r.finding.topic, className: "w-24" },
    { key: "market", header: "Mkt", cell: (r) => <MarketTag market={r.finding.market} />, sortValue: (r) => r.finding.market, className: "w-12" },
    { key: "confidence", header: "Confidence", cell: (r) => <ConfidenceBadge confidence={r.confidence} />, sortValue: (r) => ["Low", "Medium", "High"].indexOf(r.confidence), className: "w-24" },
    { key: "sources", header: "Feedback IDs", cell: (r) => <span className="text-xs tabular-nums">{r.balance.independent_sources}</span>, sortValue: (r) => r.balance.independent_sources, align: "right", className: "w-20" },
    { key: "support", header: "Topic signals", cell: (r) => <span className="text-xs tabular-nums">{r.balance.supporting}</span>, sortValue: (r) => r.balance.supporting, align: "right", className: "w-20" },
    {
      key: "contra",
      header: "Contra.",
      cell: (r) => <span className={r.balance.contradicting > 0 ? "text-xs tabular-nums text-amber-700" : "text-xs tabular-nums text-slate-400"}>{r.balance.contradicting}</span>,
      sortValue: (r) => r.balance.contradicting,
      align: "right",
      className: "w-16",
    },
    { key: "balance", header: "Balance", cell: (r) => <BalanceBar balance={r.balance} showCounts={false} />, className: "w-24" },
    { key: "updated", header: "Updated", cell: (r) => <span className="whitespace-nowrap text-xs text-slate-500">{formatDate(r.finding.updated_at)}</span>, sortValue: (r) => r.finding.updated_at, className: "w-28" },
  ];

  return (
    <div>
      <PageHeader title="Customer feedback themes" question="Which broad topics appear in US G60 feedback? Counts show extracted signals, not verified support for each proposal." />
      <FilterBar active={active} onClearAll={() => setFilters(DEFAULTS)} resultLabel={`${filtered.length} of ${rows.length} findings`}>
        <Select label="Topic" value={filters.topic} onValueChange={(v) => setFilters((f) => ({ ...f, topic: v }))} options={[{ value: "all", label: "All" }, ...topics.map((t) => ({ value: t, label: TOPIC_LABEL[t] ?? t }))]} />
        <Select label="Market" value={filters.market} onValueChange={(v) => setFilters((f) => ({ ...f, market: v }))} options={[{ value: "all", label: "All" }, ...MARKETS.map((m) => ({ value: m, label: MARKET_LABEL[m] }))]} />
      </FilterBar>
      <DataTable
        caption="Findings"
        rows={filtered}
        columns={columns}
        getRowId={(r) => r.id}
        selectedId={selectedId}
        onRowClick={(r) => select(r.id)}
        defaultSort={{ key: "sources", direction: "desc" }}
        empty={
          <EmptyState
            title="No finding matches these filters."
            detail={`Filters: ${active.map((a) => a.label).join(" + ")}.`}
            action={
              <Button size="sm" onClick={() => setFilters(DEFAULTS)}>
                Clear filters
              </Button>
            }
          />
        }
      />
      <SidePanel
        open={Boolean(selected)}
        onOpenChange={(o) => !o && select(null)}
        title={selected?.finding.title ?? ""}
        eyebrow="Finding"
        width="w-[min(620px,100vw)]"
        footer={
          selected && (
            <>
              <Button variant="primary" asChild>
                <Link href={`/evidence?topic=${selected.finding.topic}&market=${selected.finding.market}`}>Review evidence</Link>
              </Button>
              {selected.finding.requirement_ids[0] && (
                <Button asChild>
                  <Link href={`/requirements/${selected.finding.requirement_ids[0]}`}>Open requirement</Link>
                </Button>
              )}
            </>
          )
        }
      >
        {selected && <FindingDetail row={selected} />}
      </SidePanel>
    </div>
  );
}
