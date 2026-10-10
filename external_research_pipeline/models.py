"""Pydantic schemas and the controlled vocabularies they validate against.

These models are the single schema source for the pipeline. Anything the
extraction model returns is validated here before it reaches storage, so an
invalid ``topic``/``subtopic``/``source_family`` is a rejected record rather
than a corrupt line in the output file.
"""

from __future__ import annotations

from typing import Any, Literal, get_args

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# --------------------------------------------------------------------------- #
# Controlled vocabularies
# --------------------------------------------------------------------------- #

SourceFamily = Literal[
    "government_statistics",
    "independent_test_org",
    "official_manufacturer",
    "professional_review",
    "market_report",
    "youtube_review",
    "customer_forum",
    "reddit",
    "app_review",
    "dealer",
    "other",
]

Topic = Literal["infotainment", "charging", "comfort", "market_trend"]

Stance = Literal["supports", "contradicts", "neutral"]

SOURCE_FAMILIES: tuple[str, ...] = get_args(SourceFamily)
TOPICS: tuple[str, ...] = get_args(Topic)

#: Allowed subtopics per topic. A subtopic is only valid inside its own topic.
SUBTOPICS: dict[str, tuple[str, ...]] = {
    "infotainment": (
        "touchscreen",
        "menu_complexity",
        "physical_controls",
        "climate_control_interaction",
        "navigation",
        "voice_assistant",
        "smartphone_integration",
        "software_reliability",
        "connected_services",
        "display_usability",
    ),
    "charging": (
        "charging_speed",
        "charging_curve",
        "charging_time",
        "charging_reliability",
        "battery_preconditioning",
        "route_planning",
        "public_charging",
        "long_distance_charging",
        "charging_stop_duration",
        "plug_and_charge",
        "charging_infrastructure",
        "winter_charging",
    ),
    "comfort": (
        "front_seat_comfort",
        "rear_seat_comfort",
        "rear_seat_space",
        "ride_comfort",
        "cabin_noise",
        "interior_space",
        "climate_comfort",
        "long_distance_comfort",
        "suspension_comfort",
        "perceived_interior_quality",
        "material_quality",
    ),
    "market_trend": (
        "ev_adoption",
        "charging_network_growth",
        "charging_behavior",
        "future_customer_expectation",
    ),
}

ALL_SUBTOPICS: tuple[str, ...] = tuple(
    subtopic for subtopics in SUBTOPICS.values() for subtopic in subtopics
)

#: Reverse index used to repair a correct subtopic paired with the wrong topic.
SUBTOPIC_TO_TOPIC: dict[str, str] = {
    subtopic: topic for topic, subtopics in SUBTOPICS.items() for subtopic in subtopics
}


# --------------------------------------------------------------------------- #
# Scraped pages
# --------------------------------------------------------------------------- #


class SearchHit(BaseModel):
    """One result returned by the search provider, before any filtering.

    ``source_family`` and ``priority`` are filled in during ranking, not by the
    provider. They drive scrape ordering and the dry-run report only; neither is
    written to the evidence store.
    """

    model_config = ConfigDict(extra="ignore")

    url: str
    canonical_url: str
    title: str = ""
    description: str = ""
    position: int = 0
    query: str = ""
    topic: str = ""
    category: str = ""
    source_family: str = ""
    priority: int = 0


class RawPage(BaseModel):
    """A successfully scraped page, as written to ``data/raw/raw_pages.jsonl``.

    Field order matches the documented on-disk schema.
    """

    model_config = ConfigDict(extra="forbid")

    url: str
    resolved_url: str | None = None
    canonical_url: str
    title: str = ""
    source_name: str = ""
    published_at: str | None = None
    query: str = ""
    topic: str = ""
    retrieved_at: str
    markdown: str


# --------------------------------------------------------------------------- #
# Evidence
# --------------------------------------------------------------------------- #


class RawEvidence(BaseModel):
    """One atomic evidence claim extracted from a page, before scoring.

    ``source_url``, ``source_name``, ``source_title`` and ``source_family`` are
    assigned by the pipeline from page metadata and the deterministic domain
    classifier - they are never taken from the model's output, so a claim can
    never be attributed to a URL that was not actually scraped.
    """

    model_config = ConfigDict(extra="forbid")

    source_url: str
    source_name: str
    source_title: str
    source_family: SourceFamily
    published_at: str | None = None

    brand: str
    vehicle: str
    market: str

    topic: Topic
    subtopic: str

    claim: str = Field(min_length=3)
    evidence_text: str = Field(min_length=3)
    source_start_char: int = Field(ge=0)
    source_end_char: int = Field(ge=1)

    numeric_value: float | None = None
    numeric_unit: str | None = None

    @field_validator("claim", "evidence_text", "source_name", "source_title", mode="before")
    @classmethod
    def _strip_text(cls, value: Any) -> Any:
        """Collapse surrounding whitespace on free-text fields."""
        return value.strip() if isinstance(value, str) else value

    @field_validator("numeric_unit", mode="before")
    @classmethod
    def _blank_unit_to_none(cls, value: Any) -> Any:
        """Treat an empty-string unit as absent."""
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @model_validator(mode="after")
    def _check_subtopic(self) -> "RawEvidence":
        """Reject a subtopic that does not belong to the record's topic."""
        allowed = SUBTOPICS[self.topic]
        if self.subtopic not in allowed:
            raise ValueError(
                f"subtopic {self.subtopic!r} is not valid for topic {self.topic!r}; "
                f"allowed: {', '.join(allowed)}"
            )
        return self

    @model_validator(mode="after")
    def _check_numeric_pair(self) -> "RawEvidence":
        """A numeric value is only meaningful alongside its unit."""
        if self.numeric_value is not None and not self.numeric_unit:
            raise ValueError("numeric_value requires numeric_unit")
        return self

    @model_validator(mode="after")
    def _check_source_span(self) -> "RawEvidence":
        """Ensure stored locators cover the exact evidence quote."""
        if self.source_end_char - self.source_start_char != len(self.evidence_text):
            raise ValueError("source span length must match evidence_text")
        return self


class ProcessedEvidence(BaseModel):
    """A scored, grouped evidence record written to the processed store.

    Field order matches the documented output schema so the JSONL stays
    diff-friendly.
    """

    model_config = ConfigDict(extra="forbid")

    evidence_id: str

    source_url: str
    source_name: str
    source_title: str
    source_family: SourceFamily
    published_at: str | None = None
    retrieved_at: str

    brand: str
    vehicle: str
    market: str

    topic: Topic
    subtopic: str

    claim: str
    evidence_text: str
    source_start_char: int = Field(ge=0)
    source_end_char: int = Field(ge=1)

    numeric_value: float | None = None
    numeric_unit: str | None = None

    source_quality: int = Field(ge=0, le=100)

    independence_group: str
    duplicate_of: str | None = None

    @classmethod
    def from_raw(
        cls,
        raw: RawEvidence,
        *,
        evidence_id: str,
        retrieved_at: str,
        source_quality: int,
        independence_group: str,
        duplicate_of: str | None = None,
    ) -> "ProcessedEvidence":
        """Build a processed record from *raw* plus pipeline-assigned fields."""
        return cls(
            evidence_id=evidence_id,
            retrieved_at=retrieved_at,
            source_quality=source_quality,
            independence_group=independence_group,
            duplicate_of=duplicate_of,
            **raw.model_dump(),
        )


# --------------------------------------------------------------------------- #
# Run metadata
# --------------------------------------------------------------------------- #


class ResearchRun(BaseModel):
    """Counters and timing for one execution, appended to ``research_runs.jsonl``.

    Every counter is incremented at the single place the corresponding event
    happens, so the record doubles as the credit-spend audit for the run.
    """

    model_config = ConfigDict(extra="forbid")

    run_id: str
    started_at: str
    finished_at: str | None = None

    topic: str
    queries_attempted: int = 0

    search_results_found: int = 0

    urls_skipped_duplicate: int = 0
    urls_skipped_filtered: int = 0

    pages_scraped: int = 0
    pages_loaded_from_cache: int = 0
    pages_failed: int = 0

    evidence_records_created: int = 0
    evidence_duplicates_found: int = 0

    firecrawl_search_calls: int = 0
    firecrawl_scrape_calls: int = 0

    llm_calls: int = 0

    def summary_lines(self) -> list[str]:
        """Human-readable counter list for the end-of-run log."""
        return [
            f"run_id                  {self.run_id}",
            f"topic                   {self.topic}",
            f"queries attempted       {self.queries_attempted}",
            f"search results found    {self.search_results_found}",
            f"urls skipped (dupe)     {self.urls_skipped_duplicate}",
            f"urls skipped (filter)   {self.urls_skipped_filtered}",
            f"pages scraped           {self.pages_scraped}",
            f"pages from cache        {self.pages_loaded_from_cache}",
            f"pages failed            {self.pages_failed}",
            f"evidence created        {self.evidence_records_created}",
            f"evidence duplicates     {self.evidence_duplicates_found}",
            f"firecrawl search calls  {self.firecrawl_search_calls}",
            f"firecrawl scrape calls  {self.firecrawl_scrape_calls}",
            f"llm calls               {self.llm_calls}",
        ]
