import "server-only";

import { readFile } from "node:fs/promises";
import path from "node:path";

import { SUBTOPIC_ALIASES } from "@/lib/domain/contracts";
import type {
  PlanningContextSource,
  PolicyVersion,
  ProcessedEvidence,
  SuccessorProposalFile,
  ResearchRun,
  VehicleProfile,
  WebResearchSeedRecord,
} from "@/lib/domain/contracts";
import { hashString } from "@/lib/domain/scoring";
import type { Dataset, EvidenceItem, MarketCode } from "@/lib/domain/model";
import { MARKETS } from "@/lib/domain/model";
import { buildRequirements } from "./requirements";
import { groundedEvidence, groundedGraph } from "./grounded";
import { loadLiveSnapshot } from "./live";

/**
 * Repository root. The web app lives in <repo>/web, so the default is the
 * parent of the working directory. Override with BMW_REPO_ROOT.
 */
const repoRoot = () => process.env.BMW_REPO_ROOT ?? path.resolve(process.cwd(), "..");

const FILES = {
  policy: "configs/exploratory_equal_v1.json",
  profile: "configs/g60.json",
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
  profile_id: "g60_us_feedback_mvp",
  revision: 1,
  model_family: "G60",
  countries: ["US"],
  powertrains: ["ICE", "PHEV", "BEV"],
  domain_applicability: {},
  powertrain_aliases: {},
  alias_assumptions: {},
  planning_date: "2026-10-10",
  launch_window: null,
  objectives: [],
  uncovered_regions: ["CN"],
  notes: [],
};

function toMarket(code: string | null | undefined): MarketCode {
  const upper = (code ?? "").toUpperCase();
  if ((MARKETS as readonly string[]).includes(upper)) return upper as MarketCode;
  if (["FR", "IT", "ES", "NL", "AT", "CH", "BE", "SE", "PL", "UK", "GB", "EUROPE", "EU"].includes(upper)) return "EU";
  return "DE";
}

function externalToItem(record: ProcessedEvidence): EvidenceItem {
  return {
    id: record.evidence_id,
    kind: "external_claim",
    provenance: "pipeline",
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
    locator: `chars ${record.source_start_char}–${record.source_end_char}`,
    quality: record.source_quality,
    independence_group: record.independence_group,
    duplicate_of: record.duplicate_of,
    published_at: record.published_at,
    retrieved_at: record.retrieved_at,
    numeric_value: record.numeric_value,
    numeric_unit: record.numeric_unit,
    limitation: null,
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
    quality: null,
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
    quality: null,
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
  const runs = await readJsonl<ResearchRun>(await firstExisting("metadata/research_runs.jsonl"), status);
  const live = await loadLiveSnapshot(repoRoot());
  status.push({
    path: "Configured private evidence database · US G60",
    records: live.available ? live.eligible_feedback_records || 0 : 0,
    status: live.available ? "loaded" : "missing",
  });
  const signals = live.available ? live.signals || [] : [];
  const anchors = live.available ? live.feedback || [] : [];
  const resolvedAnchors = new Set(anchors.map((record) => record.source_record_id));
  const requirements = live.available
    ? buildRequirements(proposals, signals, live.eligible_feedback_records || 0, resolvedAnchors)
    : [];
  const graph = groundedGraph(requirements, signals);

  const evidence: EvidenceItem[] = [
    ...groundedEvidence(signals, anchors),
    ...pipeline.map(externalToItem),
    ...seeds.map(seedToItem),
    ...context.map(contextToItem),
  ];

  return {
    generated_at: new Date().toISOString(),
    vehicle: { family: "BMW 5 Series", generation: "G60", successor_label: "G60 → Successor", horizon: proposals.planning_window },
    planning: { version: proposals.version, status: proposals.status, window: proposals.planning_window, primary_market: "US" },
    policy,
    profile,
    planning_context: context,
    evidence,
    hypotheses: graph.hypotheses,
    findings: graph.findings,
    requirements,
    model_coverage: live.available ? live.model_coverage || [] : [],
    benchmark: [],
    audit: [],
    research_runs: runs,
    data_notes: [
      live.available
        ? `${live.eligible_feedback_records} unique US G60 feedback IDs and ${signals.length} extracted signals loaded read-only from the ${live.backend} database.`
        : `Customer evidence unavailable: ${live.reason || "database not configured"} Draft requirements are hidden until their anchors resolve.`,
      "Successor proposals and factor ratings are assistant-authored drafts, not verified customer needs or PM judgements.",
      "Extracted spans have source locators; their relevance to each proposed outcome still needs human assessment.",
      "Curated web seeds are discovery context, not verified competitor comparisons.",
      "PM actions made in this web workbench are browser-local and are not written to the shared evidence database.",
    ],
    source_files: status,
  };
}
