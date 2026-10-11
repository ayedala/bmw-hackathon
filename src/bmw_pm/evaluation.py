"""Freeze evaluation inputs before prompt tuning; human labels remain separate."""
import json
from collections import defaultdict, deque
from pathlib import Path

from .contracts import EvaluationManifest, EvaluationRecord, FeedbackRecord
from .utils import content_hash


def build_manifest(records: list[FeedbackRecord], *, seed: str = "evaluation-v1",
                   sizes: tuple[int, int, int, int] = (60, 30, 15, 15)) -> EvaluationManifest:
    if any(size <= 0 for size in sizes):
        raise ValueError("evaluation split sizes must be positive")
    if len({r.record_id for r in records}) != len(records):
        raise ValueError("duplicate input record IDs")
    groups = defaultdict(list)
    for record in records:
        groups[content_hash(" ".join(record.redacted_text.casefold().split()))].append(record)
    buckets = defaultdict(lambda: defaultdict(list))
    for group_hash, members in groups.items():
        # A group shared across models cannot independently test transfer.
        if len({r.model_code for r in members}) != 1:
            continue
        representative = min(members, key=lambda r: r.record_id)
        stratum = (representative.source_label or "unknown", representative.country or "unknown",
                   representative.powertrain or "unknown")
        buckets[representative.model_code][stratum].append((group_hash, representative, members))
    selected = []
    for model, split_sizes in (("G60", [("development", sizes[0]), ("heldout_g60", sizes[1])]),
                              ("F70", [("transfer_f70", sizes[2])]),
                              ("G70", [("transfer_g70", sizes[3])])):
        queues = {key: deque(sorted(items, key=lambda item: content_hash([seed, item[0]])))
                  for key, items in buckets[model].items()}
        ordered = []
        while any(queues.values()):
            for key in sorted(queues):
                if queues[key]:
                    ordered.append(queues[key].popleft())
        if len(ordered) < sum(n for _, n in split_sizes):
            raise ValueError(f"insufficient independent groups for {model}")
        offset = 0
        for split, size in split_sizes:
            for group_hash, record, members in ordered[offset:offset + size]:
                selected.append(EvaluationRecord(record_id=record.record_id,
                    grouped_record_ids=sorted(r.record_id for r in members), split=split,
                    model=model, source_label=record.source_label, country=record.country,
                    powertrain=record.powertrain, source_hash=record.row_locators[0].source_hash,
                    content_hash=content_hash(record.redacted_text), group_hash=group_hash,
                    double_label=False))
            offset += size
    # Distribute second-review assignments across all splits; difficulty remains human-assessed.
    double_ids = set()
    for split, count in zip(("development", "heldout_g60", "transfer_f70", "transfer_g70"), (15, 7, 4, 4)):
        candidates = sorted((r for r in selected if r.split == split),
                            key=lambda r: content_hash([seed, "double", r.record_id]))
        double_ids.update(r.record_id for r in candidates[:count])
    selected = [r.model_copy(update={"double_label": r.record_id in double_ids}) for r in selected]
    corpus_hash = content_hash(sorted((r.record_id, content_hash(r.redacted_text),
                                      content_hash(r)) for r in records))
    return EvaluationManifest(evaluation_id=seed, seed=seed, corpus_hash=corpus_hash, records=selected,
        limitations=["Exact normalized-text groups only; near-duplicate/repost adjudication remains pending.",
            "Held-out means reserved from future tuning, not guaranteed unseen: prior baseline processing and preparation inspected this corpus.",
            "No human labels, semantic accuracy or ranking quality are established by freezing inputs.",
            "Rare strata are deliberately represented; sample is not population representative.",
            "Difficult, mixed and severe cases still need human screening; 30 second-review assignments are provisional."])


def freeze_evaluation(database, output: Path, *, seed: str = "evaluation-v1") -> dict:
    records = database.feedback_records()
    manifest = build_manifest(records, seed=seed)
    by_id = {r.record_id: r for r in records}
    files = {"manifest.json": manifest.model_dump_json(indent=2)}
    for split in ("development", "heldout_g60", "transfer_f70", "transfer_g70"):
        packets = []
        for item in manifest.records:
            if item.split == split:
                record = by_id[item.record_id]
                packets.append(dict(record_id=item.record_id, text=record.redacted_text,
                    content_hash=item.content_hash, known_context=dict(model=item.model,
                    country=item.country, powertrain=item.powertrain),
                    locators=[loc.model_dump(mode="json") for loc in record.row_locators]))
        files[f"{split}.jsonl"] = "\n".join(json.dumps(p, ensure_ascii=False) for p in packets) + "\n"
    receipt = {name: content_hash(body) for name, body in files.items()}
    if output.exists():
        for name, body in files.items():
            if not (output / name).exists() or (output / name).read_text(encoding="utf-8") != body:
                raise ValueError("Frozen evaluation differs or is incomplete; use a new version, never overwrite.")
        if json.loads((output / "receipt.json").read_text()) != receipt:
            raise ValueError("Frozen receipt changed")
        return {"status": "unchanged", "records": len(manifest.records), "output": str(output)}
    # Record the private evidence export before writing; retry uses the same request identity.
    with database.connect() as connection:
        database._append_audit(connection, actor_id="evaluation-pipeline", actor_type="pipeline",
            action="freeze_evaluation_export", object_type="evaluation", object_id=seed,
            object_revision=1, before_hash=None, after_hash=content_hash(manifest),
            reason="Export redacted grouped evidence for independent human labels; no model outputs or legacy labels.",
            request_id=f"evaluation:{seed}:{content_hash(manifest)}", result="success")
        connection.commit()
    output.mkdir(parents=True)
    for name, body in files.items():
        (output / name).write_text(body, encoding="utf-8")
    (output / "receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    # Mutable human workbooks are separate from frozen input hashes.
    templates = [dict(record_id=r.record_id, reviewer_id=None, review_status="unlabelled",
        signals=[], abstention_reason=None, difficulty=None, double_label=r.double_label,
        adjudication=None) for r in manifest.records]
    (output / "human_labels.jsonl").write_text(
        "\n".join(json.dumps(row) for row in templates) + "\n", encoding="utf-8")
    return {"status": "created", "records": len(manifest.records),
            "double_label_assignments": sum(r.double_label for r in manifest.records), "output": str(output)}
