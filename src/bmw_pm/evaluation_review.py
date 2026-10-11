"""Local human-review workbench for a private, frozen evaluation set."""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from .evaluation_workflow import (
    SPLITS, HumanLabel, HumanSignal, ResolvedLabel, _validate_review,
    load_frozen, load_labels, score_extraction,
)
from .utils import content_hash


class ReviewInputError(ValueError):
    """A safe validation message for the local review interface."""


def _rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _version(path: Path) -> str:
    return content_hash(path.read_text(encoding="utf-8") if path.exists() else "")


def _write_rows(path: Path, rows: list[dict]) -> None:
    body = "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n"
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=".review-", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(body)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _signals(raw: object, text: str) -> list[HumanSignal]:
    if not isinstance(raw, list) or len(raw) > 10:
        raise ReviewInputError("Enter at most ten separate signals for this record.")
    result = []
    for entry in raw:
        if not isinstance(entry, dict):
            raise ReviewInputError("Each signal needs a topic, claim, outcome, polarity and exact quote.")
        quote = str(entry.get("evidence_text", ""))
        start = text.find(quote) if quote else -1
        if start < 0 or text.find(quote, start + 1) >= 0:
            raise ReviewInputError("Each evidence quote must occur exactly once in the frozen text. Select a longer exact quote if needed.")
        try:
            result.append(HumanSignal.model_validate({
                "need_domain": entry.get("need_domain"),
                "atomic_claim": entry.get("atomic_claim"),
                "customer_outcome": entry.get("customer_outcome"),
                "polarity": entry.get("polarity"),
                "evidence_text": quote,
                "evidence_start": start,
                "evidence_end": start + len(quote),
                "use_context": entry.get("use_context") or None,
                "uncertainties": entry.get("uncertainties") or [],
            }))
        except ValueError as exc:
            raise ReviewInputError("Complete the topic, claim, outcome, polarity and exact quote for every signal.") from exc
    return result


def _root(repo_root: Path) -> Path:
    return repo_root / "runs" / "evaluation-v1"


def review_snapshot(repo_root: Path, *, record_id: str | None = None,
                    role: str = "primary") -> dict:
    root = _root(repo_root)
    if not (root / "receipt.json").is_file():
        return {"available": False, "message": "Freeze the evaluation set with bmw-pm freeze-evaluation first."}
    if role not in {"primary", "secondary", "adjudicator"}:
        raise ReviewInputError("Choose a valid review role.")
    manifest, packets = load_frozen(root)
    secondary_path = root / "second_review.jsonl"
    primary, secondary, counts = load_labels(root, manifest, packets,
        second_review=secondary_path if secondary_path.exists() else None)
    eligible = [item for item in manifest.records if role == "primary" or item.double_label]
    if record_id is None:
        if role == "primary":
            pending = [item for item in eligible if primary[item.record_id].review_status != "labelled"]
        elif role == "secondary":
            pending = [item for item in eligible if item.record_id not in secondary
                       or secondary[item.record_id].review_status != "labelled"]
        else:
            pending = [item for item in eligible if primary[item.record_id].review_status == "labelled"
                       and item.record_id in secondary and secondary[item.record_id].review_status == "labelled"
                       and primary[item.record_id].adjudication is None]
        record_id = (pending or eligible)[0].record_id
    selected = next((item for item in eligible if item.record_id == record_id), None)
    if selected is None:
        raise ReviewInputError("That record is outside this reviewer queue.")
    baseline = {}
    for split in SPLITS:
        run = root / f"baseline-{split}"
        if (run / "run.json").is_file():
            selected_run = [item for item in manifest.records if item.split == split]
            identity = json.loads((run / "run.json").read_text(encoding="utf-8"))
            if (identity.get("evaluation_id") != manifest.evaluation_id or
                    identity.get("corpus_hash") != manifest.corpus_hash or
                    identity.get("record_ids") != [item.record_id for item in selected_run] or
                    identity.get("packet_hashes") != [item.content_hash for item in selected_run]):
                raise ValueError("baseline run does not match the frozen evaluation")
            statuses = {"success": 0, "abstained": 0, "failed": 0, "missing": 0}
            for item in selected_run:
                result_file = run / f"{item.record_id}.json"
                if not result_file.is_file():
                    statuses["missing"] += 1
                    continue
                result = json.loads(result_file.read_text(encoding="utf-8"))
                if result.get("record_id") != item.record_id or result.get("content_hash") != item.content_hash:
                    raise ValueError("baseline result does not match the frozen record")
                statuses[result["status"]] += 1
            gold_ready = sum(primary[item.record_id].review_status == "labelled" and
                (not item.double_label or (item.record_id in secondary and
                    secondary[item.record_id].review_status == "labelled" and
                    primary[item.record_id].adjudication is not None)) for item in selected_run)
            scored = (score_extraction(root, run,
                second_review=secondary_path if secondary_path.exists() else None)
                if gold_ready == len(selected_run) else None)
            baseline[split] = {"records": len(selected_run), "statuses": statuses,
                               "gold_ready": gold_ready,
                               "scored_records": scored["scored_records"] if scored else 0,
                               "metrics": scored["metrics"] if scored else None}
    items = []
    for item in eligible:
        row = secondary.get(item.record_id) if role == "secondary" else primary[item.record_id]
        status = ("resolved" if row.adjudication else "awaiting resolution") if role == "adjudicator" and row.review_status == "labelled" else (row.review_status if row else "unlabelled")
        items.append({"record_id": item.record_id, "split": item.split, "model": item.model,
                      "double_label": item.double_label,
                      "status": status})
    current_primary = primary[record_id]
    current_secondary = secondary.get(record_id)
    case = {"record_id": record_id, "text": packets[record_id].text,
            "model": selected.model, "country": selected.country, "powertrain": selected.powertrain,
            "source_label": selected.source_label, "split": selected.split,
            "double_label": selected.double_label, "content_hash": selected.content_hash}
    if role == "primary":
        case["review"] = current_primary.model_dump(mode="json")
    elif role == "secondary":
        case["review"] = current_secondary.model_dump(mode="json") if current_secondary else None
    else:
        case["primary"] = current_primary.model_dump(mode="json")
        case["secondary"] = current_secondary.model_dump(mode="json") if current_secondary else None
    return {"available": True, "evaluation_id": manifest.evaluation_id,
            "corpus_hash": manifest.corpus_hash, "total": len(manifest.records),
            "counts": {**counts, "ai_assisted_first_reviews": sum(
                row.review_status == "labelled" and row.review_method == "ai_assisted_verified"
                for row in primary.values())},
            "items": items, "case": case, "role": role,
            "file_version": _version(secondary_path if role == "secondary" else root / "human_labels.jsonl"),
            "baseline": baseline, "limitations": manifest.limitations}


def save_review(repo_root: Path, payload: dict) -> dict:
    root = _root(repo_root)
    manifest, packets = load_frozen(root)
    role = payload.get("role")
    if role not in {"primary", "secondary", "adjudicator"}:
        raise ReviewInputError("Choose a valid review role.")
    record_id = payload.get("record_id")
    item = next((row for row in manifest.records if row.record_id == record_id), None)
    if item is None or (role == "secondary" and not item.double_label):
        raise ReviewInputError("That record is outside this reviewer queue.")
    primary_path = root / "human_labels.jsonl"
    secondary_path = root / "second_review.jsonl"
    target = secondary_path if role == "secondary" else primary_path
    if payload.get("file_version") != _version(target):
        raise ReviewInputError("Another review changed this file. Reload before saving.")
    reviewer = str(payload.get("reviewer_id", "")).strip()
    if not reviewer or len(reviewer) > 100:
        raise ReviewInputError("Enter your reviewer ID before saving.")
    signals = _signals(payload.get("signals", []), packets[record_id].text)
    abstention = str(payload.get("abstention_reason") or "").strip() or None
    if not signals and not abstention:
        raise ReviewInputError("Add a supported signal or explain why you abstain.")
    if signals and abstention:
        raise ReviewInputError("Clear the abstention reason when recording signals.")
    primary_rows = _rows(primary_path)
    primary = next(row for row in primary_rows if row["record_id"] == record_id)
    secondary_rows = _rows(secondary_path)
    second = next((row for row in secondary_rows if row["record_id"] == record_id), None)
    if role == "adjudicator":
        if not item.double_label or primary["review_status"] != "labelled" or not second or second["review_status"] != "labelled":
            raise ReviewInputError("Two independent completed reviews are required before adjudication.")
        if primary["reviewer_id"] == second["reviewer_id"]:
            raise ReviewInputError("The second reviewer must be a different person.")
        if reviewer in {primary["reviewer_id"], second["reviewer_id"]}:
            raise ReviewInputError("Use an independent adjudicator ID.")
        reason = str(payload.get("reason") or "").strip()
        if not reason or len(reason) > 1000:
            raise ReviewInputError("Explain how the two reviews were resolved.")
        resolved = ResolvedLabel(reviewer_id=reviewer, reviewed_at=datetime.now(timezone.utc).isoformat(),
                                 reason=reason, signals=signals,
                                 abstention_reason=abstention)
        candidate = dict(primary, adjudication=resolved.model_dump(mode="json"))
        _validate_review(HumanLabel.model_validate(candidate), packets[record_id])
        primary_rows[primary_rows.index(primary)] = candidate
        _write_rows(primary_path, primary_rows)
    else:
        if primary.get("adjudication"):
            raise ReviewInputError("This case has been adjudicated. Preserve the resolved label.")
        if role == "secondary" and primary["reviewer_id"] == reviewer and primary["review_status"] == "labelled":
            raise ReviewInputError("The second reviewer must be a different person.")
        if role == "primary" and second and second["review_status"] == "labelled" and second["reviewer_id"] == reviewer:
            raise ReviewInputError("The first reviewer must be different from the second reviewer.")
        candidate = {"record_id": record_id, "reviewer_id": reviewer,
                     "reviewed_at": datetime.now(timezone.utc).isoformat(), "review_status": "labelled",
                     "review_method": primary.get("review_method", "independent") if role == "primary" else "independent",
                     "source_draft_hash": primary.get("source_draft_hash") if role == "primary" else None,
                     "signals": [signal.model_dump(mode="json") for signal in signals],
                     "abstention_reason": abstention, "difficulty": str(payload.get("difficulty") or "").strip() or None,
                     "double_label": item.double_label, "adjudication": None}
        _validate_review(HumanLabel.model_validate(candidate), packets[record_id])
        rows = secondary_rows if role == "secondary" else primary_rows
        if role == "secondary" and second:
            rows[rows.index(second)] = candidate
        elif role == "secondary":
            rows.append(candidate)
        else:
            rows[rows.index(primary)] = candidate
        _write_rows(target, rows)
    return review_snapshot(repo_root, record_id=record_id, role=role)


def evaluation_action(repo_root: Path, payload: dict) -> dict:
    action = payload.get("action", "summary")
    if action == "summary":
        return review_snapshot(repo_root, record_id=payload.get("record_id"),
                               role=payload.get("role", "primary"))
    if action == "save":
        return save_review(repo_root, payload)
    raise ReviewInputError("Unknown evaluation action.")
