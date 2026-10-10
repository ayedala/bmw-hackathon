"""Bounded local retrieval. Counts use unique records; examples are not a census."""
from __future__ import annotations

import json
import re
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Iterable

from ..contracts import FeedbackRecord, Polarity
from ..data_pipeline.video_memory import memory_excerpts
from ..intelligence.baseline import BaselineExtractionProvider
from ..utils import content_hash
from .contracts import AdvisorRequest, EvidenceItem, EvidencePacket, TopicSummary

ROOT = Path(__file__).resolve().parents[3]
STOPWORDS = set("the and for with this that have from want idea improve car bmw series would could should its into more".split())


def redact(text: str) -> str:
    """Additional protection for contact details in an already-redacted corpus."""
    text = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[email removed]", text)
    text = re.sub(r"(?<!\w)(?:\+?\d[\d ()-]{8,}\d)(?!\w)", "[number removed]", text)
    return text


def _terms(values: Iterable[str]) -> set[str]:
    return {t for value in values for t in re.findall(r"[a-z]{3,}", value.lower()) if t not in STOPWORDS}


def _relevance(text: str, terms: set[str]) -> int:
    return len(set(re.findall(r"[a-z]{3,}", text.lower())) & terms)


def build_packet(request: AdvisorRequest, database: Path, *, search_terms: Iterable[str] = (),
                 focus_domains: Iterable[str] = ()) -> EvidencePacket:
    if not database.is_file():
        raise ValueError("The evidence database is missing. Import the supplied data before starting research.")
    terms = _terms([request.question, *request.ideas, *search_terms])
    connection = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("BEGIN")  # One consistent read snapshot, even during another import.
        params: list[str] = [request.model_code, request.market]
        where = "model_code=? AND country=?"
        if request.powertrain != "ALL":
            where += " AND powertrain=?"
            params.append(request.powertrain)
        rows = connection.execute(
            f"SELECT payload_json FROM feedback_records WHERE {where} ORDER BY record_id", params
        ).fetchall()
        records = [FeedbackRecord.model_validate_json(row[0]) for row in rows]
        provider = BaselineExtractionProvider.from_file(ROOT / "configs/baseline_taxonomy_v1.json")
        signals = provider.extract(records, run_id="advisor_local_retrieval")
        grouped = defaultdict(list)
        for signal in signals:
            grouped[signal.need_domain].append(signal)
        evidence: list[EvidenceItem] = []
        topics = []
        selected_domains = set(focus_domains) or set(provider.config["domains"])
        for domain, spec in provider.config["domains"].items():
            applicable = spec.get("applicable_powertrains")
            eligible = [r for r in records if not applicable or r.powertrain in applicable]
            group = grouped[domain]
            support = {s.feedback_record_id for s in group if s.polarity in {Polarity.COMPLAINT, Polarity.ASPIRATION}}
            praise = {s.feedback_record_id for s in group if s.polarity == Polarity.PRAISE}
            context = {s.feedback_record_id for s in group if s.polarity in {Polarity.MIXED, Polarity.OBSERVATION}}
            topic = TopicSummary(domain=domain, outcome=spec["customer_outcome"], eligible_records=len(eligible),
                                 supporting_records=len(support), praise_records=len(praise), context_records=len(context))
            topics.append(topic)
            evidence.append(EvidenceItem(
                evidence_id=f"topic:{domain}", channel="corpus_summary", title=domain.replace("_", " ").title(),
                text=topic.model_dump_json(), selection_reason="All configured topics retained to compare alternatives.",
                scope={"model": request.model_code, "market": request.market, "powertrain": request.powertrain},
                locator={"taxonomy_version": provider.config["version"]},
                limitations=["Keyword-baseline counts; extraction quality is unmeasured. Feedback IDs are not verified people.",
                             "These counts describe the collected corpus, not customer prevalence or sales impact."],
            ))
            if domain not in selected_domains:
                continue
            for polarity in (Polarity.COMPLAINT, Polarity.ASPIRATION, Polarity.PRAISE, Polarity.MIXED):
                subset = [s for s in group if s.polarity == polarity]
                subset.sort(key=lambda s: (-_relevance(s.atomic_claim, terms), s.feedback_record_id))
                for signal in subset[:2 if polarity == Polarity.COMPLAINT else 1]:
                    span = signal.evidence_spans[0]
                    evidence.append(EvidenceItem(
                        evidence_id=f"feedback:{signal.signal_id}", channel="customer_feedback",
                        title=f"{domain.replace('_', ' ').title()} · {polarity.value}", text=redact(span.text),
                        selection_reason=f"{polarity.value.title()} example in {domain}; query-token matches: {_relevance(span.text, terms)}. Praise and mixed evidence are retained.",
                        scope=signal.vehicle_scope,
                        locator={**span.locator.model_dump(mode="json"), "record_id": span.record_id,
                                 "start": span.start, "end": span.end},
                        limitations=["Selected example, not a representative sample; feedback date and verified ownership unknown.",
                                     "Contact details are masked in the displayed/model excerpt when detected."],
                    ))
        # Lexical retrieval also covers ideas outside the existing seven-topic taxonomy.
        ranked = sorted(records, key=lambda r: (-_relevance(r.redacted_text, terms), r.record_id))
        selected_records = {item.locator.get("record_id") for item in evidence}
        for record in [r for r in ranked if _relevance(r.redacted_text, terms) and r.record_id not in selected_records][:8]:
            evidence.append(EvidenceItem(
                evidence_id=f"record:{record.record_id}", channel="customer_feedback",
                title="Additional idea-related feedback", text=redact(record.redacted_text[:1200]),
                selection_reason=f"Matches {_relevance(record.redacted_text, terms)} query terms outside the selected excerpts.",
                scope={"model": record.model_code, "country": record.country, "powertrain": record.powertrain},
                locator={**record.row_locators[0].model_dump(mode="json"), "record_id": record.record_id},
                limitations=["Lexical relevance needs semantic review; text may be truncated to 1,200 characters."],
            ))

        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        _add_context(connection, tables, request, terms, evidence)
    finally:
        connection.close()

    limitations = [
        "The LLM receives selected excerpts and aggregate counts, not every feedback record.",
        "Feedback dates, sampling frame, unique customers and verified ownership are unknown.",
        "Model year selects web research scope; undated database feedback cannot be restricted to that year.",
        "Internal feature development cost, contribution margin and causal sales lift are not supplied.",
        "Equipment from other markets and combined family sales cannot establish exact vehicle availability or financial exposure.",
    ]
    if not records:
        limitations.append("No feedback matches this vehicle/market/powertrain. Do not infer demand from another market.")
    if not any(item.channel in {"saved_video_review", "video_transcript_memory"} for item in evidence):
        limitations.append("No saved video evidence was selected for this generation. YouTube discovery or an unavailable transcript is not customer evidence.")
    return EvidencePacket(request=request, feedback_records=len(records), topics=topics, evidence=evidence,
                          limitations=limitations, fingerprint=content_hash({
                              "request": request.model_dump(mode="json"),
                              "records": [content_hash(record) for record in records],
                              "topics": [topic.model_dump(mode="json") for topic in topics],
                              "evidence": [item.model_dump(mode="json") for item in evidence],
                              "taxonomy": provider.configuration_hash,
                          }))


def _add_context(connection: sqlite3.Connection, tables: set[str], request: AdvisorRequest,
                 terms: set[str], evidence: list[EvidenceItem]) -> None:
    if "survey_observations" in tables:
        studies = [json.loads(row[0]) for row in connection.execute(
            "SELECT payload_json FROM survey_observations WHERE model=? AND market=? ORDER BY survey_id",
            (request.model_code, request.market))]
        studies.sort(key=lambda s: (-_relevance(s["category_raw"], terms), s["survey_id"]))
        for study in studies[:12]:
            evidence.append(EvidenceItem(
                evidence_id=f"study:{study['survey_id']}", channel="customer_study", title=study["category_raw"],
                text=json.dumps({k: study.get(k) for k in ("category_raw", "statistic_type", "value", "distribution", "year", "respondent_n", "scale_endpoints")}),
                selection_reason="Exact model and market match; category relevance then stable ID; at most 12 study rows.",
                scope={"model": study["model"], "market": study["market"]}, locator={"cells": study["cell_locators"]},
                limitations=study.get("limitations", []) + ["Unmatched study categories require an explicit mapping; respondent count is not supplied."],
            ))
    if "imported_evidence" in tables:
        imported = [json.loads(row[0]) for row in connection.execute(
            "SELECT payload_json FROM imported_evidence WHERE table_name IN ('sales_observation','equipment_fact') ORDER BY row_key")]
        for row in imported:
            payload = row["payload"]
            models = json.loads(payload.get("model_scope_json", "[]")) or [payload.get("model_code")]
            if request.model_code not in models:
                continue
            market = payload.get("market_code")
            if row["table_name"] == "sales_observation" and market != request.market:
                continue
            locator = connection.execute(
                "SELECT payload_json FROM imported_evidence WHERE table_name='source_locator' AND json_extract(payload_json, '$.payload.locator_id')=? LIMIT 1",
                (payload.get("locator_id"),)).fetchone()
            evidence.append(EvidenceItem(
                evidence_id=f"imported:{row['row_key']}", channel=row["table_name"],
                title=payload.get("feature") or f"Supplied {payload.get('calendar_year')} family sales",
                text=json.dumps(payload, ensure_ascii=False),
                selection_reason="Model-matched sales or equipment context, with original market retained.",
                scope={"models": models, "market": market},
                locator={"archive_sha256": row["archive_sha256"], "source": json.loads(locator[0])["payload"] if locator else payload.get("locator_id")},
                limitations=["Imported context awaits claim review. Sales may combine generations and contain no powertrain split.",
                             "Equipment market/derivative/date must match before inferring availability. Prices are not development costs."],
            ))
    if "public_evidence" in tables:
        public = [json.loads(row[0]) for row in connection.execute(
            "SELECT payload_json FROM public_evidence ORDER BY snapshot_at DESC,record_id")]
        seen = set()
        for row in public:
            if row["logical_key"] in seen:
                continue
            seen.add(row["logical_key"])
            if row.get("state") not in (None, "Total"):
                continue  # No state is selected; 51 state rows are not 51 independent arguments.
            if request.model_code not in row.get("models", []) and "*" not in row.get("models", []):
                continue
            if row.get("market") not in {request.market, "global", "GLOBAL", "*"}:
                continue
            if request.powertrain != "ALL" and request.powertrain not in row.get("powertrains", []) and "*" not in row.get("powertrains", []):
                continue
            evidence.append(EvidenceItem(
                evidence_id=f"public:{row['record_id']}", channel="public_context", title=row["kind"],
                text=json.dumps(row["payload"], ensure_ascii=False)[:4000],
                selection_reason="Latest stored snapshot for this source, matched to model and market.",
                scope={"models": row["models"], "market": row["market"], "snapshot_at": row["snapshot_at"]},
                locator={"url": row["source_url"], "sha256": row.get("source_sha256")},
                limitations=[str(row.get("limitations", "")), "Stored context is dated; endpoint failures are missing data, never zero events."],
            ))
    if "report_context" in tables:
        for result in connection.execute("SELECT payload_json FROM report_context ORDER BY context_id"):
            row = json.loads(result[0])
            evidence.append(EvidenceItem(
                evidence_id=f"report:{row['context_id']}", channel="company_context", title=row.get("kind", "Company context"),
                text=row["fact"] + " " + row.get("consideration", ""),
                selection_reason="Company context for strategic questions; no feature-level financial inference.",
                scope={"scope": "company", "published_on": row.get("published_on")},
                locator={"url": row["source_url"], "page": row.get("page")}, limitations=[row.get("limitation", "")],
            ))
    if "bmw_context" in tables:
        provided = [json.loads(row[0]) for row in connection.execute("SELECT payload_json FROM bmw_context ORDER BY observation_id")]
        provided = [row for row in provided if request.model_code in row.get("model_codes", [])
                    and (row["channel"] == "bmw_equipment" or row.get("market") == request.market)]
        provided.sort(key=lambda row: (-_relevance(json.dumps(row.get("raw_payload", {})), terms), row["observation_id"]))
        for row in provided[:10]:
            evidence.append(EvidenceItem(
                evidence_id=f"provided:{row['observation_id']}", channel=row["channel"], title=row["metric"],
                text=json.dumps({key: row.get(key) for key in ("metric", "year", "value", "raw_payload")}, ensure_ascii=False)[:3000],
                selection_reason="Canonical supplied sales/equipment context, model matched and ranked by topic relevance; at most 10 rows.",
                scope={"models": row["model_codes"], "market": row.get("market")}, locator=row["locator"],
                limitations=row.get("limitations", []) + ["Equipment matrix interpretation and cross-market applicability require review."],
            ))
    if "youtube_findings" in tables:
        findings = [json.loads(row[0]) for row in connection.execute("SELECT payload_json FROM youtube_findings ORDER BY evidence_id")]
        findings = [row for row in findings if row.get("generation") == request.model_code]
        findings.sort(key=lambda row: (-_relevance(row["supporting_excerpt"], terms), row["evidence_id"]))
        for row in findings[:6]:
            evidence.append(EvidenceItem(
                evidence_id=f"youtube:{row['evidence_id']}", channel="saved_video_review", title=f"{row['topic']} · {row.get('feedback_type', 'observation')}",
                text=redact(row["supporting_excerpt"]), selection_reason="Saved transcript finding for this generation; at most six examples.",
                scope={"generation": row["generation"], "market": "unknown", "powertrain": "unknown"},
                locator={"url": f"https://www.youtube.com/watch?v={row['video_id']}&t={int(row['timestamp_seconds'])}s",
                         "transcript_sha256": row["transcript_sha256"], "timestamp_seconds": row["timestamp_seconds"]},
                limitations=["Saved extraction; market/powertrain scope and semantic entailment still need review."],
            ))
    if "video_memories" in tables:
        for row in memory_excerpts(connection, request.model_code, request.market, terms):
            evidence.append(EvidenceItem(
                evidence_id=f"memory:{row['memory_id']}:{row['start_char']}", channel="video_transcript_memory",
                title=row["title"], text=redact(row["text"]),
                selection_reason="Reusable transcript excerpt, generation matched and ranked by query relevance; at most two excerpts per video and six total.",
                scope={"generation": row["model_code"], "market": row["market"] or "unknown", "powertrain": "unknown",
                       "scope_basis": "supplied with transcript, not independently verified"},
                locator={"url": row["video_url"], "video_id": row["video_id"], "memory_id": row["memory_id"],
                         "transcript_sha256": row["transcript_sha256"], "start_char": row["start_char"], "end_char": row["end_char"],
                         "source_kind": row["source_kind"], "original_source": row["source_locator"]},
                limitations=["Stored transcript content is source evidence, not a verified fact or engineering approval.",
                             "Video excerpts and saved findings from the same video are not independent customers; scope and claim meaning require review."],
            ))


def model_payload(packet: EvidencePacket) -> dict:
    """Send bounded redacted evidence, excluding original locator quotes/raw files."""
    return {
        "request": packet.request.model_dump(mode="json"), "feedback_records": packet.feedback_records,
        "limitations": packet.limitations,
        "evidence": [{"id": item.evidence_id, "channel": item.channel, "title": item.title,
                      "text": item.text, "scope": item.scope, "why_selected": item.selection_reason,
                      "limitations": item.limitations} for item in packet.evidence],
    }
