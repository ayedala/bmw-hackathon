"use client";

import Link from "next/link";
import { useMemo } from "react";

import { BalanceBar, ConfidenceBadge, DecisionBadge, HypothesisStatusBadge, PriorityBadge, ScoreValue } from "@/components/app/badges";
import { DecisionControls } from "@/components/app/decision-controls";
import { EvidenceList, type EvidenceListEntry } from "@/components/app/evidence-list";
import { EmptyState, KeyValue, Section, SubHeading } from "@/components/app/layout-parts";
import { PriorityBreakdown, WeightControls } from "@/components/app/score";
import { MarketSelector } from "@/components/app/shell";
import {
  balanceOf,
  confidenceOf,
  currentFactors,
  decisionStatus,
  formatDateTime,
  humanize,
  hypothesisStatus,
  inScope as isInScope,
  latestRevision,
  priorityOf,
  TOPIC_LABEL,
} from "@/lib/domain/derive";
import { MARKETS, MARKET_LABEL } from "@/lib/domain/model";
import { priorityScore } from "@/lib/domain/scoring";
import { judgmentsFor, useStore } from "@/lib/store";
import { cn } from "@/lib/utils";

function ChainStep({ label, value, href, last }: { label: string; value: string | number; href: string; last?: boolean }) {
  return (
    <li className="flex items-center gap-2">
      <a href={href} className="group rounded-sm px-1 py-0.5 hover:bg-brand-soft focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/35">
        <span className="block text-2xs uppercase tracking-wide text-slate-500 group-hover:text-brand">{label}</span>
        <span className="block text-xs font-medium tabular-nums text-zinc-900">{value}</span>
      </a>
      {!last && (
        <span aria-hidden className="text-slate-300">
          →
        </span>
      )}
    </li>
  );
}

function ProseBlock({ label, children, tone }: { label: string; children: React.ReactNode; tone?: "contrary" }) {
  return (
    <div className={cn("rounded-md border bg-white p-3", tone === "contrary" ? "border-amber-200" : "border-slate-200")}>
      <div className={cn("text-2xs font-semibold uppercase tracking-wide", tone === "contrary" ? "text-amber-800" : "text-slate-500")}>{label}</div>
      <p className="mt-1 text-xs leading-relaxed text-zinc-800">{children}</p>
    </div>
  );
}

export function RequirementWorkspace({ displayId }: { displayId: string }) {
  const { dataset, market, setMarket, policy, requirementByDisplayId, findingsById, hypothesesById, evidenceById, audit, challenges, judgments } = useStore();
  const bundle = requirementByDisplayId.get(displayId);

  const derived = useMemo(() => {
    if (!bundle) return null;
    const findings = bundle.finding_ids.map((id) => findingsById.get(id)).filter((f): f is NonNullable<typeof f> => Boolean(f));
    const hypotheses = findings
      .flatMap((f) => f.hypothesis_ids)
      .filter((id, i, arr) => arr.indexOf(id) === i)
      .map((id) => hypothesesById.get(id))
      .filter((h): h is NonNullable<typeof h> => Boolean(h));
    const rev = latestRevision(bundle);
    const seen = new Set<string>();
    const anchors: EvidenceListEntry[] = [];
    const supporting: EvidenceListEntry[] = [];
    const opposing: EvidenceListEntry[] = [];
    const context: EvidenceListEntry[] = [];
    const push = (list: EvidenceListEntry[], id: string, note?: string) => {
      if (seen.has(id)) return;
      const evidence = evidenceById.get(id);
      if (!evidence) return;
      seen.add(id);
      list.push({ evidence, note });
    };
    const allLinks = hypotheses.flatMap((h) => h.links.map((l) => ({ ...l, h: h.id })));
    for (const id of bundle.proposal.anchor_ids) {
      const link = allLinks.find((l) => l.evidence_id === id);
      const stanceText = link ? (link.stance === "supports" ? "supports" : link.stance === "contradicts" ? "contradicts" : "context") : "";
      push(anchors, id, link ? `${link.h} · ${stanceText}${link.note ? ` — ${link.note}` : ""}` : "Cited by the proposal");
    }
    for (const h of hypotheses) {
      for (const link of h.links) {
        const note = `${h.id}${link.note ? ` · ${link.note}` : ""}`;
        if (link.stance === "supports") push(supporting, link.evidence_id, note);
        else if (link.stance === "contradicts") push(opposing, link.evidence_id, note);
        else push(context, link.evidence_id, note);
      }
    }
    const anchorStance = (id: string) => allLinks.find((l) => l.evidence_id === id)?.stance ?? "neutral";
    const all = [
      ...anchors.map((e) => ({ stance: anchorStance(e.evidence.id), evidence: e.evidence })),
      ...supporting.map((e) => ({ stance: "supports" as const, evidence: e.evidence })),
      ...opposing.map((e) => ({ stance: "contradicts" as const, evidence: e.evidence })),
      ...context.map((e) => ({ stance: "neutral" as const, evidence: e.evidence })),
    ];
    const balance = balanceOf(all);
    const sources = new Set(all.map((e) => e.evidence.independence_group));
    const supportingForChallenge = [...anchors.filter((e) => anchorStance(e.evidence.id) === "supports"), ...supporting];
    const opposingForChallenge = [...anchors.filter((e) => anchorStance(e.evidence.id) === "contradicts"), ...opposing];
    return { findings, hypotheses, rev, anchors, supporting, opposing, context, balance, sources, supportingForChallenge, opposingForChallenge };
  }, [bundle, findingsById, hypothesesById, evidenceById]);

  if (!bundle || !derived) {
    return (
      <EmptyState
        title={`Requirement ${displayId} is not in this proposal set.`}
        detail="It may belong to another vehicle profile or an earlier run."
        action={
          <Link href="/requirements" className="text-xs text-brand underline underline-offset-2">
            Back to requirements
          </Link>
        }
      />
    );
  }

  const { findings, hypotheses, rev, anchors, supporting, opposing, context, balance, sources } = derived;
  const p = bundle.proposal;
  const inScope = isInScope(bundle, market);
  const { factors, basis, assessment } = currentFactors(bundle);
  const score = inScope ? priorityScore(factors, policy) : null;
  const priority = priorityOf(score, inScope ? factors : null);
  const confidence = basis === "seed" ? "Low" : confidenceOf(inScope ? factors : null, balance);
  const status = decisionStatus(rev, bundle.decisions);
  const linkJudgments = judgmentsFor(judgments, rev.requirement_id, rev.revision);
  const challengeIds = challenges.filter((c) => c.display_id === displayId).map((c) => c.challenge_id);
  const events = audit.filter((e) => e.object_id === displayId || challengeIds.includes(e.object_id)).slice().reverse();
  const openChallenge = challenges.filter((c) => c.display_id === displayId).slice(-1)[0];
  const assessable = [...anchors, ...supporting, ...opposing, ...context];
  const assessed = assessable.filter((e) => linkJudgments.has(e.evidence.id)).length;
  const assess = { displayId, judgments: linkJudgments };

  return (
    <div>
      <nav aria-label="Breadcrumb" className="mb-2 text-xs text-slate-500">
        <Link href="/requirements" className="hover:text-brand">
          Requirements
        </Link>
        <span className="mx-1.5 text-slate-300">/</span>
        <span className="font-mono text-zinc-700">{bundle.display_id}</span>
      </nav>

      <header className="border-b border-slate-200 pb-4">
        <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
          <span className="font-mono font-medium text-zinc-700">{bundle.display_id}</span>
          <span>r{rev.revision}</span>
          {rev.supersedes_revision && <span>supersedes r{rev.supersedes_revision}</span>}
          <span className="text-slate-300">·</span>
          <span>{TOPIC_LABEL[bundle.topic] ?? humanize(bundle.topic)}</span>
          <span className="text-slate-300">·</span>
          <span>G60 · US · {rev.scope.powertrains.join(" / ")}</span>
          <span className="text-slate-300">·</span>
          <span className="font-mono text-2xs">{dataset.planning.version}</span>
        </div>
        <h1 className="mt-1 max-w-4xl text-xl font-semibold leading-snug tracking-tight text-zinc-950">{rev.title}</h1>
        <dl className="mt-3 flex flex-wrap items-center gap-x-6 gap-y-2">
          <div className="flex items-center gap-2">
            <dt className="text-2xs uppercase tracking-wide text-slate-500">Priority</dt>
            <dd>
              <PriorityBadge priority={priority} />
            </dd>
          </div>
          <div className="flex items-center gap-2">
            <dt className="text-2xs uppercase tracking-wide text-slate-500">CRPS</dt>
            <dd className="text-sm">
              <ScoreValue score={score} basis={basis} />
            </dd>
          </div>
          <div className="flex items-center gap-2">
            <dt className="text-2xs uppercase tracking-wide text-slate-500">Confidence</dt>
            <dd>
              <ConfidenceBadge confidence={confidence} />
            </dd>
          </div>
          <div className="flex items-center gap-2">
            <dt className="text-2xs uppercase tracking-wide text-slate-500">PM decision</dt>
            <dd>
              <DecisionBadge status={status} />
            </dd>
          </div>
          <div className="flex items-center gap-2">
            <dt className="text-2xs uppercase tracking-wide text-slate-500">Market</dt>
            <dd>
              <MarketSelector value={market} onChange={setMarket} size="sm" />
            </dd>
          </div>
        </dl>
        <ol className="mt-3 flex flex-wrap items-center gap-1" aria-label="Traceability chain">
          <ChainStep label="Requirement" value={`r${rev.revision}`} href="#statement" />
          <ChainStep label="Customer need" value={findings.length > 0 ? "1" : "—"} href="#need" />
          <ChainStep label="Findings" value={findings.length} href="#need" />
          <ChainStep label="Hypotheses" value={hypotheses.length} href="#hypotheses" />
          <ChainStep label="Evidence" value={assessable.length} href="#evidence" />
          <ChainStep label="Sources" value={sources.size} href="#evidence" last />
        </ol>
      </header>

      {!inScope && (
        <div className="mt-4 rounded-md border border-slate-200 bg-white px-3 py-2 text-xs text-slate-700" role="status">
          <span className="font-medium text-zinc-900">Not assessed for {MARKET_LABEL[market]}.</span> This proposal is curated for the US 5 Series and is never transferred
          without a market-specific review. {bundle.market_context[market]}
        </div>
      )}
      {openChallenge && status === "challenged" && (
        <div className="mt-4 rounded-md border border-amber-200 bg-amber-50/70 px-3 py-2 text-xs text-amber-900" role="status">
          <span className="font-medium">Open challenge {openChallenge.challenge_id}:</span> {openChallenge.statement} CRPS {openChallenge.score_before.toFixed(1)} →{" "}
          {openChallenge.score_after.toFixed(1)}.{" "}
          <Link href="/audit" className="underline underline-offset-2">
            View in audit trail
          </Link>
        </div>
      )}

      <div className="mt-5 grid gap-6 lg:grid-cols-[minmax(0,1fr)_300px] xl:grid-cols-[minmax(0,1fr)_360px]">
        <div className="min-w-0 space-y-7">
          <div id="statement" className="scroll-mt-20">
            <Section title="Proposed requirement" description={`Authored successor proposal · planning window ${dataset.planning.window}`}>
              <div className="rounded-md border border-slate-200 bg-white p-4">
                <p className="text-sm leading-relaxed text-zinc-900">{rev.customer_outcome}</p>
                <dl className="mt-4 grid gap-x-6 gap-y-3 md:grid-cols-3">
                  <KeyValue label="Customer value" className="md:col-span-2">
                    <span className="text-xs leading-relaxed">{p.value}</span>
                  </KeyValue>
                  <KeyValue label="Target">
                    {rev.acceptance_proposal.target !== null ? (
                      <span className="tabular-nums">
                        {String(rev.acceptance_proposal.target)} {rev.acceptance_proposal.unit}
                      </span>
                    ) : (
                      <span className="text-xs text-slate-500">Set after a baseline exists</span>
                    )}
                  </KeyValue>
                  <KeyValue label="Validation" className="md:col-span-2">
                    <span className="text-xs leading-relaxed">{rev.acceptance_proposal.method}</span>
                  </KeyValue>
                  <KeyValue label="Feasibility">
                    <span className="text-amber-700">{humanize(rev.feasibility)}</span>
                    <span className="block text-2xs text-slate-500">Cost: {rev.implementation_cost_missing_reason.toLowerCase()}</span>
                  </KeyValue>
                  <KeyValue label="Solution alternatives" className="md:col-span-3">
                    <span className="text-xs text-zinc-800">{rev.alternatives.join(" · ")}</span>
                  </KeyValue>
                </dl>
              </div>
            </Section>
          </div>

          <Section title="Reasoning" description="Kept separate: what the evidence shows, what we assume about 2029–2031, and what argues against.">
            <div className="grid gap-3 xl:grid-cols-3">
              <ProseBlock label="Interpretation">{p.interpretation}</ProseBlock>
              <ProseBlock label={`Future assumption · ${dataset.planning.window}`}>{p.future_assumption}</ProseBlock>
              <ProseBlock label="Contrary evidence / trade-off" tone="contrary">
                {p.contrary}
              </ProseBlock>
            </div>
            <p className="mt-2 text-xs text-slate-600">
              <span className="font-medium text-zinc-900">Revisit when: </span>
              {p.review_trigger}
            </p>
          </Section>

          <div id="need" className="scroll-mt-20">
            <Section title="Customer need and derived findings">
              {findings.length === 0 ? (
                <EmptyState title="No finding is linked to this requirement." detail="Link a finding before approving so the decision is traceable." />
              ) : (
                <div className="rounded-md border border-slate-200 bg-white">
                  <div className="border-b border-slate-200 px-4 py-2.5">
                    <div className="text-2xs uppercase tracking-wide text-slate-500">Customer need</div>
                    <p className="mt-0.5 text-[13px] font-medium text-zinc-900">{findings[0]?.customer_need}</p>
                  </div>
                  <ul className="divide-y divide-slate-100">
                    {findings.map((f) => {
                      const fb = balanceOf(f.hypothesis_ids.flatMap((hid) => (hypothesesById.get(hid)?.links ?? []).map((l) => ({ stance: l.stance, evidence: evidenceById.get(l.evidence_id) }))));
                      return (
                        <li key={f.id} className="px-4 py-2.5">
                          <div className="flex items-start justify-between gap-4">
                            <Link href={`/findings?id=${f.id}`} className="min-w-0 hover:text-brand">
                              <span className="mr-2 font-mono text-2xs text-slate-500">{f.id}</span>
                              <span className="text-[13px] font-medium text-zinc-900">{f.title}</span>
                            </Link>
                            <BalanceBar balance={fb} />
                          </div>
                          <p className="mt-1 text-xs leading-relaxed text-slate-600">{f.summary}</p>
                        </li>
                      );
                    })}
                  </ul>
                </div>
              )}
            </Section>
          </div>

          <div id="hypotheses" className="scroll-mt-20">
            <Section title="Hypotheses tested" description="Each hypothesis carries its own support and contradiction count.">
              <ul className="divide-y divide-slate-100 rounded-md border border-slate-200 bg-white">
                {hypotheses.map((h) => {
                  const hb = balanceOf(h.links.map((l) => ({ stance: l.stance, evidence: evidenceById.get(l.evidence_id) })));
                  return (
                    <li key={h.id} className="flex items-center gap-3 px-4 py-2">
                      <Link href={`/hypotheses?id=${h.id}`} className="min-w-0 flex-1 text-xs hover:text-brand">
                        <span className="mr-2 font-mono text-2xs text-slate-500">{h.id}</span>
                        <span className="text-zinc-900">{h.statement}</span>
                      </Link>
                      <HypothesisStatusBadge status={hypothesisStatus(hb)} />
                      <BalanceBar balance={hb} />
                    </li>
                  );
                })}
              </ul>
            </Section>
          </div>

          <div id="evidence" className="scroll-mt-20 space-y-4">
            <Section title="Evidence summary">
              <div className="grid grid-cols-2 gap-px overflow-hidden rounded-md border border-slate-200 bg-slate-200 md:grid-cols-5">
                {[
                  ["Extracted concerns", balance.supporting],
                  ["Opposing", balance.contradicting],
                  ["Praise / other", balance.neutral],
                  ["Feedback IDs", balance.independent_sources],
                  ["Links assessed", `${assessed} / ${assessable.length}`],
                ].map(([label, value]) => (
                  <div key={label} className="bg-white px-3 py-2">
                    <div className="text-2xs uppercase tracking-wide text-slate-500">{label}</div>
                    <div className={cn("mt-0.5 text-base font-semibold tabular-nums text-zinc-950", label === "Contradicting" && "text-amber-700")}>{value}</div>
                  </div>
                ))}
              </div>
              <p className="mt-1.5 text-2xs text-slate-500">
                Record counts are not prevalence; {rev.denominator_feedback_records.toLocaleString("en-US")} eligible US G60 feedback IDs in the stored baseline run. Assessing a
                link records a human judgement; counts and scores do not change automatically.
              </p>
            </Section>

            <Section title="Anchor records" description="Redacted text and source locators from the configured private database. Interpretations remain unreviewed.">
              <EvidenceList entries={anchors} initial={6} empty="The proposal cites no anchor records." assess={assess} />
            </Section>

            <div className="grid gap-4 xl:grid-cols-2">
              <Section title="Potentially relevant concerns" description={`${supporting.length} extracted records; review their meaning before deciding`}>
                <EvidenceList entries={supporting} empty="No concerns are linked." assess={assess} />
              </Section>
              <Section title="Opposing evidence" description={`${opposing.length} reviewed links`}>
                <EvidenceList entries={opposing} tone="contradict" empty="No opposing evidence is linked. Review praise and alternative explanations in context; this is not consensus." assess={assess} />
              </Section>
            </div>
            {context.length > 0 && (
              <Section title="Context" description="Relevant but neither supports nor contradicts the outcome.">
                <EvidenceList entries={context} initial={3} empty="" assess={assess} />
              </Section>
            )}
          </div>

          <Section title="Competitive evidence gap">
            <EmptyState title="No matched cohort comparison has been verified." detail="The curated web notes remain context. Collect like-for-like model, market and test-condition evidence before rating a competitive gap." />
          </Section>

          <Section title="Market relevance" description="The proposal is authored for the US. Other markets show what exists and what a transfer would need.">
            <div className="overflow-x-auto rounded-md border border-slate-200 bg-white">
              <table className="w-full text-[13px]">
                <caption className="sr-only">Market scope for {bundle.display_id}</caption>
                <thead>
                  <tr className="border-b border-slate-200 text-2xs uppercase tracking-wide text-slate-500">
                    <th scope="col" className="h-8 px-3 text-left font-medium">Market</th>
                    <th scope="col" className="px-3 text-left font-medium">Status</th>
                    <th scope="col" className="px-3 text-right font-medium">CRPS</th>
                    <th scope="col" className="px-3 text-left font-medium">Evidence available</th>
                  </tr>
                </thead>
                <tbody>
                  {MARKETS.map((m) => {
                    const scoped = bundle.scope_markets.includes(m);
                    return (
                      <tr key={m} className={cn("border-b border-slate-100 last:border-0", m === market && "bg-brand-soft/60")}>
                        <td className="whitespace-nowrap px-3 py-1.5">
                          <button type="button" onClick={() => setMarket(m)} className="text-left hover:text-brand focus-visible:text-brand focus-visible:outline-none">
                            <span className="font-mono text-2xs font-medium text-slate-600">{m}</span> <span className="ml-1 text-xs text-zinc-800">{MARKET_LABEL[m]}</span>
                          </button>
                        </td>
                        <td className="whitespace-nowrap px-3 py-1.5 text-xs">{scoped ? <span className="text-zinc-900">In scope</span> : <span className="text-slate-500">Not transferred</span>}</td>
                        <td className="px-3 py-1.5 text-right">
                          <ScoreValue score={scoped ? priorityScore(factors, policy) : null} basis={basis} />
                        </td>
                        <td className="px-3 py-1.5 text-xs text-slate-600">{scoped ? "Supplied US G60 feedback, anchors and linked evidence above." : bundle.market_context[m]}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </Section>

          <div className="grid gap-4 xl:grid-cols-2">
            <Section title="Assumptions">
              <ul className="list-disc space-y-1 pl-4 text-xs text-slate-600">
                {rev.assumptions.map((a) => (
                  <li key={a}>{a}</li>
                ))}
              </ul>
            </Section>
            <Section title="Missing evidence">
              <ul className="list-disc space-y-1 pl-4 text-xs text-slate-600">
                {rev.missing_evidence.map((a) => (
                  <li key={a}>{a}</li>
                ))}
              </ul>
            </Section>
          </div>

          <Section
            title="Priority and decision history"
            actions={
              <Link href="/audit" className="text-xs text-slate-600 hover:text-brand">
                Full audit trail
              </Link>
            }
          >
            {events.length === 0 ? (
              <EmptyState title="No recorded events for this requirement yet." />
            ) : (
              <ol className="divide-y divide-slate-100 rounded-md border border-slate-200 bg-white">
                {events.map((e) => (
                  <li key={e.event_id} className="grid grid-cols-[110px_150px_minmax(0,1fr)] gap-3 px-3 py-1.5 text-xs">
                    <span className="tabular-nums text-slate-500">{formatDateTime(e.recorded_at)}</span>
                    <span className="truncate font-medium text-zinc-900">{humanize(e.action)}</span>
                    <span className="min-w-0 text-slate-600">
                      {e.reason}
                      <span className="ml-1.5 text-2xs text-slate-400">{e.actor_id}</span>
                    </span>
                  </li>
                ))}
              </ol>
            )}
          </Section>
        </div>

        <aside className="space-y-4 lg:sticky lg:top-20 lg:self-start" aria-label="Priority and decision">
          <div className="rounded-md border border-slate-200 bg-white p-4">
            {inScope ? (
              <PriorityBreakdown factors={factors} policy={policy} basis={basis} assessment={assessment} />
            ) : (
              <EmptyState title={`Not assessed for ${MARKET_LABEL[market]}.`} detail="Switch to United States to see and rate the priority." className="border-0 p-0" />
            )}
            <div className="mt-4 border-t border-slate-100 pt-3">
              <WeightControls dense />
            </div>
          </div>
          <div className="rounded-md border border-slate-200 bg-white p-4">
            <DecisionControls
              bundle={bundle}
              revision={rev}
              factors={factors}
              basis={basis}
              status={status}
              confidence={confidence}
              balance={balance}
              supporting={derived.supportingForChallenge}
              opposing={derived.opposingForChallenge}
              inScope={inScope}
            />
          </div>
          <div className="rounded-md border border-slate-200 bg-white p-4 text-xs">
            <SubHeading>Record provenance</SubHeading>
            <dl className="space-y-1 text-2xs text-slate-600">
              <div className="flex justify-between gap-2">
                <dt>Requirement ID</dt>
                <dd className="truncate font-mono">{rev.requirement_id}</dd>
              </div>
              <div className="flex justify-between gap-2">
                <dt>Created by</dt>
                <dd className="truncate">{rev.created_by}</dd>
              </div>
              <div className="flex justify-between gap-2">
                <dt>Priority basis</dt>
                <dd>{assessment ? `Assessment #${assessment.sequence}` : "Seed from proposal"}</dd>
              </div>
              <div className="flex justify-between gap-2">
                <dt>Assessments</dt>
                <dd className="tabular-nums">{bundle.assessments.length}</dd>
              </div>
              <div className="flex justify-between gap-2">
                <dt>Evidence review</dt>
                <dd>
                  {assessed} of {assessable.length} links
                </dd>
              </div>
            </dl>
          </div>
        </aside>
      </div>
    </div>
  );
}
