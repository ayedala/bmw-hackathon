"""Independence grouping and claim deduplication.

Two distinct ideas that are easy to conflate:

**Independence group** - which origin document a claim came from. Ten claims
pulled out of one Motor-Talk thread are ten signals but one independent source,
so downstream aggregation can count sources instead of rows.

**Duplicate** - the same claim recorded twice. Only ever decided *within* one
independence group. Two independent publishers reaching the same conclusion are
corroboration, not duplication, and are never collapsed here.

Duplicates are marked via ``duplicate_of``, never deleted.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from models import ProcessedEvidence
from utils import (
    canonicalize_url,
    claim_similarity,
    domain_of,
    get_logger,
    independence_group_id,
    normalize_claim,
)

#: Pagination parameters dropped when deriving an origin document. Page 3 of a
#: forum thread is the same thread, hence the same independent source.
PAGINATION_PARAMS: frozenset[str] = frozenset(
    {"page", "seite", "start", "offset", "pagenumber", "pagenum", "pg", "s"}
)

#: Hosts whose query string identifies the thread, and the key that does it.
_THREAD_KEY_HOSTS: dict[str, tuple[str, ...]] = {
    "goingelectric.de": ("t", "f"),
    "bimmerpost.com": ("t",),
    "bimmerfest.com": ("t",),
    "bimmerforums.com": ("t",),
    "motor-talk.de": ("t",),
    "youtube.com": ("v",),
}


def origin_key(url: str) -> str:
    """Return the canonical identity of the *origin document* behind *url*.

    Collapses pagination and per-view parameters so that every page of one
    forum thread, and every comment permalink under one Reddit post, map to a
    single key. Falls back to the plain canonical URL for ordinary articles.
    """
    canonical = canonicalize_url(url)
    if not canonical:
        return ""
    parts = urlsplit(canonical)
    host = domain_of(canonical)
    path = parts.path or "/"
    pairs = [(key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True)]

    # Reddit: /r/<sub>/comments/<post_id>/<slug> -> the post, ignoring the slug
    # and any single-comment permalink below it.
    if host.endswith("reddit.com") and "/comments/" in path:
        segments = [segment for segment in path.split("/") if segment]
        index = segments.index("comments")
        if len(segments) > index + 1:
            path = "/" + "/".join(segments[: index + 2])
            pairs = []

    # Forum and video hosts where the thread or video id lives in the query.
    thread_keys = _THREAD_KEY_HOSTS.get(host)
    if thread_keys:
        kept = [(key, value) for key, value in pairs if key.lower() in thread_keys]
        if kept:
            pairs = kept

    pairs = [(key, value) for key, value in pairs if key.lower() not in PAGINATION_PARAMS]
    return urlunsplit((parts.scheme, parts.netloc, path, urlencode(sorted(pairs), doseq=True), ""))


def independence_group_for(url: str) -> str:
    """Return the ``SRC-`` identifier for the origin document behind *url*."""
    return independence_group_id(origin_key(url))


# --------------------------------------------------------------------------- #
# Duplicate marking
# --------------------------------------------------------------------------- #


@dataclass(slots=True)
class DuplicateReport:
    """Outcome of a duplicate-marking pass."""

    marked: int = 0
    groups_examined: int = 0
    cross_source_matches: list[tuple[str, str, float]] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.cross_source_matches is None:
            self.cross_source_matches = []


def mark_duplicates(
    records: Sequence[ProcessedEvidence], *, threshold: float
) -> DuplicateReport:
    """Set ``duplicate_of`` on same-origin records whose claims repeat.

    Comparison is confined to one independence group. The first record in a
    group is the keeper; any later record scoring at or above *threshold*
    against an already-kept claim points at it. Records are mutated in place and
    none are removed.

    Returns:
        A :class:`DuplicateReport` with the count marked and any cross-source
        near-identical pairs worth a human look.
    """
    log = get_logger()
    grouped: dict[str, list[ProcessedEvidence]] = {}
    for record in records:
        grouped.setdefault(record.independence_group, []).append(record)

    report = DuplicateReport(groups_examined=len(grouped))
    for group, members in grouped.items():
        keepers: list[ProcessedEvidence] = []
        for record in members:
            if record.duplicate_of:
                continue
            match = _best_match(record, keepers, threshold)
            if match is None:
                keepers.append(record)
                continue
            record.duplicate_of = match.evidence_id
            report.marked += 1
            log.debug(
                "duplicate in %s: %s -> %s (%.0f%% similar)",
                group,
                record.evidence_id,
                match.evidence_id,
                claim_similarity(record.claim, match.claim),
            )

    report.cross_source_matches = find_cross_source_matches(records, threshold=threshold)
    if report.cross_source_matches:
        log.info(
            "%d near-identical claim pair(s) across different sources - kept as "
            "independent corroboration, review if you suspect syndication",
            len(report.cross_source_matches),
        )
    return report


def _best_match(
    candidate: ProcessedEvidence, keepers: Iterable[ProcessedEvidence], threshold: float
) -> ProcessedEvidence | None:
    """Return the kept record *candidate* duplicates, if any clears *threshold*."""
    best: ProcessedEvidence | None = None
    best_score = threshold
    for keeper in keepers:
        score = claim_similarity(candidate.claim, keeper.claim)
        if score >= best_score:
            best, best_score = keeper, score
    return best


def find_cross_source_matches(
    records: Sequence[ProcessedEvidence], *, threshold: float
) -> list[tuple[str, str, float]]:
    """Report near-identical claims that sit in *different* independence groups.

    These are deliberately **not** marked as duplicates: independent tests
    reaching the same number is exactly the corroboration this pipeline exists
    to surface. The list is informational - a long one may indicate syndicated
    copies that the URL filter did not catch.
    """
    live = [record for record in records if not record.duplicate_of]
    matches: list[tuple[str, str, float]] = []
    for index, left in enumerate(live):
        for right in live[index + 1 :]:
            if left.independence_group == right.independence_group:
                continue
            score = claim_similarity(left.claim, right.claim)
            if score >= threshold:
                matches.append((left.evidence_id, right.evidence_id, score))
    return matches


def drop_known_ids(
    records: Sequence[ProcessedEvidence], known_ids: set[str]
) -> list[ProcessedEvidence]:
    """Return the records whose ``evidence_id`` is not already stored."""
    return [record for record in records if record.evidence_id not in known_ids]


def count_independent_sources(records: Iterable[ProcessedEvidence]) -> int:
    """Number of distinct independence groups among non-duplicate records."""
    return len({record.independence_group for record in records if not record.duplicate_of})


def claim_key(record: ProcessedEvidence) -> str:
    """Normalized claim text, exposed for callers that need the comparison key."""
    return normalize_claim(record.claim)
