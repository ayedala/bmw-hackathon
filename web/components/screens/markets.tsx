"use client";

import Link from "next/link";
import { useMemo } from "react";

import { PriorityBadge, ScoreValue } from "@/components/app/badges";
import { EmptyState, PageHeader, Section } from "@/components/app/layout-parts";
import { PROVENANCE_LABEL, TOPIC_LABEL } from "@/lib/domain/derive";
import { MARKETS, MARKET_LABEL, type MarketCode, type Provenance } from "@/lib/domain/model";
import { usePersistentState, useStore } from "@/lib/store";
import { cn } from "@/lib/utils";
import { useRequirementRows } from "@/lib/view";

const PROVENANCES: Provenance[] = ["bmw_record", "pipeline", "curated_seed", "synthetic"];

export function MarketsScreen() {
  const { dataset, market, setMarket } = useStore();
  const usRows = useRequirementRows(dataset.planning.primary_market);
  const [selectedId, setSelectedId] = usePersistentState<string>("markets-req", "REQ-TRP-03");
  const selected = usRows.find((r) => r.id === selectedId) ?? usRows[0];

  const evidenceByMarket = useMemo(() => {
    const out = {} as Record<MarketCode, { total: number; byProvenance: Record<Provenance, number>; topics: Set<string> }>;
    for (const m of MARKETS) out[m] = { total: 0, byProvenance: { bmw_record: 0, pipeline: 0, curated_seed: 0, synthetic: 0 }, topics: new Set() };
    for (const e of dataset.evidence) {
      if (e.duplicate_of) continue;
      const bucket = out[e.market];
      bucket.total += 1;
      bucket.byProvenance[e.provenance] += 1;
      bucket.topics.add(e.topic);
    }
    return out;
  }, [dataset.evidence]);

  if (!selected) return <EmptyState title="No successor proposals are loaded." detail="configs/successor_proposals_v1.json is missing or empty." />;
  const th = "h-8 px-3 text-2xs font-medium uppercase tracking-wide text-slate-500";

  return (
    <div className="space-y-6">
      <PageHeader
        title="Market lens"
        question="Where is each requirement assessed, and what would it take to assess another market?"
        meta={
          <span>
            Proposals are authored for the US 5 Series and, as in <span className="font-mono text-2xs">proposal_for()</span>, never transferred to another market without its own
            review. Uncovered by feedback: {dataset.profile.uncovered_regions.join(", ") || "none"}.
          </span>
        }
      />

      <Section title="Evidence available by market" description="Duplicates excluded. A market needs its own customer evidence before a requirement can be scored there.">
        <div className="overflow-x-auto rounded-md border border-slate-200 bg-white">
          <table className="w-full text-[13px]">
            <caption className="sr-only">Evidence records per market and provenance</caption>
            <thead>
              <tr className="border-b border-slate-200">
                <th scope="col" className={cn(th, "text-left")}>Market</th>
                {PROVENANCES.map((p) => (
                  <th key={p} scope="col" className={cn(th, "text-right")}>
                    {PROVENANCE_LABEL[p]}
                  </th>
                ))}
                <th scope="col" className={cn(th, "text-right")}>Total</th>
                <th scope="col" className={cn(th, "text-left")}>Topics</th>
                <th scope="col" className={cn(th, "text-left")}>Status</th>
              </tr>
            </thead>
            <tbody>
              {MARKETS.map((m) => {
                const b = evidenceByMarket[m];
                const primary = m === dataset.planning.primary_market;
                return (
                  <tr key={m} className={cn("border-b border-slate-100 last:border-0", m === market && "bg-brand-soft/60")}>
                    <th scope="row" className="whitespace-nowrap px-3 py-1.5 text-left font-normal">
                      <button type="button" onClick={() => setMarket(m)} className="hover:text-brand focus-visible:text-brand focus-visible:outline-none">
                        <span className="font-mono text-2xs font-medium text-slate-600">{m}</span> <span className="ml-1 text-xs text-zinc-900">{MARKET_LABEL[m]}</span>
                      </button>
                    </th>
                    {PROVENANCES.map((p) => (
                      <td key={p} className={cn("px-3 py-1.5 text-right text-xs tabular-nums", b.byProvenance[p] === 0 ? "text-slate-300" : "text-zinc-900")}>
                        {b.byProvenance[p]}
                      </td>
                    ))}
                    <td className="px-3 py-1.5 text-right text-xs font-medium tabular-nums text-zinc-900">{b.total}</td>
                    <td className="px-3 py-1.5 text-xs text-slate-600">{[...b.topics].map((t) => TOPIC_LABEL[t] ?? t).join(", ") || "—"}</td>
                    <td className="whitespace-nowrap px-3 py-1.5 text-xs">
                      {primary ? <span className="font-medium text-brand">Assessed · {usRows.length} proposals</span> : <span className="text-slate-500">Context only</span>}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Section>

      <Section title="Requirement × market" description="Only the authored market carries a CRPS. Click a requirement to see what each other market has.">
        <div className="overflow-x-auto rounded-md border border-slate-200 bg-white">
          <table className="w-full text-[13px]">
            <caption className="sr-only">CRPS per requirement and market</caption>
            <thead>
              <tr className="border-b border-slate-200">
                <th scope="col" className={cn(th, "text-left")}>Requirement</th>
                {MARKETS.map((m) => (
                  <th key={m} scope="col" className={cn(th, "w-36 text-right", m === market && "text-brand")}>
                    {MARKET_LABEL[m]}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {usRows.map((r) => (
                <tr key={r.id} className={cn("border-b border-slate-100 last:border-0", r.id === selected.id && "bg-brand-soft/60")}>
                  <th scope="row" className="px-3 py-1.5 text-left font-normal">
                    <button type="button" onClick={() => setSelectedId(r.id)} className="text-left hover:text-brand focus-visible:text-brand focus-visible:outline-none">
                      <span className="mr-2 font-mono text-2xs text-slate-500">{r.id}</span>
                      <span className="text-xs text-zinc-900">{r.revision.title}</span>
                    </button>
                  </th>
                  {MARKETS.map((m) => {
                    const scoped = r.bundle.scope_markets.includes(m);
                    return (
                      <td key={m} className={cn("px-3 py-1.5 text-right", m === market && "bg-slate-50/80")}>
                        {scoped ? (
                          <span className="inline-flex items-center gap-2">
                            <ScoreValue score={r.score} basis={r.basis} />
                            <PriorityBadge priority={r.priority} />
                          </span>
                        ) : (
                          <span className="text-2xs text-slate-400">Not transferred</span>
                        )}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>

      <Section
        title={`What exists outside the US · ${selected.id}`}
        description={selected.revision.title}
        actions={
          <Link href={`/requirements/${selected.id}`} className="text-xs text-brand hover:underline">
            Open workspace
          </Link>
        }
      >
        <ul className="grid gap-3 md:grid-cols-3">
          {MARKETS.filter((m) => m !== dataset.planning.primary_market).map((m) => (
            <li key={m} className="rounded-md border border-slate-200 bg-white p-3">
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium text-zinc-900">{MARKET_LABEL[m]}</span>
                <span className="text-2xs text-slate-500">{evidenceByMarket[m].total} records</span>
              </div>
              <p className="mt-1 text-xs leading-relaxed text-slate-600">{selected.bundle.market_context[m] ?? "No market-specific evidence is linked."}</p>
              <p className="mt-2 text-2xs text-slate-500">To assess: market-scoped customer feedback, a confirmed vehicle/trim mapping and a PM-approved market objective.</p>
            </li>
          ))}
        </ul>
      </Section>
    </div>
  );
}
