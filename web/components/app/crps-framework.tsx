"use client";

import { useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  CRPS_WEIGHTS, EVIDENCE_WEIGHTS, emptyCrpsInputs, evaluateCrps,
  type CrpsDimension, type CrpsInputs, type CrpsRating, type EvidenceDimension,
} from "@/lib/domain/crps";
import { useStore } from "@/lib/store";

const LABELS: Record<CrpsDimension | EvidenceDimension, string> = {
  customer_impact: "Customer impact", frequency: "Frequency in an eligible population",
  market_relevance: "Market relevance", competitive_gap: "Competitive gap",
  future_relevance: "Future relevance", strategic_fit: "Strategic fit",
  source_quality: "Source quality", source_diversity: "Independent source families",
  consistency: "Consistency and contradiction", volume: "Relevant evidence volume",
  recency: "Source recency",
};

const PRIMARY = Object.keys(CRPS_WEIGHTS).filter((key) => key !== "evidence_strength") as CrpsDimension[];
const EVIDENCE = Object.keys(EVIDENCE_WEIGHTS) as EvidenceDimension[];

export function CrpsFrameworkPanel({ displayId, requirementId, revision, inScope }: {
  displayId: string; requirementId: string; revision: number; inScope: boolean;
}) {
  const { actorId, setActorId, crpsAssessments, saveCrpsAssessment } = useStore();
  const history = (crpsAssessments[displayId] ?? []).filter((item) => item.requirement_revision === revision);
  const latest = history.at(-1) ?? null;
  const [inputs, setInputs] = useState<CrpsInputs>(emptyCrpsInputs);
  const [rationale, setRationale] = useState("");
  const [error, setError] = useState("");
  const [saved, setSaved] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setInputs(latest ? structuredClone(latest.inputs) : emptyCrpsInputs());
    setRationale("");
    setError("");
    setSaved("");
    // A new saved snapshot or requirement revision starts a new editable draft.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [displayId, revision, latest?.assessment_id]);

  const preview = useMemo(() => {
    try { return evaluateCrps(inputs); } catch { return null; }
  }, [inputs]);

  const update = (key: CrpsDimension | EvidenceDimension, evidence: boolean, rating: CrpsRating) => {
    setInputs((previous) => evidence
      ? { ...previous, evidence: { ...previous.evidence, [key]: rating } }
      : { ...previous, [key]: rating });
    setError(""); setSaved("");
  };

  const row = (key: CrpsDimension | EvidenceDimension, weight: number, evidence: boolean) => {
    const rating = evidence ? inputs.evidence[key as EvidenceDimension] : inputs[key as CrpsDimension];
    return (
      <div key={key} className="grid gap-2 border-t border-slate-100 py-3 md:grid-cols-[minmax(130px,1fr)_86px_145px]">
        <div>
          <div className="text-xs font-medium text-zinc-900">{LABELS[key]}</div>
          <div className="text-2xs text-slate-500">{Math.round(weight * 100)}% of {evidence ? "evidence strength" : "customer priority"}</div>
        </div>
        <label className="text-2xs text-slate-500">Score /100
          <input type="number" min="0" max="100" step="1" value={rating.value ?? ""}
            aria-label={`${LABELS[key]} score`} placeholder="Unknown"
            onChange={(event) => {
              const raw = event.target.value;
              update(key, evidence, raw === "" ? { value: null, basis: "missing", explanation: "", evidence_ids: [] }
                : { ...rating, value: Number(raw), basis: rating.basis === "missing" ? key === "frequency" ? "source_review" : "reviewer_judgment" : rating.basis });
            }}
            className="mt-1 w-full rounded border border-slate-200 px-2 py-1 text-xs text-zinc-900" />
        </label>
        <label className="text-2xs text-slate-500">Basis
          <select value={rating.basis} disabled={rating.value === null}
            aria-label={`${LABELS[key]} basis`}
            onChange={(event) => update(key, evidence, { ...rating, basis: event.target.value as CrpsRating["basis"] })}
            className="mt-1 w-full rounded border border-slate-200 bg-white px-2 py-1 text-xs text-zinc-900">
            <option value="missing">Missing</option>
            {key !== "frequency" && <option value="reviewer_judgment">Reviewer judgment</option>}
            <option value="source_review">Source review</option>
          </select>
        </label>
        {rating.value !== null && (
          <div className="md:col-span-3 grid gap-2 md:grid-cols-2">
            <div className="md:col-span-2 flex items-center gap-3">
              <span className="w-8 text-right font-mono text-2xs text-slate-500">0</span>
              <input type="range" min="0" max="100" step="1" value={rating.value} aria-label={`${LABELS[key]} slider`}
                onChange={(event) => update(key, evidence, { ...rating, value: Number(event.target.value) })}
                className="h-2 w-full cursor-pointer accent-brand" />
              <span className="w-8 font-mono text-2xs text-slate-500">100</span>
            </div>
            <label className="text-2xs text-slate-500">Why this score?
              <input value={rating.explanation} onChange={(event) => update(key, evidence, { ...rating, explanation: event.target.value })}
                aria-label={`${LABELS[key]} explanation`} placeholder="Explain the rating and its limits"
                className="mt-1 w-full rounded border border-slate-200 px-2 py-1 text-xs text-zinc-900" />
            </label>
            <label className="text-2xs text-slate-500">Source IDs or URLs {rating.basis === "source_review" ? "(required)" : "(optional)"}
              <input value={rating.evidence_ids.join(", ")} onChange={(event) => update(key, evidence,
                { ...rating, evidence_ids: event.target.value.split(",").map((part) => part.trim()).filter(Boolean) })}
                aria-label={`${LABELS[key]} source IDs`} placeholder="Separate references with commas"
                className="mt-1 w-full rounded border border-slate-200 px-2 py-1 text-xs text-zinc-900" />
            </label>
          </div>
        )}
      </div>
    );
  };

  if (!inScope) return <p className="text-xs text-slate-600">This requirement needs a market-specific review before a CRPS assessment can be saved here.</p>;

  const interval = preview?.customer_priority;
  return (
    <div className="space-y-4 text-xs">
      <p className="text-slate-600">The seven-factor framework is a new assessment. Existing four-factor scores remain historical planning estimates. Leave unsupported inputs blank; missing weights stay in the range instead of becoming zero or being redistributed.</p>
      <div className="grid gap-3 rounded-md border border-slate-200 bg-slate-50 p-3 sm:grid-cols-3">
        <div><div className="text-2xs uppercase text-slate-500">Framework CRPS</div>
          <strong className="text-lg tabular-nums text-zinc-900">{interval ? interval.value === null ? `${interval.lower.toFixed(1)}–${interval.upper.toFixed(1)}` : interval.value.toFixed(1) : "Complete input notes"}</strong></div>
        <div><div className="text-2xs uppercase text-slate-500">Priority band</div>
          <strong className="text-sm text-zinc-900">{preview?.priority_band ?? "Undetermined"}</strong></div>
        <div><div className="text-2xs uppercase text-slate-500">Evidence strength</div>
          <strong className="text-sm tabular-nums text-zinc-900">{preview ? preview.evidence_strength.value?.toFixed(1) ?? `${preview.evidence_strength.lower.toFixed(1)}–${preview.evidence_strength.upper.toFixed(1)}` : "Unknown"}</strong></div>
      </div>
      <p className="text-2xs text-slate-600">The PDF weights are a proposed policy, not a validated BMW policy. Frequency needs a representative eligible population, requirement-matched numerator and source reference in its note. No confidence percentage or feasibility multiplier is shown; neither is calibrated for this dataset.</p>
      <div className="rounded-md border border-slate-200 px-3">
        {PRIMARY.map((key) => row(key, CRPS_WEIGHTS[key], false))}
        <details className="border-t border-slate-100 py-3">
          <summary className="cursor-pointer text-xs font-medium text-zinc-900">Evidence strength inputs (20% of CRPS)</summary>
          <p className="mt-2 text-2xs text-slate-600">Rate source quality, independent families, consistency, volume and recency separately. A large number of comments from one source is still one source family. Contradiction affects consistency; it does not automatically reduce customer impact.</p>
          {EVIDENCE.map((key) => row(key, EVIDENCE_WEIGHTS[key], true))}
        </details>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="text-2xs text-slate-500">Indicative feasibility (kept separate)
          <select value={inputs.feasibility} onChange={(event) => setInputs({ ...inputs, feasibility: event.target.value as CrpsInputs["feasibility"] })}
            className="mt-1 w-full rounded border border-slate-200 bg-white px-2 py-1 text-xs text-zinc-900">
            {["unknown", "very_high", "high", "medium", "low", "very_low"].map((value) => <option key={value} value={value}>{value.replace("_", " ")}</option>)}
          </select>
        </label>
        <label className="text-2xs text-slate-500">Feasibility basis
          <input value={inputs.feasibility_explanation} onChange={(event) => setInputs({ ...inputs, feasibility_explanation: event.target.value })}
            placeholder="Engineering basis, if known" className="mt-1 w-full rounded border border-slate-200 px-2 py-1 text-xs text-zinc-900" />
        </label>
      </div>
      {preview && preview.missing_inputs.length > 0 && <p className="text-2xs text-amber-800">Missing: {preview.missing_inputs.map((key) => key.replace("evidence.", "evidence / ").replaceAll("_", " ")).join(", ")}. No priority band is assigned until all eleven inputs have a supported rating.</p>}
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="text-2xs text-slate-500">Reviewer ID
          <input value={actorId} onChange={(event) => setActorId(event.target.value)} className="mt-1 w-full rounded border border-slate-200 px-2 py-1 text-xs text-zinc-900" />
        </label>
        <label className="text-2xs text-slate-500">Assessment rationale
          <input value={rationale} onChange={(event) => setRationale(event.target.value)} placeholder="Why save this assessment now?"
            className="mt-1 w-full rounded border border-slate-200 px-2 py-1 text-xs text-zinc-900" />
        </label>
      </div>
      {error && <p role="alert" className="text-xs text-red-700">{error}</p>}
      {saved && <p role="status" className="text-xs text-brand">{saved}</p>}
      <div className="flex flex-wrap items-center gap-3">
        <Button variant="primary" loading={saving} disabled={!preview || !rationale.trim() || !actorId.trim()}
          onClick={async () => {
            setSaving(true);
            try {
              const item = await saveCrpsAssessment(displayId, inputs, rationale);
              setSaved(`Assessment #${item.sequence} saved with ${item.result.missing_inputs.length} missing inputs. Review its source notes before using the result.`);
              setError("");
            } catch (cause) { setError(cause instanceof Error ? cause.message : "Could not save assessment."); }
            finally { setSaving(false); }
          }}>Save framework assessment</Button>
        <span className="text-2xs text-slate-500">{history.length} saved for revision {revision} · {requirementId}</span>
      </div>
      {latest && <p className="text-2xs text-slate-500">Latest snapshot #{latest.sequence} by {latest.actor_id}, {new Date(latest.recorded_at).toLocaleString()}: {latest.rationale}. Stored in this browser session with the audit trail.</p>}
    </div>
  );
}
