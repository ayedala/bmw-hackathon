"use client";

import { useEffect, useState } from "react";
import type { AdvisorResult, Option, Vehicle } from "./contracts";

const KEY = "bmw-pdl:studio-requirement-reviews:v1";
const CHANGE = "bmw-pdl:studio-requirement-reviews-changed";

export interface ReviewDraft {
  id: string;
  source_run_id: string;
  option_id: string;
  model_code: Vehicle;
  market: string;
  powertrain: string;
  title: string;
  proposal: string;
  customer_outcome: string;
  evidence_ids: string[];
  created_at: string;
  status: "pending" | "approved" | "rejected";
  reviewer_id: string | null;
  rationale: string | null;
  reviewed_at: string | null;
}

export function readReviewDrafts(): ReviewDraft[] {
  try {
    const raw = JSON.parse(window.localStorage.getItem(KEY) || "[]");
    return Array.isArray(raw) ? raw.filter((item): item is ReviewDraft =>
      typeof item?.id === "string" && typeof item?.title === "string" &&
      ["F70", "G60", "G70"].includes(item?.model_code)) : [];
  } catch { return []; }
}

function writeDrafts(drafts: ReviewDraft[]) {
  window.localStorage.setItem(KEY, JSON.stringify(drafts));
  window.dispatchEvent(new Event(CHANGE));
}

export function useReviewDrafts(): ReviewDraft[] {
  const [drafts, setDrafts] = useState<ReviewDraft[]>([]);
  useEffect(() => {
    const refresh = () => setDrafts(readReviewDrafts());
    refresh();
    window.addEventListener(CHANGE, refresh);
    window.addEventListener("storage", refresh);
    return () => { window.removeEventListener(CHANGE, refresh); window.removeEventListener("storage", refresh); };
  }, []);
  return drafts;
}

export function saveSuggestedRequirement(result: AdvisorResult, option: Option): string {
  const id = `${result.run_id}-${option.option_id}`;
  const drafts = readReviewDrafts();
  if (drafts.some((draft) => draft.id === id)) return id;
  const request = result.packet.request;
  try { window.sessionStorage.setItem("bmw-pdl:filters:requirements:model", JSON.stringify(request.model_code)); } catch { /* navigation still works */ }
  const evidence_ids = Array.from(new Set(option.customer_case.flatMap((claim) => claim.evidence_ids)));
  drafts.unshift({
    id, source_run_id: result.run_id, option_id: option.option_id,
    model_code: request.model_code, market: request.market, powertrain: request.powertrain,
    title: option.title, proposal: option.proposal,
    customer_outcome: option.customer_case[0]?.text || option.proposal,
    evidence_ids, created_at: new Date().toISOString(), status: "pending",
    reviewer_id: null, rationale: null, reviewed_at: null,
  });
  writeDrafts(drafts);
  return id;
}

export function decideSuggestedRequirement(id: string, status: "approved" | "rejected", reviewer: string, rationale: string): boolean {
  if (!reviewer.trim() || rationale.trim().length < 5) return false;
  const drafts = readReviewDrafts();
  const index = drafts.findIndex((draft) => draft.id === id);
  if (index < 0) return false;
  drafts[index] = { ...drafts[index]!, status, reviewer_id: reviewer.trim(),
    rationale: rationale.trim(), reviewed_at: new Date().toISOString() };
  writeDrafts(drafts);
  return true;
}
