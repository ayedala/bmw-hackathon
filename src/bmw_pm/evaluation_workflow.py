"""Private, frozen-input extraction evaluation. Human labels are never model output."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .contracts import EvaluationManifest, FeedbackRecord, Polarity, Signal, SourceLocator
from .intelligence.provider import ExtractionProvider
from .utils import content_hash


SPLITS = ("development", "heldout_g60", "transfer_f70", "transfer_g70")


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FrozenPacket(_Strict):
    record_id: str
    text: str
    content_hash: str
    known_context: dict[str, str | None]
    locators: list[SourceLocator]


class HumanSignal(_Strict):
    need_domain: str = Field(min_length=1)
    atomic_claim: str = Field(min_length=1)
    customer_outcome: str = Field(min_length=1)
    polarity: Polarity
    evidence_text: str = Field(min_length=1)
    evidence_start: int = Field(ge=0)
    evidence_end: int = Field(gt=0)
    use_context: str | None = None
    uncertainties: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def valid_offsets(self) -> "HumanSignal":
        if self.evidence_end <= self.evidence_start:
            raise ValueError("evidence_end must exceed evidence_start")
        return self


class ResolvedLabel(_Strict):
    reviewer_id: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    signals: list[HumanSignal]
    abstention_reason: str | None = None


class HumanLabel(_Strict):
    record_id: str
    reviewer_id: str | None
    review_status: Literal["unlabelled", "labelled"]
    signals: list[HumanSignal]
    abstention_reason: str | None
    difficulty: str | None
    double_label: bool
    adjudication: ResolvedLabel | None


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def load_frozen(root: Path) -> tuple[EvaluationManifest, dict[str, FrozenPacket]]:
    receipt = json.loads((root / "receipt.json").read_text(encoding="utf-8"))
    expected = {"manifest.json", *(f"{split}.jsonl" for split in SPLITS)}
    if set(receipt) != expected:
        raise ValueError("frozen receipt has missing or extra entries")
    for name, digest in receipt.items():
        if content_hash((root / name).read_text(encoding="utf-8")) != digest:
            raise ValueError(f"frozen input hash mismatch: {name}")
    manifest = EvaluationManifest.model_validate_json((root / "manifest.json").read_text(encoding="utf-8"))
    entries = {item.record_id: item for item in manifest.records}
    packets: dict[str, FrozenPacket] = {}
    for split in SPLITS:
        for raw in _read_jsonl(root / f"{split}.jsonl"):
            packet = FrozenPacket.model_validate(raw)
            item = entries.get(packet.record_id)
            if item is None or item.split != split or packet.record_id in packets:
                raise ValueError(f"unexpected or duplicate packet: {packet.record_id}")
            if (content_hash(packet.text) != item.content_hash or packet.content_hash != item.content_hash
                    or packet.known_context != {"model": item.model, "country": item.country,
                                                 "powertrain": item.powertrain}
                    or not packet.locators or packet.locators[0].source_hash != item.source_hash):
                raise ValueError(f"packet differs from manifest: {packet.record_id}")
            packets[packet.record_id] = packet
    if set(packets) != set(entries):
        raise ValueError("frozen packets do not cover manifest exactly")
    return manifest, packets


def _validate_review(label: HumanLabel, packet: FrozenPacket) -> None:
    if label.review_status == "unlabelled":
        if label.reviewer_id or label.signals or label.abstention_reason or label.adjudication:
            raise ValueError("unlabelled row contains review content")
        return
    if not label.reviewer_id or not label.reviewer_id.strip():
        raise ValueError("labelled row needs reviewer_id")
    _validate_signals(label.signals, label.abstention_reason, packet)
    if label.adjudication:
        _validate_signals(label.adjudication.signals, label.adjudication.abstention_reason, packet)


def _validate_signals(signals: list[HumanSignal], abstention_reason: str | None,
                      packet: FrozenPacket) -> None:
    if not signals and not (abstention_reason and abstention_reason.strip()):
        raise ValueError("empty signals require an abstention reason")
    if signals and abstention_reason:
        raise ValueError("nonempty signals cannot also abstain")
    for signal in signals:
        if packet.text[signal.evidence_start:signal.evidence_end] != signal.evidence_text:
            raise ValueError("human evidence span does not match frozen text")


def load_labels(root: Path, manifest: EvaluationManifest, packets: dict[str, FrozenPacket],
                *, second_review: Path | None = None) -> tuple[dict[str, HumanLabel], dict[str, HumanLabel], dict]:
    entries = {item.record_id: item for item in manifest.records}

    def read(path: Path, *, secondary: bool) -> dict[str, HumanLabel]:
        result: dict[str, HumanLabel] = {}
        for raw in _read_jsonl(path):
            row = HumanLabel.model_validate(raw)
            item = entries.get(row.record_id)
            if item is None or row.record_id in result or row.double_label != item.double_label:
                raise ValueError(f"unknown, duplicate, or inconsistent label: {row.record_id}")
            if secondary and (not item.double_label or row.adjudication):
                raise ValueError(f"invalid second review: {row.record_id}")
            _validate_review(row, packets[row.record_id])
            result[row.record_id] = row
        return result

    primary = read(root / "human_labels.jsonl", secondary=False)
    if set(primary) != set(entries):
        raise ValueError("primary labels must cover frozen manifest exactly")
    secondary = read(second_review, secondary=True) if second_review else {}
    ready = 0
    provisional = 0
    for record_id, row in primary.items():
        if row.review_status != "labelled":
            continue
        if not row.double_label:
            if row.adjudication:
                raise ValueError(f"unexpected adjudication: {record_id}")
            ready += 1
            continue
        second = secondary.get(record_id)
        if second and second.review_status == "labelled" and second.reviewer_id == row.reviewer_id:
            raise ValueError(f"second review must be independent: {record_id}")
        if second and second.review_status == "labelled" and row.adjudication:
            ready += 1
        else:
            provisional += 1
    report = {"total": len(entries), "unlabelled": len(entries) - ready - provisional,
              "provisional": provisional, "gold_ready": ready,
              "second_reviewed": sum(row.review_status == "labelled" for row in secondary.values())}
    return primary, secondary, report


def _feedback_from_packet(packet: FrozenPacket) -> FeedbackRecord:
    scope = packet.known_context
    return FeedbackRecord(record_id=packet.record_id, source_id=packet.locators[0].source_id,
        source_record_id=packet.record_id, raw_text_ref="frozen redacted evaluation packet",
        cleaned_text=packet.text, redacted_text=packet.text, raw_country=scope["country"],
        country=scope["country"], raw_model=scope["model"], model_code=scope["model"],
        raw_brand=None, raw_sales_description=None, raw_derivative=None,
        powertrain_raw=scope["powertrain"], powertrain=scope["powertrain"],
        powertrain_mapping_status="exact", source_label=None,
        row_locators=packet.locators, transformation_ids=[])


def _atomic_json(path: Path, data: dict) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def run_extraction(root: Path, output: Path, provider: ExtractionProvider,
                   *, split: str = "development", retry_failures: bool = False) -> dict:
    if split not in SPLITS:
        raise ValueError(f"unknown split: {split}")
    manifest, packets = load_frozen(root)
    descriptor = provider.descriptor.model_dump(mode="json")
    selected = [item for item in manifest.records if item.split == split]
    identity = {"evaluation_id": manifest.evaluation_id, "corpus_hash": manifest.corpus_hash,
                "split": split, "record_ids": [item.record_id for item in selected],
                "packet_hashes": [item.content_hash for item in selected],
                "provider": descriptor,
                "provider_config_hash": getattr(provider, "configuration_hash", None)}
    output.mkdir(parents=True, exist_ok=True)
    meta = output / "run.json"
    if meta.exists():
        if json.loads(meta.read_text(encoding="utf-8")) != identity:
            raise ValueError("run identity changed; use a new output directory")
    else:
        if any(output.iterdir()):
            raise ValueError("output directory contains files without a run manifest")
        _atomic_json(meta, identity)
    counts = {"success": 0, "abstained": 0, "failed": 0, "reused": 0}
    for item in selected:
        target = output / f"{item.record_id}.json"
        if target.exists():
            prior = json.loads(target.read_text(encoding="utf-8"))
            if prior.get("record_id") != item.record_id or prior.get("content_hash") != item.content_hash:
                raise ValueError(f"saved result does not match frozen record: {item.record_id}")
            if prior.get("status") != "failed" or not retry_failures:
                counts[prior["status"]] += 1
                counts["reused"] += 1
                continue
        started = time.perf_counter()
        try:
            signals = provider.extract([_feedback_from_packet(packets[item.record_id])], run_id=output.name)
            for signal in signals:
                _check_prediction(signal, packets[item.record_id])
            status = "success" if signals else "abstained"
            result = {"record_id": item.record_id, "content_hash": item.content_hash,
                      "status": status, "signals": [s.model_dump(mode="json") for s in signals],
                      "abstention_reason": getattr(provider, "last_abstention_reason", None) if not signals else None,
                      "returned_model": provider.descriptor.model_id,
                      "usage": getattr(provider, "last_usage", None),
                      "duration_ms": round((time.perf_counter() - started) * 1000, 2)}
        except Exception as exc:
            result = {"record_id": item.record_id, "content_hash": item.content_hash,
                      "status": "failed", "signals": [], "error_type": type(exc).__name__,
                      "duration_ms": round((time.perf_counter() - started) * 1000, 2)}
            status = "failed"
        _atomic_json(target, result)
        counts[status] += 1
    return {"output": str(output), "split": split, "attempted": len(selected), **counts,
            "quality": "unmeasured until independently reviewed labels are available"}


def _check_prediction(signal: Signal, packet: FrozenPacket) -> None:
    if signal.feedback_record_id != packet.record_id or not signal.evidence_spans:
        raise ValueError("predicted signal has missing or wrong evidence record")
    for span in signal.evidence_spans:
        if (span.record_id != packet.record_id or packet.text[span.start:span.end] != span.text
                or span.locator.source_hash != packet.locators[0].source_hash):
            raise ValueError("predicted evidence span does not match frozen packet")


def _matches(predicted: Signal, gold: HumanSignal) -> bool:
    if predicted.need_domain.casefold().strip() != gold.need_domain.casefold().strip() or predicted.polarity != gold.polarity:
        return False
    return any(span.start < gold.evidence_end and gold.evidence_start < span.end
               for span in predicted.evidence_spans)


def _max_matches(predictions: list[Signal], gold: list[HumanSignal]) -> int:
    matched: dict[int, int] = {}

    def assign(i: int, seen: set[int]) -> bool:
        for j, label in enumerate(gold):
            if j in seen or not _matches(predictions[i], label):
                continue
            seen.add(j)
            if j not in matched or assign(matched[j], seen):
                matched[j] = i
                return True
        return False

    return sum(assign(i, set()) for i in range(len(predictions)))


def score_extraction(root: Path, output: Path, *, second_review: Path | None = None) -> dict:
    manifest, packets = load_frozen(root)
    primary, secondary, label_status = load_labels(root, manifest, packets, second_review=second_review)
    identity = json.loads((output / "run.json").read_text(encoding="utf-8"))
    selected = [item for item in manifest.records if item.split == identity["split"]]
    if (identity["evaluation_id"] != manifest.evaluation_id or identity["corpus_hash"] != manifest.corpus_hash
            or identity["record_ids"] != [item.record_id for item in selected]
            or identity["packet_hashes"] != [item.content_hash for item in selected]):
        raise ValueError("extraction run is not for these frozen inputs")
    statuses = {"success": 0, "abstained": 0, "failed": 0, "missing": 0}
    tp = fp = fn = evaluated = 0
    gold_ready_in_split = 0
    for item in selected:
        row = primary[item.record_id]
        second = secondary.get(item.record_id)
        ready = (row.review_status == "labelled" and
                 (not row.double_label or (second is not None and second.review_status == "labelled"
                                           and row.adjudication is not None)))
        gold_ready_in_split += int(ready)
        path = output / f"{item.record_id}.json"
        if not path.exists():
            statuses["missing"] += 1
            continue
        result = json.loads(path.read_text(encoding="utf-8"))
        if result["record_id"] != item.record_id or result["content_hash"] != item.content_hash:
            raise ValueError(f"result identity mismatch: {item.record_id}")
        status = result["status"]
        statuses[status] += 1
        predictions = [Signal.model_validate(raw) for raw in result["signals"]]
        for prediction in predictions:
            _check_prediction(prediction, packets[item.record_id])
        if not ready or status == "failed":
            continue
        gold = row.adjudication.signals if row.adjudication else row.signals
        matches = _max_matches(predictions, gold)
        tp += matches
        fp += len(predictions) - matches
        fn += len(gold) - matches
        evaluated += 1
    metrics = None
    if evaluated:
        precision = tp / (tp + fp) if tp + fp else None
        recall = tp / (tp + fn) if tp + fn else None
        f1 = 2 * precision * recall / (precision + recall) if precision is not None and recall is not None and precision + recall else None
        metrics = {"records": evaluated, "true_positive": tp, "false_positive": fp,
                   "false_negative": fn, "precision": precision, "recall": recall, "f1": f1,
                   "definition": "Exact normalized topic and polarity, overlapping evidence span, one-to-one matches; proxy only, not semantic entailment."}
    return {"run": str(output), "split": identity["split"], "provider": identity["provider"],
            "records": len(selected), "statuses": statuses, "labels": label_status,
            "primary_labels_hash": content_hash((root / "human_labels.jsonl").read_text(encoding="utf-8")),
            "second_review_hash": content_hash(second_review.read_text(encoding="utf-8")) if second_review else None,
            "gold_ready_in_split": gold_ready_in_split, "scored_records": evaluated,
            "gold_ready_not_scored": gold_ready_in_split - evaluated,
            "metrics": metrics, "citation_entailment": "unmeasured_human_review_required"}
