"""Typed evidence, requirement, score and audit contracts shared across modules."""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SourceDocument(Contract):
    schema_version: str = "1"
    source_id: str
    local_or_web: Literal["local", "web"]
    original_name_or_url: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    byte_count: int = Field(ge=0)
    mime_type: str
    acquired_at: datetime
    publication_date: date | None = None
    source_type: str
    access_scope: str
    origin_family_id: str
    parser_version: str
    rights_notes: str


class WebResearchSeed(Contract):
    """A curated discovery note that is not yet a verified source claim."""

    schema_version: str = "1"
    research_id: str
    source_key: str
    source_url: str
    page_title: str
    retrieved_at: datetime
    publication_date: date | None = None
    market_code: str | None = None
    vehicle_scope: dict[str, Any] = Field(default_factory=dict)
    themes: list[str] = Field(default_factory=list)
    observation: str
    locator_hint: str
    capture_method: Literal["web_search_curated", "official_api_docs_curated"]
    verification_state: Literal["candidate_needs_snapshot"] = "candidate_needs_snapshot"
    access_notes: str
    limitations: str


class SourceLocator(Contract):
    schema_version: str = "1"
    source_id: str
    source_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    locator_type: Literal["sheet_range", "page_region", "url_span"]
    sheet: str | None = None
    cell_range: str | None = None
    page: int | None = None
    section: str | None = None
    exact_quote: str | None = None
    extracted_value: str | None = None
    normalized_text_hash: str | None = None

    @model_validator(mode="after")
    def require_locator_coordinates(self) -> "SourceLocator":
        if self.locator_type == "sheet_range" and not (self.sheet and self.cell_range):
            raise ValueError("sheet_range locators require sheet and cell_range")
        return self


class SpanMapSegment(Contract):
    clean_start: int = Field(ge=0)
    clean_end: int = Field(ge=0)
    raw_start: int = Field(ge=0)
    raw_end: int = Field(ge=0)


class TransformationLog(Contract):
    schema_version: str = "1"
    transformation_id: str
    record_id: str
    operation: str
    operation_version: str
    input_hash: str
    output_hash: str
    span_map: list[SpanMapSegment] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)


class FeedbackRecord(Contract):
    schema_version: str = "1"
    record_id: str
    source_id: str
    source_record_id: str
    raw_text_ref: str
    cleaned_text: str
    redacted_text: str
    raw_country: str | None
    country: str | None
    raw_model: str | None
    model_code: str | None
    raw_brand: str | None
    raw_sales_description: str | None
    raw_derivative: str | None
    powertrain_raw: str | None
    powertrain: str | None
    powertrain_mapping_status: Literal["exact", "assumed_alias", "unknown"]
    source_label: str | None
    author_status: None = None
    author_status_missing_reason: str = "Not supplied"
    observed_at: None = None
    observed_at_missing_reason: str = "Not supplied"
    row_locators: list[SourceLocator]
    transformation_ids: list[str]
    assumptions: list[str] = Field(default_factory=list)


class LegacyAnnotation(Contract):
    schema_version: str = "1"
    annotation_id: str
    feedback_record_id: str
    raw_feedback_type: str | None
    raw_level2_3: str | None
    raw_level2: str | None
    raw_level3: str | None
    row_locator: SourceLocator
    verification_status: Literal["supplied_unverified"] = "supplied_unverified"


class QuarantineFinding(Contract):
    source_id: str
    source_record_id: str | None
    row_numbers: list[int]
    reason: str


class FeedbackIngestionResult(Contract):
    source: SourceDocument
    input_annotation_rows: int
    input_unique_ids: int
    records: list[FeedbackRecord]
    annotations: list[LegacyAnnotation]
    transformations: list[TransformationLog]
    quarantined: list[QuarantineFinding]

    @model_validator(mode="after")
    def reconcile(self) -> "FeedbackIngestionResult":
        accepted_ids = len(self.records)
        quarantined_ids = len({q.source_record_id for q in self.quarantined})
        if accepted_ids + quarantined_ids != self.input_unique_ids:
            raise ValueError("accepted and quarantined feedback IDs do not reconcile")
        if len(self.annotations) + sum(len(q.row_numbers) for q in self.quarantined) != self.input_annotation_rows:
            raise ValueError("accepted and quarantined annotation rows do not reconcile")
        return self


class SurveyObservation(Contract):
    schema_version: str = "1"
    survey_id: str
    source_id: str
    market: str
    model: str
    instrument_id: str
    category_raw: str
    category_canonical: str | None = None
    statistic_type: Literal["mean", "categorical_distribution"]
    value: float | None = None
    distribution: dict[str, float] | None = None
    scale_endpoints: tuple[float, float] | None = None
    respondent_n: int | None = None
    respondent_n_missing_reason: str = "Not supplied"
    year: int
    mapping_version: str
    cell_locators: list[SourceLocator]
    limitations: list[str]


class StudyIngestionResult(Contract):
    source: SourceDocument
    observations: list[SurveyObservation]
    quarantined: list[QuarantineFinding] = Field(default_factory=list)


class EvidenceSpan(Contract):
    record_id: str
    locator: SourceLocator
    text: str
    start: int = Field(ge=0)
    end: int = Field(ge=0)

    @model_validator(mode="after")
    def valid_span(self) -> "EvidenceSpan":
        if self.end <= self.start:
            raise ValueError("evidence span end must be greater than start")
        return self


class Polarity(StrEnum):
    COMPLAINT = "complaint"
    PRAISE = "praise"
    ASPIRATION = "aspiration"
    OBSERVATION = "observation"
    MIXED = "mixed"


class Signal(Contract):
    schema_version: str = "1"
    signal_id: str
    feedback_record_id: str
    signal_type: Literal["customer_feedback"] = "customer_feedback"
    need_domain: str
    atomic_claim: str
    customer_outcome: str
    polarity: Polarity
    severity_label: str | None = None
    use_context: str | None = None
    vehicle_scope: dict[str, Any]
    evidence_spans: list[EvidenceSpan]
    extraction_status: Literal["validated"] = "validated"
    run_id: str
    provider_mode: Literal["baseline_no_ai", "live_ai", "cached_replay"]


class RequirementScope(Contract):
    models: list[str]
    countries: list[str]
    powertrains: list[str]
    use_cases: list[str] = Field(default_factory=list)


class AcceptanceProposal(Contract):
    method: str
    target: float | str | None = None
    unit: str | None = None


class RequirementEvidenceLink(Contract):
    signal_id: str
    role: Literal["supports", "preserves", "context"]
    atomic_claim: str
    locator: SourceLocator
    exact_span_checked: bool
    semantic_entailment: Literal["unreviewed", "reviewed_supports", "reviewed_rejects"] = "unreviewed"
    provenance: Literal["supplied_anonymized"] = "supplied_anonymized"
    author_expertise: Literal["unknown"] = "unknown"


class CrossChannelEvidence(Contract):
    evidence_id: str
    channel: Literal["youtube", "bmw_study", "bmw_sales", "bmw_equipment", "imported_context"]
    role: Literal["supports", "preserves", "context"]
    source_family: str
    claim: str
    locator: dict[str, Any]
    payload: dict[str, Any]
    applicability: Literal["matched", "scope_unconfirmed"]
    limitations: list[str]
    semantic_entailment: Literal["unreviewed"] = "unreviewed"


class BMWContextObservation(Contract):
    observation_id: str
    channel: Literal["bmw_sales", "bmw_equipment"]
    source_id: str
    source_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    model_codes: list[str]
    market: str
    metric: str
    year: int | None = None
    value: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    locator: SourceLocator
    raw_payload: dict[str, Any]
    limitations: list[str]


class YouTubeFinding(Contract):
    evidence_id: str
    video_id: str = Field(pattern=r"^[A-Za-z0-9_-]+$")
    generation: str
    topic: str
    feedback_type: Literal["positive", "pain_point", "requested_improvement"]
    source_statement: str
    supporting_excerpt: str = Field(min_length=1)
    timestamp_seconds: float = Field(ge=0, allow_inf_nan=False)
    transcript_segment: dict[str, Any]
    transcript_sha256: str
    bundle_sha256: str
    payload: dict[str, Any]


class EvidenceLinkJudgment(Contract):
    """A human assessment of one candidate signal-to-requirement link."""

    schema_version: str = "1"
    judgment_id: str
    requirement_id: str
    requirement_revision: int = Field(ge=1)
    signal_id: str
    verdict: Literal["supports", "does_not_support", "context_only"]
    rationale: str = Field(min_length=1)
    actor_id: str = Field(min_length=1)
    recorded_at: datetime
    request_id: str


class RequirementRevision(Contract):
    successor_draft_id: str | None = None
    schema_version: str = "1"
    requirement_id: str
    revision: int = Field(ge=1)
    title: str
    customer_outcome: str
    scope: RequirementScope
    use_conditions: list[str]
    acceptance_proposal: AcceptanceProposal
    target_status: Literal["pending_engineering_review", "proposed_target", "reviewed_target"]
    supporting_signal_ids: list[str]
    counter_signal_ids: list[str]
    context_signal_ids: list[str] = Field(default_factory=list)
    evidence_links: list[RequirementEvidenceLink] = Field(default_factory=list)
    context_observation_ids: list[str] = Field(default_factory=list)
    alternatives: list[str]
    assumptions: list[str]
    missing_evidence: list[str]
    feasibility: Literal["unknown", "conditional", "feasible_reviewed", "blocked"]
    implementation_cost: None = None
    implementation_cost_missing_reason: str = "Not supplied"
    lifecycle_status: Literal["draft", "needs_review"]
    supersedes_revision: int | None = None
    created_by: str
    created_at: datetime
    denominator_feedback_records: int = Field(ge=0)
    processed_feedback_records: int = Field(ge=0)
    support_count: int = Field(ge=0)
    counter_count: int = Field(ge=0)
    cross_channel_evidence: list[CrossChannelEvidence] = Field(default_factory=list)
    evidence_synthesis: list[str] = Field(default_factory=list)


class CriterionDefinition(Contract):
    dimension: Literal["customer", "business"]
    weight: float = Field(ge=0, le=1)
    anchor_0: str
    anchor_4: str


class PolicyVersion(Contract):
    schema_version: str = "1"
    policy_id: str
    revision: int = Field(ge=1)
    name: str
    criteria: dict[str, CriterionDefinition]
    saturation_share: float = Field(gt=0, le=1)
    unknown_rule: str
    approved: bool
    elicitation_record: str

    @model_validator(mode="after")
    def weights_sum_to_one(self) -> "PolicyVersion":
        if abs(sum(c.weight for c in self.criteria.values()) - 1.0) > 1e-9:
            raise ValueError("policy weights must sum to 1")
        for dimension in ("customer", "business"):
            if sum(c.weight for c in self.criteria.values() if c.dimension == dimension) <= 0:
                raise ValueError(f"policy needs a positive {dimension} weight")
        return self


class CriterionInput(Contract):
    value: float | None = Field(default=None, ge=0, le=4)
    lower_value: float | None = Field(default=None, ge=0, le=4)
    upper_value: float | None = Field(default=None, ge=0, le=4)
    basis: str | None = None
    missing_reason: str | None = None

    @model_validator(mode="after")
    def known_or_explained(self) -> "CriterionInput":
        has_interval = self.lower_value is not None or self.upper_value is not None
        if self.value is not None and has_interval:
            raise ValueError("criterion input cannot have both an exact value and interval")
        if has_interval:
            if self.lower_value is None or self.upper_value is None:
                raise ValueError("criterion intervals require lower_value and upper_value")
            if self.lower_value > self.upper_value:
                raise ValueError("criterion lower_value cannot exceed upper_value")
            if not self.basis:
                raise ValueError("criterion intervals require basis")
        elif self.value is None and not self.missing_reason:
            raise ValueError("unknown criterion inputs require missing_reason")
        elif self.value is not None and not self.basis:
            raise ValueError("known criterion inputs require basis")
        return self


class DimensionInterval(Contract):
    lower_bound: float = Field(ge=0, le=100)
    upper_bound: float = Field(ge=0, le=100)
    criteria: list[str]
    missing_criteria: list[str]
    interpretation: str


class ScoreSnapshot(Contract):
    schema_version: str = "1"
    score_snapshot_id: str
    requirement_id: str
    requirement_revision: int
    policy_id: str
    policy_revision: int
    profile_id: str
    profile_revision: int
    corpus_manifest_hash: str
    criterion_inputs: dict[str, CriterionInput]
    contributions: dict[str, tuple[float, float]]
    dimension_intervals: dict[str, DimensionInterval] = Field(default_factory=dict)
    lower_bound: float = Field(ge=0, le=100)
    upper_bound: float = Field(ge=0, le=100)
    scope: RequirementScope
    coverage: dict[str, Any]
    feasibility_status: str
    feasibility_basis: str = "No reviewed engineering evidence is linked."
    evidence_review_status: Literal["unreviewed", "human_reviewed"] = "unreviewed"
    assumptions: list[str]
    run_id: str


class ProviderDescriptor(Contract):
    name: str
    mode: Literal["baseline_no_ai", "live_ai", "cached_replay"]
    model_id: str | None
    prompt_version: str
    schema_version: str = "1"
    label: str


class RunManifest(Contract):
    schema_version: str = "1"
    run_id: str
    started_at: datetime
    finished_at: datetime | None = None
    dataset_hashes: list[str]
    corpus_manifest_hash: str
    provider: ProviderDescriptor
    profile_id: str
    profile_revision: int
    policy_id: str
    policy_revision: int
    statuses: dict[str, int | str]
    replay_of_run_id: str | None = None


class DecisionAction(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"
    EDIT = "edit"
    CHALLENGE = "challenge"
    DEFER = "defer"


class Decision(Contract):
    schema_version: str = "1"
    decision_id: str
    requirement_id: str
    requirement_revision: int
    action: DecisionAction
    rationale: str
    actor_id: str
    role: Literal["pm", "engineering_reviewer", "demo_pm"]
    recorded_at: datetime
    policy_revision: int | None = None
    score_snapshot_id: str | None = None
    priority_assessment_id: str | None = None
    expected_revision: int
    request_id: str
    uncertainty_acknowledged: bool = False


class PriorityFactors(Contract):
    impact: int = Field(ge=0, le=4)
    evidence: int = Field(ge=0, le=4)
    relevance: int = Field(ge=0, le=4)
    uncertainty: int = Field(ge=0, le=4)


class PriorityPolicy(Contract):
    impact: float = Field(ge=0, le=1)
    evidence: float = Field(ge=0, le=1)
    relevance: float = Field(ge=0, le=1)
    uncertainty: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def normalized(self):
        if abs(sum(self.model_dump().values()) - 1) > 1e-9:
            raise ValueError("priority weights must sum to one")
        return self


class PlanningCriterion(Contract):
    name: str = Field(min_length=1)
    rating: float = Field(ge=0, le=4, allow_inf_nan=False)
    weight: float = Field(ge=0, allow_inf_nan=False)
    direction: Literal["benefit", "risk"] = "benefit"
    explanation: str = Field(min_length=1)


class PriorityAssessment(Contract):
    criteria: list[PlanningCriterion] = Field(default_factory=list)
    rank_override: int | None = Field(default=None, ge=1)
    priority_confirmed: bool = False
    input_origin: Literal["legacy_unconfirmed", "explicit_pm"] = "legacy_unconfirmed"
    assessment_id: str
    requirement_id: str
    requirement_revision: int = Field(ge=1)
    sequence: int = Field(ge=1)
    factors: PriorityFactors
    policy: PriorityPolicy
    score: float = Field(ge=0, le=100)
    actor_id: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    recorded_at: datetime
    request_id: str
    interpretation: str = "Declared PM judgement, not measured customer prevalence or calibrated confidence."


class SuccessorProposal(Contract):
    domain: str
    title: str
    outcome: str
    value: str
    interpretation: str
    future_assumption: str
    contrary: str
    validation: str
    review_trigger: str
    anchor_ids: list[str]
    factors: PriorityFactors


class SuccessorDraft(Contract):
    draft_id: str
    requirement_id: str
    base_revision: int
    recipe_version: str
    method: str = "Assistant-authored evidence-linked template synthesis; no live model call."
    planning_window: str = "2029–2031: scenario 3–5 years from 2026, not a launch commitment"
    proposal: SuccessorProposal
    quoted_records: list[FeedbackRecord]
    context_evidence: list[CrossChannelEvidence]
    external_context: list[dict[str, str]] = Field(default_factory=list)
    unknowns: list[str]
    priority_policy: PriorityPolicy
    priority_explanations: dict[str, str]


class AuditEvent(Contract):
    schema_version: str = "1"
    event_id: str
    monotonic_sequence: int = Field(ge=1)
    recorded_at: datetime
    actor_id: str
    actor_type: str
    action: str
    object_type: str
    object_id: str
    object_revision: int | None = None
    before_hash: str | None = None
    after_hash: str | None = None
    reason: str
    request_id: str
    run_id: str | None = None
    previous_event_hash: str
    event_hash: str
    result: Literal["success", "failure", "noop"]


class ImportedEvidenceRow(Contract):
    """Unmodified foreign-schema evidence; import is not semantic verification."""

    schema_version: str = "1"
    archive_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    table_name: str
    row_key: str
    payload: dict[str, Any]
    verification_status: Literal["imported_unreviewed"] = "imported_unreviewed"


class HostedSettings(Contract):
    database_path: str
    app_password: str = Field(min_length=20, repr=False)
    admin_password: str = Field(min_length=20, repr=False)
    bootstrap_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
