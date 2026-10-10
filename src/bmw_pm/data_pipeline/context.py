"""Supplied sales and equipment context, without interpreting PDF matrix symbols."""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any
from uuid import uuid4

from openpyxl import load_workbook

from ..contracts import BMWContextObservation, SourceDocument, SourceLocator
from ..storage import Database
from ..utils import content_hash, sha256_file, stable_id, utc_now
from .feedback import IngestionError

PARSER_VERSION = "bmw-context-v1"


def source_document(path: Path, kind: str) -> SourceDocument:
    digest = sha256_file(path)
    return SourceDocument(source_id=stable_id("source", digest), local_or_web="local",
        original_name_or_url=path.name, sha256=digest, byte_count=path.stat().st_size,
        mime_type="application/pdf" if path.suffix.lower() == ".pdf" else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        acquired_at=utc_now(), source_type=kind, access_scope="local_restricted",
        origin_family_id=stable_id("source", digest), parser_version=PARSER_VERSION,
        rights_notes="Private user-supplied BMW challenge material. Preserve original bytes and scope.")


def parse_sales(path: Path) -> tuple[SourceDocument, list[BMWContextObservation]]:
    source = source_document(path, "supplied_sales_workbook")
    book = load_workbook(path, read_only=True, data_only=False)
    cached = load_workbook(path, read_only=False, data_only=True)
    result = []
    try:
        for sheet in book:
            rows = sheet.iter_rows(min_row=1, max_row=5, max_col=5)
            if [c.value for c in next(rows)] != ["market", "market_code", "volume_2024", "volume_2025", "volume_2030"]:
                raise IngestionError(f"Unexpected sales headers in {sheet.title}")
            models = sheet.title.split("_")
            for row in rows:
                if not isinstance(row[0].value, str) or not isinstance(row[1].value, str):
                    raise IngestionError("Missing sales market labels")
                for cell, year in zip(row[2:], (2024, 2025, 2030)):
                    formula = cell.value if cell.data_type == "f" else None
                    value = cached[sheet.title][cell.coordinate].value if formula else cell.value
                    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                        raise IngestionError(f"Missing/invalid numeric sales value at {sheet.title}!{cell.coordinate}; formulas are never evaluated")
                    limitations = ["Supplied workbook values are not independently verified sales statistics.",
                        "Market labels are aggregate regions; they do not make feedback representative.",
                        "No powertrain breakdown is supplied."]
                    if len(models) > 1:
                        limitations.append("Combined G60/G68 family totals cannot be split between generations.")
                    if year == 2030:
                        limitations.append("2030 is a supplied planning scenario, not observed sales.")
                    if formula:
                        limitations.append("Value is the workbook's saved formula cache; the formula was retained and not executed or independently recalculated.")
                    result.append(BMWContextObservation(
                        observation_id=stable_id("context", source.sha256, PARSER_VERSION, sheet.title, cell.coordinate),
                        channel="bmw_sales", source_id=source.source_id, source_hash=source.sha256,
                        model_codes=models, market=row[1].value, metric="supplied_sales_volume", year=year, value=value,
                        locator=SourceLocator(source_id=source.source_id, source_hash=source.sha256,
                            locator_type="sheet_range", sheet=sheet.title, cell_range=cell.coordinate,
                            extracted_value=str(value)),
                        raw_payload={"market_label": row[0].value, "market_code": row[1].value,
                            "model_family_raw": sheet.title, "raw_cell_value": cell.value, "cached_formula_value": value if formula else None},
                        limitations=limitations))
    finally:
        book.close()
        cached.close()
    return source, result


def parse_equipment(path: Path, model: str) -> tuple[SourceDocument, list[BMWContextObservation]]:
    try:
        from pypdf import PdfReader
    except ImportError as error:
        raise IngestionError("Equipment ingestion requires the data extra: pip install -e '.[data]'") from error
    source = source_document(path, "supplied_equipment_pdf")
    reader = PdfReader(path)
    result = []
    for number, page in enumerate(reader.pages, 1):
        text = page.extract_text() or ""
        result.append(BMWContextObservation(
            observation_id=stable_id("context", source.sha256, PARSER_VERSION, str(number)),
            channel="bmw_equipment", source_id=source.source_id, source_hash=source.sha256,
            model_codes=[model], market="DE", metric="equipment_page_text",
            locator=SourceLocator(source_id=source.source_id, source_hash=source.sha256,
                locator_type="page_region", page=number, section="Full page text; matrix interpretation unreviewed",
                exact_quote=text), raw_payload={"text": text, "file_name": path.name,
                    "extraction_status": "text_extracted" if text.strip() else "needs_ocr_or_visual_review"},
            limitations=["German-market equipment document; does not establish equipment fitted to an undated US vehicle.",
                "Page text is discovery context. Derivative columns, option codes, symbols, prices and footnotes require visual interpretation before making equipment claims.",
                "A blank standard-equipment matrix cell does not establish that a feature is unavailable as an option.",
                "Document edition/date must be checked on original pages; no feedback observation date is supplied."]))
    return source, result


def ingest_provided_context(database: Database, root: Path) -> dict[str, Any]:
    parsed = []
    if (root / "sales_volumes.xlsx").exists():
        parsed.append(parse_sales(root / "sales_volumes.xlsx"))
    for model in ("F70", "G60", "G70"):
        path = root / f"{model}_OptionList.PDF"
        if path.exists():
            parsed.append(parse_equipment(path, model))
    report: dict[str, Any] = {"sales_observations": 0, "equipment_pages": 0, "sources": []}
    manifest_path = root / "drive_manifest.json"
    acquisition = json.loads(manifest_path.read_text()) if manifest_path.exists() else None
    with database.connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute("CREATE TABLE IF NOT EXISTS bmw_context (observation_id TEXT PRIMARY KEY, source_id TEXT NOT NULL REFERENCES sources(source_id), payload_json TEXT NOT NULL, payload_hash TEXT NOT NULL)")
        connection.execute("CREATE TABLE IF NOT EXISTS source_acquisitions (acquisition_id TEXT PRIMARY KEY, source_id TEXT NOT NULL REFERENCES sources(source_id), payload_json TEXT NOT NULL, payload_hash TEXT NOT NULL)")
        inserted = 0
        for source, observations in parsed:
            database._ensure_source(connection, source)
            report["sources"].append({"name": source.original_name_or_url, "sha256": source.sha256, "observations": len(observations)})
            for observation in observations:
                inserted += database._insert_immutable(connection, "bmw_context", "observation_id", observation.observation_id,
                    {"observation_id": observation.observation_id, "source_id": source.source_id,
                        "payload_json": observation.model_dump_json(), "payload_hash": content_hash(observation)})
                report["sales_observations" if observation.channel == "bmw_sales" else "equipment_pages"] += 1
        if acquisition:
            for item in acquisition["files"]:
                path = root / item["name"]
                if path.name != item["name"] or sha256_file(path) != item["sha256"]:
                    raise IngestionError("Drive acquisition manifest does not match original bytes")
                source_id = stable_id("source", item["sha256"])
                payload = {"folder_url": acquisition["folder_url"], **item}
                key = content_hash(payload)
                database._insert_immutable(connection, "source_acquisitions", "acquisition_id", key,
                    {"acquisition_id": key, "source_id": source_id, "payload_json": json.dumps(payload), "payload_hash": content_hash(payload)})
        database._append_audit(connection, actor_id="provided-context-ingestion", actor_type="pipeline",
            action="ingest_bmw_context", object_type="evidence_corpus", object_id=content_hash(report),
            object_revision=None, before_hash=None, after_hash=content_hash(report),
            reason=f"{inserted} new sales/page context observations; Drive lineage retained where supplied.",
            request_id=f"provided-context:{uuid4().hex}", result="success" if inserted else "noop")
        connection.commit()
    report["inserted"] = inserted
    return report


def source_acquisition_urls(database: Database) -> dict[str, str]:
    with database.connect() as connection:
        if not connection.execute("SELECT 1 FROM sqlite_master WHERE name='source_acquisitions'").fetchone():
            return {}
        urls = {row[0]: json.loads(row[1])["url"] for row in connection.execute(
            "SELECT source_id,payload_json FROM source_acquisitions ORDER BY acquisition_id")}
        database._append_audit(connection, actor_id="workbench", actor_type="pipeline",
            action="read_source_acquisitions", object_type="evidence_corpus", object_id="drive_lineage",
            object_revision=None, before_hash=None, after_hash=None, reason="Display original Drive source links.",
            request_id=uuid4().hex, result="success")
        connection.commit()
        return urls
