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
import type { Dataset, EvidenceItem, Finding, Hypothesis, MarketCode, RequirementBundle } from "@/lib/domain/model";
import { MARKETS } from "@/lib/domain/model";
import { DEFAULT_PRIORITY_POLICY, hashString, normalisePolicy, priorityScore } from "@/lib/domain/scoring";
import {
  isReviewError,
  postDecision,
  postEdit,
  postJudgment,
  probeBackend,
  fetchAudit,
  importCanonical,
  postChallenge,
  postReassessment,
  type BackendAvailability,
  type ReviewError,
} from "@/lib/review/client";
import type { CanonicalChallenge } from "@/lib/review/contracts";

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
  version: 2;
  revisions: Record<string, RequirementRevision[]>;
  assessments: Record<string, PriorityAssessment[]>;
  decisions: Record<string, Decision[]>;
  judgments: EvidenceLinkJudgment[];
  challenges: ChallengeRecord[];
  audit: AuditEvent[];
}

const EMPTY: Overlay = { version: 2, revisions: {}, assessments: {}, decisions: {}, judgments: [], challenges: [], audit: [] };
/**
 * Stamped on any action the review service could not accept, so a browser-local
 * entry is never mistaken for an audited decision. The session overlay is a
 * demo convenience, not a record of what was decided.
 */
const SESSION_ONLY_NOTE =
  "Recorded in this browser session only: this requirement has no revision in the audited review database, so no audit event was written there.";
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
  canonicalChallenges: CanonicalChallenge[];
  auditVerification: { valid: boolean; checkpoint: string } | null;
  auditError: string | null;
  refreshBackend: () => Promise<BackendAvailability>;
  importCanonicalRequirements: (rationale: string) => Promise<boolean>;
  createChallenge: (displayId: string, hypothesis: string, rationale: string) => Promise<boolean>;
  resolveChallenge: (challenge: CanonicalChallenge, accept: boolean, rationale: string) => Promise<boolean>;
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
  sessionEventCount: number;
  hydrated: boolean;
  /**
   * Whether the Python review service is reachable, and which requirements it
   * can actually record decisions for. The browser is not the authority; when
   * a requirement is backend-backed, a refused action stays refused.
   */
  backend: BackendAvailability;
  /** True once the backend has been probed, so the UI can avoid claiming either way. */
  backendProbed: boolean;
  /** Whether this requirement's decisions are written to the audited database. */
  isBackendBacked: (displayId: string) => boolean;
  /** The last backend refusal, for the UI to show instead of a silent failure. */
  reviewError: ReviewError | null;
  clearReviewError: () => void;
  recordDecision: (displayId: string, action: Exclude<DecisionAction, "edit" | "challenge">, rationale: string) => Promise<boolean>;
  editRequirement: (
    displayId: string,
    patch: Pick<RequirementRevision, "title" | "customer_outcome" | "acceptance_proposal">,
    rationale: string,
  ) => Promise<boolean>;
  saveAssessment: (displayId: string, factors: PriorityFactors, rationale: string) => Promise<PriorityAssessment>;
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
  const [backendAudit, setBackendAudit] = useState<AuditEvent[]>([]);
  const [auditVerification, setAuditVerification] = useState<StoreValue["auditVerification"]>(null);
  const [auditError, setAuditError] = useState<string | null>(null);
  const [overlay, setOverlay] = useState<Overlay>(EMPTY);
  const [market, setMarketState] = useState<MarketCode>(dataset.planning.primary_market);
  const [weights, setWeightsState] = useState<PriorityPolicy>(DEFAULT_WEIGHTS);
  const [actorId, setActorState] = useState(DEFAULT_ACTOR);
  const [hydrated, setHydrated] = useState(false);
  const [backend, setBackend] = useState<BackendAvailability>({
    reachable: false,
    reason: "The review service has not been contacted yet.",
    statesById: new Map(),
  });
  const [backendProbed, setBackendProbed] = useState(false);
  const [reviewError, setReviewError] = useState<ReviewError | null>(null);
  const overlayRef = useRef(overlay);
  overlayRef.current = overlay;
  const backendRef = useRef(backend);
  backendRef.current = backend;

  useEffect(() => {
    const stored = readStorage<Overlay | null>(OVERLAY_KEY, null);
    setOverlay(dataset.mode === "demo" && stored && stored.version === 2 ? stored : EMPTY);
    const m = readStorage<string>(MARKET_KEY, dataset.planning.primary_market);
    if ((MARKETS as readonly string[]).includes(m)) setMarketState(m as MarketCode);
    setWeightsState(readStorage<PriorityPolicy>(WEIGHTS_KEY, DEFAULT_WEIGHTS));
    setActorState(readStorage<string>(ACTOR_KEY, DEFAULT_ACTOR));
    setHydrated(true);
  }, [dataset.mode, dataset.planning.primary_market]);

  // Ask the backend which requirements it holds. Doing this once on mount means
  // the UI can say plainly which cards produce audited decisions and which are
  // session-only, instead of presenting both as if they were the same thing.
  useEffect(() => {
    let cancelled = false;
    const ids = dataset.requirements
      .map((bundle) => bundle.revisions[bundle.revisions.length - 1]?.requirement_id)
      .filter((id): id is string => Boolean(id));
    probeBackend(ids).then((availability) => {
      if (!cancelled) {
        setBackend(availability);
        setBackendProbed(true);
      }
    });
    fetchAudit().then((result) => {
      if (cancelled) return;
      if (result.type === "audit") {
        setBackendAudit(result.events as unknown as AuditEvent[]);
        setAuditVerification({ valid: result.valid, checkpoint: result.checkpoint });
        setAuditError(null);
      } else { setAuditError(result.type === "error" ? result.message : "Unexpected audit response"); }
    });
    return () => {
      cancelled = true;
    };
  }, [dataset.requirements]);

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
      dataset.requirements.map((bundle) => {
        const state = backend.statesById.get(bundle.revisions.at(-1)?.requirement_id ?? "");
        if (bundle.canonical) return { ...bundle,
          revisions: state?.revisions?.length ? state.revisions : state?.requirement ? [state.requirement] : bundle.revisions,
          decisions: state?.decisions ?? (state?.decision ? [state.decision as unknown as Decision] : []),
          crps: state ? state.crps ?? null : bundle.crps,
          quality: state?.quality ?? bundle.quality,
        };
        return ({
        ...bundle,
        revisions: [...bundle.revisions, ...(overlay.revisions[bundle.display_id] ?? [])],
        assessments: [...bundle.assessments, ...(overlay.assessments[bundle.display_id] ?? [])],
        decisions: [...bundle.decisions, ...(overlay.decisions[bundle.display_id] ?? [])],
      }); }),
    [dataset.requirements, overlay, backend],
  );

  const audit = useMemo(() => dataset.mode === "demo" ? [...dataset.audit, ...overlay.audit] : backendAudit, [dataset.mode, dataset.audit, overlay.audit, backendAudit]);

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

  /** The backend's record for this requirement, or null when it has none. */
  const backendStateFor = useCallback(
    (displayId: string) => {
      const bundle = requirements.find((b) => b.display_id === displayId);
      const requirementId = bundle?.revisions[bundle.revisions.length - 1]?.requirement_id;
      if (!requirementId) return null;
      return backendRef.current.statesById.get(requirementId) ?? null;
    },
    [requirements],
  );

  const isBackendBacked = useCallback(
    (displayId: string) => backendStateFor(displayId) !== null,
    [backendStateFor],
  );

  /** Idempotency key. The backend refuses a reused id with a different payload. */
  const newRequestId = useCallback(() => {
    try {
      return `ui-${crypto.randomUUID()}`;
    } catch {
      return `ui-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
    }
  }, []);

  /** Re-read backend state so a later action uses the current revision. */
  const refreshBackend = useCallback(async () => {
    const ids = dataset.requirements.map((b) => b.revisions.at(-1)!.requirement_id);
    const availability = await probeBackend(ids);
    setBackend(availability);
    setBackendProbed(true);
    const trail = await fetchAudit();
    if (trail.type === "audit") {
      setBackendAudit(trail.events as unknown as AuditEvent[]);
      setAuditVerification({ valid: trail.valid, checkpoint: trail.checkpoint });
      setAuditError(null);
    } else { setAuditVerification(null); setAuditError(trail.type === "error" ? trail.message : "Unexpected audit response"); }
    return availability;
  }, [dataset.requirements]);

  const requireBackend = useCallback((displayId: string) => {
    const state = backendStateFor(displayId);
    if (!state || !backendRef.current.reachable) {
      setReviewError({ type: "error", code: "backend_unavailable", message: "Canonical review requires an imported backend revision. Import the corpus or restore the review service; no browser-only action was recorded." });
      return null;
    }
    return state;
  }, [backendStateFor]);

  const importCanonicalRequirements = useCallback(async (rationale: string) => {
    setReviewError(null);
    const result = await importCanonical({ actor_id: actorId, rationale, request_id: newRequestId() });
    if (isReviewError(result)) { setReviewError(result); return false; }
    await refreshBackend(); return true;
  }, [actorId, newRequestId, refreshBackend]);

  const createChallenge = useCallback(async (displayId: string, hypothesis: string, rationale: string) => {
    const state = requireBackend(displayId); if (!state?.revision) return false;
    setReviewError(null);
    const result = await postChallenge({ requirement_id: state.requirement_id, expected_revision: state.revision, hypothesis, rationale, actor_id: actorId, request_id: newRequestId() });
    if (isReviewError(result)) { setReviewError(result); await refreshBackend(); return false; }
    await refreshBackend(); return true;
  }, [requireBackend, actorId, newRequestId, refreshBackend]);

  const resolveChallenge = useCallback(async (challenge: CanonicalChallenge, accept: boolean, rationale: string) => {
    setReviewError(null);
    const result = await postReassessment({ challenge_id: challenge.challenge_id, requirement_id: challenge.requirement_id,
      expected_revision: challenge.requirement_revision, accept, rationale, actor_id: actorId, request_id: newRequestId() });
    if (isReviewError(result)) { setReviewError(result); await refreshBackend(); return false; }
    await refreshBackend(); return true;
  }, [actorId, newRequestId, refreshBackend]);

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
      const backendState = backendStateFor(displayId);

      if (bundle.canonical && !requireBackend(displayId)) return false;

      // Backend-backed: the review service decides. Its revision check, its
      // audit event, its decision id. A refusal is final and is surfaced
      // rather than being replaced by a local decision that looks the same.
      if (backendState?.revision !== undefined) {
        setReviewError(null);
        const result = await postDecision({
          requirement_id: backendState.requirement_id,
          expected_revision: backendState.revision,
          action,
          rationale,
          actor_id: actorId,
          request_id: newRequestId(),
          // Approval needs this acknowledgement; the rule is enforced in
          // ReviewService, which refuses the call when it is missing.
          uncertainty_acknowledged: action === "approve",
        });
        if (isReviewError(result)) {
          setReviewError(result);
          await refreshBackend();
          return false;
        }
        await refreshBackend();
        return true;
      }

      // No backend revision for this card. Record it in the session so the
      // demo still works, but say so in the trail instead of presenting a
      // browser-local entry as an audited decision.
      const base = overlayRef.current;
      const decision = makeDecision(latest, action, rationale, latestAssessmentId(bundle, latest.revision));
      const events = await appendEvents(base, [
        {
          action: `decision_${action}`,
          object_type: "requirement",
          object_id: displayId,
          object_revision: latest.revision,
          after_hash: decision.decision_id,
          reason: `${rationale} ${SESSION_ONLY_NOTE}`,
        },
      ]);
      commit({
        ...base,
        decisions: { ...base.decisions, [displayId]: [...(base.decisions[displayId] ?? []), decision] },
        audit: [...base.audit, ...events],
      });
      return true;
    },
    [actorId, appendEvents, backendStateFor, commit, findBundle, makeDecision, newRequestId, refreshBackend, requireBackend],
  );

  const editRequirement = useCallback<StoreValue["editRequirement"]>(
    async (displayId, patch, rationale) => {
      const { bundle, latest } = findBundle(displayId);
      const backendState = backendStateFor(displayId);
      if (bundle.canonical && !requireBackend(displayId)) return false;

      // Backend-backed: the service creates the immutable new revision and
      // decides which fields may change. Doing it here as well would be a
      // second implementation of the same rules.
      if (backendState?.revision !== undefined) {
        setReviewError(null);
        const result = await postEdit({
          requirement_id: backendState.requirement_id,
          expected_revision: backendState.revision,
          changes: {
            title: patch.title,
            customer_outcome: patch.customer_outcome,
            acceptance_proposal: patch.acceptance_proposal,
          },
          rationale,
          actor_id: actorId,
          request_id: newRequestId(),
        });
        if (isReviewError(result)) {
          setReviewError(result);
          await refreshBackend();
          return false;
        }
        await refreshBackend();
        return true;
      }

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
      return true;
    },
    [actorId, appendEvents, backendStateFor, commit, findBundle, makeDecision, newRequestId, refreshBackend, requireBackend],
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
      if (bundle.canonical) throw new Error("Canonical CRPS is derived by the backend; use an evidence-grounded challenge.");
      const base = overlayRef.current;
      const assessment = buildAssessment(bundle, latest, factors, rationale);
      const events = await appendEvents(base, [
        {
          action: "set_priority",
          object_type: "requirement",
          object_id: displayId,
          object_revision: latest.revision,
          after_hash: assessment.assessment_id,
          reason: `CRPS ${fmt(assessment.score)} (impact ${factors.impact}, evidence ${factors.evidence}, market fit ${factors.relevance}, uncertainty ${factors.uncertainty}). ${rationale}`,
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

  const submitChallenge = useCallback<StoreValue["submitChallenge"]>(
    async (record) => {
      const { bundle, latest } = findBundle(record.display_id);
      if (bundle.canonical) throw new Error("Canonical challenges must use backend corpus retrieval.");
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
        reason: `CRPS ${fmt(challenge.score_before)} → ${fmt(challenge.score_after)} after ${challenge.challenge_id}${changed.length ? ` (${changed.map((k) => `${k} ${record.factors_before[k]}→${record.factors_after[k]}`).join(", ")})` : ""}.`,
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
      const { bundle, latest } = findBundle(displayId);
      const backendState = backendStateFor(displayId);
      if (bundle.canonical && !requireBackend(displayId)) return;

      // Backend-backed: the service checks that the evidence really is linked
      // to this revision before accepting a judgement on it.
      if (backendState?.revision !== undefined) {
        setReviewError(null);
        const result = await postJudgment({
          requirement_id: backendState.requirement_id,
          expected_revision: backendState.revision,
          signal_id: evidenceId,
          verdict,
          rationale,
          actor_id: actorId,
          request_id: newRequestId(),
        });
        if (isReviewError(result)) {
          setReviewError(result);
          await refreshBackend();
          return;
        }
        await refreshBackend();
        return;
      }

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
    [actorId, appendEvents, backendStateFor, commit, findBundle, newRequestId, refreshBackend, requireBackend],
  );

  const logAction = useCallback<StoreValue["logAction"]>(
    async (action, objectType, objectId, reason) => {
      if (dataset.mode !== "demo") throw new Error("Canonical actions require an explicit backend audit operation.");
      const base = overlayRef.current;
      const events = await appendEvents(base, [{ action, object_type: objectType, object_id: objectId, object_revision: null, reason }]);
      commit({ ...base, audit: [...base.audit, ...events] });
    },
    [appendEvents, commit, dataset.mode],
  );

  const clearReviewError = useCallback(() => setReviewError(null), []);

  /**
   * Clears the session overlay only. Decisions the review service accepted are
   * in the audited database and are deliberately not reachable from here.
   */
  const resetSession = useCallback(() => commit(EMPTY), [commit]);

  const value = useMemo<StoreValue>(
    () => ({
      auditVerification, auditError, refreshBackend, importCanonicalRequirements, createChallenge, resolveChallenge,
      canonicalChallenges: [...backend.statesById.values()].flatMap((s) => s.challenges ?? []),
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
      backend,
      backendProbed,
      isBackendBacked,
      reviewError,
      clearReviewError,
      challenges: overlay.challenges,
      judgments: dataset.mode === "demo" ? overlay.judgments : [...backend.statesById.values()].flatMap((s) => Object.values(s.judgments ?? {}) as unknown as EvidenceLinkJudgment[]),
      sessionEventCount: overlay.audit.length,
      hydrated,
      recordDecision,
      editRequirement,
      saveAssessment,
      submitChallenge,
      judgeLink,
      logAction,
      resetSession,
    }),
    [
      dataset, market, setMarket, weights, setWeights, policy, weightsAreDefault, actorId, setActorId, requirements, audit, overlay, hydrated,
      backend, backendProbed, isBackendBacked, reviewError, clearReviewError,
      recordDecision, editRequirement, saveAssessment, submitChallenge, judgeLink, logAction, resetSession,
      auditVerification, auditError, refreshBackend, importCanonicalRequirements, createChallenge, resolveChallenge,
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
