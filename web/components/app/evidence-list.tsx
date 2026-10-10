"use client";

import { useState } from "react";

import { ProvenanceBadge, QualityValue, SourceFamilyBadge } from "@/components/app/badges";
import { useEvidencePanel } from "@/components/app/shell";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import type { EvidenceLinkJudgment } from "@/lib/domain/contracts";
import type { EvidenceItem } from "@/lib/domain/model";
import { useStore } from "@/lib/store";
import { cn } from "@/lib/utils";

export interface EvidenceListEntry {
  evidence: EvidenceItem;
  note?: string;
}

/** Strongest first: external before feedback, then by quality. */
export function rankEvidence(entries: EvidenceListEntry[]) {
  return [...entries].sort((a, b) => {
    if (a.evidence.duplicate_of && !b.evidence.duplicate_of) return 1;
    if (!a.evidence.duplicate_of && b.evidence.duplicate_of) return -1;
    const anchor = (e: EvidenceListEntry) => (e.evidence.provenance === "bmw_record" ? 1 : 0);
    if (anchor(a) !== anchor(b)) return anchor(b) - anchor(a);
    return (b.evidence.quality ?? 40) - (a.evidence.quality ?? 40);
  });
}

export function EvidenceList({
  entries,
  initial = 4,
  empty,
  tone = "neutral",
  selectable,
  assess,
}: {
  entries: EvidenceListEntry[];
  initial?: number;
  empty: string;
  tone?: "support" | "contradict" | "neutral";
  selectable?: { selected: Set<string>; onToggle: (id: string) => void; label: string };
  /** Enables the human evidence-link assessment for one requirement revision. */
  assess?: { displayId: string; judgments: Map<string, EvidenceLinkJudgment> };
}) {
  const panel = useEvidencePanel();
  const [expanded, setExpanded] = useState(false);
  const ranked = rankEvidence(entries);
  const visible = expanded ? ranked : ranked.slice(0, initial);

  if (entries.length === 0) {
    return <p className="rounded-md border border-dashed border-slate-200 px-3 py-3 text-xs text-slate-500">{empty}</p>;
  }

  return (
    <div>
      <ul className={cn("divide-y divide-slate-100 rounded-md border bg-white", tone === "contradict" ? "border-amber-200/70" : "border-slate-200/60")}>
        {visible.map(({ evidence, note }) => {
          const excluded = selectable?.selected.has(evidence.id);
          return (
            <li key={evidence.id} className={cn("flex items-start gap-2 px-3 py-2", excluded && "bg-slate-50 opacity-60")}>
              {selectable && (
                <input
                  type="checkbox"
                  className="mt-0.5 size-3.5 accent-zinc-900"
                  checked={Boolean(excluded)}
                  onChange={() => selectable.onToggle(evidence.id)}
                  aria-label={`${selectable.label} ${evidence.id}`}
                />
              )}
              <button
                type="button"
                onClick={() => panel.open(evidence.id)}
                className="min-w-0 flex-1 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/35"
              >
                <span className={cn("block text-xs leading-snug text-zinc-900", excluded && "line-through")}>
                  {evidence.claim}
                  {evidence.numeric_value !== null && !evidence.claim.includes(String(evidence.numeric_value)) && (
                    <span className="ml-1 font-medium tabular-nums">
                      ({evidence.numeric_value} {evidence.numeric_unit})
                    </span>
                  )}
                </span>
                {note && <span className="mt-0.5 block text-2xs text-slate-500">{note}</span>}
                <span className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-2xs text-slate-500">
                  <ProvenanceBadge provenance={evidence.provenance} />
                  <SourceFamilyBadge family={evidence.source_family} />
                  <span className="truncate">{evidence.source_name}</span>
                  <span className="font-mono">{evidence.market}</span>
                  {evidence.duplicate_of && <span className="text-amber-700">duplicate</span>}
                </span>
              </button>
              <div className="flex shrink-0 flex-col items-end gap-1">
                <QualityValue quality={evidence.quality} />
                {assess && <AssessLink displayId={assess.displayId} evidenceId={evidence.id} judgment={assess.judgments.get(evidence.id)} />}
              </div>
            </li>
          );
        })}
      </ul>
      {ranked.length > initial && (
        <Button variant="ghost" size="sm" className="mt-1" onClick={() => setExpanded((e) => !e)} aria-expanded={expanded}>
          {expanded ? "Show fewer" : `Show all ${ranked.length}`}
        </Button>
      )}
    </div>
  );
}

const VERDICTS: { value: EvidenceLinkJudgment["verdict"]; label: string }[] = [
  { value: "supports", label: "Supports" },
  { value: "does_not_support", label: "Does not support" },
  { value: "context_only", label: "Context only" },
];

/** Human assessment of one candidate link (EvidenceLinkJudgment). Counts and scores do not change automatically. */
function AssessLink({ displayId, evidenceId, judgment }: { displayId: string; evidenceId: string; judgment: EvidenceLinkJudgment | undefined }) {
  const { judgeLink } = useStore();
  const [open, setOpen] = useState(false);
  const [verdict, setVerdict] = useState<EvidenceLinkJudgment["verdict"]>(judgment?.verdict ?? "supports");
  const [rationale, setRationale] = useState("");
  const label = judgment ? VERDICTS.find((v) => v.value === judgment.verdict)?.label : null;
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          className={cn(
            "rounded-sm px-1 text-2xs leading-4 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/35",
            judgment
              ? judgment.verdict === "supports"
                ? "bg-emerald-50 text-emerald-800"
                : judgment.verdict === "does_not_support"
                  ? "bg-red-50 text-red-800"
                  : "bg-slate-100 text-slate-700"
              : "text-brand hover:underline",
          )}
          aria-label={judgment ? `Assessed: ${label}. Change assessment` : `Assess link ${evidenceId}`}
        >
          {judgment ? label : "Assess"}
        </button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-72 p-3">
        <p className="text-xs font-medium text-zinc-900">Does this record support {displayId}?</p>
        <p className="mt-0.5 text-2xs text-slate-500">An exact span proves where wording came from, not that it supports the outcome.</p>
        <div role="radiogroup" aria-label="Verdict" className="mt-2 grid grid-cols-3 gap-1">
          {VERDICTS.map((v) => (
            <button
              key={v.value}
              type="button"
              role="radio"
              aria-checked={verdict === v.value}
              onClick={() => setVerdict(v.value)}
              className={cn(
                "rounded-sm border px-1 py-1 text-2xs leading-tight focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/35",
                verdict === v.value ? "border-brand bg-brand-soft text-brand" : "border-slate-200 text-slate-600 hover:text-zinc-900",
              )}
            >
              {v.label}
            </button>
          ))}
        </div>
        <textarea
          value={rationale}
          onChange={(e) => setRationale(e.target.value)}
          placeholder="Rationale (required)"
          aria-label="Assessment rationale"
          className="mt-2 min-h-[56px] w-full rounded-md border border-slate-200 px-2 py-1 text-xs focus-visible:border-brand focus-visible:outline-none"
        />
        <div className="mt-2 flex justify-end">
          <Button
            size="sm"
            variant="primary"
            disabled={rationale.trim().length < 5}
            onClick={async () => {
              await judgeLink(displayId, evidenceId, verdict, rationale.trim());
              setRationale("");
              setOpen(false);
            }}
          >
            Save assessment
          </Button>
        </div>
      </PopoverContent>
    </Popover>
  );
}
