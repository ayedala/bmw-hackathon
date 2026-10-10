from __future__ import annotations

from pathlib import Path
from typing import Callable

from ..utils import stable_id, utc_now
from .contracts import AdvisorRequest, AdvisorResult
from .evidence import build_packet, model_payload
from .provider import AdvisorProvider, PROMPT_VERSION, validate_report


def run_advisor(request: AdvisorRequest, database: Path, provider: AdvisorProvider,
                progress: Callable[[str], None] = lambda _: None) -> AdvisorResult:
    steps: list[str] = []

    def report_step(message: str) -> None:
        steps.append(message)
        progress(message)

    report_step("Reading feedback and context for the selected vehicle, market and powertrain.")
    initial = build_packet(request, database)
    report_step(f"Found {initial.feedback_records:,} scoped feedback records. Planning the research questions.")
    plan = provider.plan(request, [topic.domain for topic in initial.topics])
    packet = build_packet(request, database, search_terms=plan.search_terms,
                          focus_domains=plan.focus_domains if request.journey != "improve" else ())
    report_step(f"Selected {len(packet.evidence)} evidence items, including supporting and preservation examples.")
    report_step("Searching public sources for competitor implementations, technical paths and economic evidence.")
    research = provider.research(request, plan)
    report_step(f"Research returned {len(research.sources)} cited sources. Comparing options and delivery risks.")
    report = provider.synthesize({"local_evidence": model_payload(packet),
                                 "research_plan": plan.model_dump(mode="json"),
                                 "public_research": research.model_dump(mode="json")})
    validate_report(report, [*packet.evidence, *research.sources], request)
    report_step("Checked cited evidence identities and option coverage. Decision brief is ready for review.")
    created_at = utc_now().isoformat()
    return AdvisorResult(run_id=stable_id("advisor", packet.fingerprint, created_at), created_at=created_at,
                         model_id=provider.model_id, prompt_version=PROMPT_VERSION, packet=packet,
                         plan=plan, research=research, report=report, steps=steps, usage=provider.usage)
