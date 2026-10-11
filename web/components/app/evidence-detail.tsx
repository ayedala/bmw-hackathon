"use client";

import { ExternalLink } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { ProvenanceBadge, QualityValue, SourceFamilyBadge, StanceBadge } from "@/components/app/badges";
import { KeyValue, SubHeading } from "@/components/app/layout-parts";
import { Button } from "@/components/ui/button";
import { FAMILY_LABEL, formatDate, formatDateTime, humanize, TOPIC_LABEL } from "@/lib/domain/derive";
import type { EvidenceItem } from "@/lib/domain/model";
import { MARKET_LABEL } from "@/lib/domain/model";
import { useStore } from "@/lib/store";

export function EvidenceDetail({ evidence }: { evidence: EvidenceItem }) {
  const { dataset, evidenceById, requirements } = useStore();
  const [showRaw, setShowRaw] = useState(false);
  const usedBy = dataset.hypotheses.filter((h) => h.links.some((l) => l.evidence_id === evidence.id));
  const findings = dataset.reasoning.authoritative
    ? dataset.findings.filter((f) => dataset.reasoning.findings.some((row) => row.artifact.finding_id === f.id && row.artifact.evidence_ids.includes(evidence.id)))
    : dataset.findings.filter((f) => f.hypothesis_ids.some((id) => usedBy.some((h) => h.id === id)));
  const needs = dataset.reasoning.authoritative ? dataset.reasoning.needs.filter((n) => n.artifact.evidence_ids.includes(evidence.id) || n.findings.some((f) => f.artifact.evidence_ids.includes(evidence.id))) : [];
  const reqs = requirements.filter(
    (r) => r.finding_ids.some((fid) => findings.some((f) => f.id === fid)) ||
      r.revisions.some((rev) => rev.evidence_links.some((l) => l.signal_id === evidence.id) || rev.evidence_references?.some((ref) => ref.evidence_id === evidence.id)),
  );
  const original = evidence.duplicate_of ? evidenceById.get(evidence.duplicate_of) : undefined;

  return (
    <div className="space-y-5">
      <div className="space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <ProvenanceBadge provenance={evidence.provenance} />
          <span className="font-mono text-2xs text-slate-500">{evidence.id}</span>
          {evidence.duplicate_of && (
            <span className="rounded-sm bg-amber-50 px-1 text-2xs text-amber-800">Duplicate — excluded from counts</span>
          )}
        </div>
        <p className="text-[13px] font-medium leading-snug text-zinc-950">{evidence.claim}</p>
        {evidence.numeric_value !== null && (
          <div className="flex items-baseline gap-2">
            <span className="text-2xl font-semibold tabular-nums tracking-tight text-zinc-950">
              {evidence.numeric_value} <span className="text-base font-medium text-slate-600">{evidence.numeric_unit}</span>
            </span>
            <span className="text-xs text-slate-500">{humanize(evidence.subtopic)}</span>
          </div>
        )}
      </div>

      <div>
        <SubHeading>Exact excerpt</SubHeading>
        <blockquote className="rounded-sm border-l-2 border-zinc-900 bg-slate-50 px-3 py-2 text-[13px] leading-relaxed text-zinc-800" lang={evidence.excerpt_language}>
          {evidence.excerpt}
        </blockquote>
        <p className="mt-1 text-2xs text-slate-500">Locator: {evidence.locator}</p>
      </div>

      <div>
        <SubHeading>Source lineage</SubHeading>
        <ol className="space-y-1.5 text-xs">
          <li className="flex gap-2">
            <span className="w-16 shrink-0 text-slate-500">Source</span>
            <span className="min-w-0 text-zinc-900">
              {evidence.source_name}
              <span className="block text-slate-500">{evidence.source_title}</span>
            </span>
          </li>
          <li className="flex gap-2">
            <span className="w-16 shrink-0 text-slate-500">URL</span>
            {evidence.source_url ? (
              <a href={evidence.source_url} target="_blank" rel="noreferrer noopener" className="min-w-0 break-all text-zinc-900 underline decoration-slate-300 underline-offset-2 hover:decoration-zinc-900">
                {evidence.source_url}
              </a>
            ) : (
              <span className="text-slate-500">
                {evidence.kind === "customer_feedback" ? "Supplied workbook (no public URL)" : evidence.provenance === "synthetic" ? "Synthetic illustration (no URL)" : "Source URL was not captured"}
              </span>
            )}
          </li>
          <li className="flex gap-2">
            <span className="w-16 shrink-0 text-slate-500">Group</span>
            <span className="font-mono text-2xs text-zinc-800">{evidence.independence_group}</span>
          </li>
          <li className="flex gap-2">
            <span className="w-16 shrink-0 text-slate-500">Duplicate</span>
            {original ? (
              <span className="text-zinc-900">
                Repeats <span className="font-mono text-2xs">{original.id}</span> ({original.source_name})
              </span>
            ) : (
              <span className="text-zinc-900">Original record</span>
            )}
          </li>
        </ol>
      </div>

      <dl className="grid grid-cols-3 gap-x-4 gap-y-3">
        <KeyValue label="Vehicle">{evidence.vehicle}</KeyValue>
        <KeyValue label="Market">{MARKET_LABEL[evidence.market]}</KeyValue>
        <KeyValue label="Topic">
          {TOPIC_LABEL[evidence.topic]} · <span className="text-slate-600">{humanize(evidence.subtopic)}</span>
        </KeyValue>
        <KeyValue label="Source family">
          <SourceFamilyBadge family={evidence.source_family} />
        </KeyValue>
        <KeyValue label="Quality">
          <QualityValue quality={evidence.quality} />
        </KeyValue>
        <KeyValue label="Published">{formatDate(evidence.published_at)}</KeyValue>
        <KeyValue label="Retrieved">{formatDateTime(evidence.retrieved_at)}</KeyValue>
        <KeyValue label="Kind">{evidence.kind === "customer_feedback" ? "Customer feedback" : "External claim"}</KeyValue>
        <KeyValue label="Family code">
          <span className="font-mono text-2xs">{FAMILY_LABEL[evidence.source_family] ? evidence.source_family : "—"}</span>
        </KeyValue>
      </dl>

      {evidence.limitation && (
        <div>
          <SubHeading>Applicability limit</SubHeading>
          <p className="text-xs text-slate-600">{evidence.limitation}</p>
        </div>
      )}

      {!dataset.reasoning.authoritative && <div>
        <SubHeading count={usedBy.length}>Used in hypotheses</SubHeading>
        {usedBy.length === 0 ? (
          <p className="text-xs text-slate-500">Not linked to a hypothesis yet.</p>
        ) : (
          <ul className="space-y-1">
            {usedBy.map((h) => {
              const link = h.links.find((l) => l.evidence_id === evidence.id);
              return (
                <li key={h.id} className="flex items-start gap-2 text-xs">
                  {link && <StanceBadge stance={link.stance} />}
                  <Link href={`/hypotheses?id=${h.id}`} className="min-w-0 text-zinc-900 hover:underline">
                    <span className="font-mono text-2xs text-slate-500">{h.id}</span> {h.statement}
                    {link?.note && <span className="block text-slate-500">{link.note}</span>}
                  </Link>
                </li>
              );
            })}
          </ul>
        )}
      </div>}

      {(findings.length > 0 || needs.length > 0 || reqs.length > 0) && (
        <div className="grid grid-cols-2 gap-4">
          <div>
            <SubHeading count={findings.length}>Findings</SubHeading>
            <ul className="space-y-1 text-xs">
              {findings.map((f) => (
                <li key={f.id}>
                  <Link href={`/findings?id=${f.id}`} className="text-zinc-900 hover:underline">
                    {f.title}
                  </Link>
                </li>
              ))}
            </ul>
          </div>
          {needs.length > 0 && <div><SubHeading count={needs.length}>Customer needs</SubHeading><ul className="space-y-1 text-xs">{needs.map((n) => <li key={n.artifact.need_id}><Link href={`/needs?id=${encodeURIComponent(n.artifact.need_id)}`} className="text-zinc-900 hover:underline">{n.artifact.statement}</Link></li>)}</ul></div>}
          <div>
            <SubHeading count={reqs.length}>Requirements</SubHeading>
            <ul className="space-y-1 text-xs">
              {reqs.map((r) => (
                <li key={r.display_id}>
                  <Link href={`/requirements/${r.display_id}`} className="text-zinc-900 hover:underline">
                    <span className="font-mono text-2xs text-slate-500">{r.display_id}</span> {r.revisions[r.revisions.length - 1]?.title}
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}

      <div>
        <Button size="sm" variant="ghost" onClick={() => setShowRaw((v) => !v)} aria-expanded={showRaw}>
          {showRaw ? "Hide stored record" : "Show stored record"}
        </Button>
        {showRaw && (
          <pre className="mt-2 max-h-72 overflow-auto rounded-sm bg-slate-50 p-2 font-mono text-2xs leading-relaxed text-slate-700">
            {JSON.stringify(evidence.raw, null, 2)}
          </pre>
        )}
      </div>
    </div>
  );
}

export function OpenSourceButton({ evidence }: { evidence: EvidenceItem }) {
  if (!evidence.source_url) {
    return (
      <Button variant="primary" disabled title="No captured URL for this record">
        Open source
      </Button>
    );
  }
  return (
    <Button variant="primary" asChild>
      <a href={evidence.source_url} target="_blank" rel="noreferrer noopener">
        Open source <ExternalLink />
      </a>
    </Button>
  );
}
