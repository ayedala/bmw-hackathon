"use client";

import { useMemo } from "react";

import type { PriorityFactors, RequirementRevision } from "@/lib/domain/contracts";
import { priorityScore } from "@/lib/domain/scoring";
import {
  balanceOf,
  confidenceForHypothesis,
  confidenceOf,
  currentFactors,
  decisionStatus,
  evidenceStrength,
  findingLinks,
  hypothesisLinks,
  hypothesisStatus,
  inScope,
  latestRevision,
  priorityOf,
  type Balance,
  type Confidence,
  type DecisionStatus,
  type Priority,
} from "@/lib/domain/derive";
import type { EvidenceItem, Finding, Hypothesis, HypothesisStatus, MarketCode, RequirementBundle } from "@/lib/domain/model";
import { useStore } from "@/lib/store";

export interface RequirementRow {
  id: string;
  bundle: RequirementBundle;
  revision: RequirementRevision;
  in_scope: boolean;
  factors: PriorityFactors;
  basis: "saved" | "seed";
  /** CRPS under the current what-if weights; null when the market is out of scope. */
  score: number | null;
  priority: Priority;
  confidence: Confidence;
  status: DecisionStatus;
  balance: Balance;
  external_count: number;
  updated_at: string;
}

export function useRequirementRows(market: MarketCode): RequirementRow[] {
  const { requirements, findingsById, hypothesesById, evidenceById, policy } = useStore();
  return useMemo(
    () =>
      requirements.map((bundle) => {
        const revision = latestRevision(bundle);
        const { factors, basis, assessment } = currentFactors(bundle);
        const in_scope = inScope(bundle, market);
        const score = in_scope ? priorityScore(factors, policy) : null;
        const links = bundle.finding_ids.flatMap((fid) => {
          const f = findingsById.get(fid);
          return f ? findingLinks(f, hypothesesById, evidenceById) : [];
        });
        const balance = balanceOf(links);
        const lastDecision = bundle.decisions[bundle.decisions.length - 1];
        const updated_at = [revision.created_at, lastDecision?.recorded_at ?? "", assessment?.recorded_at ?? ""].sort().reverse()[0] ?? revision.created_at;
        return {
          id: bundle.display_id,
          bundle,
          revision,
          in_scope,
          factors,
          basis,
          score,
          priority: priorityOf(score, in_scope ? factors : null),
          confidence: confidenceOf(in_scope ? factors : null, balance),
          status: decisionStatus(revision, bundle.decisions),
          balance,
          external_count: links.filter((l) => l.evidence?.kind === "external_claim" && !l.evidence.duplicate_of).length,
          updated_at,
        };
      }),
    [requirements, market, findingsById, hypothesesById, evidenceById, policy],
  );
}

export interface HypothesisRow {
  id: string;
  hypothesis: Hypothesis;
  links: { evidence_id: string; stance: "supports" | "contradicts" | "neutral"; note: string; evidence: EvidenceItem | undefined }[];
  balance: Balance;
  strength: number;
  status: HypothesisStatus;
  confidence: Confidence;
}

export function useHypothesisRows(): HypothesisRow[] {
  const { dataset, evidenceById } = useStore();
  return useMemo(
    () =>
      dataset.hypotheses.map((hypothesis) => {
        const links = hypothesisLinks(hypothesis, evidenceById);
        const balance = balanceOf(links);
        return {
          id: hypothesis.id,
          hypothesis,
          links,
          balance,
          strength: evidenceStrength(links),
          status: hypothesisStatus(balance),
          confidence: confidenceForHypothesis(balance),
        };
      }),
    [dataset.hypotheses, evidenceById],
  );
}

export interface FindingRow {
  id: string;
  finding: Finding;
  links: ReturnType<typeof findingLinks>;
  balance: Balance;
  strength: number;
  confidence: Confidence;
}

export function useFindingRows(): FindingRow[] {
  const { dataset, hypothesesById, evidenceById } = useStore();
  return useMemo(
    () =>
      dataset.findings.map((finding) => {
        const links = findingLinks(finding, hypothesesById, evidenceById);
        const balance = balanceOf(links);
        return {
          id: finding.id,
          finding,
          links,
          balance,
          strength: evidenceStrength(links),
          confidence: confidenceForHypothesis(balance),
        };
      }),
    [dataset.findings, hypothesesById, evidenceById],
  );
}
