import "server-only";

import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import path from "node:path";

import { SUBTOPIC_ALIASES } from "@/lib/domain/contracts";
import type {
  AuditEvent,
  PlanningContextSource,
  PolicyVersion,
  ProcessedEvidence,
  SuccessorProposalFile,
  ResearchRun,
  VehicleProfile,
  WebResearchSeedRecord,
} from "@/lib/domain/contracts";
import { FACTOR_LABEL } from "@/lib/domain/derive";
import { DEFAULT_PRIORITY_POLICY, hashString, priorityScore } from "@/lib/domain/scoring";
import type { Dataset, EvidenceItem, MarketCode, RequirementBundle } from "@/lib/domain/model";
import { MARKETS } from "@/lib/domain/model";
import type {
  ArtifactCustomerNeed,
  ArtifactFinding,
  ArtifactRequirement,
  ArtifactRequirementScore,
} from "@/lib/domain/reasoning";
import { buildReasoningGraph } from "@/lib/domain/reasoning";
import { SYNTHETIC_EXTERNAL } from "./fixtures/external";
import { feedbackEvidence, SYNTHETIC_SIGNALS } from "./fixtures/feedback";
import { BENCHMARK, FINDINGS, HYPOTHESES } from "./fixtures/graph";
import { anchorEvidence } from "./fixtures/anchors";
import { buildRequirements } from "./fixtures/requirements";

/**
 * Repository root. The web app lives in <repo>/web, so the default is the
 * parent of the working directory. Override with BMW_REPO_ROOT.
 */
const repoRoot = () => process.env.BMW_REPO_ROOT ?? path.resolve(process.cwd(), "..");

const FILES = {
  policy: "configs/exploratory_equal_v1.json",
  profile: "configs/g60_de_2030.json",
  proposals: "configs/successor_proposals_v1.json",
  context: "configs/planning_public_context.json",
  seeds: "research/web_evidence_seed.jsonl",
} as const;

/** The web-research pipeline moved into src/bmw_pm/data_pipeline on main; older checkouts keep data at the legacy path. */
const PIPELINE_DIRS = ["src/bmw_pm/data_pipeline/web_research/data", "external_research_pipeline/data"] as const;

async function firstExisting(relativeFile: string): Promise<string> {
  for (const dir of PIPELINE_DIRS) {
    const candidate = `${dir}/${relativeFile}`;
    if ((await readText(candidate)) !== null) return candidate;
  }
  return `${PIPELINE_DIRS[0]}/${relativeFile}`;
}

type FileStatus = Dataset["source_files"][number];

async function readText(relative: string): Promise<string | null> {
  try {
    return await readFile(path.join(repoRoot(), relative), "utf8");
  } catch {
    return null;
  }
}

async function readJsonl<T>(relative: string, status: FileStatus[]): Promise<T[]> {
  const text = await readText(relative);
  if (text === null) {
    status.push({ path: relative, records: 0, status: "missing" });
    return [];
  }
  const rows: T[] = [];
  let invalid = 0;
  for (const line of text.split("\n")) {
    if (!line.trim()) continue;
    try {
      rows.push(JSON.parse(line) as T);
    } catch {
      invalid += 1;
    }
  }
  status.push({ path: relative, records: rows.length, status: invalid > 0 && rows.length === 0 ? "invalid" : "loaded" });
  return rows;
}

async function readJson<T>(relative: string, fallback: T, status: FileStatus[]): Promise<T> {
  const text = await readText(relative);
  if (text === null) {
    status.push({ path: relative, records: 0, status: "missing" });
    return fallback;
  }
  try {
    const parsed = JSON.parse(text) as T;
    status.push({ path: relative, records: 1, status: "loaded" });
    return parsed;
  } catch {
    status.push({ path: relative, records: 0, status: "invalid" });
    return fallback;
  }
}

const FALLBACK_POLICY: PolicyVersion = {
  schema_version: "1",
  policy_id: "exploratory_equal",
  revision: 1,
  name: "Exploratory equal-weight policy (unapproved)",
  criteria: {
    customer_impact: { dimension: "customer", weight: 0.25, anchor_0: "No demonstrated improvement", anchor_4: "Material improvement to a repeatedly blocked core use case" },
    evidence_backed_reach: { dimension: "customer", weight: 0.25, anchor_0: "No observed affected eligible records", anchor_4: "Mention share reaches saturation point" },
    strategic_contribution: { dimension: "business", weight: 0.25, anchor_0: "No contribution to an agreed objective", anchor_4: "Strong direct contribution to an approved objective" },
    competitive_outlook_need: { dimension: "business", weight: 0.25, anchor_0: "Verified adequate position", anchor_4: "Material matched gap or scenario pressure" },
  },
  saturation_share: 0.05,
  unknown_rule: "Missing dimensions retain their weight and contribute [0, 4] scenario bounds; known weights are not renormalized.",
  approved: false,
  elicitation_record: "Seed policy for exploration only.",
};

const FALLBACK_PROFILE: VehicleProfile = {
  schema_version: "1",
  profile_id: "g60_de_2030",
  revision: 1,
  model_family: "G60",
  countries: ["DE"],
  powertrains: ["ICE", "PHEV", "BEV", "BEVE"],
  domain_applicability: {},
  powertrain_aliases: {},
  alias_assumptions: {},
  planning_date: "2026-10-11",
  launch_window: "2030",
  objectives: [],
  uncovered_regions: ["CN", "US"],
  notes: ["Fallback profile; configs/g60_de_2030.json was not readable."],
};

function toMarket(code: string | null | undefined): MarketCode {
  const upper = (code ?? "").toUpperCase();
  if ((MARKETS as readonly string[]).includes(upper)) return upper as MarketCode;
  if (["FR", "IT", "ES", "NL", "AT", "CH", "BE", "SE", "PL", "UK", "GB", "EUROPE", "EU"].includes(upper)) return "EU";
  return "DE";
}

function externalToItem(record: ProcessedEvidence, provenance: "pipeline" | "synthetic"): EvidenceItem {
  return {
    id: record.evidence_id,
    kind: "external_claim",
    provenance,
    claim: record.claim,
    excerpt: record.evidence_text,
    excerpt_language: /[äöüßÄÖÜ]|\b(der|die|das|mit|und|nicht|noch)\b/.test(record.evidence_text) ? "de" : "en",
    brand: record.brand,
    vehicle: record.vehicle,
    market: toMarket(record.market),
    topic: record.topic,
    subtopic: SUBTOPIC_ALIASES[record.subtopic] ?? record.subtopic,
    source_name: record.source_name,
    source_title: record.source_title,
    source_url: record.source_url || null,
    source_family: record.source_family,
    locator:
      provenance === "pipeline"
        ? `chars ${record.source_start_char}–${record.source_end_char}`
        : "No locator (not captured by pipeline)",
    quality: record.source_quality,
    independence_group: record.independence_group,
    duplicate_of: record.duplicate_of,
    published_at: record.published_at,
    retrieved_at: record.retrieved_at,
    numeric_value: record.numeric_value,
    numeric_unit: record.numeric_unit,
    limitation: provenance === "synthetic" ? "Synthetic illustration; value not span-verified." : null,
    raw: record,
  };
}

const SEED_TOPIC: Record<string, { topic: EvidenceItem["topic"]; subtopic: string }> = {
  "seed-W01-01": { topic: "comfort", subtopic: "rear_seat_space" },
  "seed-W03-01": { topic: "range", subtopic: "real_world_range" },
  "seed-W03-02": { topic: "infotainment", subtopic: "climate_control_interaction" },
  "seed-W04-01": { topic: "charging", subtopic: "charging_time" },
  "seed-W05-01": { topic: "infotainment", subtopic: "physical_controls" },
};

const QUALITY_BY_METHOD: Record<string, number> = {
  independent_instrumented_test: 90,
  manufacturer_specification: 80,
  manufacturer_product_description: 70,
  assessment_body_announcement: 85,
  expert_usability_opinion: 70,
};

const FAMILY_BY_METHOD: Record<string, EvidenceItem["source_family"]> = {
  independent_instrumented_test: "independent_test_org",
  manufacturer_specification: "official_manufacturer",
  manufacturer_product_description: "official_manufacturer",
  assessment_body_announcement: "independent_test_org",
  expert_usability_opinion: "independent_test_org",
};

function seedToItem(seed: WebResearchSeedRecord): EvidenceItem {
  const mapped = SEED_TOPIC[seed.seed_id] ?? { topic: "market_trend" as const, subtopic: "future_customer_expectation" };
  const scope = seed.scope;
  const vehicle = String(scope.model ?? scope.family ?? "Segment context");
  const market = toMarket(String(scope.market ?? scope.region ?? ""));
  let host = seed.url;
  try {
    host = new URL(seed.url).hostname.replace(/^www\./, "");
  } catch {
    /* keep raw url as name */
  }
  return {
    id: seed.seed_id,
    kind: "external_claim",
    provenance: "curated_seed",
    claim: seed.claim,
    excerpt: seed.section,
    excerpt_language: /[äöüß]|\b(Die|Der|mit)\b/.test(seed.section) ? "de" : "en",
    brand: vehicle.includes("EQE") ? "Mercedes-Benz" : vehicle.includes("BMW") || vehicle.includes("5 Series") ? "BMW" : "—",
    vehicle,
    market,
    topic: mapped.topic,
    subtopic: mapped.subtopic,
    source_name: host,
    source_title: seed.section,
    source_url: seed.url,
    source_family: FAMILY_BY_METHOD[seed.claim_method] ?? "other",
    locator: `section: ${seed.section}`,
    quality: QUALITY_BY_METHOD[seed.claim_method] ?? 50,
    independence_group: `SEED-${seed.source_id}`,
    duplicate_of: null,
    published_at: seed.publication_date,
    retrieved_at: `${seed.retrieved_on}T00:00:00Z`,
    numeric_value: typeof seed.value === "number" ? seed.value : null,
    numeric_unit: seed.unit ?? null,
    limitation: seed.limitation,
    raw: seed,
  };
}

/** Builds AuditEvent records with the same hash-chain fields as bmw_pm.storage. */
function buildSeedAudit(bundles: RequirementBundle[], evidenceCount: number, runs: ResearchRun[]): AuditEvent[] {
  type Draft = Omit<AuditEvent, "schema_version" | "event_id" | "monotonic_sequence" | "previous_event_hash" | "event_hash">;
  const drafts: Draft[] = [];
  const lastRun = runs[runs.length - 1];
  if (lastRun) {
    drafts.push({
      recorded_at: lastRun.finished_at ?? lastRun.started_at,
      actor_id: "external_research_pipeline",
      actor_type: "pipeline",
      action: "research_run_completed",
      object_type: "research_run",
      object_id: lastRun.run_id,
      object_revision: null,
      before_hash: null,
      after_hash: null,
      reason: `Topic ${lastRun.topic}: ${lastRun.evidence_records_created} evidence records created, ${lastRun.firecrawl_scrape_calls} pages scraped.`,
      request_id: lastRun.run_id,
      run_id: lastRun.run_id,
      result: "success",
    });
  }
  drafts.push({
    recorded_at: "2026-10-10T14:20:00Z",
    actor_id: "web.adapter",
    actor_type: "pipeline",
    action: "evidence_imported",
    object_type: "evidence_store",
    object_id: "external_evidence.jsonl",
    object_revision: null,
    before_hash: null,
    after_hash: null,
    reason: `${evidenceCount} external evidence records available to the workspace.`,
    request_id: "seed-import",
    run_id: null,
    result: "success",
  });
  for (const bundle of bundles) {
    const rev = bundle.revisions[0];
    if (!rev) continue;
    drafts.push({
      recorded_at: "2026-10-10T14:22:00Z",
      actor_id: "pipeline:baseline_no_ai",
      actor_type: "pipeline",
      action: "requirement_generated",
      object_type: "requirement",
      object_id: bundle.display_id,
      object_revision: 1,
      before_hash: null,
      after_hash: null,
      reason: `Candidate generated from ${rev.support_count} supporting feedback IDs.`,
      request_id: `seed-gen-${bundle.display_id}`,
      run_id: "run-demo-baseline-20261010",
      result: "success",
    });
  }
  for (const bundle of bundles) {
    const f = bundle.proposal.factors;
    const score = priorityScore(f, DEFAULT_PRIORITY_POLICY);
    drafts.push({
      recorded_at: "2026-10-10T14:27:00Z",
      actor_id: "successor_us_g60_v1",
      actor_type: "pipeline",
      action: "seed_priority_loaded",
      object_type: "requirement",
      object_id: bundle.display_id,
      object_revision: 1,
      before_hash: null,
      after_hash: null,
      reason: `Illustrative seed CRPS ${score.toFixed(1)} under default weights (${(Object.keys(f) as (keyof typeof f)[]).map((k) => `${FACTOR_LABEL[k]} ${f[k]}`).join(", ")}).`,
      request_id: `seed-score-${bundle.display_id}`,
      run_id: null,
      result: "success",
    });
  }
  for (const bundle of bundles) {
    for (const decision of bundle.decisions) {
      drafts.push({
        recorded_at: decision.recorded_at,
        actor_id: decision.actor_id,
        actor_type: "human",
        action: `decision_${decision.action}`,
        object_type: "requirement",
        object_id: bundle.display_id,
        object_revision: decision.requirement_revision,
        before_hash: null,
        after_hash: decision.decision_id,
        reason: decision.rationale,
        request_id: decision.request_id,
        run_id: null,
        result: "success",
      });
    }
  }
  drafts.sort((a, b) => a.recorded_at.localeCompare(b.recorded_at));
  const events: AuditEvent[] = [];
  let previous = "0".repeat(64);
  drafts.forEach((draft, index) => {
    const body = { ...draft, monotonic_sequence: index + 1, previous_event_hash: previous };
    const event_hash = createHash("sha256").update(JSON.stringify(body)).digest("hex");
    events.push({
      schema_version: "1",
      event_id: `evt-${event_hash.slice(0, 12)}`,
      ...body,
      event_hash,
    });
    previous = event_hash;
  });
  return events;
}

const EMPTY_PROPOSALS: SuccessorProposalFile = { version: "missing", status: "configs/successor_proposals_v1.json not found", planning_window: "2029-2031", proposals: [] };

const CONTEXT_META: Record<string, { family: EvidenceItem["source_family"]; topic: EvidenceItem["topic"]; subtopic: string; market: MarketCode; vehicle: string; brand: string }> = {
  "adac.de": { family: "independent_test_org", topic: "range", subtopic: "real_world_range", market: "DE", vehicle: "i5 eDrive40", brand: "BMW" },
  "mbusa.com": { family: "official_manufacturer", topic: "charging", subtopic: "route_planning", market: "US", vehicle: "EQE 320 4MATIC Sedan", brand: "Mercedes-Benz" },
  "iea.org": { family: "market_report", topic: "market_trend", subtopic: "adoption_trend", market: "EU", vehicle: "Global EV market", brand: "—" },
};

function contextToItem(source: PlanningContextSource): EvidenceItem {
  let host = source.url;
  try {
    host = new URL(source.url).hostname.replace(/^www\./, "");
  } catch {
    /* keep raw url */
  }
  const meta = CONTEXT_META[host] ?? { family: "other" as const, topic: "market_trend" as const, subtopic: "customer_expectation", market: "US" as const, vehicle: "—", brand: "—" };
  const id = host.startsWith("adac") ? "ctx-adac-i5" : host.startsWith("mbusa") ? "ctx-mbusa-eqe" : host.startsWith("iea") ? "ctx-iea-gevo" : `ctx-${hashString(source.url)}`;
  return {
    id,
    kind: "external_claim",
    provenance: "curated_seed",
    claim: source.observation,
    excerpt: source.title,
    excerpt_language: "en",
    brand: meta.brand,
    vehicle: meta.vehicle,
    market: meta.market,
    topic: meta.topic,
    subtopic: meta.subtopic,
    source_name: host,
    source_title: source.title,
    source_url: source.url,
    source_family: meta.family,
    locator: "configs/planning_public_context.json",
    quality: meta.family === "independent_test_org" ? 90 : meta.family === "market_report" ? 80 : 75,
    independence_group: `CTX-${host}`,
    duplicate_of: null,
    published_at: null,
    retrieved_at: "2026-10-10T00:00:00Z",
    numeric_value: null,
    numeric_unit: null,
    limitation: source.use,
    raw: source as unknown as Record<string, unknown>,
  };
}

export async function loadDataset(): Promise<Dataset> {
  const status: FileStatus[] = [];
  const policy = await readJson<PolicyVersion>(FILES.policy, FALLBACK_POLICY, status);
  const profile = await readJson<VehicleProfile>(FILES.profile, FALLBACK_PROFILE, status);
  const proposals = await readJson<SuccessorProposalFile>(FILES.proposals, EMPTY_PROPOSALS, status);
  const context = await readJson<PlanningContextSource[]>(FILES.context, [], status);
  const pipeline = await readJsonl<ProcessedEvidence>(await firstExisting("processed/external_evidence.jsonl"), status);
  const seeds = await readJsonl<WebResearchSeedRecord>(FILES.seeds, status);

  // The real reasoning chain. Present on main; absent in demo checkouts, in
  // which case the fixture graph below is used and the UI says so.
  const artifactFindings = await readJsonl<ArtifactFinding>(
    await firstExisting("processed/findings.jsonl"), status);
  const artifactNeeds = await readJsonl<ArtifactCustomerNeed>(
    await firstExisting("processed/customer_needs.jsonl"), status);
  const artifactRequirements = await readJsonl<ArtifactRequirement>(
    await firstExisting("processed/requirements.jsonl"), status);
  const artifactScores = await readJsonl<ArtifactRequirementScore>(
    await firstExisting("processed/requirement_scores.jsonl"), status);
  const runs = await readJsonl<ResearchRun>(await firstExisting("metadata/research_runs.jsonl"), status);

  const evidence: EvidenceItem[] = [
    ...anchorEvidence(),
    ...pipeline.map((r) => externalToItem(r, "pipeline")),
    ...seeds.map(seedToItem),
    ...context.map(contextToItem),
    ...SYNTHETIC_EXTERNAL.map((r) => externalToItem(r, "synthetic")),
    ...feedbackEvidence(SYNTHETIC_SIGNALS),
  ];

  const requirements = buildRequirements(proposals, SYNTHETIC_SIGNALS);

  // The planning scope is whatever the loaded profile declares. Hardcoding it
  // here would let the profile and the UI disagree silently.
  const primaryMarket = toMarket(profile.countries[0]);
  const horizon = profile.launch_window ?? proposals.planning_window;

  const reasoning = buildReasoningGraph({
    evidence: pipeline,
    findings: artifactFindings,
    needs: artifactNeeds,
    requirements: artifactRequirements,
    scores: artifactScores,
  });

  return {
    generated_at: new Date().toISOString(),
    vehicle: { family: "BMW 5 Series", generation: "G60", successor_label: "G60 → Successor", horizon },
    planning: { version: proposals.version, status: proposals.status, window: horizon, primary_market: primaryMarket },
    policy,
    profile,
    planning_context: context,
    evidence,
    signals: SYNTHETIC_SIGNALS,
    hypotheses: HYPOTHESES,
    findings: FINDINGS,
    reasoning,
    requirements,
    benchmark: BENCHMARK,
    audit: buildSeedAudit(requirements, pipeline.length + seeds.length + context.length, runs),
    research_runs: runs,
    data_notes: [
      reasoning.authoritative
        ? `Reasoning chain is the real pipeline output: ${reasoning.counts.findings} findings, ` +
          `${reasoning.counts.needs} customer needs and ${reasoning.counts.requirements} requirements ` +
          `resolved against ${reasoning.counts.evidence} evidence records` +
          (reasoning.issues.length
            ? `; ${reasoning.issues.length} traceability issue(s) are reported rather than repaired.`
            : " with every reference resolving.")
        : "Reasoning artifacts (findings/customer_needs/requirements) were not found, so the demo fixture graph is shown. These are illustrations, not evidence-derived findings.",
      "Requirements are the authored successor proposals in configs/successor_proposals_v1.json; seed factor ratings are illustrative PM judgements.",
      "Anchor records (G60-xxxx) are real supplied feedback IDs; their verbatim text stays in the private bmw_pm.db.",
      "Pipeline evidence, curated seeds and planning context are read from the repository at request time.",
      "Additional customer signals and competitor specifications marked Synthetic are demo illustrations.",
      "PM assessments, decisions and link judgements made here are stored on this device, not in bmw_pm.db.",
    ],
    source_files: status,
  };
}
