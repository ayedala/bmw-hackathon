"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo } from "react";

import { BalanceBar, ConfidenceBadge, DecisionBadge, MarketTag, PriorityBadge, ScoreValue } from "@/components/app/badges";
import { BenchmarkMatrix } from "@/components/app/benchmark-matrix";
import { DataTable, type Column } from "@/components/app/data-table";
import { Metric, MetricStrip, PageHeader, Section } from "@/components/app/layout-parts";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip } from "@/components/ui/tooltip";
import { priorityRank, TOPIC_LABEL } from "@/lib/domain/derive";
import { MARKET_LABEL } from "@/lib/domain/model";
import { useStore } from "@/lib/store";
import { useFindingRows, useRequirementRows, type FindingRow, type RequirementRow } from "@/lib/view";

const EvidenceBalanceChart = dynamic(() => import("@/components/app/charts").then((m) => m.EvidenceBalanceChart), {
  ssr: false,
  loading: () => <Skeleton className="h-48 w-full" />,
});

export function OverviewScreen() {
  const router = useRouter();
  const { dataset, market, challenges, weightsAreDefault } = useStore();
  const rows = useRequirementRows(market);
  const findingRows = useFindingRows();

  const active = rows.filter((r) => r.status !== "rejected");
  const p1 = active.filter((r) => r.priority === "P1");
  const openDecisions = rows.filter((r) => r.status === "under_review" || r.status === "challenged" || r.status === "draft");
  const nonDuplicate = dataset.evidence.filter((e) => !e.duplicate_of);
  const externalGroups = new Set(nonDuplicate.filter((e) => e.kind === "external_claim").map((e) => e.independence_group));
  const feedbackRecords = nonDuplicate.filter((e) => e.kind === "customer_feedback").length;

  const top = useMemo(
    () =>
      [...active]
        .sort((a, b) => priorityRank(a.priority) - priorityRank(b.priority) || (b.score ?? 0) - (a.score ?? 0))
        .slice(0, 6),
    [active],
  );

  const attention = useMemo(() => {
    const items: { key: string; label: string; detail: string; href: string }[] = [];
    for (const r of rows) {
      if (r.status === "challenged") {
        items.push({ key: `${r.id}-c`, label: `${r.id} is challenged`, detail: "Resolve the challenge or record that no change is warranted.", href: `/requirements/${r.id}` });
      } else if (r.priority === "P1" && r.status === "under_review") {
        items.push({ key: `${r.id}-r`, label: `${r.id} awaits a decision`, detail: `P1 in ${MARKET_LABEL[market]}; ${r.balance.contradicting} contradicting records to weigh.`, href: `/requirements/${r.id}` });
      } else if (r.in_scope && r.priority === "Watch" && r.status !== "rejected") {
        items.push({ key: `${r.id}-w`, label: `${r.id} cannot be ranked yet`, detail: "Uncertainty is rated 4/4 — resolve the open question before ranking.", href: `/requirements/${r.id}` });
      }
    }
    const seeds = rows.filter((r) => r.in_scope && r.basis === "seed" && r.status !== "rejected");
    if (seeds.length > 0) {
      items.push({
        key: "seeds",
        label: `${seeds.length} of ${rows.length} priorities are still illustrative seeds`,
        detail: "Rate them before approval; seed ratings are authored assumptions, not PM judgements.",
        href: "/prioritization",
      });
    }
    for (const f of findingRows) {
      const decisive = f.balance.supporting + f.balance.contradicting;
      if (decisive > 0 && f.balance.contradicting / decisive >= 0.35) {
        items.push({ key: f.id, label: `${f.id} is contested`, detail: `${f.balance.supporting} supporting vs ${f.balance.contradicting} contradicting.`, href: `/findings?id=${f.id}` });
      }
    }
    return items.slice(0, 7);
  }, [rows, findingRows, market]);

  const chartData = useMemo(() => {
    const map = new Map<string, { Supporting: number; Contradicting: number; Neutral: number }>();
    const seen = new Set<string>();
    for (const h of dataset.hypotheses) {
      for (const link of h.links) {
        const key = `${link.evidence_id}`;
        if (seen.has(key)) continue;
        seen.add(key);
        const e = dataset.evidence.find((x) => x.id === link.evidence_id);
        if (!e || e.duplicate_of) continue;
        const topic = TOPIC_LABEL[h.topic] ?? h.topic;
        const bucket = map.get(topic) ?? { Supporting: 0, Contradicting: 0, Neutral: 0 };
        if (link.stance === "supports") bucket.Supporting += 1;
        else if (link.stance === "contradicts") bucket.Contradicting += 1;
        else bucket.Neutral += 1;
        map.set(topic, bucket);
      }
    }
    return [...map.entries()].map(([topic, v]) => ({ topic, ...v }));
  }, [dataset.hypotheses, dataset.evidence]);

  const reqColumns: Column<RequirementRow>[] = [
    { key: "priority", header: "Priority", cell: (r) => <PriorityBadge priority={r.priority} />, className: "w-16" },
    {
      key: "title",
      header: "Requirement",
      cell: (r) => (
        <div className="min-w-0">
          <div className="truncate font-medium text-zinc-900">{r.revision.title}</div>
          <div className="font-mono text-2xs text-slate-500">{r.id}</div>
        </div>
      ),
      className: "max-w-[420px]",
    },
    { key: "score", header: "CRPS", cell: (r) => <ScoreValue score={r.score} basis={r.basis} />, align: "right", className: "w-24" },
    { key: "confidence", header: "Confidence", cell: (r) => <ConfidenceBadge confidence={r.confidence} />, className: "w-24" },
    {
      key: "evidence",
      header: "Evidence",
      cell: (r) => (
        <Tooltip content={`${r.balance.supporting} supporting, ${r.balance.contradicting} contradicting, ${r.balance.independent_sources} independent sources linked through findings.`}>
          <span tabIndex={0} className="whitespace-nowrap text-xs tabular-nums text-zinc-700">
            {r.balance.independent_sources} sources
          </span>
        </Tooltip>
      ),
      className: "w-24",
    },
    { key: "market", header: "Market", cell: () => <MarketTag market={market} />, className: "w-14" },
    { key: "status", header: "Status", cell: (r) => <DecisionBadge status={r.status} />, className: "w-28" },
  ];

  const findingColumns: Column<FindingRow>[] = [
    {
      key: "finding",
      header: "Finding",
      cell: (f) => <span className="line-clamp-1 font-medium text-zinc-900">{f.finding.title}</span>,
      className: "max-w-[380px]",
    },
    { key: "topic", header: "Topic", cell: (f) => <span className="text-xs text-slate-600">{TOPIC_LABEL[f.finding.topic]}</span>, className: "w-24" },
    { key: "signal", header: "Signal", cell: (f) => <BalanceBar balance={f.balance} />, className: "w-40" },
    { key: "confidence", header: "Confidence", cell: (f) => <ConfidenceBadge confidence={f.confidence} />, className: "w-24" },
    { key: "sources", header: "Sources", cell: (f) => <span className="text-xs tabular-nums">{f.balance.independent_sources}</span>, align: "right", className: "w-16" },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        title={`${dataset.vehicle.family} (${dataset.vehicle.generation}) — successor requirements`}
        question="What needs my attention before the next requirement gate?"
        meta={
          <>
            <span>
              Market <span className="text-zinc-900">{MARKET_LABEL[market]}</span>
            </span>
            <span>
              Planning window <span className="text-zinc-900">{dataset.planning.window}</span>
            </span>
            <span>
              Proposal set <span className="font-mono text-2xs text-zinc-900">{dataset.planning.version}</span>
            </span>
            <span>
              Weights{" "}
              <span className="text-zinc-900">
                {weightsAreDefault ? "default PriorityPolicy" : "custom what-if"}
              </span>
            </span>
          </>
        }
      />

      {market !== dataset.planning.primary_market && (
        <div className="rounded-md border border-slate-200 bg-white px-3 py-2 text-xs text-slate-700" role="status">
          <span className="font-medium text-zinc-900">The successor proposals are curated for the United States.</span> They are not transferred to {MARKET_LABEL[market]} without a
          market-specific review. The Market lens shows which evidence exists for {MARKET_LABEL[market]}.
        </div>
      )}

      <MetricStrip className="grid-cols-3 md:grid-cols-6">
        <Metric label="Active requirements" value={active.length} detail={`${rows.length - active.length} rejected`} href="/requirements" />
        <Metric label="P1 requirements" value={p1.length} detail={MARKET_LABEL[market]} href="/prioritization" hint="P1: CRPS ≥70 under the current weights, with uncertainty below 4." />
        <Metric label="Findings" value={dataset.findings.length} href="/findings" />
        <Metric label="Independent sources" value={externalGroups.size} detail={`+${feedbackRecords} feedback IDs`} href="/sources" hint="Distinct external independence groups; reposts of one origin count once." />
        <Metric label="Evidence records" value={dataset.evidence.length} detail={`${dataset.evidence.filter((e) => e.provenance === "pipeline").length} from pipeline`} href="/evidence" />
        <Metric label="Open PM decisions" value={openDecisions.length} detail={challenges.length > 0 ? `${challenges.length} challenge${challenges.length > 1 ? "s" : ""}` : undefined} href="/decisions" />
      </MetricStrip>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_340px]">
        <Section
          title="Top priority requirements"
          description={`Sorted by priority, then CRPS under the current weights · ${MARKET_LABEL[market]}.`}
          actions={
            <Link href="/requirements" className="text-xs text-slate-600 hover:text-zinc-900">
              All requirements
            </Link>
          }
        >
          <DataTable
            caption="Top priority requirements"
            rows={top}
            columns={reqColumns}
            getRowId={(r) => r.id}
            onRowClick={(r) => router.push(`/requirements/${r.id}`)}
          />
        </Section>
        <Section title="Needs attention" description="Decisions waiting, contested findings, unrankable items.">
          {attention.length === 0 ? (
            <p className="rounded-md border border-dashed border-slate-200 bg-white px-3 py-4 text-xs text-slate-500">
              Nothing is waiting on you in {MARKET_LABEL[market]}.
            </p>
          ) : (
            <ul className="divide-y divide-slate-100 rounded-md border border-slate-200/60 bg-white">
              {attention.map((a) => (
                <li key={a.key}>
                  <Link href={a.href} className="block px-3 py-2 hover:bg-slate-50 focus-visible:bg-slate-50 focus-visible:outline-none">
                    <span className="block text-xs font-medium text-zinc-900">{a.label}</span>
                    <span className="block text-2xs text-slate-500">{a.detail}</span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Section>
      </div>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_420px]">
        <Section
          title="Major customer findings"
          description="Support / contradict / neutral counts are shown together."
          actions={
            <Link href="/findings" className="text-xs text-slate-600 hover:text-zinc-900">
              All findings
            </Link>
          }
        >
          <DataTable
            caption="Major customer findings"
            rows={[...findingRows].sort((a, b) => b.strength - a.strength).slice(0, 6)}
            columns={findingColumns}
            getRowId={(f) => f.id}
            onRowClick={(f) => router.push(`/findings?id=${f.id}`)}
          />
        </Section>
        <Section
          title="Evidence balance by topic"
          description="Where is the evidence one-sided, and where is it contested? Feedback has no observation dates, so no time trend is shown."
        >
          <div className="rounded-md border border-slate-200/60 bg-white p-3">
            <EvidenceBalanceChart data={chartData} />
            <div className="mt-1 flex gap-4 text-2xs text-slate-500">
              <span className="inline-flex items-center gap-1">
                <span aria-hidden className="size-2 rounded-sm bg-zinc-800" /> Supporting
              </span>
              <span className="inline-flex items-center gap-1">
                <span aria-hidden className="size-2 rounded-sm bg-amber-500" /> Contradicting
              </span>
              <span className="inline-flex items-center gap-1">
                <span aria-hidden className="size-2 rounded-sm bg-slate-300" /> Neutral
              </span>
            </div>
          </div>
        </Section>
      </div>

      <Section
        title="Competitive position"
        description="BMW i5 against the premium BEV cohort. A dash is an evidence gap, not parity — collect matched evidence before rating the competitive criterion."
      >
        <BenchmarkMatrix rows={dataset.benchmark} />
      </Section>
    </div>
  );
}
