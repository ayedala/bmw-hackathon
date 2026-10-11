"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { CrpsInterval } from "@/components/app/canonical-crps";
import { DecisionBadge, PriorityBadge } from "@/components/app/badges";
import { PageHeader, Section, EmptyState } from "@/components/app/layout-parts";
import { ReasoningSourceNotice } from "@/components/app/reasoning-chain";
import { CRPS_FACTOR_LABEL, CRPS_WEIGHTS, type CrpsFactor } from "@/lib/domain/crps";
import { MARKET_LABEL } from "@/lib/domain/model";
import { useStore } from "@/lib/store";
import { useRequirementRows } from "@/lib/view";

export function CanonicalOverviewScreen() {
  const { dataset, market, canonicalChallenges, backend, auditVerification } = useStore();
  const rows = useRequirementRows(market);
  const counts = dataset.reasoning.counts;
  const ranked = [...rows].filter((r) => r.in_scope).sort((a, b) => (b.score ?? -1) - (a.score ?? -1));
  return <div className="space-y-6"><PageHeader title="Germany 2030 decision overview" question="What should the next BMW 5 Series offer, and which decisions need review?" /><ReasoningSourceNotice />
    <div className="grid gap-3 md:grid-cols-5">{[["Evidence", counts.evidence, "/evidence"], ["Findings", counts.findings, "/findings"], ["Customer needs", counts.needs, "/needs"], ["Requirements", counts.requirements, "/requirements"], ["Open challenges", canonicalChallenges.filter((c) => !c.resolution).length, "/decisions"]].map(([label, number, href]) => <Link key={label} href={String(href)} className="rounded border border-slate-200 bg-white p-3"><span className="block text-2xs uppercase text-slate-500">{label}</span><span className="mt-1 block text-xl font-semibold">{number}</span></Link>)}</div>
    <p className="rounded border border-slate-200 bg-white p-3 text-xs">Review database: {backend.reachable ? `${backend.statesById.size} imported requirements` : backend.reason}. Audit chain: {auditVerification ? auditVerification.valid ? "verified" : `failed (${auditVerification.checkpoint})` : "not verified"}. Feasibility and policy approval remain separate from CRPS.</p>
    <Section title="Requirements by conservative CRPS" description="Ranks use the lower interval bound. Unknown factors retain their weight; Decision Confidence is separate."><ul className="divide-y divide-slate-100 rounded border border-slate-200 bg-white">{ranked.map((row) => <li key={row.id} className="flex flex-wrap items-center gap-3 p-3 text-xs"><PriorityBadge priority={row.priority} hint={row.bundle.crps?.result.band_basis} /><Link href={`/requirements/${row.id}`} className="min-w-0 flex-1 text-brand hover:underline"><span className="font-mono">{row.id}</span> · {row.revision.title}</Link><span>{row.bundle.crps ? <CrpsInterval score={row.bundle.crps} /> : "Unknown score"}</span><DecisionBadge status={row.status} /></li>)}</ul>{!ranked.length && <EmptyState title="No canonical requirement is in the selected market." />}</Section>
  </div>;
}

export function CanonicalPrioritizationScreen() {
  const { market } = useStore();
  const rows = useRequirementRows(market);
  const [first, setFirst] = useState(rows[0]?.id ?? "");
  const [second, setSecond] = useState(rows[1]?.id ?? "");
  const ranked = useMemo(() => [...rows].filter((r) => r.in_scope && r.bundle.crps).sort((a, b) => (b.score ?? -1) - (a.score ?? -1) || a.id.localeCompare(b.id)), [rows]);
  const a = rows.find((r) => r.id === first), b = rows.find((r) => r.id === second);
  const factors = Object.keys(CRPS_WEIGHTS) as CrpsFactor[];
  return <div className="space-y-6"><PageHeader title="Prioritization" question={`Which Germany 2030 requirements have the strongest conservative case in ${MARKET_LABEL[market]}?`} /><ReasoningSourceNotice />
    <p className="rounded border border-slate-200 bg-white p-3 text-xs">Python seven-factor CRPS uses Customer Impact 25%, Evidence Strength 20%, Frequency 15%, Market Relevance 15%, Competitive Gap 10%, Future Relevance 10%, Strategic Fit 5%. Bands use the lower bound: P1 ≥80, P2 ≥65, P3 ≥50. An interval overlap means the order is unresolved. Decision Confidence and feasibility do not alter priority.</p>
    <Section title="Conservative ranking"><ol className="divide-y divide-slate-100 rounded border border-slate-200 bg-white">{ranked.map((row, index) => <li key={row.id} className="flex flex-wrap items-center gap-3 p-3 text-xs"><span className="w-5 text-slate-500">{index + 1}</span><PriorityBadge priority={row.priority} hint={row.bundle.crps?.result.band_basis} /><Link href={`/requirements/${row.id}`} className="min-w-0 flex-1 text-brand hover:underline"><span className="font-mono">{row.id}</span> · {row.revision.title}</Link>{row.bundle.crps && <><CrpsInterval score={row.bundle.crps} /><span>Confidence {row.bundle.crps.confidence.value_0_to_100}/100</span></>}<DecisionBadge status={row.status} /></li>)}</ol>{!ranked.length && <EmptyState title="No scored requirement in this market." />}</Section>
    <Section title="Compare two requirement intervals"><div className="mb-3 flex flex-wrap gap-2">{[first, second].map((id, index) => <select key={index} aria-label={index ? "Second requirement" : "First requirement"} className="rounded border border-slate-200 p-2 text-xs" value={id} onChange={(event) => (index ? setSecond : setFirst)(event.target.value)}>{rows.map((row) => <option key={row.id} value={row.id}>{row.id} · {row.revision.title}</option>)}</select>)}</div>
      {a?.bundle.crps && b?.bundle.crps && <div className="overflow-x-auto rounded border border-slate-200 bg-white text-xs"><table className="w-full"><thead><tr className="border-b border-slate-100 text-left"><th className="p-2">Factor</th><th className="p-2">Weight</th><th className="p-2">{a.id}</th><th className="p-2">{b.id}</th></tr></thead><tbody>{factors.map((name) => <tr key={name} className="border-b border-slate-100"><th className="p-2 text-left font-medium">{CRPS_FACTOR_LABEL[name]}</th><td className="p-2">{CRPS_WEIGHTS[name] * 100}%</td>{[a, b].map((row) => { const input = row.bundle.crps!.result.factors[name]; return <td key={row.id} className="p-2">{input ? `${input.lower_value}–${input.upper_value} /4` : "Unavailable"}</td>; })}</tr>)}</tbody></table><p className="p-3">{a.bundle.crps.result.crps_100_lower > b.bundle.crps.result.crps_100_upper || b.bundle.crps.result.crps_100_lower > a.bundle.crps.result.crps_100_upper ? "Intervals do not overlap; their lower-bound order is resolved under this display policy." : "Intervals overlap; the order is unresolved. Review evidence and uncertainty before choosing."}</p></div>}
    </Section>
  </div>;
}

export function CanonicalSettingsScreen() {
  const { dataset, actorId, setActorId, backend, auditVerification } = useStore();
  return <div className="space-y-6"><PageHeader title="Settings" question="Which corpus and policy power Germany 2030 review?" /><ReasoningSourceNotice />
    <Section title="CRPS policy" description="Python bmw_pm.decision.crps is authoritative; this hackathon display policy is unapproved."><ul className="grid gap-2 md:grid-cols-2">{(Object.keys(CRPS_WEIGHTS) as CrpsFactor[]).map((name) => <li key={name} className="rounded border border-slate-200 bg-white p-3 text-xs">{CRPS_FACTOR_LABEL[name]} · {(CRPS_WEIGHTS[name] * 100).toFixed(0)}%</li>)}</ul><p className="mt-3 text-xs">Frequency is unknown without a valid customer denominator. Missing factors retain a 0–4 interval. Engineering feasibility is reviewed separately.</p></Section>
    <Section title="Review authority"><p className="text-xs">{backend.reachable ? `${backend.statesById.size} requirements available in the audited database.` : backend.reason} Hash chain: {auditVerification ? auditVerification.valid ? "valid" : auditVerification.checkpoint : "unavailable"}.</p><label className="mt-3 block text-xs" htmlFor="canonical-actor">Reviewer ID</label><input id="canonical-actor" className="mt-1 rounded border border-slate-200 p-2 text-xs" value={actorId} onChange={(event) => setActorId(event.target.value)} /></Section>
    <Section title="Loaded source artifacts"><ul className="space-y-1 text-xs">{dataset.source_files.map((file) => <li key={file.path} className="break-all font-mono">{file.path} · {file.status} · {file.records} records</li>)}</ul></Section>
  </div>;
}
