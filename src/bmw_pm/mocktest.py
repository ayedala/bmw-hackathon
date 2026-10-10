"""In-memory feedback sandbox using the project's deterministic baseline path."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from .contracts import Contract, FeedbackRecord, RequirementRevision, Signal, SourceLocator
from .intelligence.baseline import BaselineExtractionProvider
from .decision.requirements import build_requirement_candidates
from .utils import content_hash, sha256_bytes, stable_id


class MockTestInput(Contract):
    model_code: Literal["F70", "G60", "G70"]
    country: str = Field(pattern=r"^[A-Z]{2}$")
    powertrain: Literal["ICE", "PHEV", "BEV"]
    feedback_text: str = Field(max_length=2000)

    @model_validator(mode="after")
    def nonempty_text(self) -> "MockTestInput":
        if len(self.feedback_text.strip()) < 3:
            raise ValueError("enter at least three non-space characters")
        return self


class MockTestResult(Contract):
    input_hash: str
    provider_mode: Literal["baseline_no_ai"] = "baseline_no_ai"
    provider_label: str
    taxonomy_version: str
    signals: list[Signal]
    candidates: list[RequirementRevision]
    status: Literal["candidate_for_review", "no_update_proposed", "no_keyword_match"]


def run_mocktest(request: MockTestInput, *, project_root: Path | None = None) -> MockTestResult:
    """Run one synthetic statement without a database, network call or score."""
    root = project_root or Path(__file__).resolve().parents[2]
    profile = json.loads((root / "configs" / f"{request.model_code.lower()}.json").read_text(encoding="utf-8"))
    if request.powertrain not in profile["powertrains"]:
        raise ValueError(f"{request.powertrain} is outside the {request.model_code} profile")
    if profile["countries"] and request.country not in profile["countries"]:
        raise ValueError(f"{request.country} is outside the {request.model_code} profile")

    provider = BaselineExtractionProvider.from_file(root / "configs" / "baseline_taxonomy_v1.json")
    input_hash = content_hash({"input": request.model_dump(mode="json"),
                               "profile": profile, "taxonomy": provider.configuration_hash})
    record_id = stable_id("mock_feedback", input_hash)
    source_id = stable_id("mock_source", input_hash)
    locator = SourceLocator(
        source_id=source_id, source_hash=sha256_bytes(request.feedback_text.encode("utf-8")),
        locator_type="sheet_range", sheet="Mock input", cell_range="A1",
        exact_quote=request.feedback_text,
    )
    record = FeedbackRecord(
        record_id=record_id, source_id=source_id, source_record_id=record_id,
        raw_text_ref="in_memory_mock_input", cleaned_text=request.feedback_text,
        redacted_text=request.feedback_text, raw_country=request.country,
        country=request.country, raw_model=request.model_code,
        model_code=request.model_code, raw_brand="BMW", raw_sales_description=None,
        raw_derivative=None, powertrain_raw=request.powertrain,
        powertrain=request.powertrain, powertrain_mapping_status="exact",
        source_label="mock_synthetic", row_locators=[locator], transformation_ids=[],
        assumptions=["One synthetic statement; no corpus coverage or customer prevalence follows."],
    )
    run_id = stable_id("mock_run", input_hash)
    signals = provider.extract([record], run_id=run_id)
    candidates = build_requirement_candidates(
        signals=signals, eligible_records=[record], processed_record_ids={record_id},
        profile=profile, created_by=provider.descriptor.name,
    )
    status = ("candidate_for_review" if candidates else
              "no_update_proposed" if signals else "no_keyword_match")
    return MockTestResult(
        input_hash=input_hash, provider_label=provider.descriptor.label,
        taxonomy_version=str(provider.config["version"]), signals=signals,
        candidates=candidates, status=status,
    )
