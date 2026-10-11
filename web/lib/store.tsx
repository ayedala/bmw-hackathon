"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import type {
  AuditEvent,
  Decision,
  DecisionAction,
  EvidenceLinkJudgment,
  PriorityAssessment,
  PriorityFactors,
  PriorityPolicy,
  RequirementRevision,
} from "@/lib/domain/contracts";
import type { Confidence } from "@/lib/domain/derive";
import { CRPS_POLICY_VERSION, evaluateCrps, type CrpsAssessment, type CrpsInputs } from "@/lib/domain/crps";
import type { Dataset, EvidenceItem, Finding, Hypothesis, MarketCode, RequirementBundle } from "@/lib/domain/model";
import { MARKETS } from "@/lib/domain/model";
import { DEFAULT_PRIORITY_POLICY, hashString, normalisePolicy, priorityScore } from "@/lib/domain/scoring";

/* ------------------------------------------------------------------ */
/* Local session overlay                                               */
/* ------------------------------------------------------------------ */

export interface ChallengeRecord {
  challenge_id: string;
  display_id: string;
  requirement_revision: number;
  statement: string;
  factors_before: PriorityFactors;
  factors_after: PriorityFactors;
  excluded_evidence_ids: string[];
  gaps: string[];
  score_before: number;
  score_after: number;
  confidence_before: Confidence;
  confidence_after: Confidence;
  assessment_id: string;
  recorded_at: string;
}

interface Overlay {
  version: 3;
  revisions: Record<string, RequirementRevision[]>;
  assessments: Record<string, PriorityAssessment[]>;
  crpsAssessments: Record<string, CrpsAssessment[]>;
  decisions: Record<string, Decision[]>;
  judgments: EvidenceLinkJudgment[];
  challenges: ChallengeRecord[];
  audit: AuditEvent[];
}

const EMPTY: Overlay = { version: 3, revisions: {}, assessments: {}, crpsAssessments: {}, decisions: {}, judgments: [], challenges: [], audit: [] };
const OVERLAY_KEY = "bmw-pdl:session:v2";
const MARKET_KEY = "bmw-pdl:market";
const WEIGHTS_KEY = "bmw-pdl:weights";
const ACTOR_KEY = "bmw-pdl:actor";
export const DEFAULT_ACTOR = "pm.demo";
/** Slider values 0–100; normalised before use. Defaults equal PriorityPolicy(). */
export const DEFAULT_WEIGHTS: PriorityPolicy = { impact: 35, evidence: 25, relevance: 25, uncertainty: 15 };

function readStorage<T>(key: string, fallback: T, storage: "local" | "session" = "local"): T {
  try {
    const store = storage === "local" ? window.localStorage : window.sessionStorage;
    const raw = store.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}

function writeStorage(key: string, value: unknown, storage: "local" | "session" = "local") {
  try {
    const store = storage === "local" ? window.localStorage : window.sessionStorage;
    store.setItem(key, JSON.stringify(value));
  } catch {
    /* storage unavailable; the session still works in memory */
  }
}

async function sha256(text: string): Promise<string> {
  try {
    const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
    return Array.from(new Uint8Array(digest))
      .map((b) => b.toString(16).padStart(2, "0"))
      .join("");
  } catch {
    return hashString(text).padEnd(64, "0");
  }
}

const fmt = (n: number) => n.toFixed(1);

/* ------------------------------------------------------------------ */
/* Context                                                             */
/* ------------------------------------------------------------------ */

type EventDraft = Pick<AuditEvent, "action" | "object_type" | "object_id" | "object_revision" | "reason"> &
  Partial<Pick<AuditEvent, "before_hash" | "after_hash" | "run_id">>;

interface StoreValue {
  dataset: Dataset;
  market: MarketCode;
  setMarket: (m: MarketCode) => void;
  /** Raw what-if weights (0–100 sliders). */
  weights: PriorityPolicy;
  setWeights: (w: PriorityPolicy) => void;
  /** Normalised policy used for every score shown. */
  policy: PriorityPolicy;
  weightsAreDefault: boolean;
  actorId: string;
  setActorId: (id: string) => void;
  requirements: RequirementBundle[];
  evidenceById: Map<string, EvidenceItem>;
  hypothesesById: Map<string, Hypothesis>;
  findingsById: Map<string, Finding>;
  requirementByDisplayId: Map<string, RequirementBundle>;
  audit: AuditEvent[];
  challenges: ChallengeRecord[];
  judgments: EvidenceLinkJudgment[];
  crpsAssessments: Record<string, CrpsAssessment[]>;
  sessionEventCount: number;
  hydrated: boolean;
  recordDecision: (displayId: string, action: Exclude<DecisionAction, "edit" | "challenge">, rationale: string) => Promise<void>;
  editRequirement: (
    displayId: string,
    patch: Pick<RequirementRevision, "title" | "customer_outcome" | "acceptance_proposal">,
    rationale: string,
  ) => Promise<void>;
  saveAssessment: (displayId: string, factors: PriorityFactors, rationale: string) => Promise<PriorityAssessment>;
  saveCrpsAssessment: (displayId: string, inputs: CrpsInputs, rationale: string) => Promise<CrpsAssessment>;
  submitChallenge: (
    record: Omit<ChallengeRecord, "challenge_id" | "recorded_at" | "assessment_id" | "score_before" | "score_after">,
  ) => Promise<void>;
  judgeLink: (displayId: string, evidenceId: string, verdict: EvidenceLinkJudgment["verdict"], rationale: string) => Promise<void>;
  /** Records a non-decision action (e.g. an export) in the audit trail. */
  logAction: (action: string, objectType: string, objectId: string, reason: string) => Promise<void>;
  resetSession: () => void;
}

const StoreContext = createContext<StoreValue | null>(null);

export function StoreProvider({ dataset, children }: { dataset: Dataset; children: ReactNode }) {
  const [overlay, setOverlay] = useState<Overlay>(EMPTY);
  const [market, setMarketState] = useState<MarketCode>(dataset.planning.primary_market);
  const [weights, setWeightsState] = useState<PriorityPolicy>(DEFAULT_WEIGHTS);
  const [actorId, setActorState] = useState(DEFAULT_ACTOR);
  const [hydrated, setHydrated] = useState(false);
  const overlayRef = useRef(overlay);
  overlayRef.current = overlay;

  useEffect(() => {
    const stored = readStorage<(Omit<Overlay, "version" | "crpsAssessments"> & { version: 2 }) | Overlay | null>(OVERLAY_KEY, null);
    setOverlay(stored?.version === 3 ? stored : stored?.version === 2 ? { ...stored, version: 3, crpsAssessments: {} } : EMPTY);
    const m = readStorage<string>(MARKET_KEY, dataset.planning.primary_market);
    if ((MARKETS as readonly string[]).includes(m)) setMarketState(m as MarketCode);
    setWeightsState(readStorage<PriorityPolicy>(WEIGHTS_KEY, DEFAULT_WEIGHTS));
    setActorState(readStorage<string>(ACTOR_KEY, DEFAULT_ACTOR));
    setHydrated(true);
  }, [dataset.planning.primary_market]);

  const commit = useCallback((next: Overlay) => {
    overlayRef.current = next;
    setOverlay(next);
    writeStorage(OVERLAY_KEY, next);
  }, []);

  const setMarket = useCallback((m: MarketCode) => {
    setMarketState(m);
    writeStorage(MARKET_KEY, m);
  }, []);
  const setWeights = useCallback((w: PriorityPolicy) => {
    setWeightsState(w);
    writeStorage(WEIGHTS_KEY, w);
  }, []);
  const setActorId = useCallback((id: string) => {
    setActorState(id);
    writeStorage(ACTOR_KEY, id);
  }, []);

  const policy = useMemo(() => normalisePolicy(weights), [weights]);
  const weightsAreDefault = (Object.keys(DEFAULT_WEIGHTS) as (keyof PriorityPolicy)[]).every((k) => weights[k] === DEFAULT_WEIGHTS[k]);

  const requirements = useMemo<RequirementBundle[]>(
    () =>
      dataset.requirements.map((bundle) => ({
        ...bundle,
        revisions: [...bundle.revisions, ...(overlay.revisions[bundle.display_id] ?? [])],
        assessments: [...bundle.assessments, ...(overlay.assessments[bundle.display_id] ?? [])],
        decisions: [...bundle.decisions, ...(overlay.decisions[bundle.display_id] ?? [])],
      })),
    [dataset.requirements, overlay],
  );

  const audit = useMemo(() => [...dataset.audit, ...overlay.audit], [dataset.audit, overlay.audit]);

  const appendEvents = useCallback(
    async (base: Overlay, drafts: EventDraft[]): Promise<AuditEvent[]> => {
      const all = [...dataset.audit, ...base.audit];
      let previous = all[all.length - 1]?.event_hash ?? "0".repeat(64);
      let sequence = all.length;
      const created: AuditEvent[] = [];
      for (const draft of drafts) {
        sequence += 1;
        const body = {
          recorded_at: new Date().toISOString(),
          actor_id: actorId,
          actor_type: "human",
          action: draft.action,
          object_type: draft.object_type,
          object_id: draft.object_id,
          object_revision: draft.object_revision,
          before_hash: draft.before_hash ?? null,
          after_hash: draft.after_hash ?? null,
          reason: draft.reason,
          request_id: `ui-${Date.now().toString(36)}-${sequence}`,
          run_id: draft.run_id ?? null,
          result: "success" as const,
          monotonic_sequence: sequence,
          previous_event_hash: previous,
        };
        const event_hash = await sha256(JSON.stringify(body));
        created.push({ schema_version: "1", event_id: `evt-${event_hash.slice(0, 12)}`, ...body, event_hash });
        previous = event_hash;
      }
      return created;
    },
    [dataset.audit, actorId],
  );

  const findBundle = useCallback(
    (displayId: string) => {
      const bundle = requirements.find((b) => b.display_id === displayId);
      if (!bundle) throw new Error(`Unknown requirement ${displayId}`);
      const latest = bundle.revisions[bundle.revisions.length - 1];
      if (!latest) throw new Error(`Requirement ${displayId} has no revision`);
      return { bundle, latest };
    },
    [requirements],
  );

  const makeDecision = useCallback(
    (latest: RequirementRevision, action: DecisionAction, rationale: string, assessmentId: string | null): Decision => ({
      schema_version: "1",
      decision_id: `dec-${hashString(`${latest.requirement_id}${action}${Date.now()}`)}`,
      requirement_id: latest.requirement_id,
      requirement_revision: latest.revision,
      action,
      rationale,
      actor_id: actorId,
      role: "demo_pm",
      recorded_at: new Date().toISOString(),
      policy_revision: null,
      score_snapshot_id: assessmentId,
      expected_revision: latest.revision,
      request_id: `ui-${Date.now().toString(36)}`,
    }),
    [actorId],
  );

  const latestAssessmentId = (bundle: RequirementBundle, revision: number) =>
    bundle.assessments.filter((a) => a.requirement_revision === revision).slice(-1)[0]?.assessment_id ?? null;

  const recordDecision = useCallback<StoreValue["recordDecision"]>(
    async (displayId, action, rationale) => {
      const { bundle, latest } = findBundle(displayId);
      const base = overlayRef.current;
      const decision = makeDecision(latest, action, rationale, latestAssessmentId(bundle, latest.revision));
      const events = await appendEvents(base, [
        { action: `decision_${action}`, object_type: "requirement", object_id: displayId, object_revision: latest.revision, after_hash: decision.decision_id, reason: rationale },
      ]);
      commit({
        ...base,
        decisions: { ...base.decisions, [displayId]: [...(base.decisions[displayId] ?? []), decision] },
        audit: [...base.audit, ...events],
      });
    },
    [appendEvents, commit, findBundle, makeDecision],
  );

  const editRequirement = useCallback<StoreValue["editRequirement"]>(
    async (displayId, patch, rationale) => {
      const { latest } = findBundle(displayId);
      const base = overlayRef.current;
      const next: RequirementRevision = {
        ...latest,
        ...patch,
        revision: latest.revision + 1,
        supersedes_revision: latest.revision,
        created_by: actorId,
        created_at: new Date().toISOString(),
        lifecycle_status: "needs_review",
      };
      const decision = makeDecision(next, "edit", rationale, null);
      const events = await appendEvents(base, [
        {
          action: "requirement_edited",
          object_type: "requirement",
          object_id: displayId,
          object_revision: next.revision,
          before_hash: `r${latest.revision}`,
          after_hash: `r${next.revision}`,
          reason: `${rationale} Saved priority and approvals of r${latest.revision} do not carry over.`,
        },
      ]);
      commit({
        ...base,
        revisions: { ...base.revisions, [displayId]: [...(base.revisions[displayId] ?? []), next] },
        decisions: { ...base.decisions, [displayId]: [...(base.decisions[displayId] ?? []), decision] },
        audit: [...base.audit, ...events],
      });
    },
    [actorId, appendEvents, commit, findBundle, makeDecision],
  );

  const buildAssessment = useCallback(
    (bundle: RequirementBundle, latest: RequirementRevision, factors: PriorityFactors, rationale: string): PriorityAssessment => {
      const sequence = bundle.assessments.filter((a) => a.requirement_revision === latest.revision).length + 1;
      return {
        assessment_id: `priority_${hashString(`${latest.requirement_id}${Date.now()}${sequence}`)}`,
        requirement_id: latest.requirement_id,
        requirement_revision: latest.revision,
        sequence,
        factors,
        policy,
        score: priorityScore(factors, policy),
        actor_id: actorId,
        rationale,
        recorded_at: new Date().toISOString(),
        request_id: `ui-${Date.now().toString(36)}`,
        interpretation: "Declared PM judgement, not measured customer prevalence or calibrated confidence.",
      };
    },
    [actorId, policy],
  );

  const saveAssessment = useCallback<StoreValue["saveAssessment"]>(
    async (displayId, factors, rationale) => {
      const { bundle, latest } = findBundle(displayId);
      const base = overlayRef.current;
      const assessment = buildAssessment(bundle, latest, factors, rationale);
      const events = await appendEvents(base, [
        {
          action: "set_priority",
          object_type: "requirement",
          object_id: displayId,
          object_revision: latest.revision,
          after_hash: assessment.assessment_id,
          reason: `Legacy planning score ${fmt(assessment.score)} (impact ${factors.impact}, evidence ${factors.evidence}, market fit ${factors.relevance}, uncertainty ${factors.uncertainty}). ${rationale}`,
        },
      ]);
      commit({
        ...base,
        assessments: { ...base.assessments, [displayId]: [...(base.assessments[displayId] ?? []), assessment] },
        audit: [...base.audit, ...events],
      });
      return assessment;
    },
    [appendEvents, buildAssessment, commit, findBundle],
  );

  const saveCrpsAssessment = useCallback<StoreValue["saveCrpsAssessment"]>(
    async (displayId, inputs, rationale) => {
      if (!rationale.trim() || !actorId.trim()) throw new Error("Reviewer and rationale are required.");
      const { bundle, latest } = findBundle(displayId);
      const result = evaluateCrps(inputs);
      if (!bundle.scope_markets.includes(market)) throw new Error(`Requirement is not assessed for ${market}.`);
      if (result.missing_inputs.length === 11) throw new Error("Rate at least one input before saving a framework assessment.");
      const base = overlayRef.current;
      const history = base.crpsAssessments[displayId] ?? [];
      const assessment: CrpsAssessment = {
        assessment_id: `crps_${hashString(`${latest.requirement_id}${Date.now()}${history.length}`)}`,
        requirement_id: latest.requirement_id,
        requirement_revision: latest.revision,
        sequence: history.filter((item) => item.requirement_revision === latest.revision).length + 1,
        policy_version: CRPS_POLICY_VERSION,
        inputs: structuredClone(inputs), result,
        actor_id: actorId.trim(), rationale: rationale.trim(), recorded_at: new Date().toISOString(),
      };
      const events = await appendEvents(base, [{
        action: "crps_assessment_saved", object_type: "requirement", object_id: displayId,
        object_revision: latest.revision, after_hash: await sha256(JSON.stringify(assessment)),
        reason: `Framework CRPS ${result.customer_priority.value?.toFixed(1) ?? `${result.customer_priority.lower.toFixed(1)}-${result.customer_priority.upper.toFixed(1)}`}; ${result.missing_inputs.length} missing inputs. ${assessment.rationale}`,
      }]);
      commit({ ...base, crpsAssessments: { ...base.crpsAssessments, [displayId]: [...history, assessment] }, audit: [...base.audit, ...events] });
      return assessment;
    },
    [actorId, appendEvents, commit, findBundle, market],
  );

  const submitChallenge = useCallback<StoreValue["submitChallenge"]>(
    async (record) => {
      const { bundle, latest } = findBundle(record.display_id);
      const base = overlayRef.current;
      const assessment = buildAssessment(bundle, latest, record.factors_after, `Challenge: ${record.statement}`);
      const challenge: ChallengeRecord = {
        ...record,
        challenge_id: `CHL-${hashString(record.statement + Date.now()).slice(0, 6).toUpperCase()}`,
        recorded_at: new Date().toISOString(),
        assessment_id: assessment.assessment_id,
        score_before: priorityScore(record.factors_before, policy),
        score_after: assessment.score,
      };
      const decision = makeDecision(latest, "challenge", record.statement, assessment.assessment_id);
      const changed = (Object.keys(record.factors_after) as (keyof PriorityFactors)[]).filter((k) => record.factors_after[k] !== record.factors_before[k]);
      const drafts: EventDraft[] = [
        { action: "challenge_created", object_type: "requirement", object_id: record.display_id, object_revision: latest.revision, after_hash: challenge.challenge_id, reason: record.statement },
      ];
      if (record.excluded_evidence_ids.length > 0) {
        drafts.push({ action: "evidence_excluded", object_type: "challenge", object_id: challenge.challenge_id, object_revision: null, reason: `Excluded from this challenge: ${record.excluded_evidence_ids.join(", ")}` });
      }
      drafts.push({
        action: "set_priority",
        object_type: "requirement",
        object_id: record.display_id,
        object_revision: latest.revision,
        after_hash: assessment.assessment_id,
        reason: `Legacy planning score ${fmt(challenge.score_before)} → ${fmt(challenge.score_after)} after ${challenge.challenge_id}${changed.length ? ` (${changed.map((k) => `${k} ${record.factors_before[k]}→${record.factors_after[k]}`).join(", ")})` : ""}.`,
      });
      const events = await appendEvents(base, drafts);
      commit({
        ...base,
        assessments: { ...base.assessments, [record.display_id]: [...(base.assessments[record.display_id] ?? []), assessment] },
        decisions: { ...base.decisions, [record.display_id]: [...(base.decisions[record.display_id] ?? []), decision] },
        challenges: [...base.challenges, challenge],
        audit: [...base.audit, ...events],
      });
    },
    [appendEvents, buildAssessment, commit, findBundle, makeDecision, policy],
  );

  const judgeLink = useCallback<StoreValue["judgeLink"]>(
    async (displayId, evidenceId, verdict, rationale) => {
      const { latest } = findBundle(displayId);
      const base = overlayRef.current;
      const judgment: EvidenceLinkJudgment = {
        schema_version: "1",
        judgment_id: `judgment_${hashString(`${displayId}${evidenceId}${Date.now()}`)}`,
        requirement_id: latest.requirement_id,
        requirement_revision: latest.revision,
        signal_id: evidenceId,
        verdict,
        rationale,
        actor_id: actorId,
        recorded_at: new Date().toISOString(),
        request_id: `ui-${Date.now().toString(36)}`,
      };
      const events = await appendEvents(base, [
        {
          action: "assess_evidence_link",
          object_type: "requirement",
          object_id: displayId,
          object_revision: latest.revision,
          after_hash: judgment.judgment_id,
          reason: `${evidenceId}: ${verdict.replace(/_/g, " ")}. ${rationale}`,
        },
      ]);
      commit({ ...base, judgments: [...base.judgments, judgment], audit: [...base.audit, ...events] });
    },
    [actorId, appendEvents, commit, findBundle],
  );

  const logAction = useCallback<StoreValue["logAction"]>(
    async (action, objectType, objectId, reason) => {
      const base = overlayRef.current;
      const events = await appendEvents(base, [{ action, object_type: objectType, object_id: objectId, object_revision: null, reason }]);
      commit({ ...base, audit: [...base.audit, ...events] });
    },
    [appendEvents, commit],
  );

  const resetSession = useCallback(() => commit(EMPTY), [commit]);

  const value = useMemo<StoreValue>(
    () => ({
      dataset,
      market,
      setMarket,
      weights,
      setWeights,
      policy,
      weightsAreDefault,
      actorId,
      setActorId,
      requirements,
      evidenceById: new Map(dataset.evidence.map((e) => [e.id, e])),
      hypothesesById: new Map(dataset.hypotheses.map((h) => [h.id, h])),
      findingsById: new Map(dataset.findings.map((f) => [f.id, f])),
      requirementByDisplayId: new Map(requirements.map((r) => [r.display_id, r])),
      audit,
      challenges: overlay.challenges,
      judgments: overlay.judgments,
      crpsAssessments: overlay.crpsAssessments,
      sessionEventCount: overlay.audit.length,
      hydrated,
      recordDecision,
      editRequirement,
      saveAssessment,
      saveCrpsAssessment,
      submitChallenge,
      judgeLink,
      logAction,
      resetSession,
    }),
    [
      dataset, market, setMarket, weights, setWeights, policy, weightsAreDefault, actorId, setActorId, requirements, audit, overlay, hydrated,
      recordDecision, editRequirement, saveAssessment, saveCrpsAssessment, submitChallenge, judgeLink, logAction, resetSession,
    ],
  );

  return <StoreContext.Provider value={value}>{children}</StoreContext.Provider>;
}

export function useStore(): StoreValue {
  const value = useContext(StoreContext);
  if (!value) throw new Error("useStore must be used inside StoreProvider");
  return value;
}

/** Latest judgement per evidence ID for a requirement's current revision. */
export function judgmentsFor(judgments: EvidenceLinkJudgment[], requirementId: string, revision: number) {
  const map = new Map<string, EvidenceLinkJudgment>();
  for (const j of judgments) if (j.requirement_id === requirementId && j.requirement_revision === revision) map.set(j.signal_id, j);
  return map;
}

/** Page filters that survive navigating away and back (sessionStorage). */
export function usePersistentState<T>(key: string, initial: T): [T, (value: T | ((prev: T) => T)) => void] {
  const [state, setState] = useState<T>(initial);
  useEffect(() => {
    setState(readStorage<T>(`bmw-pdl:filters:${key}`, initial, "session"));
    // initial is a stable literal at call sites
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  const update = useCallback(
    (value: T | ((prev: T) => T)) => {
      setState((prev) => {
        const next = typeof value === "function" ? (value as (p: T) => T)(prev) : value;
        writeStorage(`bmw-pdl:filters:${key}`, next, "session");
        return next;
      });
    },
    [key],
  );
  return [state, update];
}

export { DEFAULT_PRIORITY_POLICY };
