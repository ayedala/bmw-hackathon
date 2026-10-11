"use client";

import type { Stance } from "@/lib/domain/contracts";
import {
  CONFIDENCE_RULE,
  DECISION_STATUS_LABEL,
  FAMILY_LABEL,
  HYPOTHESIS_STATUS_LABEL,
  PRIORITY_RULE,
  PROVENANCE_HINT,
  PROVENANCE_LABEL,
  humanize,
  type Balance,
  type Confidence,
  type DecisionStatus,
  type Priority,
} from "@/lib/domain/derive";
import type { HypothesisStatus, Provenance } from "@/lib/domain/model";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Tooltip } from "@/components/ui/tooltip";

export function PriorityBadge({ priority, hint }: { priority: Priority; hint?: string }) {
  const styles: Record<Priority, string> = {
    P1: "bg-zinc-900 text-white",
    P2: "bg-zinc-700 text-white",
    P3: "bg-slate-200 text-zinc-800",
    P4: "bg-slate-100 text-slate-600",
    Watch: "border border-dashed border-slate-300 text-slate-600",
  };
  return (
    <Tooltip content={hint ?? PRIORITY_RULE}>
      <span
        tabIndex={0}
        className={cn(
          "inline-flex h-[18px] min-w-[30px] items-center justify-center rounded-sm px-1 font-mono text-2xs font-semibold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/35",
          styles[priority],
        )}
      >
        {priority}
      </span>
    </Tooltip>
  );
}

export function ConfidenceBadge({ confidence, hint }: { confidence: Confidence; hint?: string }) {
  const dot: Record<Confidence, string> = { High: "bg-zinc-900", Medium: "bg-zinc-400", Low: "bg-white border border-zinc-400" };
  return (
    <Tooltip content={hint ?? CONFIDENCE_RULE}>
      <span tabIndex={0} className="inline-flex items-center gap-1.5 text-xs text-zinc-700 focus-visible:outline-none">
        <span aria-hidden className={cn("size-1.5 rounded-full", dot[confidence])} />
        {confidence}
      </span>
    </Tooltip>
  );
}

export function DecisionBadge({ status }: { status: DecisionStatus }) {
  const tone: Record<DecisionStatus, "neutral" | "outline" | "positive" | "negative" | "caution" | "info"> = {
    draft: "outline",
    under_review: "neutral",
    approved: "positive",
    rejected: "negative",
    challenged: "caution",
    deferred: "outline",
  };
  return <Badge tone={tone[status]}>{DECISION_STATUS_LABEL[status]}</Badge>;
}

export function ProvenanceBadge({ provenance, className }: { provenance: Provenance; className?: string }) {
  return (
    <Tooltip content={PROVENANCE_HINT[provenance]}>
      <span
        tabIndex={0}
        className={cn(
          "inline-flex items-center rounded-sm px-1 text-2xs leading-4 focus-visible:outline-none",
          provenance === "bmw_record" && "bg-brand text-white",
          provenance === "pipeline" && "bg-zinc-900 text-white",
          provenance === "curated_seed" && "border border-zinc-300 text-zinc-700",
          provenance === "synthetic" && "border border-dashed border-slate-300 text-slate-500",
          className,
        )}
      >
        {PROVENANCE_LABEL[provenance]}
      </span>
    </Tooltip>
  );
}

export function SourceFamilyBadge({ family }: { family: string }) {
  return <span className="text-xs text-slate-600">{FAMILY_LABEL[family] ?? humanize(family)}</span>;
}

export function StanceBadge({ stance }: { stance: Stance }) {
  if (stance === "supports") return <Badge tone="neutral">Supports</Badge>;
  if (stance === "contradicts") return <Badge tone="caution">Contradicts</Badge>;
  return <Badge tone="outline">Neutral</Badge>;
}

export function HypothesisStatusBadge({ status }: { status: HypothesisStatus }) {
  const tone = { supported: "solid", contested: "caution", not_supported: "negative", insufficient: "outline" } as const;
  return <Badge tone={tone[status]}>{HYPOTHESIS_STATUS_LABEL[status]}</Badge>;
}

export function MarketTag({ market }: { market: string }) {
  return <span className="font-mono text-2xs font-medium text-slate-600">{market}</span>;
}

export function QualityValue({ quality }: { quality: number | null }) {
  if (quality === null) {
    return (
      <Tooltip content="Supplied-anonymized feedback: author and method unknown, so no quality score is assigned.">
        <span tabIndex={0} className="text-xs text-slate-400">n/a</span>
      </Tooltip>
    );
  }
  return (
    <span className="inline-flex items-center gap-1.5 tabular-nums">
      <span className="text-xs text-zinc-800">{quality}</span>
      <span aria-hidden className="h-1 w-8 overflow-hidden rounded-full bg-slate-100">
        <span className={cn("block h-full bg-zinc-500", qualityWidth(quality))} />
      </span>
    </span>
  );
}

function qualityWidth(q: number) {
  if (q >= 90) return "w-full";
  if (q >= 75) return "w-4/5";
  if (q >= 60) return "w-3/5";
  if (q >= 45) return "w-2/5";
  if (q >= 30) return "w-1/4";
  return "w-1/6";
}

/** Legacy planning score display. Seed (illustrative) ratings are marked; out-of-scope markets show no number. */
export function ScoreValue({ score, basis, className }: { score: number | null; basis?: "saved" | "seed"; className?: string }) {
  if (score === null) {
    return (
      <Tooltip content="This proposal is curated for the US market. It is not transferred to other markets without a market-specific review.">
        <span tabIndex={0} className="whitespace-nowrap text-xs text-slate-400 focus-visible:outline-none">
          Not in scope
        </span>
      </Tooltip>
    );
  }
  return (
    <Tooltip content={basis === "saved" ? "Saved PM assessment, recomputed under the current what-if weights." : "Illustrative seed rating from the successor proposal — not yet confirmed by a PM."}>
      <span tabIndex={0} className={cn("inline-flex items-baseline gap-1 tabular-nums focus-visible:outline-none", className)}>
        <span className="font-semibold text-zinc-900">{score.toFixed(1)}</span>
        {basis === "seed" && <span className="text-2xs font-normal text-slate-400">seed</span>}
        {basis === "saved" && <span className="text-2xs font-normal text-brand">PM</span>}
      </span>
    </Tooltip>
  );
}

/** Horizontal support / contradict / neutral bar. Contradictions are never hidden. */
export function BalanceBar({ balance, showCounts = true, className }: { balance: Balance; showCounts?: boolean; className?: string }) {
  const total = Math.max(balance.total, 1);
  const pct = (n: number) => `${((n / total) * 100).toFixed(1)}%`;
  return (
    <div className={cn("flex items-center gap-2", className)}>
      <svg aria-hidden viewBox="0 0 100 6" preserveAspectRatio="none" className="h-1.5 w-20 shrink-0 overflow-hidden rounded-full bg-slate-100">
        <rect x="0" y="0" height="6" width={(balance.supporting / total) * 100} className="fill-zinc-800" />
        <rect x={(balance.supporting / total) * 100} y="0" height="6" width={(balance.contradicting / total) * 100} className="fill-amber-500" />
      </svg>
      {showCounts && (
        <span className="whitespace-nowrap text-2xs tabular-nums text-slate-500">
          <span className="text-zinc-800">{balance.supporting}</span> / <span className="text-amber-700">{balance.contradicting}</span> /{" "}
          {balance.neutral}
        </span>
      )}
      <span className="sr-only">
        {balance.supporting} same-topic complaint or aspiration spans, {balance.contradicting} opposing, {balance.neutral} praise or other; {pct(balance.supporting)} complaint or aspiration spans
      </span>
    </div>
  );
}
