"use client";

import { useEvidencePanel } from "@/components/app/shell";
import { Tooltip } from "@/components/ui/tooltip";
import type { BenchmarkCell, BenchmarkTopic, CompetitorBenchmark } from "@/lib/domain/model";
import { BENCHMARK_TOPICS } from "@/lib/domain/model";
import { cn } from "@/lib/utils";

const POSITION_LABEL = {
  ahead: "Ahead of i5",
  parity: "Parity",
  behind: "Behind i5",
  no_evidence: "No evidence",
} as const;

function Cell({ cell, reference }: { cell: BenchmarkCell; reference: boolean }) {
  const panel = useEvidencePanel();
  const first = cell.evidence_ids[0];
  if (cell.position === "no_evidence") {
    return (
      <span className="text-2xs text-slate-300" aria-label="No matched evidence">
        —
      </span>
    );
  }
  return (
    <div className="min-w-0">
      {!reference && (
        <span
          className={cn(
            "mb-0.5 inline-block rounded-sm px-1 text-2xs font-medium leading-4",
            cell.position === "ahead" && "bg-amber-50 text-amber-800",
            cell.position === "behind" && "bg-slate-100 text-slate-700",
            cell.position === "parity" && "bg-slate-100 text-slate-600",
          )}
        >
          {POSITION_LABEL[cell.position]}
        </span>
      )}
      <Tooltip content={`${cell.evidence_ids.length} linked record${cell.evidence_ids.length === 1 ? "" : "s"}. Click to open the first.`}>
        <button
          type="button"
          disabled={!first}
          onClick={() => first && panel.open(first)}
          className="block text-left text-xs text-zinc-800 hover:underline focus-visible:underline focus-visible:outline-none"
        >
          {cell.summary}
        </button>
      </Tooltip>
    </div>
  );
}

export function BenchmarkMatrix({ rows, topics }: { rows: CompetitorBenchmark[]; topics?: BenchmarkTopic[] }) {
  const columns = BENCHMARK_TOPICS.filter((t) => !topics || topics.includes(t.key));
  return (
    <div className="overflow-x-auto rounded-md border border-slate-200/60 bg-white">
      <table className="w-full border-collapse text-[13px]">
        <caption className="sr-only">Competitive position of BMW i5 versus cohort vehicles by topic</caption>
        <thead>
          <tr className="border-b border-slate-200/70">
            <th scope="col" className="h-8 w-44 px-3 text-left text-2xs font-medium uppercase tracking-wide text-slate-500">
              Vehicle
            </th>
            {columns.map((c) => (
              <th key={c.key} scope="col" className="h-8 px-3 text-left text-2xs font-medium uppercase tracking-wide text-slate-500">
                {c.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.vehicle} className={cn("border-b border-slate-100 last:border-0", row.is_reference && "bg-slate-50/70")}>
              <th scope="row" className="px-3 py-2 text-left text-xs font-medium text-zinc-900">
                {row.vehicle}
                {row.is_reference && <span className="ml-1.5 text-2xs font-normal text-slate-500">reference</span>}
              </th>
              {columns.map((c) => {
                const cell = row.cells[c.key];
                return (
                  <td key={c.key} className="px-3 py-2 align-top">
                    {cell ? <Cell cell={cell} reference={row.is_reference} /> : <span className="text-2xs text-slate-400">—</span>}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
