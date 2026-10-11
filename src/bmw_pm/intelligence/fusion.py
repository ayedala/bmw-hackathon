"""Conservative cross-channel synthesis with separate evidence denominators."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Sequence
from uuid import uuid4

from ..contracts import (AcceptanceProposal, BMWContextObservation, CrossChannelEvidence, RequirementRevision,
                         RequirementScope, SurveyObservation, YouTubeFinding)
from ..storage import Database
from ..utils import content_hash, sha256_bytes, stable_id, utc_now

FUSION_VERSION = "cross_channel_v3_evidence_only"


def fusion_manifest(inputs: dict[str, Any]) -> dict[str, Any]:
    return {"youtube": [v.model_dump(mode="json") for v in inputs["youtube"]],
            "studies": [v.model_dump(mode="json") for v in inputs["studies"]],
            "imported": inputs["imported"],
            "provided": [v.model_dump(mode="json") for v in inputs.get("provided", [])]}


def import_youtube_run(database: Database, directory: str | Path) -> dict[str, Any]:
    """Recheck quotes against saved transcripts, preserving original bundle bytes.

    No YouTube/LLM requests are made here. Invalid findings are reported individually.
    """
    root = Path(directory)
    evidence_bytes = (root / "evidence.json").read_bytes()
    source_bytes = (root / "sources.json").read_bytes()
    observations = json.loads(evidence_bytes)
    sources = json.loads(source_bytes)
    if not isinstance(observations, list) or not isinstance(sources, list):
        raise ValueError("YouTube evidence and sources must be JSON lists")
    videos = {v["video_id"]: v for v in sources if isinstance(v, dict) and "video_id" in v}
    transcripts: dict[str, str] = {}
    findings, rejected = {}, []
    for index, item in enumerate(observations):
        try:
            video_id = item["video_id"]
            if not re.fullmatch(r"[A-Za-z0-9_-]+", video_id):
                raise ValueError("invalid video ID")
            source = videos[video_id]
            if source.get("retrieval_status") != "retrieved":
                raise ValueError("source has no retrieved transcript")
            raw = (root / "transcripts" / f"{video_id}.json").read_bytes()
            transcripts[video_id] = raw.decode("utf-8")
            segments = json.loads(raw)
            timestamp = float(item["timestamp_seconds"])
            excerpt = item["supporting_excerpt"]
            if not isinstance(excerpt, str) or not excerpt.strip():
                raise ValueError("empty excerpt")
            segment = next((s for s in segments
                            if round(float(s["start"]), 2) == round(timestamp, 2)
                            and excerpt in s["text"]), None)
            if segment is None:
                raise ValueError("quote or timestamp does not match saved transcript")
            # Identity excludes model paraphrases and run directories to avoid repeat inflation.
            identity = stable_id("yt", video_id, str(round(timestamp, 2)), excerpt,
                                 item["feedback_type"], item["generation"])
            findings[identity] = dict(
                evidence_id=identity, video_id=video_id, generation=item["generation"],
                topic=item.get("topic") or "unspecified", feedback_type=item["feedback_type"],
                source_statement=excerpt,
                supporting_excerpt=excerpt, timestamp_seconds=timestamp,
                transcript_segment=segment, transcript_sha256=sha256_bytes(raw),
                payload={"observation": item, "source": source})
        except (KeyError, TypeError, ValueError, OSError) as error:
            rejected.append({"index": index, "reason": str(error)})
    bundle = {"evidence": evidence_bytes.decode("utf-8"),
              "sources": source_bytes.decode("utf-8"), "transcripts": transcripts}
    bundle_hash = content_hash(bundle)
    valid = []
    for item in findings.values():
        try:
            valid.append(YouTubeFinding(**item, bundle_sha256=bundle_hash))
        except ValueError as error:
            rejected.append({"evidence_id": item["evidence_id"], "reason": str(error)})
    with database.connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute("CREATE TABLE IF NOT EXISTS youtube_bundles (bundle_hash TEXT PRIMARY KEY, payload_json TEXT NOT NULL)")
        connection.execute("CREATE TABLE IF NOT EXISTS youtube_findings (evidence_id TEXT PRIMARY KEY, payload_json TEXT NOT NULL)")
        connection.execute("INSERT OR IGNORE INTO youtube_bundles VALUES (?,?)", (bundle_hash, json.dumps(bundle)))
        inserted = 0
        for finding in valid:
            inserted += connection.execute("INSERT OR IGNORE INTO youtube_findings VALUES (?,?)",
                                           (finding.evidence_id, finding.model_dump_json())).rowcount
        database._append_audit(connection, actor_id="youtube-import", actor_type="pipeline",
            action="import_youtube_evidence", object_type="youtube_bundle", object_id=bundle_hash,
            object_revision=None, before_hash=None, after_hash=bundle_hash,
            reason=f"{inserted} new findings; {len(rejected)} rejected; original bundle retained.",
            request_id=f"youtube-import:{uuid4().hex}", result="success" if inserted else "noop")
        connection.commit()
    return {"bundle_sha256": bundle_hash, "accepted": len(valid), "inserted": inserted,
            "rejected": rejected, "discovered_sources": len(sources),
            "readable_sources": sum(v.get("retrieval_status") == "retrieved" for v in videos.values())}


def read_fusion_inputs(database: Database) -> dict[str, Any]:
    with database.connect() as connection:
        tables = {r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        findings = [YouTubeFinding.model_validate_json(r[0]) for r in connection.execute(
            "SELECT payload_json FROM youtube_findings ORDER BY evidence_id")] if "youtube_findings" in tables else []
        studies = [SurveyObservation.model_validate_json(r[0]) for r in connection.execute(
            "SELECT payload_json FROM survey_observations ORDER BY survey_id")]
        imported = [json.loads(r[0]) for r in connection.execute(
            "SELECT payload_json FROM imported_evidence WHERE table_name IN ('sales_observation','equipment_fact','external_claim','web_research_seed') ORDER BY row_key"
        )] if "imported_evidence" in tables else []
        provided = [BMWContextObservation.model_validate_json(r[0]) for r in connection.execute(
            "SELECT payload_json FROM bmw_context ORDER BY observation_id")] if "bmw_context" in tables else []
        database._append_audit(connection, actor_id="fusion", actor_type="pipeline",
            action="read_fusion_inputs", object_type="evidence_corpus",
            object_id=content_hash(fusion_manifest({"youtube": findings, "studies": studies, "imported": imported, "provided": provided})),
            object_revision=None, before_hash=None, after_hash=None,
            reason="Read YouTube, BMW studies and imported context for joint synthesis.",
            request_id=uuid4().hex, result="success")
        connection.commit()
    return {"youtube": findings, "studies": studies, "imported": imported, "provided": provided}


def validate_cross_channel_links(database: Database, requirements: Sequence[RequirementRevision]) -> list[str]:
    errors = []
    with database.connect() as connection:
        tables = {r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        findings = {f.evidence_id: f for f in (
            YouTubeFinding.model_validate_json(r[0]) for r in connection.execute("SELECT payload_json FROM youtube_findings")
        )} if "youtube_findings" in tables else {}
        bundles = {r[0]: json.loads(r[1]) for r in connection.execute("SELECT bundle_hash,payload_json FROM youtube_bundles")} if "youtube_bundles" in tables else {}
        studies = {s.survey_id: s for s in (
            SurveyObservation.model_validate_json(r[0]) for r in connection.execute("SELECT payload_json FROM survey_observations"))}
        imported = {r[0]: json.loads(r[1]) for r in connection.execute("SELECT row_key,payload_json FROM imported_evidence")} if "imported_evidence" in tables else {}
        provided = {v.observation_id: v for v in (
            BMWContextObservation.model_validate_json(r[0]) for r in connection.execute("SELECT payload_json FROM bmw_context")
        )} if "bmw_context" in tables else {}
        source_hashes = {r[0]: r[1] for r in connection.execute("SELECT source_id,sha256 FROM sources")}
    for requirement in requirements:
        for link in requirement.cross_channel_evidence:
            valid = False
            if link.channel == "youtube":
                finding = findings.get(link.evidence_id)
                if finding:
                    bundle = bundles.get(finding.bundle_sha256, {})
                    transcript = bundle.get("transcripts", {}).get(finding.video_id, "")
                    valid = (content_hash(bundle) == finding.bundle_sha256
                             and sha256_bytes(transcript.encode("utf-8")) == finding.transcript_sha256
                             and finding.transcript_segment in json.loads(transcript or "[]")
                             and finding.supporting_excerpt in finding.transcript_segment["text"]
                             and round(finding.timestamp_seconds, 2) == round(float(finding.transcript_segment["start"]), 2)
                             and link.payload == finding.payload
                             and link.locator.get("exact_quote") == finding.supporting_excerpt
                             and link.locator.get("transcript_sha256") == finding.transcript_sha256
                             and link.locator.get("bundle_sha256") == finding.bundle_sha256
                             and link.locator.get("timestamp_seconds") == finding.timestamp_seconds)
            elif link.channel == "bmw_study":
                study = studies.get(link.evidence_id)
                valid = study is not None and link.payload == study.model_dump(mode="json") and link.locator.get("cells") == [l.model_dump(mode="json") for l in study.cell_locators]
            elif link.channel == "imported_context":
                original = imported.get(link.evidence_id)
                valid = original is not None and link.payload == original["payload"] and link.locator.get("archive_sha256") == original["archive_sha256"]
            elif link.channel in {"bmw_sales", "bmw_equipment"}:
                original = provided.get(link.evidence_id)
                valid = (original is not None and link.payload == original.model_dump(mode="json")
                    and link.locator == original.locator.model_dump(mode="json")
                    and original.source_hash == source_hashes.get(original.source_id))
            if not valid:
                errors.append(f"{requirement.requirement_id}: unresolved {link.channel} evidence {link.evidence_id}")
    return errors


def _matches(text: str, domain: str, spec: dict[str, Any]) -> bool:
    phrases = [domain.replace("_", " "), *spec["phrases"]]
    return any(re.search(r"(?<!\w)" + re.escape(p) + r"(?!\w)", text, re.I) for p in phrases)


def fuse_candidates(*, candidates: Sequence[RequirementRevision], inputs: dict[str, Any],
                    taxonomy: dict[str, Any], eligible: Sequence[Any], processed_ids: set[str],
                    profile: dict[str, Any], created_by: str) -> list[RequirementRevision]:
    domains = taxonomy["domains"]
    youtube_by_domain: dict[str, list[CrossChannelEvidence]] = {d: [] for d in domains}
    for finding in inputs["youtube"]:
        if finding.generation != profile["model_family"]:
            continue
        for domain, spec in domains.items():
            # Match source wording/topic, never the extractor's inferred customer need.
            if not _matches(finding.topic + " " + finding.supporting_excerpt, domain, spec):
                continue
            applicable = spec.get("applicable_powertrains", [])
            if applicable and profile.get("powertrains") and not set(applicable) & set(profile["powertrains"]):
                continue
            youtube_by_domain[domain].append(CrossChannelEvidence(
                evidence_id=finding.evidence_id, channel="youtube",
                role="preserves" if finding.feedback_type == "positive" else "supports",
                source_family=f"youtube:{finding.video_id}", claim=finding.supporting_excerpt,
                locator={"url": f"https://www.youtube.com/watch?v={finding.video_id}&t={int(finding.timestamp_seconds)}s",
                         "timestamp_seconds": finding.timestamp_seconds, "exact_quote": finding.supporting_excerpt,
                         "transcript_sha256": finding.transcript_sha256, "bundle_sha256": finding.bundle_sha256},
                payload=finding.payload, applicability="scope_unconfirmed",
                limitations=["Vehicle metadata is source/user asserted; country and powertrain applicability require review.",
                             "Speaker ownership, expertise and independence from BMW feedback are unknown.",
                             "Exact transcript quote checked; transcription and claim entailment are unreviewed."] ))
    result = list(candidates)
    represented = {r.title.lower().replace(" ", "_") for r in result}
    for domain, links in youtube_by_domain.items():
        if domain in represented or not any(l.role == "supports" for l in links):
            continue
        spec = domains[domain]
        powertrains = profile.get("domain_applicability", {}).get(domain) or spec.get("applicable_powertrains") or profile.get("powertrains", [])
        scoped = {r.record_id for r in eligible if not powertrains or r.powertrain in powertrains}
        result.append(RequirementRevision(
            requirement_id=stable_id("req", str(profile["profile_id"]), domain, spec["customer_outcome"].casefold()),
            revision=1, title=domain.replace("_", " ").title(), customer_outcome=f"Video evidence topic: {domain}. A PM must define any requirement from the cited source wording.",
            scope=RequirementScope(models=[profile["model_family"]], countries=profile.get("countries", []), powertrains=powertrains),
            use_conditions=["YouTube-led hypothesis; intended market and configuration require confirmation."],
            acceptance_proposal=AcceptanceProposal(method="Not supplied. PM definition required."),
            target_status="pending_engineering_review", supporting_signal_ids=[], counter_signal_ids=[],
            alternatives=["Confirm applicability before choosing a solution."], assumptions=[],
            missing_evidence=["No supporting BMW feedback signal was extracted for this outcome.",
                              "Engineering feasibility, costs and representative customer prevalence are unknown."],
            feasibility="unknown", lifecycle_status="needs_review", created_by=created_by, created_at=utc_now(),
            denominator_feedback_records=len(scoped), processed_feedback_records=len(scoped & processed_ids),
            support_count=0, counter_count=0))
    fused = []
    for candidate in result:
        domain = candidate.title.lower().replace(" ", "_")
        spec = domains.get(domain)
        links = list(youtube_by_domain.get(domain, []))
        for observation in inputs.get("provided", []):
            if not set(observation.model_codes) & set(candidate.scope.models):
                continue
            if observation.channel == "bmw_equipment":
                phrases = profile.get("equipment_context_phrases", {}).get(domain, [])
                text = observation.raw_payload.get("text", "")
                if not (spec and _matches(text, domain, spec) or any(p.casefold() in text.casefold() for p in phrases)):
                    continue
            claim = (f"Supplied {observation.year} sales/planning volume: {observation.value:g} ({'/'.join(observation.model_codes)}, {observation.market})."
                     if observation.channel == "bmw_sales" else
                     f"German equipment reference: {observation.raw_payload['file_name']}, page {observation.locator.page}; feature applicability unreviewed.")
            links.append(CrossChannelEvidence(evidence_id=observation.observation_id, channel=observation.channel,
                role="context", source_family=observation.source_id, claim=claim,
                locator=observation.locator.model_dump(mode="json"), payload=observation.model_dump(mode="json"),
                applicability="scope_unconfirmed", limitations=observation.limitations))
        for study in inputs["studies"]:
            if study.model not in candidate.scope.models or not spec or not _matches(study.category_raw, domain, spec):
                continue
            links.append(CrossChannelEvidence(
                evidence_id=study.survey_id, channel="bmw_study", role="context", source_family=study.source_id,
                claim=f"{study.category_raw}: {study.value if study.value is not None else study.distribution} ({study.market}, {study.year})",
                locator={"cells": [l.model_dump(mode="json") for l in study.cell_locators]},
                payload=study.model_dump(mode="json"), applicability="scope_unconfirmed",
                limitations=["Category matching is a lexical hypothesis, not a reviewed crosswalk.",
                             "Study market may differ from feedback countries; scale endpoints and respondent counts are unknown."]))
        for imported in inputs["imported"]:
            payload = imported["payload"]
            text = json.dumps(payload, ensure_ascii=False)
            # Preserve family-level business facts as context, never as per-powertrain exposure.
            model_match = any(re.search(r"(?<![A-Z0-9])" + re.escape(m) + r"(?![A-Z0-9])", text) for m in candidate.scope.models)
            if not model_match or not (imported["table_name"] == "sales_observation" or spec and _matches(text, domain, spec)):
                continue
            links.append(CrossChannelEvidence(
                evidence_id=imported["row_key"], channel="imported_context", role="context",
                source_family=f"archive:{imported['archive_sha256']}",
                claim=f"Imported {imported['table_name']} context; original payload retained below.",
                locator={"archive_sha256": imported["archive_sha256"], "table": imported["table_name"], "row_key": imported["row_key"]},
                payload=payload, applicability="scope_unconfirmed",
                limitations=["Unreviewed context: original scope, source locators and claim entailment require inspection.",
                             "G60/G68 sales are family totals; no powertrain denominator or engineering feasibility follows."]))
        links = sorted({(l.channel, l.evidence_id): l for l in links}.values(), key=lambda l: (l.channel, l.evidence_id))
        support_videos = {l.source_family for l in links if l.channel == "youtube" and l.role == "supports"}
        praise_videos = {l.source_family for l in links if l.channel == "youtube" and l.role == "preserves"}
        synthesis = [f"BMW feedback: {candidate.support_count} supporting and {candidate.counter_count} preservation records; YouTube: {len(support_videos)} supporting and {len(praise_videos)} preservation videos.",
                     f"{sum(l.channel == 'bmw_study' for l in links)} BMW study observations and {sum(l.channel == 'imported_context' for l in links)} imported context rows inform review; they are not pooled into recurrence."]
        if any(l.channel in {"bmw_sales", "bmw_equipment"} for l in links):
            synthesis.append(f"BMW supplied context: {sum(l.channel == 'bmw_sales' for l in links)} sales/planning values and {sum(l.channel == 'bmw_equipment' for l in links)} equipment pages. Sales expose model-family/region scale; equipment pages identify current-baseline questions without proving availability in the feedback vehicle.")
        if (candidate.support_count or support_videos) and (candidate.counter_count or praise_videos):
            synthesis.append("Mixed evidence: investigate differing tasks, configurations and conditions; praise is a preservation need, not a proven contradiction.")
        if candidate.support_count and support_videos:
            synthesis.append("Both channels contain related concerns. Cross-channel corroboration is provisional until scope, entailment and source independence are reviewed.")
        if not links:
            synthesis.append("No additional matched cross-channel evidence is available for this outcome.")
        assumptions = list(candidate.assumptions)
        if links:
            assumptions += ["Cross-channel theme alignment uses the versioned keyword taxonomy and requires semantic review.",
                            "YouTube discovery region is not evidence of the speaker's market; external evidence does not alter BMW feedback denominators or grant a scoring bonus."]
        fused.append(candidate.model_copy(update={"cross_channel_evidence": links, "evidence_synthesis": synthesis,
                                                   "assumptions": list(dict.fromkeys(assumptions))}))
    return sorted(fused, key=lambda r: r.requirement_id)
