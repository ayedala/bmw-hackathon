"use client";

import { RotateCcw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Tooltip } from "@/components/ui/tooltip";
import type { PriorityAssessment, PriorityFactors, PriorityPolicy } from "@/lib/domain/contracts";
import { FACTOR_HINT, FACTOR_LABEL, formatDateTime } from "@/lib/domain/derive";
import { PRIORITY_FORMULA, priorityContributions, priorityScore } from "@/lib/domain/scoring";
import { DEFAULT_WEIGHTS, useStore } from "@/lib/store";
import { cn } from "@/lib/utils";

export const FACTOR_KEYS: (keyof PriorityFactors)[] = ["impact", "evidence", "relevance", "uncertainty"];

export const factorLabel = (key: string) => FACTOR_LABEL[key as keyof PriorityFactors] ?? key;

/** Contribution bar: share of the factor's maximum possible points. */
function ContributionBar({ points, max }: { points: number; max: number }) {
  const pct = max <= 0 ? 0 : Math.min(100, (points / max) * 100);
  return (
    <svg aria-hidden viewBox="0 0 100 4" preserveAspectRatio="none" className="h-1 w-full overflow-hidden rounded-full bg-slate-100">
      <rect x="0" y="0" width={pct} height="4" className="fill-brand" />
    </svg>
  );
}

function Pips({ value, inverted }: { value: number; inverted?: boolean }) {
  return (
    <span aria-hidden className="inline-flex gap-0.5">
      {[0, 1, 2, 3].map((i) => (
        <span key={i} className={cn("h-2 w-1.5 rounded-[1px]", i < value ? (inverted ? "bg-amber-500" : "bg-zinc-800") : "bg-slate-200")} />
      ))}
    </span>
  );
}

export function PriorityBreakdown({
  factors,
  policy,
  basis,
  assessment,
  compact = false,
}: {
  factors: PriorityFactors;
  policy: PriorityPolicy;
  basis: "saved" | "seed";
  assessment: PriorityAssessment | null;
  compact?: boolean;
}) {
  const score = priorityScore(factors, policy);
  const contributions = priorityContributions(factors, policy);
  return (
    <div>
      <div className="flex items-baseline justify-between">
        <div className="text-2xs font-medium uppercase tracking-wide text-slate-500">Legacy planning score</div>
        <div className={cn("text-2xs", basis === "saved" ? "text-brand" : "text-slate-500")}>{basis === "saved" ? "Saved PM assessment" : "Illustrative seed rating"}</div>
      </div>
      <div className="mt-0.5 flex items-baseline gap-2">
        <span className="text-[28px] font-semibold leading-none tabular-nums tracking-tight text-zinc-950">{score.toFixed(1)}</span>
        <span className="text-xs text-slate-500">/ 100</span>
      </div>

      <table className="mt-3 w-full text-xs">
        <caption className="sr-only">Factor ratings, weights and contributions</caption>
        <thead>
          <tr className="text-2xs uppercase tracking-wide text-slate-500">
            <th scope="col" className="pb-1 text-left font-medium">Factor</th>
            <th scope="col" className="pb-1 text-right font-medium">Rating</th>
            <th scope="col" className="pb-1 text-right font-medium">Wt</th>
            <th scope="col" className="pb-1 text-right font-medium">Pts</th>
          </tr>
        </thead>
        <tbody>
          {FACTOR_KEYS.map((key) => (
            <tr key={key} className="align-top">
              <td className="pt-2 text-zinc-800">
                <Tooltip content={FACTOR_HINT[key]}>
                  <span tabIndex={0} className="cursor-help underline decoration-slate-300 decoration-dotted underline-offset-2 focus-visible:outline-none">
                    {FACTOR_LABEL[key]}
                  </span>
                </Tooltip>
                {key === "uncertainty" && <span className="ml-1 text-2xs text-amber-700">counts against</span>}
                <div className="mt-1 pr-3">
                  <ContributionBar points={contributions[key]} max={100 * policy[key]} />
                </div>
              </td>
              <td className="pt-2 text-right">
                <span className="inline-flex items-center gap-1.5 tabular-nums text-zinc-900">
                  <Pips value={factors[key]} inverted={key === "uncertainty"} />
                  {factors[key]}
                </span>
              </td>
              <td className="pt-2 text-right tabular-nums text-slate-500">{policy[key].toFixed(2)}</td>
              <td className="pt-2 text-right font-medium tabular-nums text-zinc-900">{contributions[key].toFixed(1)}</td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr className="border-t border-slate-200">
            <td className="pt-2 font-medium text-zinc-900">Total</td>
            <td />
            <td className="pt-2 text-right tabular-nums text-slate-500">1.00</td>
            <td className="pt-2 text-right font-semibold tabular-nums text-zinc-950">{score.toFixed(1)}</td>
          </tr>
        </tfoot>
      </table>
      {!compact && (
        <p className="mt-2 text-2xs leading-relaxed text-slate-500">
          {PRIORITY_FORMULA}. Ratings are declared PM judgements 0–4, not measured prevalence or calibrated confidence.
          {assessment && (
            <span className="mt-1 block">
              Assessment #{assessment.sequence} by {assessment.actor_id}, {formatDateTime(assessment.recorded_at)}: “{assessment.rationale}”
            </span>
          )}
        </p>
      )}
    </div>
  );
}

/** Integer 0–4 segmented control for one factor. */
export function FactorInput({ name, value, onChange, original }: { name: keyof PriorityFactors; value: number; onChange: (v: number) => void; original: number }) {
  return (
    <div className="flex items-center justify-between gap-3 py-1.5">
      <div className="min-w-0">
        <div className="text-xs font-medium text-zinc-900">
          {FACTOR_LABEL[name]}
          {name === "uncertainty" && <span className="ml-1 text-2xs font-normal text-amber-700">counts against</span>}
        </div>
        <div className="truncate text-2xs text-slate-500">{FACTOR_HINT[name]}</div>
      </div>
      <div role="radiogroup" aria-label={FACTOR_LABEL[name]} className="inline-flex shrink-0 rounded-md border border-slate-200 bg-white p-0.5">
        {[0, 1, 2, 3, 4].map((v) => (
          <button
            key={v}
            type="button"
            role="radio"
            aria-checked={value === v}
            onClick={() => onChange(v)}
            className={cn(
              "h-6 w-7 rounded-sm text-xs tabular-nums focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/35",
              value === v ? "bg-brand font-medium text-white" : v === original ? "text-zinc-900 underline decoration-slate-300 underline-offset-2" : "text-slate-500 hover:bg-slate-50 hover:text-zinc-900",
            )}
          >
            {v}
          </button>
        ))}
      </div>
    </div>
  );
}

export function FactorEditor({ factors, original, onChange }: { factors: PriorityFactors; original: PriorityFactors; onChange: (f: PriorityFactors) => void }) {
  return (
    <div className="divide-y divide-slate-100 rounded-md border border-slate-200 px-3">
      {FACTOR_KEYS.map((key) => (
        <FactorInput key={key} name={key} value={factors[key]} original={original[key]} onChange={(v) => onChange({ ...factors, [key]: v })} />
      ))}
    </div>
  );
}

export function ScoreDiff({ before, after }: { before: number; after: number }) {
  const delta = after - before;
  return (
    <div className="flex items-baseline gap-3 tabular-nums">
      <span className="text-sm text-slate-500 line-through decoration-slate-300">{before.toFixed(1)}</span>
      <span aria-hidden className="text-slate-400">→</span>
      <span className="text-lg font-semibold tracking-tight text-zinc-950">{after.toFixed(1)}</span>
      {Math.abs(delta) >= 0.05 && <span className={cn("text-xs", delta < 0 ? "text-amber-700" : "text-zinc-700")}>{`${delta > 0 ? "+" : ""}${delta.toFixed(1)}`}</span>}
    </div>
  );
}

/** What-if weights, shared by every screen. Shown in the open, never hidden in a sidebar. */
export function WeightControls({ dense = false }: { dense?: boolean }) {
  const { weights, setWeights, policy, weightsAreDefault } = useStore();
  return (
    <div>
      <div className="flex items-center justify-between">
        <div className="text-2xs font-medium uppercase tracking-wide text-slate-500">What-if weights</div>
        <Button size="sm" variant="ghost" disabled={weightsAreDefault} onClick={() => setWeights(DEFAULT_WEIGHTS)} aria-label="Reset weights to the default policy">
          <RotateCcw /> Default
        </Button>
      </div>
      <div className={cn("mt-1 grid gap-x-4 gap-y-1.5", dense ? "grid-cols-2" : "grid-cols-1")}>
        {FACTOR_KEYS.map((key) => (
          <label key={key} className="block">
            <span className="flex items-center justify-between text-xs text-zinc-800">
              {FACTOR_LABEL[key]}
              <span className="tabular-nums text-slate-500">{Math.round(policy[key] * 100)}% of total</span>
            </span>
            <input
              type="range"
              min={0}
              max={100}
              step={5}
              value={weights[key]}
              onChange={(e) => setWeights({ ...weights, [key]: Number(e.target.value) })}
              className="mt-0.5 h-1 w-full cursor-pointer accent-brand"
              aria-label={`${FACTOR_LABEL[key]} weight`}
              aria-valuetext={`${weights[key]} relative weight; ${Math.round(policy[key] * 100)} percent of total`}
            />
          </label>
        ))}
      </div>
      <p className="mt-1.5 text-2xs text-slate-500">
        Sliders are relative; displayed shares are normalized to 100%. {weightsAreDefault ? "Default legacy policy (0.35 / 0.25 / 0.25 / 0.15)." : "Custom weights affect legacy planning scores, not framework CRPS assessments."}
      </p>
    </div>
  );
}
