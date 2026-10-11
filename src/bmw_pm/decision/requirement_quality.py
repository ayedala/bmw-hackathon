"""Deterministic quality validation for a drafted requirement.

Distinct from :func:`bmw_pm.decision.readiness.assess_readiness`, which gates
the *process* before a card becomes a commitment - is the policy approved, has
entailment been reviewed, is feasibility documented, is the score current.

This module asks a different question: is the requirement itself *well formed*.
A requirement can pass every process gate and still be unusable because it
prescribes an implementation, bundles three outcomes, quotes a number no source
supports, or restates a regulation. Both checks are needed and neither replaces
the other.

Every check is deterministic and reports its own basis, so a reviewer can see
why a requirement was flagged rather than being handed a verdict.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any, Literal

Severity = Literal["blocker", "warning", "info"]


@dataclass(frozen=True)
class QualityCheck:
    """One check with its outcome and the reason for it."""

    check_id: str
    title: str
    passed: bool
    severity: Severity
    detail: str

    @property
    def is_blocker(self) -> bool:
        return not self.passed and self.severity == "blocker"

    @property
    def is_warning(self) -> bool:
        return not self.passed and self.severity == "warning"


@dataclass(frozen=True)
class QualityReport:
    """Structured result for the requirement workbench."""

    requirement_id: str
    passed: bool
    checks: list[QualityCheck] = field(default_factory=list)

    @property
    def blockers(self) -> list[QualityCheck]:
        return [check for check in self.checks if check.is_blocker]

    @property
    def warnings(self) -> list[QualityCheck]:
        return [check for check in self.checks if check.is_warning]

    def as_dict(self) -> dict[str, Any]:
        """Serialisable form for the API bridge and the UI."""
        return {
            "requirement_id": self.requirement_id,
            "passed": self.passed,
            "blockers": [
                {"check_id": c.check_id, "title": c.title, "detail": c.detail}
                for c in self.blockers
            ],
            "warnings": [
                {"check_id": c.check_id, "title": c.title, "detail": c.detail}
                for c in self.warnings
            ],
            "checks": [
                {
                    "check_id": c.check_id, "title": c.title, "passed": c.passed,
                    "severity": c.severity, "detail": c.detail,
                }
                for c in self.checks
            ],
        }


# --------------------------------------------------------------------------- #
# Vocabularies
# --------------------------------------------------------------------------- #

#: Implementation prescriptions. A requirement names the customer outcome; how
#: to build it is an engineering decision made later with cost and feasibility.
ENGINEERING_PRESCRIPTION = re.compile(
    r"\b800\s*v\b|\b400\s*v\b|\blidar\b|\bsnapdragon\b|\bqualcomm\b|\bnvidia\b"
    r"|\blfp\b|\bnmc\b|\bsilicon carbide\b|\bsic inverter\b"
    r"|\bshall use (?:a|an|the)\b|\bmust use (?:a|an|the)\b|\bimplement(?:ed)? (?:using|with) (?:a|an|the)\b"
    r"|\bheat pump\b|\b\d+\s*kwh (?:battery|pack)\b",
    re.I,
)

#: Pure pricing or business-case framing with no customer outcome.
BUSINESS_CASE_ONLY = re.compile(
    r"\bresidual value\b|\btotal cost of ownership\b|\btco\b|\bmargin\b|\bprofitabilit"
    r"|\bbusiness case\b|\bleasing rate\b|\bdiscount\b|\blist price shall\b",
    re.I,
)

#: Regulation restated as a requirement. Compliance is necessary but it is not a
#: customer requirement on its own.
REGULATION_ONLY = re.compile(
    r"\bhomologation\b|\btype approval\b|\bunece\b|\bun r\d+\b|\beuro ncap\b"
    r"|\bgdpr\b|\bwltp (?:procedure|cycle) shall\b|\bregulation \(eu\)\b"
    r"|\bshall comply with\b.*\b(?:regulation|directive|standard)\b",
    re.I,
)

#: Customer-facing subjects. One must appear for the requirement to be about
#: the product as the customer meets it.
CUSTOMER_SUBJECT = re.compile(
    r"\bdriver\b|\bcustomer\b|\boccupant\b|\bpassenger\b|\buser\b"
    r"|\bcharg|\brange\b|\bconsumption\b|\bcomfort\b|\bseat|\bnoise\b|\bquiet\b"
    r"|\bsteer|\bbrak|\bride\b|\bhandling\b|\bspace\b|\bload\b|\bboot\b|\bluggage\b"
    r"|\bcontrol|\bdisplay\b|\bscreen\b|\bapp\b|\bnavigation\b|\bsoftware\b|\bupdate\b"
    r"|\bquality\b|\bmaterial\b|\binterior\b|\bdesign\b|\bexperience\b|\boperate\b"
    r"|\bwithout looking\b|\beyes\b|\bshortcut",
    re.I,
)

#: Claims that an engineering target has already been validated.
VALIDATED_TARGET_CLAIM = re.compile(
    r"\bvalidated target\b|\bconfirmed by engineering\b|\bengineering has (?:approved|confirmed)\b"
    r"|\bapproved target\b|\bsigned off\b|\bverified target\b",
    re.I,
)

#: Numbers that describe a measurement window rather than asserting a target, so
#: they do not require their own source: the conventional 10-80 percent
#: state-of-charge charging window, a trivial count, or a planning year. These
#: are reported in the check detail rather than skipped silently, because the
#: allowance is a convention and a reviewer should be able to see it applied.
STRUCTURAL_NUMBER = re.compile(r"^(?:10|80|100|20\d\d)$")

NUMBER_IN_TEXT = re.compile(r"\d+(?:[.,]\d+)?")

FEASIBILITY_INFERENCE = re.compile(
    r"\bfeasible because\b|\bcompetitors (?:already )?(?:do|have|offer)\b.*\bso it is feasible\b"
    r"|\btechnically straightforward\b|\bno engineering risk\b",
    re.I,
)

DUPLICATE_SIMILARITY_THRESHOLD = 0.88


def _text_of(requirement: Mapping[str, Any]) -> str:
    return f"{requirement.get('title', '')} {requirement.get('requirement', '')}".strip()


def _evidence_corpus(evidence: Sequence[Mapping[str, Any]]) -> str:
    parts: list[str] = []
    for row in evidence:
        parts.append(str(row.get("claim", "")))
        parts.append(str(row.get("evidence_text", "")))
        value = row.get("numeric_value")
        if value is not None:
            parts.append(f"{value:g}" if isinstance(value, (int, float)) else str(value))
    return " ".join(parts).lower()


def _decimal_variants(raw: str) -> tuple[str, ...]:
    """Both decimal spellings of a number, point and comma."""
    return (raw, raw.replace(",", "."), raw.replace(".", ","))


def validate_requirement_quality(
    requirement: Mapping[str, Any],
    linked_need: Sequence[Mapping[str, Any]] | Mapping[str, Any] | None = None,
    linked_findings: Sequence[Mapping[str, Any]] = (),
    linked_evidence: Sequence[Mapping[str, Any]] = (),
    *,
    peer_requirements: Sequence[Mapping[str, Any]] = (),
    primary_market: str = "DE",
) -> QualityReport:
    """Validate one requirement's content quality.

    Args:
        requirement: the requirement artifact.
        linked_need: the need(s) it cites. A single mapping is accepted for
            convenience and normalised to a list.
        linked_findings: findings reached through those needs.
        linked_evidence: evidence reached through those findings.
        peer_requirements: the other requirements, for duplicate detection.
        primary_market: the planning market that scope is checked against.

    Returns:
        A :class:`QualityReport`. ``passed`` is true only when no blocker fired;
        warnings do not block but are surfaced.
    """
    if linked_need is None:
        needs: list[Mapping[str, Any]] = []
    elif isinstance(linked_need, Mapping):
        needs = [linked_need]
    else:
        needs = list(linked_need)

    requirement_id = str(requirement.get("requirement_id", "unknown"))
    text = _text_of(requirement)
    body = str(requirement.get("requirement", ""))
    checks: list[QualityCheck] = []

    def add(check_id: str, title: str, passed: bool, severity: Severity, detail: str) -> None:
        checks.append(QualityCheck(check_id, title, passed, severity, detail))

    # -- traceability ------------------------------------------------------ #
    add(
        "need_linked", "Cites a customer need",
        bool(needs), "blocker",
        f"{len(needs)} linked need(s)." if needs
        else "No customer need is linked, so the requirement has no stated customer motivation.",
    )
    add(
        "finding_linked", "Reaches a finding",
        bool(linked_findings), "blocker",
        f"{len(linked_findings)} finding(s) reached through the linked need(s)." if linked_findings
        else "No finding is reachable, so nothing connects this requirement to evidence.",
    )
    add(
        "evidence_linked", "Reaches evidence",
        bool(linked_evidence), "blocker",
        f"{len(linked_evidence)} evidence row(s) reached." if linked_evidence
        else "No evidence is reachable through the chain.",
    )

    # -- customer-facing outcome ------------------------------------------- #
    has_subject = bool(CUSTOMER_SUBJECT.search(text))
    add(
        "customer_facing", "States a customer-facing outcome",
        has_subject, "blocker",
        "Names a customer-facing subject." if has_subject
        else "No customer-facing subject found; the requirement reads as internal or abstract.",
    )

    prescription = ENGINEERING_PRESCRIPTION.search(body)
    add(
        "no_implementation_prescription", "Describes the outcome, not the implementation",
        prescription is None, "warning",
        "No implementation prescription detected." if prescription is None
        else f"Prescribes an implementation ({prescription.group(0)!r}); state the customer "
             "outcome and leave the solution to engineering.",
    )

    # -- one coherent outcome ---------------------------------------------- #
    shall_count = len(re.findall(r"\bshall\b", body, re.I))
    multi = shall_count > 1
    add(
        "single_outcome", "Expresses one coherent outcome",
        not multi, "warning",
        "One outcome stated." if not multi
        else f"Contains {shall_count} 'shall' clauses; split into separate requirements so each "
             "can be accepted or rejected on its own.",
    )

    # -- not merely a regulation or a business case ------------------------ #
    regulation = REGULATION_ONLY.search(text)
    add(
        "not_regulation_only", "Not merely a regulatory restatement",
        regulation is None or has_subject, "warning",
        "Not a bare compliance restatement." if regulation is None or has_subject
        else f"Reads as regulatory compliance only ({regulation.group(0)!r}) with no customer "
             "outcome; compliance is necessary but is not a customer requirement.",
    )
    business = BUSINESS_CASE_ONLY.search(text)
    add(
        "not_business_case_only", "Not pure pricing or business-case language",
        business is None or has_subject, "warning",
        "Not a bare business case." if business is None or has_subject
        else f"Reads as business-case framing only ({business.group(0)!r}).",
    )

    # -- numeric targets must be sourced ----------------------------------- #
    corpus = _evidence_corpus(linked_evidence)
    unsourced: list[str] = []
    structural: list[str] = []
    for raw in NUMBER_IN_TEXT.findall(body):
        # German sources write a decimal comma ("17,5") where the requirement
        # writes a point, so a number must be sought in both spellings or
        # genuinely sourced targets would read as invented.
        if any(variant in corpus for variant in _decimal_variants(raw)):
            continue
        if STRUCTURAL_NUMBER.match(raw):
            structural.append(raw)
            continue
        unsourced.append(raw)
    if unsourced:
        numeric_detail = (
            f"Number(s) {sorted(set(unsourced))} appear in the requirement but in none of the "
            f"{len(linked_evidence)} linked evidence rows, and no PM input declares them. "
            "An invented target cannot be validated."
        )
    elif structural:
        numeric_detail = (
            f"No unsourced numbers. {sorted(set(structural))} treated as measurement-window "
            "convention rather than sourced targets."
        )
    else:
        numeric_detail = "No unsourced numbers."
    add(
        "numeric_targets_sourced", "Numeric targets appear in the linked evidence",
        not unsourced, "blocker", numeric_detail,
    )

    # -- duplicate detection ----------------------------------------------- #
    duplicates: list[str] = []
    own_text = text.lower()
    for peer in peer_requirements:
        peer_id = str(peer.get("requirement_id", ""))
        if not peer_id or peer_id == requirement_id:
            continue
        ratio = SequenceMatcher(None, own_text, _text_of(peer).lower()).ratio()
        if ratio >= DUPLICATE_SIMILARITY_THRESHOLD:
            duplicates.append(f"{peer_id} ({ratio:.0%})")
    add(
        "not_duplicate", "Not an obvious duplicate of another requirement",
        not duplicates, "warning",
        "No near-duplicate found." if not duplicates
        else f"Closely resembles {', '.join(duplicates)}; consider merging.",
    )

    # -- explicit scope ---------------------------------------------------- #
    vehicle_scope = str(requirement.get("vehicle_scope") or requirement.get("vehicle") or "")
    vehicles_from_findings = {
        vehicle
        for finding in linked_findings
        for vehicle in (finding.get("vehicles_covered") or [])
        if str(vehicle).strip() and str(vehicle).lower() != "unknown"
    }
    has_vehicle = bool(vehicle_scope.strip()) or bool(vehicles_from_findings)
    add(
        "vehicle_scope_explicit", "Vehicle scope is explicit",
        has_vehicle, "warning",
        f"Vehicle scope: {vehicle_scope or sorted(vehicles_from_findings)}." if has_vehicle
        else "No vehicle or generation scope is stated, so applicability is ambiguous.",
    )

    markets = {str(need.get("target_market", "")).upper() for need in needs}
    markets |= {
        str(market).upper()
        for finding in linked_findings
        for market in (finding.get("markets_covered") or [])
    }
    markets.discard("")
    markets.discard("UNKNOWN")
    has_market = bool(markets)
    add(
        "market_scope_explicit", "Market scope is explicit",
        has_market, "warning",
        f"Markets: {sorted(markets)}." if has_market
        else "No market scope is stated.",
    )
    primary_present = primary_market.upper() in markets
    add(
        "primary_market_covered", f"Covers the planning market ({primary_market})",
        primary_present, "warning",
        f"{primary_market} evidence is present." if primary_present
        else f"No {primary_market} evidence reaches this requirement; applicability to the "
             "planning market is an assumption rather than a finding.",
    )

    # -- explicit assumptions and gaps ------------------------------------- #
    assumptions = list(requirement.get("assumptions") or [])
    missing_evidence = list(requirement.get("missing_evidence") or [])
    add(
        "assumptions_explicit", "Assumptions are written down",
        bool(assumptions) or bool(missing_evidence), "warning",
        f"{len(assumptions)} assumption(s), {len(missing_evidence)} declared gap(s)."
        if assumptions or missing_evidence
        else "No assumptions or evidence gaps are declared; a requirement with none is unusual "
             "and usually means they are implicit.",
    )

    # -- evidence strength state assigned ---------------------------------- #
    confidence = str(requirement.get("confidence") or "").strip()
    add(
        "confidence_assigned", "Evidence confidence state is assigned",
        bool(confidence), "blocker",
        f"Confidence: {confidence}." if confidence
        else "No confidence state is assigned, so evidence strength is unstated.",
    )

    # -- feasibility not falsely inferred ---------------------------------- #
    inferred = FEASIBILITY_INFERENCE.search(text)
    feasibility = str(requirement.get("feasibility") or "").strip()
    feasibility_ok = inferred is None and feasibility in ("", "unknown", "conditional",
                                                          "feasible_reviewed")
    add(
        "feasibility_not_inferred", "Feasibility is not inferred from customer evidence",
        feasibility_ok, "blocker",
        "Feasibility is left to engineering review." if feasibility_ok
        else (f"Infers feasibility from non-engineering evidence ({inferred.group(0)!r})."
              if inferred else
              f"Feasibility value {feasibility!r} is not a recognised contract state."),
    )

    # -- acceptance proposal honesty --------------------------------------- #
    validation_method = str(requirement.get("validation_method") or "")
    overclaim = VALIDATED_TARGET_CLAIM.search(f"{text} {validation_method}")
    add(
        "acceptance_not_overclaimed", "Acceptance proposal does not claim validation happened",
        overclaim is None, "blocker",
        "Acceptance is proposed, not asserted as validated." if overclaim is None
        else f"Claims a target is already validated ({overclaim.group(0)!r}); acceptance is a "
             "proposal until engineering review records otherwise.",
    )
    add(
        "validation_method_present", "States how it would be validated",
        bool(validation_method.strip()), "warning",
        "Validation method stated." if validation_method.strip()
        else "No validation method, so the requirement cannot be tested.",
    )

    report = QualityReport(
        requirement_id=requirement_id,
        passed=not any(check.is_blocker for check in checks),
        checks=checks,
    )
    return report


def validate_all(
    requirements: Sequence[Mapping[str, Any]],
    needs_by_id: Mapping[str, Mapping[str, Any]],
    findings_by_id: Mapping[str, Mapping[str, Any]],
    evidence_by_id: Mapping[str, Mapping[str, Any]],
    *,
    primary_market: str = "DE",
) -> list[QualityReport]:
    """Validate every requirement, resolving its chain from the id maps."""
    reports: list[QualityReport] = []
    for requirement in requirements:
        needs = [
            needs_by_id[need_id]
            for need_id in requirement.get("need_ids", [])
            if need_id in needs_by_id
        ]
        findings = [
            findings_by_id[finding_id]
            for finding_id in requirement.get("finding_ids", [])
            if finding_id in findings_by_id
        ]
        evidence = [
            evidence_by_id[evidence_id]
            for evidence_id in requirement.get("evidence_ids", [])
            if evidence_id in evidence_by_id
        ]
        reports.append(
            validate_requirement_quality(
                requirement, needs, findings, evidence,
                peer_requirements=requirements, primary_market=primary_market,
            )
        )
    return reports
