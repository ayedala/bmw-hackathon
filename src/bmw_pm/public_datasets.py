"""Bounded public-data imports for review context, never automatic priority multipliers."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from .contracts import RequirementRevision


NHTSA_ROOT = "https://api.nhtsa.gov"
COMPONENT_DOMAINS = {
    "software_reliability": ("ELECTRICAL SYSTEM",),
    "driver_assistance": (
        "FORWARD COLLISION AVOIDANCE", "BACK OVER PREVENTION",
        "LANE DEPARTURE", "VEHICLE SPEED CONTROL",
    ),
    "ride_and_comfort": ("SEATS", "SUSPENSION"),
}


def validate_public_record(record: dict[str, Any]) -> None:
    required = ("record_id", "logical_key", "snapshot_at", "kind", "source_url",
                "market", "models", "domains", "limitations", "payload")
    if not all(record.get(key) for key in required):
        raise ValueError("public evidence record is missing provenance or scope")
    if not str(record["source_url"]).startswith("https://"):
        raise ValueError("public evidence requires an HTTPS source")
    if not isinstance(record["models"], list) or not isinstance(record["domains"], list):
        raise ValueError("public evidence scope must use lists")


def public_record_applies(
    record: dict[str, Any], requirement: RequirementRevision, *, state: str | None = None,
    domain: str | None = None,
) -> bool:
    domain = domain or requirement.title.casefold().replace(" ", "_")
    if record["market"] not in requirement.scope.countries:
        return False
    if "*" not in record["models"] and not set(record["models"]).intersection(requirement.scope.models):
        return False
    if "*" not in record["domains"] and domain not in record["domains"]:
        return False
    if record["kind"] == "nhtsa_model_year_summary":
        matched = record["payload"]["by_domain"].get(domain, {})
        if not matched.get("complaint_ids") and not matched.get("campaign_ids"):
            return False
    powertrains = record.get("powertrains", ["*"])
    if "*" not in powertrains and not set(powertrains).intersection(requirement.scope.powertrains):
        return False
    row_state = record.get("state")
    return row_state in (None, "Total") if state is None else row_state == state


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _get(url: str) -> bytes:
    if not url.startswith((NHTSA_ROOT + "/", "https://afdc.energy.gov/")):
        raise ValueError("public-data collector only fetches the two approved official hosts")
    request = Request(url, headers={"User-Agent": "BMWProductDecisionLab/0.1 (public data research)"})
    try:
        with urlopen(request, timeout=25) as response:
            if not response.geturl().startswith((NHTSA_ROOT + "/", "https://afdc.energy.gov/")):
                raise ValueError("public source redirected outside the approved hosts")
            if response.status != 200:
                raise RuntimeError(f"public source returned HTTP {response.status}: {url}")
            return response.read(10_000_001)
    except HTTPError as exc:
        raise RuntimeError(f"public source returned HTTP {exc.code}: {url}") from exc


def _get_json(url: str) -> tuple[dict[str, Any], str]:
    raw = _get(url)
    if len(raw) > 10_000_000:
        raise ValueError("NHTSA response exceeds the 10 MB import limit")
    data = json.loads(raw)
    if not isinstance(data, dict) or not isinstance(data.get("results"), list):
        raise ValueError("unexpected NHTSA response structure")
    return data, _sha(raw)


def _nhtsa_url(path: str, **params: object) -> str:
    return f"{NHTSA_ROOT}/{path}?{urlencode(params)}"


def _exact_model_query(url: str, *, listed: bool) -> tuple[dict[str, Any], str | None, str]:
    if not listed:
        return {"results": []}, None, "not_listed"
    try:
        data, digest = _get_json(url)
        return data, digest, "ok"
    except RuntimeError as exc:
        if "HTTP 400:" in str(exc):
            return {"results": []}, None, "http_400"
        raise


def _domains_for_components(value: str) -> set[str]:
    upper = value.upper()
    return {domain for domain, labels in COMPONENT_DOMAINS.items()
            if any(label in upper for label in labels)}


def _powertrain_for_model(model: str) -> str:
    upper = model.upper()
    if upper.startswith(("I5", "I7")) or " BEV" in upper:
        return "BEV"
    if "HYBRID" in upper or "PHEV" in upper:
        return "PHEV"
    if re.fullmatch(r"(?:530|540|740|760)I", upper):
        return "ICE"
    return "*"


def nhtsa_records(config: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Fetch exact NHTSA model names and retain aggregate metadata, excluding VIN/text."""
    if config.get("schema_version") != "1":
        raise ValueError("unsupported public dataset config")
    records: list[dict[str, Any]] = []
    coverage: dict[str, Any] = {"model_years": {}, "source": NHTSA_ROOT}
    snapshot_day = datetime.now(timezone.utc).date().isoformat()
    snapshot_at = snapshot_day + "T00:00:00Z"
    prefixes = config["nhtsa"]["model_prefixes"]
    for year in config["nhtsa"]["model_years"]:
        discovered_by_type: dict[str, set[str]] = {}
        for issue_type in ("c", "r"):
            url = _nhtsa_url("products/vehicle/models", modelYear=year, make="BMW", issueType=issue_type)
            data, _ = _get_json(url)
            discovered_by_type[issue_type] = {
                str(row.get("model", "")).strip().upper() for row in data["results"]
            }
        discovered = discovered_by_type["c"] | discovered_by_type["r"]
        selected = {
            code: sorted(model for model in discovered
                         if model and any(model.startswith(prefix) for prefix in code_prefixes))
            for code, code_prefixes in prefixes.items()
        }
        coverage["model_years"][str(year)] = selected
        for model_code, models in selected.items():
            for model in models:
                complaint_url = _nhtsa_url("complaints/complaintsByVehicle", make="BMW", model=model, modelYear=year)
                recall_url = _nhtsa_url("recalls/recallsByVehicle", make="BMW", model=model, modelYear=year)
                complaints, complaint_hash, complaint_status = _exact_model_query(
                    complaint_url, listed=model in discovered_by_type["c"]
                )
                recalls, recall_hash, recall_status = _exact_model_query(
                    recall_url, listed=model in discovered_by_type["r"]
                )
                complaint_rows = {str(row.get("odiNumber")): row for row in complaints["results"]
                                  if row.get("odiNumber") is not None}
                recall_rows = {str(row.get("NHTSACampaignNumber")): row for row in recalls["results"]
                               if row.get("NHTSACampaignNumber")}
                by_domain: dict[str, dict[str, set[str]]] = {
                    domain: {"complaints": set(), "recalls": set()}
                    for domain in COMPONENT_DOMAINS
                }
                for odi, row in complaint_rows.items():
                    for domain in _domains_for_components(str(row.get("components", ""))):
                        by_domain[domain]["complaints"].add(odi)
                for campaign, row in recall_rows.items():
                    for domain in _domains_for_components(str(row.get("Component", ""))):
                        by_domain[domain]["recalls"].add(campaign)
                digest = _sha(((complaint_hash or "not_listed") + (recall_hash or "not_listed")).encode())[:16]
                logical_key = f"nhtsa:{model_code}:{year}:{model}"
                records.append({
                    "record_id": f"{logical_key}:{snapshot_day}:{digest}",
                    "logical_key": logical_key,
                    "snapshot_at": snapshot_at,
                    "kind": "nhtsa_model_year_summary",
                    "source_url": complaint_url,
                    "related_source_url": recall_url,
                    "source_sha256": {"complaints_response": complaint_hash, "recalls_response": recall_hash},
                    "market": "US", "models": [model_code], "domains": ["*"],
                    "powertrains": [_powertrain_for_model(model)],
                    "limitations": (
                        "NHTSA complaints are unverified reports, with no vehicle population denominator. "
                        "Component tags are broad and do not prove the cause or a feature match. "
                        "Recall counts are distinct campaigns, not affected-vehicle counts."
                    ),
                    "payload": {
                        "model_year": year, "nhtsa_model": model,
                        "complaint_endpoint_status": complaint_status,
                        "recall_endpoint_status": recall_status,
                        "complaints_api_count": complaints.get("count"),
                        "unique_complaint_ids": len(complaint_rows),
                        "recalls_api_count": recalls.get("Count", recalls.get("count")),
                        "unique_campaign_ids": len(recall_rows),
                        "by_domain": {domain: {
                            "complaint_ids": sorted(values["complaints"]),
                            "campaign_ids": sorted(values["recalls"]),
                        } for domain, values in by_domain.items()},
                    },
                })
    return records, coverage


class _CountTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.in_table = False
        self.section = ""
        self.in_cell = False
        self.cell_parts: list[str] = []
        self.cells: list[str] = []
        self.rows: list[tuple[str, list[str]]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "table" and dict(attrs).get("id") == "count_table":
            self.in_table = True
        elif self.in_table and tag in ("tbody", "tfoot"):
            self.section = tag
        elif self.in_table and tag == "tr":
            self.cells = []
        elif self.in_table and tag == "td":
            self.in_cell, self.cell_parts = True, []
        elif self.in_cell and tag == "br":
            self.cell_parts.append(" ")

    def handle_data(self, data: str) -> None:
        if self.in_cell:
            self.cell_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "td" and self.in_cell:
            self.cells.append(" ".join("".join(self.cell_parts).split()))
            self.in_cell = False
        elif tag == "tr" and self.in_table and self.section and self.cells:
            self.rows.append((self.section, self.cells))
        elif tag in ("tbody", "tfoot"):
            self.section = ""
        elif tag == "table" and self.in_table:
            self.in_table = False


def parse_afdc_counts(html: str) -> tuple[str, list[dict[str, int | str]]]:
    parser = _CountTableParser()
    parser.feed(html)
    date_match = re.search(r"Data last updated:\s*(\d{1,2}/\d{1,2}/\d{4})", html)
    if not date_match:
        raise ValueError("AFDC update date missing")
    as_of = datetime.strptime(date_match.group(1), "%m/%d/%Y").date().isoformat()
    output: list[dict[str, int | str]] = []
    for section, cells in parser.rows:
        if section not in ("tbody", "tfoot") or len(cells) != 10:
            continue
        numbers = [int(value.replace(",", "")) for value in re.findall(r"\d[\d,]*", cells[4])]
        if len(numbers) != 5:
            raise ValueError(f"unexpected AFDC electric count cell for {cells[0]}")
        locations, ports, level_1, level_2, dc_fast = numbers
        classified = level_1 + level_2 + dc_fast
        if classified > ports:
            raise ValueError(f"AFDC charging port components exceed the total for {cells[0]}")
        output.append({"state": cells[0], "locations": locations,
                       "ports": ports, "level_1_ports": level_1,
                       "level_2_ports": level_2, "dc_fast_ports": dc_fast,
                       "unclassified_or_legacy_ports": ports - classified})
    totals = [row for row in output if row["state"] == "Total"]
    if len(totals) != 1 or not 45 <= len(output) <= 60:
        raise ValueError("AFDC state table is incomplete")
    if sum(int(row["ports"]) for row in output if row["state"] != "Total") != totals[0]["ports"]:
        raise ValueError("AFDC state counts do not reconcile with the published total")
    return as_of, output


def afdc_records(config: dict[str, Any], *, snapshot_root: Path) -> list[dict[str, Any]]:
    url = config["afdc"]["url"]
    if url != "https://afdc.energy.gov/stations/states?count=public":
        raise ValueError("AFDC import must use public available-station counts")
    raw = _get(url)
    if len(raw) > 10_000_000:
        raise ValueError("AFDC response exceeds the 10 MB import limit")
    html = raw.decode("utf-8")
    as_of, rows = parse_afdc_counts(html)
    source_hash = _sha(raw)
    snapshot_root.mkdir(parents=True, exist_ok=True)
    snapshot_path = snapshot_root / f"afdc-public-states-{as_of}-{source_hash[:12]}.html"
    if not snapshot_path.exists():
        snapshot_path.write_bytes(raw)
    return [{
        "record_id": f"afdc:{row['state']}:{as_of}:{source_hash[:16]}",
        "logical_key": f"afdc:{row['state']}",
        "snapshot_at": as_of + "T00:00:00Z",
        "kind": "afdc_public_charging_ports_by_state",
        "source_url": url,
        "source_sha256": source_hash,
        "market": "US", "state": row["state"], "models": ["*"],
        "domains": ["charging_and_range"], "powertrains": ["BEV", "PHEV"],
        "limitations": (
            "Counts are public available locations and ports, not charger reliability, route spacing, "
            "home charging, charging power above 80% state of charge, or BMW-compatible access. "
            "The feedback corpus has no state-level scope."
        ),
        "payload": {**row, "data_last_updated": as_of},
    } for row in rows]


def curated_records(document: dict[str, Any]) -> list[dict[str, Any]]:
    if document.get("schema_version") != "1" or not isinstance(document.get("items"), list):
        raise ValueError("unsupported curated public evidence document")
    output = []
    for item in document["items"]:
        for field in ("id", "kind", "source_url", "source_date", "market", "models",
                      "domains", "fact", "consideration", "limitation"):
            if not item.get(field):
                raise ValueError(f"curated item missing {field}")
        output.append({
            "record_id": f"curated:{item['id']}", "logical_key": f"curated:{item['id']}",
            "snapshot_at": item["source_date"] + "T00:00:00Z",
            "kind": item["kind"], "source_url": item["source_url"],
            "market": item["market"], "models": item["models"],
            "domains": item["domains"],
            "limitations": item["limitation"],
            "payload": {"fact": item["fact"], "consideration": item["consideration"],
                        "source_date": item["source_date"],
                        "verification": "curated_public_page_no_local_snapshot"},
        })
    return output
