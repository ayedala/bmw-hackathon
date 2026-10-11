"use client";

import { Download } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo } from "react";

import { DecisionBadge, PriorityBadge, ScoreValue } from "@/components/app/badges";
import { DataTable, type Column } from "@/components/app/data-table";
import { EmptyState, FilterBar, PageHeader, Section } from "@/components/app/layout-parts";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { buildDecisionBrief } from "@/lib/brief";
import { formatDateTime, humanize } from "@/lib/domain/derive";
import { MARKET_LABEL } from "@/lib/domain/model";
import { usePersistentState, useStore } from "@/lib/store";
import { useRequirementRows, type RequirementRow } from "@/lib/view";
import { CanonicalDecisionsScreen } from "./canonical-decisions";

export function DecisionsScreen() {
  const { dataset } = useStore();
  if (dataset.mode !== "demo") return <CanonicalDecisionsScreen />;
  return <DemoDecisionsScreen />;
}

function DemoDecisionsScreen() {
  const router = useRouter();
  const { dataset, market, challenges, policy, judgments, actorId, logAction } = useStore();
  const usRows = useRequirementRows(dataset.planning.primary_market);

  const exportBrief = async () => {
    const markdown = buildDecisionBrief(dataset, usRows, policy, judgments, actorId);
    const blob = new Blob([markdown], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `bmw-successor-decision-brief-${new Date().toISOString().slice(0, 10)}.md`;
    a.click();
    URL.revokeObjectURL(url);
    await logAction("download_planning_export", "decision_brief", dataset.planning.version, `Exported a Markdown decision brief for ${usRows.length} US proposals.`);
  };
  const rows = useRequirementRows(market);
  const [view, setView] = usePersistentState<string>("decisions", "open");

  const filtered = useMemo(
    () =>
      rows.filter((r) => {
        const open = r.status === "under_review" || r.status === "challenged" || r.status === "draft";
        return view === "all" || (view === "open" ? open : !open);
      }),
    [rows, view],
  );

  const columns: Column<RequirementRow>[] = [
    { key: "priority", header: "Priority", cell: (r) => <PriorityBadge priority={r.priority} />, className: "w-16" },
    {
      key: "title",
      header: "Requirement",
      cell: (r) => (
        <div className="min-w-0">
          <div className="line-clamp-1 font-medium text-zinc-900">{r.revision.title}</div>
          <div className="font-mono text-2xs text-slate-500">
            {r.id} r{r.revision.revision}
          </div>
        </div>
      ),
      className: "min-w-[280px] max-w-[440px]",
    },
    { key: "crps", header: "Legacy score", cell: (r) => <ScoreValue score={r.score} basis={r.basis} />, sortValue: (r) => r.score ?? -1, align: "right", className: "w-20" },
    { key: "status", header: "Status", cell: (r) => <DecisionBadge status={r.status} />, sortValue: (r) => r.status, className: "w-28" },
    {
      key: "last",
      header: "Last decision",
      cell: (r) => {
        const d = r.bundle.decisions[r.bundle.decisions.length - 1];
        if (!d) return <span className="text-xs text-slate-400">No decision recorded</span>;
        return (
          <span className="text-xs leading-snug text-slate-700">
            <span className="font-medium text-zinc-900">{humanize(d.action)}</span> · {d.actor_id} · {formatDateTime(d.recorded_at)}
            <span className="mt-0.5 line-clamp-2 block text-slate-500">{d.rationale}</span>
          </span>
        );
      },
      className: "min-w-[320px]",
    },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        title="Decisions"
        question={`Which requirements still need a PM decision in ${MARKET_LABEL[market]}?`}
        actions={
          <Button variant="primary" onClick={exportBrief}>
            <Download /> Export decision brief
          </Button>
        }
      />
      <div>
        <FilterBar active={[]} onClearAll={() => setView("open")} resultLabel={`${filtered.length} requirements`}>
          <Select
            label="Show"
            value={view === "open" ? "open" : view}
            onValueChange={setView}
            options={[
              { value: "open", label: "Open decisions" },
              { value: "decided", label: "Decided" },
              { value: "all", label: "All" },
            ]}
          />
        </FilterBar>
        <DataTable
          caption="PM decisions"
          rows={filtered}
          columns={columns}
          getRowId={(r) => r.id}
          onRowClick={(r) => router.push(`/requirements/${r.id}`)}
          defaultSort={{ key: "crps", direction: "desc" }}
          empty={<EmptyState title={view === "open" ? "No open decisions. Every requirement has an approve, reject or defer on its latest revision." : "No requirements in this view."} />}
        />
      </div>
      <Section title="Challenges" description="Recorded in this browser session.">
        {challenges.length === 0 ? (
          <EmptyState title="No challenges recorded yet." detail="Open a requirement and use Challenge to dispute a premise or score input." />
        ) : (
          <ul className="divide-y divide-slate-100 rounded-md border border-slate-200/60 bg-white">
            {[...challenges].reverse().map((c) => (
              <li key={c.challenge_id} className="grid grid-cols-[96px_110px_minmax(0,1fr)_160px] items-start gap-3 px-3 py-2 text-xs">
                <span className="font-mono text-2xs text-slate-500">{c.challenge_id}</span>
                <Link href={`/requirements/${c.display_id}`} className="font-mono text-2xs text-zinc-900 hover:underline">
                  {c.display_id}
                </Link>
                <span className="text-zinc-900">{c.statement}</span>
                <span className="text-right tabular-nums text-slate-600">
                  Legacy score {c.score_before.toFixed(1)} → <span className="font-medium text-zinc-900">{c.score_after.toFixed(1)}</span>
                </span>
              </li>
            ))}
          </ul>
        )}
      </Section>
    </div>
  );
}
