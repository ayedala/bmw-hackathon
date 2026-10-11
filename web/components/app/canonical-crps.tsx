"use client";

import { useEvidencePanel } from "@/components/app/shell";
import { EmptyState, Section } from "@/components/app/layout-parts";
import { CRPS_FACTOR_LABEL, CRPS_WEIGHTS, type CanonicalCrps, type CrpsFactor, type RequirementQuality } from "@/lib/domain/crps";
import { formatDateTime } from "@/lib/domain/derive";

const number = (value: number) => Number(value.toFixed(2)).toString();

export function CrpsInterval({ score }: { score: CanonicalCrps }) {
  return <span className="whitespace-nowrap font-medium tabular-nums">{number(score.result.crps_100_lower)}{!score.result.is_point && `–${number(score.result.crps_100_upper)}`}<span className="ml-1 text-2xs font-normal text-slate-500">/100</span></span>;
}

/** Display the Python snapshot as-is: never fills unknown factors or recalculates a score. */
export function CanonicalScoreBreakdown({ score }: { score: CanonicalCrps | null | undefined }) {
  const panel = useEvidencePanel();
  if (!score) return <EmptyState title="No authoritative CRPS snapshot available." detail="A missing backend score stays unknown; the legacy four-factor rating is not substituted." />;
  return (
    <Section title="Seven-factor CRPS" description={`Python ${score.result.policy_id} r${score.result.policy_revision} · calculated ${formatDateTime(score.calculated_at)} · ${score.result.approved ? "approved policy" : "unapproved display policy"}`}>
      <div className="overflow-x-auto rounded-md border border-slate-200 bg-white">
        <table className="w-full text-xs">
          <caption className="sr-only">All seven CRPS factors, bounds, weights, contributions and exact evidence references</caption>
          <thead className="border-b border-slate-200 bg-slate-50 text-left text-2xs uppercase tracking-wide text-slate-500"><tr><th className="p-3">Factor</th><th className="p-3">Value /4</th><th className="p-3">Lower–upper /4</th><th className="p-3">Weight</th><th className="p-3">CRPS points</th></tr></thead>
          <tbody>
            {(Object.keys(CRPS_WEIGHTS) as CrpsFactor[]).map((name) => {
              const factor = score.result.factors[name];
              if (!factor) return <tr key={name} className="border-b border-amber-200"><th className="p-3 text-left">{CRPS_FACTOR_LABEL[name]}</th><td colSpan={4} className="p-3 text-amber-800">Factor missing from authoritative snapshot. No value substituted.</td></tr>;
              const ids = score.factor_evidence_ids[name] ?? [];
              return <tr key={name} className="border-b border-slate-100 last:border-0"><td colSpan={5} className="p-0">
                <div className="grid grid-cols-[minmax(150px,1.4fr)_repeat(4,minmax(80px,1fr))] items-start gap-3 px-3 py-3">
                  <span className="font-medium text-zinc-900">{CRPS_FACTOR_LABEL[name]}</span>
                  <span className="tabular-nums">{!factor.known ? "Unknown" : factor.lower_value === factor.upper_value ? number(factor.lower_value) : "Bounded"}</span>
                  <span className="tabular-nums">{number(factor.lower_value)}–{number(factor.upper_value)}</span>
                  <span className="tabular-nums">{number(factor.weight * 100)}%</span>
                  <span className="tabular-nums">{number(factor.lower_contribution * 25)}–{number(factor.upper_contribution * 25)}</span>
                </div>
                <div className="space-y-1 px-3 pb-3 text-slate-600">
                  <p><span className="font-medium text-zinc-800">Basis: </span>{factor.basis || "No supported basis supplied."}</p>
                  {factor.missing_reason && <p className="text-amber-800"><span className="font-medium">Missing: </span>{factor.missing_reason}</p>}
                  <details className="text-2xs"><summary className="cursor-pointer text-brand">Evidence IDs ({ids.length})</summary>{ids.length ? <div className="mt-1 flex flex-wrap gap-1">{ids.map((id) => <button key={id} type="button" onClick={() => panel.open(id)} className="rounded border border-slate-200 px-1.5 py-0.5 font-mono hover:bg-slate-50">{id}</button>)}</div> : <p className="mt-1">No evidence IDs supplied for this factor; read its declared basis or missing reason.</p>}</details>
                </div>
              </td></tr>;
            })}
          </tbody>
        </table>
      </div>
      <p className="mt-2 text-2xs text-slate-500">CRPS = Σ(weight × factor) × 25. Unknown factors retain their weight and a 0–4 interval. Priority is based on the lower bound; feasibility and Decision Confidence are separate.</p>
      <p className="mt-1 text-2xs text-slate-500">{score.result.band_basis}</p>
      <details className="mt-3 rounded-md border border-slate-200 bg-white p-3 text-xs"><summary className="cursor-pointer font-medium">Decision Confidence: {number(score.confidence.value_0_to_100)}/100</summary><p className="mt-2 text-slate-600">{score.confidence.basis}</p><dl className="mt-2 grid grid-cols-2 gap-2">{Object.entries(score.confidence.components).map(([key, value]) => <div key={key}><dt className="text-2xs text-slate-500">{key.replaceAll("_", " ")}</dt><dd className="tabular-nums">{number(value)} /4</dd></div>)}</dl><p className="mt-2 text-2xs text-slate-500">Evidence strength 45% · consistency 25% · source diversity 20% · recency 10%.</p></details>
    </Section>
  );
}

export function RequirementQualityPanel({ quality }: { quality: RequirementQuality | null | undefined }) {
  if (!quality) return <EmptyState title="Quality validation not available." detail="No passed state is inferred from missing validation output." />;
  return <Section title="Requirement quality" description={`${quality.passed ? "No blocking content checks" : "Blocking checks require attention"} · ${quality.blockers.length} blockers · ${quality.warnings.length} warnings. This does not constitute approval.`}>
    <ul className="divide-y divide-slate-100 rounded-md border border-slate-200 bg-white">{quality.checks.map((check) => <li key={check.check_id} className="px-3 py-2"><div className="flex gap-2 text-xs"><span className={check.passed ? "text-emerald-700" : check.severity === "blocker" ? "text-red-700" : "text-amber-700"}>{check.passed ? "Pass" : check.severity}</span><span className="font-medium text-zinc-900">{check.title}</span></div><p className="mt-1 text-2xs leading-relaxed text-slate-600">{check.detail}</p></li>)}</ul>
  </Section>;
}
