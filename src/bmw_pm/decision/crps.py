"""Canonical Customer Requirement Priority Score (CRPS) and Decision Confidence.

This is the authoritative implementation. The TypeScript preview in
``web/lib/domain/crps.ts`` is a port kept honest by shared fixtures
(``tests/fixtures/crps_parity.json``) and a parity test.

Why this module exists alongside :mod:`bmw_pm.decision.scoring`
---------------------------------------------------------------
``scoring.py`` implements the four-criterion exploratory policy against
``PolicyVersion`` and stays untouched - its tests and audit behaviour are
relied on elsewhere. This module implements the seven-factor CRPS framework
specified for this exercise. Both deliberately share the same interval
discipline, and this module reuses :class:`CriterionInput` and
:class:`DimensionInterval` rather than inventing parallel models.

Three properties are load-bearing:

**Unknowns keep their weight.** A factor with no basis contributes the interval
``[0, 4]``, so the result is a CRPS *interval*. A midpoint is never substituted
for a missing factor, because renormalising an unknown away silently inflates
confidence in the factors that remain.

**Priority and confidence are separate.** CRPS says how much something matters;
Decision Confidence says how sure the evidence makes us. Collapsing them hides
exactly the case a reviewer needs to see - high priority on thin evidence.

**Duplicates are never independent confirmation.** Confirmation counts use
``independence_group``, and rows carrying ``duplicate_of`` are excluded, so ten
rows scraped from one page count once.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Literal

from ..contracts import CriterionInput, DimensionInterval

FACTOR_ORDER: tuple[str, ...] = (
    "customer_impact",
    "evidence_strength",
    "frequency",
    "market_relevance",
    "competitive_gap",
    "future_relevance",
    "strategic_fit",
)

#: Mirrors configs/crps_v1.json. Loaded from disk by :func:`load_policy`; this
#: literal is the fallback so the module is usable without file IO and so a
#: drifted config fails a test rather than silently changing scores.
DEFAULT_WEIGHTS: dict[str, float] = {
    "customer_impact": 0.25,
    "evidence_strength": 0.20,
    "frequency": 0.15,
    "market_relevance": 0.15,
    "competitive_gap": 0.10,
    "future_relevance": 0.10,
    "strategic_fit": 0.05,
}

EVIDENCE_STRENGTH_WEIGHTS: dict[str, float] = {
    "source_quality": 0.30,
    "source_diversity": 0.25,
    "consistency": 0.20,
    "evidence_volume": 0.15,
    "recency": 0.10,
}

DECISION_CONFIDENCE_WEIGHTS: dict[str, float] = {
    "evidence_strength": 0.45,
    "consistency": 0.25,
    "source_diversity": 0.20,
    "recency": 0.10,
}

#: Source-family quality guide, used to map raw ``source_quality`` onto 0-4.
QUALITY_FLOOR = 40.0
QUALITY_CEILING = 95.0

DIVERSITY_SATURATION_GROUPS = 6
VOLUME_SATURATION_GROUPS = 8

RECENCY_BANDS_DAYS: tuple[tuple[int, float], ...] = (
    (365, 4.0),
    (730, 3.0),
    (1095, 2.0),
    (1825, 1.0),
)

PRIORITY_BANDS: tuple[tuple[str, str, float], ...] = (
    ("P1", "Critical", 80.0),
    ("P2", "High", 65.0),
    ("P3", "Medium", 50.0),
    ("P4", "Low", 0.0),
)

#: Market applicability for the Germany 2030 scenario.
PRIMARY_MARKET = "DE"
EU_MARKETS = frozenset({"EU", "AT", "CH", "FR", "IT", "ES", "NL", "BE", "PL", "SE", "DK"})
COMPARABLE_MARKETS = frozenset({"US", "UK", "GB", "CA", "GLOBAL", "WORLD", "CN", "JP"})

#: Topics/subtopics that carry genuine forward-looking signal.
FUTURE_SUBTOPICS = frozenset({
    "infrastructure_growth", "customer_expectation", "adoption_trend",
    "charging_network_growth", "future_customer_expectation", "ev_adoption",
    "charging_behavior",
})

COMPETITOR_BRANDS = frozenset({"audi", "mercedes", "mercedes-benz", "porsche", "tesla",
                               "volkswagen", "vw", "hyundai", "kia", "polestar", "nio"})


def load_policy(path: str | Path | None = None) -> dict[str, Any]:
    """Load ``configs/crps_v1.json``, falling back to the module literals."""
    if path is None:
        path = Path(__file__).resolve().parents[3] / "configs" / "crps_v1.json"
    path = Path(path)
    if not path.is_file():
        return {
            "policy_id": "crps_v1",
            "revision": 1,
            "approved": False,
            "weights": dict(DEFAULT_WEIGHTS),
        }
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["weights"] = {
        name: float(spec["weight"]) for name, spec in payload["factors"].items()
    }
    return payload


# --------------------------------------------------------------------------- #
# Evidence strength
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class EvidenceStrength:
    """Deterministic 0-4 evidence strength with every component exposed."""

    value: float
    components: dict[str, float]
    independent_groups: int
    source_families: int
    supporting_groups: int
    contradicting_groups: int
    duplicate_rows_excluded: int
    rows_considered: int
    newest_evidence_date: str | None
    basis: str

    def as_criterion(self) -> CriterionInput:
        """Express as a :class:`CriterionInput` for interval propagation."""
        return CriterionInput(value=round(self.value, 4), basis=self.basis)


def _independent_rows(rows: Iterable[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    """Drop rows marked as duplicates; they are not independent confirmation."""
    return [row for row in rows if not row.get("duplicate_of")]


def _group_of(row: Mapping[str, Any]) -> str:
    """Independence group, falling back to the source URL then the row id."""
    return str(
        row.get("independence_group")
        or row.get("source_url")
        or row.get("evidence_id")
        or "unknown"
    )


def _parse_date(value: Any) -> date | None:
    """Parse an ISO date or datetime, tolerating a trailing Z."""
    if not value:
        return None
    text = str(value).strip().replace("Z", "+00:00")
    for parser in (datetime.fromisoformat,):
        try:
            parsed = parser(text)
            return parsed.date() if isinstance(parsed, datetime) else parsed
        except ValueError:
            pass
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _saturating(count: int, saturation: int) -> float:
    """Map a count onto 0-4, reaching 4 at *saturation* and never exceeding it."""
    if count <= 0:
        return 0.0
    return round(min(1.0, count / saturation) * 4, 4)


def compute_evidence_strength(
    supporting: Sequence[Mapping[str, Any]],
    contradicting: Sequence[Mapping[str, Any]] = (),
    *,
    today: date | None = None,
) -> EvidenceStrength:
    """Evidence strength on 0-4 from supporting and contradicting evidence rows.

    Contradiction lowers **consistency only**. It must not lower customer
    impact: that a claim is disputed does not make the underlying customer
    problem matter less.
    """
    today = today or datetime.now(timezone.utc).date()
    all_rows = list(supporting) + list(contradicting)
    duplicates = sum(1 for row in all_rows if row.get("duplicate_of"))

    independent_support = _independent_rows(supporting)
    independent_contra = _independent_rows(contradicting)
    support_groups = {_group_of(row) for row in independent_support}
    contra_groups = {_group_of(row) for row in independent_contra}
    families = {str(row.get("source_family") or "unknown") for row in independent_support}

    if not independent_support:
        return EvidenceStrength(
            value=0.0,
            components={name: 0.0 for name in EVIDENCE_STRENGTH_WEIGHTS},
            independent_groups=0, source_families=0, supporting_groups=0,
            contradicting_groups=len(contra_groups),
            duplicate_rows_excluded=duplicates, rows_considered=len(all_rows),
            newest_evidence_date=None,
            basis="No independent supporting evidence after excluding duplicates.",
        )

    # Source quality: mean of the independent supporting rows, mapped onto 0-4.
    qualities = [float(row.get("source_quality") or QUALITY_FLOOR) for row in independent_support]
    mean_quality = sum(qualities) / len(qualities)
    span = QUALITY_CEILING - QUALITY_FLOOR
    quality_component = round(
        max(0.0, min(1.0, (mean_quality - QUALITY_FLOOR) / span)) * 4, 4
    )

    # Diversity rewards distinct independent groups and distinct families.
    group_part = _saturating(len(support_groups), DIVERSITY_SATURATION_GROUPS)
    family_part = _saturating(len(families), 4)
    diversity_component = round((group_part + family_part) / 2, 4)

    # Consistency: share of independent groups that agree.
    total_groups = len(support_groups) + len(contra_groups)
    consistency_component = round((len(support_groups) / total_groups) * 4, 4) if total_groups else 0.0

    # Volume saturates on groups, never on raw rows.
    volume_component = _saturating(len(support_groups), VOLUME_SATURATION_GROUPS)

    # Recency from the newest independent supporting row.
    dates = [
        parsed for parsed in (
            _parse_date(row.get("published_at")) or _parse_date(row.get("retrieved_at"))
            for row in independent_support
        ) if parsed is not None
    ]
    newest = max(dates) if dates else None
    recency_component = 0.0
    if newest is not None:
        age_days = (today - newest).days
        for limit, score in RECENCY_BANDS_DAYS:
            if age_days <= limit:
                recency_component = score
                break

    components = {
        "source_quality": quality_component,
        "source_diversity": diversity_component,
        "consistency": consistency_component,
        "evidence_volume": volume_component,
        "recency": recency_component,
    }
    value = round(
        sum(components[name] * weight for name, weight in EVIDENCE_STRENGTH_WEIGHTS.items()), 4
    )
    basis = (
        f"{len(support_groups)} independent supporting source group(s) across "
        f"{len(families)} source family/families, mean source quality "
        f"{mean_quality:.0f}; {len(contra_groups)} contradicting group(s); "
        f"{duplicates} duplicate row(s) excluded from confirmation."
    )
    return EvidenceStrength(
        value=value, components=components,
        independent_groups=len(support_groups), source_families=len(families),
        supporting_groups=len(support_groups), contradicting_groups=len(contra_groups),
        duplicate_rows_excluded=duplicates, rows_considered=len(all_rows),
        newest_evidence_date=newest.isoformat() if newest else None, basis=basis,
    )


# --------------------------------------------------------------------------- #
# Individual factors
# --------------------------------------------------------------------------- #


def compute_market_relevance(
    rows: Sequence[Mapping[str, Any]], *, primary_market: str = PRIMARY_MARKET
) -> CriterionInput:
    """Market applicability on 0-4 from the markets the evidence actually covers.

    US evidence is never treated as German evidence. The score reflects the
    strongest applicability present, and the basis names what was found.
    """
    independent = _independent_rows(rows)
    if not independent:
        return CriterionInput(
            missing_reason="No independent evidence from which to judge market applicability."
        )
    markets = {str(row.get("market") or "unknown").strip().upper() for row in independent}
    direct = primary_market.upper() in markets
    eu = bool(markets & EU_MARKETS)
    comparable = bool(markets & COMPARABLE_MARKETS)
    known = {m for m in markets if m not in ("", "UNKNOWN")}

    if direct:
        value, label = 4.0, f"direct {primary_market} evidence present"
    elif eu:
        value, label = 3.0, "EU evidence likely applicable to the primary market"
    elif comparable:
        value, label = 2.0, "comparable-market evidence only, not direct for the primary market"
    elif known:
        value, label = 1.0, "weak indirect applicability"
    else:
        return CriterionInput(
            lower_value=0.0, upper_value=2.0,
            basis=f"Evidence carries no usable market field ({sorted(markets)}); "
                  "applicability bounded rather than assumed.",
        )
    return CriterionInput(
        value=value,
        basis=f"{label}; markets observed: {sorted(known) or sorted(markets)}.",
    )


def compute_frequency(
    *,
    unique_affected_records: int | None = None,
    unique_eligible_records: int | None = None,
    saturation_share: float = 0.25,
) -> CriterionInput:
    """Frequency on 0-4, or unknown when no legitimate denominator exists.

    Public web evidence cannot establish population prevalence: the number of
    pages mentioning something says nothing about how many customers experience
    it. Without a denominator this returns the full ``[0, 4]`` interval rather
    than a guessed midpoint.
    """
    if not unique_eligible_records or unique_affected_records is None:
        return CriterionInput(
            missing_reason=(
                "No valid denominator of unique eligible records. Public web evidence "
                "cannot establish population prevalence, and page counts are not a proxy."
            )
        )
    if unique_eligible_records <= 0:
        return CriterionInput(missing_reason="Denominator of eligible records is zero.")
    share = unique_affected_records / unique_eligible_records
    value = round(min(1.0, share / saturation_share) * 4, 4)
    return CriterionInput(
        value=value,
        basis=(
            f"{unique_affected_records} unique affected of {unique_eligible_records} "
            f"unique eligible records ({share:.1%}); saturation share {saturation_share:.0%}."
        ),
    )


def compute_competitive_gap(
    bmw_rows: Sequence[Mapping[str, Any]],
    competitor_rows: Sequence[Mapping[str, Any]],
) -> tuple[CriterionInput, dict[str, Any]]:
    """Competitive gap on 0-4 from matched BMW-versus-competitor evidence.

    Scored only on dimensions where both sides have evidence. Unmatched
    dimensions are reported as missing rather than assumed adequate, because
    absence of competitor evidence is not evidence of parity.
    """
    bmw_independent = _independent_rows(bmw_rows)
    competitor_independent = _independent_rows(competitor_rows)
    bmw_dims = {str(row.get("subtopic") or "") for row in bmw_independent} - {""}
    comp_dims = {str(row.get("subtopic") or "") for row in competitor_independent} - {""}
    matched = sorted(bmw_dims & comp_dims)
    brands = sorted({
        str(row.get("brand") or "").strip().lower()
        for row in competitor_independent
    } & COMPETITOR_BRANDS)

    detail: dict[str, Any] = {
        "matched_dimensions": matched,
        "bmw_only_dimensions": sorted(bmw_dims - comp_dims),
        "competitor_only_dimensions": sorted(comp_dims - bmw_dims),
        "competitor_brands": brands,
        "bmw_evidence_ids": [str(r.get("evidence_id")) for r in bmw_independent][:20],
        "competitor_evidence_ids": [str(r.get("evidence_id")) for r in competitor_independent][:20],
        "missing": [],
    }
    if not matched:
        detail["missing"].append("no dimension has evidence on both sides")
        return CriterionInput(
            missing_reason=(
                "No matched BMW-versus-competitor evidence on a shared dimension; "
                "a gap cannot be scored and parity must not be assumed."
            )
        ), detail

    # More matched dimensions with competitor presence implies a better-evidenced
    # gap signal. Bounded because direction needs human reading of the claims.
    coverage = len(matched) / max(len(bmw_dims | comp_dims), 1)
    lower = round(min(4.0, 1.0 + 2.0 * coverage), 4)
    upper = round(min(4.0, lower + 1.5), 4)
    detail["coverage_share"] = round(coverage, 4)
    if len(brands) < 2:
        detail["missing"].append("fewer than two distinct competitor brands matched")
    return CriterionInput(
        lower_value=lower, upper_value=upper,
        basis=(
            f"{len(matched)} matched dimension(s) ({', '.join(matched[:4])}) against "
            f"{len(brands) or 'no identified'} competitor brand(s); direction of the gap "
            "requires human reading, so the factor is bounded rather than exact."
        ),
    ), detail


def compute_future_relevance(rows: Sequence[Mapping[str, Any]]) -> CriterionInput:
    """Forward-looking relevance on 0-4, only from explicit trend evidence."""
    independent = _independent_rows(rows)
    trend = [
        row for row in independent
        if str(row.get("topic")) == "market_trend"
        or str(row.get("subtopic")) in FUTURE_SUBTOPICS
    ]
    if not trend:
        return CriterionInput(
            missing_reason=(
                "No market-trend, future-expectation or infrastructure-trend evidence is "
                "linked. Forward relevance is not inferred by a model."
            )
        )
    groups = {_group_of(row) for row in trend}
    value = _saturating(len(groups), 4)
    return CriterionInput(
        value=value,
        basis=(
            f"{len(trend)} trend/expectation row(s) across {len(groups)} independent "
            "source group(s)."
        ),
    )


def compute_strategic_fit(
    *,
    approved_objectives: Sequence[str] = (),
    pm_value: float | None = None,
    pm_basis: str | None = None,
) -> CriterionInput:
    """Strategic fit on 0-4, or unknown. Never inferred by a model.

    A belief about what the business probably values is not a strategic fact, so
    this returns unknown unless approved objectives or an explicit PM value
    exist.
    """
    if pm_value is not None:
        if not pm_basis:
            raise ValueError("a PM-supplied strategic fit requires an explicit basis")
        return CriterionInput(value=float(pm_value), basis=f"PM input: {pm_basis}")
    if approved_objectives:
        return CriterionInput(
            lower_value=1.0, upper_value=3.0,
            basis=(
                "Linked to approved objective(s): "
                f"{', '.join(list(approved_objectives)[:3])}; magnitude not elicited."
            ),
        )
    return CriterionInput(
        missing_reason=(
            "No approved strategic objectives in config and no PM input. Strategic fit "
            "is not inferred."
        )
    )


# --------------------------------------------------------------------------- #
# CRPS
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class FactorContribution:
    """One factor's bounded contribution to the score."""

    name: str
    weight: float
    lower_value: float
    upper_value: float
    lower_contribution: float
    upper_contribution: float
    known: bool
    basis: str | None
    missing_reason: str | None


@dataclass(frozen=True)
class CrpsResult:
    """A CRPS interval with every input and contribution exposed."""

    policy_id: str
    policy_revision: int
    approved: bool
    lower_0_to_4: float
    upper_0_to_4: float
    crps_100_lower: float
    crps_100_upper: float
    is_point: bool
    band: str
    band_label: str
    band_basis: str
    factors: dict[str, FactorContribution]
    unknown_factors: list[str]
    dimension_intervals: dict[str, DimensionInterval] = field(default_factory=dict)

    @property
    def display(self) -> str:
        """Human-readable score, as a range when unknowns remain."""
        if self.is_point:
            return f"{self.crps_100_lower:.0f}"
        return f"{self.crps_100_lower:.0f}-{self.crps_100_upper:.0f}"


def _bounds(item: CriterionInput) -> tuple[float, float, bool]:
    """Bounds for a criterion input, widening an unknown to the full range."""
    if item.value is not None:
        return item.value, item.value, True
    if item.lower_value is not None and item.upper_value is not None:
        return item.lower_value, item.upper_value, True
    return 0.0, 4.0, False


def band_for(crps_100_lower: float) -> tuple[str, str, str]:
    """Priority band from the LOWER bound, so unknowns cannot promote a score."""
    for band, label, threshold in PRIORITY_BANDS:
        if crps_100_lower >= threshold:
            return band, label, (
                f"lower CRPS bound {crps_100_lower:.0f} >= {threshold:.0f} "
                "(hackathon display policy, unapproved)"
            )
    return "P4", "Low", "below all thresholds"


def compute_crps(
    factors: Mapping[str, CriterionInput],
    *,
    policy: Mapping[str, Any] | None = None,
) -> CrpsResult:
    """Compute the CRPS interval from the seven factors.

    Every factor must be supplied, including the unknown ones: an absent key is
    an error rather than a silent zero, so a caller cannot quietly drop a factor
    and inflate the remaining weights.
    """
    policy = policy or load_policy()
    weights: Mapping[str, float] = policy.get("weights") or DEFAULT_WEIGHTS

    missing_keys = set(FACTOR_ORDER) - set(factors)
    if missing_keys:
        raise ValueError(
            f"CRPS needs all seven factors; missing {sorted(missing_keys)}. "
            "Supply an unknown CriterionInput rather than omitting a factor."
        )
    extra = set(factors) - set(FACTOR_ORDER)
    if extra:
        raise ValueError(f"unknown CRPS factor(s): {sorted(extra)}")

    total = sum(weights[name] for name in FACTOR_ORDER)
    if abs(total - 1.0) > 1e-9:
        raise ValueError(f"CRPS weights must sum to 1, got {total}")

    contributions: dict[str, FactorContribution] = {}
    lower_total = upper_total = 0.0
    unknown: list[str] = []

    for name in FACTOR_ORDER:
        item = factors[name]
        weight = weights[name]
        lower_value, upper_value, known = _bounds(item)
        if not known:
            unknown.append(name)
        lower_contribution = weight * lower_value
        upper_contribution = weight * upper_value
        contributions[name] = FactorContribution(
            name=name, weight=weight,
            lower_value=lower_value, upper_value=upper_value,
            lower_contribution=round(lower_contribution, 6),
            upper_contribution=round(upper_contribution, 6),
            known=known, basis=item.basis, missing_reason=item.missing_reason,
        )
        lower_total += lower_contribution
        upper_total += upper_contribution

    lower_100 = round(lower_total / 4 * 100, 4)
    upper_100 = round(upper_total / 4 * 100, 4)
    band, label, band_basis = band_for(lower_100)

    dimension_intervals: dict[str, DimensionInterval] = {}
    factor_specs = policy.get("factors") or {}
    for dimension in ("customer", "business"):
        names = [
            name for name in FACTOR_ORDER
            if (factor_specs.get(name, {}) or {}).get("dimension") == dimension
        ]
        if not names:
            continue
        dimension_weight = sum(weights[name] for name in names)
        dimension_intervals[dimension] = DimensionInterval(
            lower_bound=round(
                sum(contributions[n].lower_contribution for n in names) / dimension_weight / 4 * 100, 4
            ),
            upper_bound=round(
                sum(contributions[n].upper_contribution for n in names) / dimension_weight / 4 * 100, 4
            ),
            criteria=names,
            missing_criteria=[n for n in names if not contributions[n].known],
            interpretation=(
                "Policy-dependent 0-100 scenario bounds within this dimension; "
                "not a probability or a measured product outcome."
            ),
        )

    return CrpsResult(
        policy_id=str(policy.get("policy_id", "crps_v1")),
        policy_revision=int(policy.get("revision", 1)),
        approved=bool(policy.get("approved", False)),
        lower_0_to_4=round(lower_total, 6),
        upper_0_to_4=round(upper_total, 6),
        crps_100_lower=lower_100, crps_100_upper=upper_100,
        is_point=not unknown and abs(upper_100 - lower_100) < 1e-9,
        band=band, band_label=label, band_basis=band_basis,
        factors=contributions, unknown_factors=unknown,
        dimension_intervals=dimension_intervals,
    )


# --------------------------------------------------------------------------- #
# Decision confidence
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class DecisionConfidence:
    """How much the evidence supports acting, separate from priority."""

    value_0_to_4: float
    value_0_to_100: float
    components: dict[str, float]
    basis: str


def compute_decision_confidence(strength: EvidenceStrength) -> DecisionConfidence:
    """Decision confidence on 0-100 from the evidence-strength components.

    Deliberately not folded into CRPS: a requirement can matter a great deal on
    thin evidence, and a reviewer must see both numbers.
    """
    components = {
        "evidence_strength": strength.value,
        "consistency": strength.components.get("consistency", 0.0),
        "source_diversity": strength.components.get("source_diversity", 0.0),
        "recency": strength.components.get("recency", 0.0),
    }
    value = sum(components[name] * weight for name, weight in DECISION_CONFIDENCE_WEIGHTS.items())
    return DecisionConfidence(
        value_0_to_4=round(value, 4),
        value_0_to_100=round(value / 4 * 100, 2),
        components={k: round(v, 4) for k, v in components.items()},
        basis=(
            f"{strength.supporting_groups} independent supporting group(s), "
            f"{strength.contradicting_groups} contradicting, "
            f"{strength.source_families} source family/families."
        ),
    )


# --------------------------------------------------------------------------- #
# Conservative ranking
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class RankedRequirement:
    requirement_id: str
    result: CrpsResult
    rank: int | None
    unresolved_against: list[str]


def rank_requirements(
    scored: Mapping[str, CrpsResult],
) -> tuple[list[RankedRequirement], dict[str, Any]]:
    """Order requirements only where CRPS intervals do not overlap.

    Overlapping intervals are reported as unresolved rather than given a false
    ordinal position, which is the same conservatism :mod:`scoring` applies.
    """
    items = sorted(scored.items(), key=lambda kv: (-kv[1].crps_100_lower, kv[0]))
    ranked: list[RankedRequirement] = []
    for index, (requirement_id, result) in enumerate(items):
        overlapping = [
            other_id for other_id, other in items
            if other_id != requirement_id
            and result.crps_100_lower <= other.crps_100_upper
            and other.crps_100_lower <= result.crps_100_upper
        ]
        ranked.append(RankedRequirement(
            requirement_id=requirement_id, result=result,
            rank=None if overlapping else index + 1,
            unresolved_against=sorted(overlapping),
        ))
    resolved = sum(1 for item in ranked if item.rank is not None)
    return ranked, {
        "total": len(ranked),
        "resolved_by_non_overlapping_bounds": resolved,
        "unresolved": len(ranked) - resolved,
        "interpretation": (
            "Only non-overlapping CRPS intervals are ordered. Unresolved pairs "
            "share a plausible score range and must not be presented as ranked."
        ),
    }


FactorSource = Literal[
    "pm_judgement_or_evidence", "deterministic_subscore", "denominator_required",
    "deterministic_from_evidence_market", "deterministic_from_matched_competitor_evidence",
    "deterministic_from_trend_evidence", "approved_objectives_or_pm_input",
]
