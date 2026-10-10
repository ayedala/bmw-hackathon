from __future__ import annotations

from typing import Any

from .contracts import RequirementRevision


def validate_report_context(document: dict[str, Any]) -> list[dict[str, Any]]:
    if document.get("schema_version") != "1" or document.get("status") != "company_report_context_not_feature_evidence":
        raise ValueError("unsupported report context document")
    if not str(document.get("source_url", "")).startswith("https://www.bmwgroup.com/"):
        raise ValueError("report context requires an official BMW Group source URL")
    if not document.get("report_id") or not document.get("published_on"):
        raise ValueError("report identity and publication date are required")
    items = document.get("items")
    if not isinstance(items, list) or not items:
        raise ValueError("report context needs at least one item")
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict) or not all(item.get(key) for key in (
            "id", "page", "fact", "consideration", "domains", "powertrains", "kind", "limitation"
        )):
            raise ValueError("each report item needs an id, locator, fact, consideration and limitations")
        if item["id"] in seen:
            raise ValueError("duplicate report context id")
        if item["kind"] not in {"portfolio_context", "domain_context"}:
            raise ValueError("unsupported report context kind")
        if not isinstance(item["page"], int) or item["page"] < 1:
            raise ValueError("report page must be a positive integer")
        if not isinstance(item["domains"], list) or not isinstance(item["powertrains"], list):
            raise ValueError("report context scope must use lists")
        seen.add(item["id"])
    return items


def applies_to_requirement(item: dict[str, Any], requirement: RequirementRevision,
                           *, domain: str | None = None) -> bool:
    domain = domain or requirement.title.casefold().replace(" ", "_")
    domains = set(item["domains"])
    powertrains = set(item["powertrains"])
    return ("*" in domains or domain in domains) and (
        "*" in powertrains or bool(powertrains.intersection(requirement.scope.powertrains))
    )
