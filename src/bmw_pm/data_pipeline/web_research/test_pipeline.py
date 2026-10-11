"""Tests for evidence yield per scraped page.

Run from inside this folder::

    python test_pipeline.py          # stdlib unittest, no extra deps
    python -m pytest test_pipeline.py -q

**No test spends a Firecrawl or LLM credit.** The scrape and search providers
are never constructed; extraction goes through a fake provider that returns
canned JSON. Where the real cached pages from a previous run are present under
``data/cache/``, they are used as fixtures - that is the whole point of the
cache, and re-reading it costs nothing.
"""

from __future__ import annotations

import json
import pathlib
import tempfile
import unittest

import config
import normalization
import scraper
import relevance
from extractor import EvidenceExtractor, ExtractionOutcome
from llm_provider import BaseLLMProvider, LLMError, LLMTruncatedError
from models import RawPage, ResearchRun, SearchHit
from scraper import ScrapeCoordinator, ScrapeOutcome
from storage import PageCache, VisitedUrlStore
from utils import HAVE_RAPIDFUZZ, canonicalize_url, chunk_text, trim_markdown

CACHE_DIR = pathlib.Path(__file__).resolve().parent / "data" / "cache"


# --------------------------------------------------------------------------- #
# Fakes
# --------------------------------------------------------------------------- #


class FakeProvider(BaseLLMProvider):
    """Returns queued responses and records every prompt it was given.

    A queued entry is either a JSON string to return or an exception to raise,
    which is how chunk failure and truncation are simulated.
    """

    name = "fake"

    def __init__(self, responses=None):
        super().__init__(model="fake-1", api_key="not-a-real-key")
        self.responses = list(responses or [])
        self.prompts: list[str] = []

    def complete_json(self, *, system, user, schema, schema_name="x", max_output_tokens=0):
        self.call_count += 1
        self.prompts.append(user)
        if not self.responses:
            return json.dumps({"evidence": []})
        nxt = self.responses.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        return nxt


class ExplodingScrapeClient:
    """Fails the test if anything tries to scrape."""

    call_count = 0

    def fetch(self, url):  # pragma: no cover - must never run
        raise AssertionError(f"a test attempted a real Firecrawl scrape of {url}")


#: Sentences that make up the fixture pages. ``evidence_text`` must be an exact
#: span of the captured page - :meth:`EvidenceExtractor._coerce` rejects a quote
#: it cannot locate - so every fixture quote is taken from this table.
SENTENCES = {
    "peak": "Der BMW i5 eDrive40 G60 ladet mit bis zu 205 kW Ladeleistung.",
    "curve": "Die Ladekurve faellt ab 60 Prozent ab, 10-80 Prozent dauert 30 Minuten.",
    "precon": (
        "Die Vorkonditionierung der Batterie funktioniert im Winter gut und das "
        "Schnellladen am HPC-Lader ist zuverlaessig."
    ),
    "route": "Die Ladeplanung im Routenplaner schlaegt passende Ladepunkte vor.",
    "market": "In Deutschland waechst die Zahl der Schnellladepunkte weiter.",
    # Non-charging sentences, so a cross-topic fixture can pair each claim with
    # a quote that actually supports it. The correction rules in
    # normalization.py trust the quote over the model's claim text, so a comfort
    # claim quoting a charging sentence is correctly retopiced to charging.
    "comfort": "Die Sitze sind bequem und der Fahrkomfort ist hervorragend.",
    "noise": "Oberhalb von 130 km/h sind Windgeraeusche deutlich hoerbar.",
    "info": "Die Klimabedienung erfolgt ueber den Touchscreen statt ueber Tasten.",
}

#: Text that clears both gates: plenty of charging vocabulary and the vehicle.
RELEVANT = " ".join(SENTENCES.values()) + " "


def claim(text, *, topic="charging", subtopic="charging_time", value=None, unit=None,
          evidence=SENTENCES["peak"]):
    """One record as the model would return it. *evidence* must be a page span."""
    return {
        "topic": topic, "subtopic": subtopic, "brand": "BMW", "vehicle": "BMW i5",
        "market": "DE", "claim": text, "evidence_text": evidence,
        "numeric_value": value, "numeric_unit": unit, "published_at": None,
        "source_family_hint": "other",
    }


def payload(*claims):
    return json.dumps({"evidence": list(claims)})


def page(markdown, *, url="https://www.adac.de/bmw-i5-ladetest", topic="charging", title="BMW i5 Ladetest"):
    return RawPage(
        url=url, canonical_url=canonicalize_url(url), title=title, source_name="ADAC",
        published_at="2026-03-01", query="BMW i5 Ladegeschwindigkeit Test", topic=topic,
        retrieved_at="2026-10-10T00:00:00Z", markdown=markdown,
    )


def relevant_text(target_chars):
    """Relevant filler text of at least *target_chars* characters."""
    body = RELEVANT
    while len(body) < target_chars:
        body += RELEVANT
    return body[:target_chars]


def settings(**overrides):
    base = dict(
        firecrawl_api_key=None, llm_provider="openai", openai_api_key=None,
        openai_model="gpt-5-mini", anthropic_api_key=None, anthropic_model="claude-opus-5",
        search_limit=5, max_pages_per_run=20, extraction_chunk_chars=7000,
    )
    base.update(overrides)
    return config.Settings(**base)


# --------------------------------------------------------------------------- #
# 1. Chunking
# --------------------------------------------------------------------------- #


class TestChunking(unittest.TestCase):
    def test_long_content_splits_into_several_chunks(self):
        """The 14.8k-char article that previously went through as one chunk."""
        body = relevant_text(14_844)
        chunks = chunk_text(body, 7000, 600)
        self.assertGreater(len(chunks), 1, "14.8k chars must not be a single chunk")
        self.assertTrue(all(len(c) <= 7000 for c in chunks), [len(c) for c in chunks])

    def test_chunk_size_is_configurable(self):
        body = relevant_text(20_000)
        for size in (6000, 7000, 8000):
            chunks = chunk_text(body, size, 600)
            self.assertTrue(all(len(c) <= size for c in chunks))
            self.assertGreater(len(chunks), 1)

    def test_overlap_keeps_a_boundary_sentence_whole(self):
        marker = "DER GRENZSATZ: Die Ladeleistung erreicht 205 kW."
        body = relevant_text(7000) + "\n\n" + marker + "\n\n" + relevant_text(7000)
        chunks = chunk_text(body, 7000, 600)
        self.assertTrue(any(marker in c for c in chunks), "boundary sentence lost")

    def test_overlap_means_total_chars_exceed_the_original(self):
        body = relevant_text(20_000)
        chunks = chunk_text(body, 7000, 600)
        self.assertGreater(sum(len(c) for c in chunks), len(body))

    def test_chunking_is_deterministic(self):
        body = relevant_text(20_000)
        self.assertEqual(chunk_text(body, 7000, 600), chunk_text(body, 7000, 600))

    def test_degenerate_inputs(self):
        self.assertEqual(chunk_text("", 7000, 600), [])
        self.assertEqual(chunk_text("   \n ", 7000, 600), [])
        self.assertEqual(chunk_text("short", 7000, 600), ["short"])

    def test_overlap_larger_than_chunk_does_not_hang(self):
        chunks = chunk_text("x" * 5000, 100, 500)
        self.assertGreater(len(chunks), 1)


# --------------------------------------------------------------------------- #
# 2. Thin content
# --------------------------------------------------------------------------- #


class TestThinContent(unittest.TestCase):
    def test_thin_page_never_reaches_the_model(self):
        provider = FakeProvider([payload(claim("should never be requested"))])
        extractor = EvidenceExtractor(provider, settings(min_content_chars=1000))
        result = extractor.extract_from_page(page("Loading. Sorry to interrupt." * 5))
        self.assertIs(result.outcome, ExtractionOutcome.SKIPPED_THIN)
        self.assertEqual(provider.call_count, 0, "a thin page must cost no LLM call")
        self.assertEqual(result.records, [])
        self.assertFalse(result.reached_model)

    def test_threshold_is_configurable(self):
        body = relevant_text(600)
        strict = EvidenceExtractor(FakeProvider([payload(claim("unused"))]), settings(min_content_chars=1000))
        self.assertIs(strict.extract_from_page(page(body)).outcome, ExtractionOutcome.SKIPPED_THIN)
        lenient_provider = FakeProvider([payload(claim("The i5 charges at 205 kW."))])
        lenient = EvidenceExtractor(lenient_provider, settings(min_content_chars=400))
        self.assertIs(lenient.extract_from_page(page(body)).outcome, ExtractionOutcome.EXTRACTED)
        self.assertEqual(lenient_provider.call_count, 1)

    def test_the_real_bmw_faq_page_is_skipped_as_thin(self):
        """The 428-char JS shell that wasted an LLM call in the real run."""
        fixture = self._find_cached("faq.bmwusa.com")
        if fixture is None:
            self.skipTest("BMW FAQ page not in data/cache/")
        provider = FakeProvider()
        extractor = EvidenceExtractor(provider, settings(min_content_chars=1000))
        result = extractor.extract_from_page(page(fixture["markdown"], url=fixture["canonical_url"]))
        self.assertIs(result.outcome, ExtractionOutcome.SKIPPED_THIN)
        self.assertEqual(provider.call_count, 0)
        self.assertIn("428", result.reason)

    @staticmethod
    def _find_cached(host_fragment):
        for path in CACHE_DIR.glob("*.json"):
            data = json.loads(path.read_text())
            if host_fragment in data.get("canonical_url", ""):
                return data
        return None


# --------------------------------------------------------------------------- #
# 3. Relevance gate
# --------------------------------------------------------------------------- #


class TestRelevanceGate(unittest.TestCase):
    def test_irrelevant_page_never_reaches_the_model(self):
        off_topic = (
            "Mix the flour, sugar and eggs in a large bowl. Bake for forty "
            "minutes until the sponge is golden brown and springs back. "
        ) * 12
        provider = FakeProvider([payload(claim("should never be requested"))])
        extractor = EvidenceExtractor(provider, settings())
        result = extractor.extract_from_page(page(off_topic))
        self.assertIs(result.outcome, ExtractionOutcome.SKIPPED_IRRELEVANT)
        self.assertEqual(provider.call_count, 0, "an off-topic page must cost no LLM call")

    def test_conservative_a_page_using_only_synonyms_is_kept(self):
        """Comfort wording with no charging term and no model name still passes."""
        text = (
            "Der Fahrkomfort ist hervorragend, die Sitze sind bequem und die "
            "Federung schluckt Unebenheiten. Kaum Windgeraeusche im Innenraum. "
        ) * 10
        verdict = relevance.assess(text, topic="charging")
        self.assertTrue(verdict.relevant, verdict.reason)

    def test_market_page_without_any_vehicle_term_is_kept(self):
        text = (
            "Die Bundesnetzagentur meldet 56.572 Schnellladepunkte. Die "
            "Ladeinfrastruktur waechst, Elektroauto Zulassungen steigen. "
        ) * 10
        self.assertTrue(relevance.assess(text, topic="market_trend").relevant)

    def test_vehicle_only_page_is_kept(self):
        text = "Der BMW i5 eDrive40 G60 M60 xDrive40 ist eine Limousine. " * 20
        verdict = relevance.assess(text, topic="charging")
        self.assertTrue(verdict.relevant)
        self.assertGreaterEqual(verdict.vehicle_hits, 2)

    def test_german_compounds_match_without_false_positives(self):
        self.assertGreater(relevance.assess("Ladekurve und Ladeplanung beim Schnellladen.").topic_hits, 0)
        self.assertEqual(relevance.assess("Schokolade, Marmelade und Limonade.").topic_hits, 0)

    def test_both_real_strong_pages_pass_the_gate(self):
        kept = 0
        for path in CACHE_DIR.glob("*.json"):
            data = json.loads(path.read_text())
            body = trim_markdown(data.get("markdown", ""))
            if len(body) < 1000:
                continue
            self.assertTrue(
                relevance.assess(body, topic="charging").relevant,
                f"strong page wrongly rejected: {data.get('canonical_url')}",
            )
            kept += 1
        if kept == 0:
            self.skipTest("no substantial pages in data/cache/")


# --------------------------------------------------------------------------- #
# 4. Cross-topic evidence
# --------------------------------------------------------------------------- #


class TestCrossTopicEvidence(unittest.TestCase):
    def test_non_requested_topics_are_kept(self):
        """A charging run must keep the comfort and infotainment claims too."""
        provider = FakeProvider([payload(
            claim("The i5 charges 10-80 percent in 30 minutes.", value=30.0, unit="min"),
            claim("Ride comfort is excellent.", topic="comfort", subtopic="ride_comfort",
                  evidence=SENTENCES["comfort"]),
            claim("Wind noise rises above 130 km/h.", topic="comfort", subtopic="cabin_noise",
                  evidence=SENTENCES["noise"]),
            claim("Touchscreen climate control is cumbersome.", topic="infotainment",
                  subtopic="climate_control_interaction", evidence=SENTENCES["info"]),
            claim("Germany keeps adding fast chargers.", topic="market_trend",
                  subtopic="charging_network_growth", evidence=SENTENCES["market"]),
        )])
        extractor = EvidenceExtractor(provider, settings())
        result = extractor.extract_from_page(page(relevant_text(2000), topic="charging"))
        self.assertIs(result.outcome, ExtractionOutcome.EXTRACTED)
        self.assertEqual(len(result.records), 5)
        self.assertEqual(
            {"charging", "comfort", "infotainment", "market_trend"},
            {r.topic for r in result.records},
        )


class TestQuoteOutranksClaim(unittest.TestCase):
    """The correction rules read the evidence quote, not the model's claim.

    The quote is verifiable text from the page; the claim is generated prose. So
    when the two disagree about what the record is about, the quote decides.
    """

    def test_a_comfort_claim_quoting_a_charging_figure_is_retopiced(self):
        provider = FakeProvider([payload(
            claim("Ride comfort is excellent.", topic="comfort", subtopic="ride_comfort",
                  evidence=SENTENCES["peak"]),
        )])
        extractor = EvidenceExtractor(provider, settings(extraction_chunk_chars=40_000))
        result = extractor.extract_from_page(page(relevant_text(3000)))
        self.assertEqual(result.records[0].topic, "charging")
        self.assertEqual(extractor.stats.records_reclassified, 1)

    def test_a_matching_claim_and_quote_are_left_alone(self):
        provider = FakeProvider([payload(
            claim("Ride comfort is excellent.", topic="comfort", subtopic="ride_comfort",
                  evidence=SENTENCES["comfort"]),
        )])
        extractor = EvidenceExtractor(provider, settings(extraction_chunk_chars=40_000))
        result = extractor.extract_from_page(page(relevant_text(3000)))
        self.assertEqual(
            (result.records[0].topic, result.records[0].subtopic), ("comfort", "ride_comfort")
        )
        self.assertEqual(extractor.stats.records_reclassified, 0)


# --------------------------------------------------------------------------- #
# 5. Chunk failure isolation and truncation recovery
# --------------------------------------------------------------------------- #


class TestChunkFailureHandling(unittest.TestCase):
    def test_one_failed_chunk_keeps_the_others(self):
        provider = FakeProvider([
            payload(claim("Chunk one: peak charging is 205 kW.", value=205.0, unit="kW")),
            LLMError("502 upstream from the provider"),
            payload(claim("Chunk three: preconditioning works in winter.",
                          subtopic="battery_preconditioning", evidence=SENTENCES["precon"])),
        ])
        extractor = EvidenceExtractor(provider, settings(extraction_chunk_chars=7000))
        result = extractor.extract_from_page(page(relevant_text(18_000)))
        self.assertIs(result.outcome, ExtractionOutcome.EXTRACTED)
        self.assertEqual(len(result.records), 2, "evidence from healthy chunks must survive")
        self.assertEqual(result.chunks_failed, 1)
        self.assertEqual(result.chunks, 3)

    def test_all_chunks_failing_is_reported_as_extraction_failure(self):
        provider = FakeProvider([LLMError("boom"), LLMError("boom"), LLMError("boom")])
        extractor = EvidenceExtractor(provider, settings())
        result = extractor.extract_from_page(page(relevant_text(18_000)))
        self.assertIs(result.outcome, ExtractionOutcome.EXTRACTION_FAILED)
        self.assertEqual(result.records, [])

    def test_truncated_chunk_is_retried_as_halves(self):
        """finish_reason=length must not lose the chunk."""
        provider = FakeProvider([
            LLMTruncatedError("finish_reason=length"),
            payload(claim("First half: 205 kW peak.", value=205.0, unit="kW")),
            payload(claim("Second half: 30 minutes 10-80.", value=30.0, unit="min",
                          evidence=SENTENCES["curve"])),
        ])
        extractor = EvidenceExtractor(provider, settings(extraction_chunk_chars=20_000))
        result = extractor.extract_from_page(page(relevant_text(9_000)))
        self.assertIs(result.outcome, ExtractionOutcome.EXTRACTED)
        self.assertEqual(len(result.records), 2)
        self.assertEqual(extractor.stats.sub_chunk_recoveries, 1)

    def test_truncation_recovery_does_not_retry_forever(self):
        provider = FakeProvider([LLMTruncatedError("length")] * 12)
        extractor = EvidenceExtractor(provider, settings(extraction_chunk_chars=20_000))
        result = extractor.extract_from_page(page(relevant_text(9_000)))
        self.assertIs(result.outcome, ExtractionOutcome.EXTRACTION_FAILED)
        self.assertLessEqual(provider.call_count, 3, "one chunk must cost at most 3 requests")

    def test_zero_evidence_is_distinct_from_failure(self):
        provider = FakeProvider([json.dumps({"evidence": []})])
        extractor = EvidenceExtractor(provider, settings(extraction_chunk_chars=20_000))
        result = extractor.extract_from_page(page(relevant_text(2000)))
        self.assertIs(result.outcome, ExtractionOutcome.NO_EVIDENCE)
        self.assertEqual(result.chunks_failed, 0)


# --------------------------------------------------------------------------- #
# 6. Merge / dedup after chunking
# --------------------------------------------------------------------------- #


class TestChunkMergeDedup(unittest.TestCase):
    def test_identical_claim_from_overlapping_chunks_is_written_once(self):
        same = "The BMW i5 charges from 10 to 80 percent in 30 minutes."
        provider = FakeProvider([
            payload(claim(same, value=30.0, unit="min")),
            payload(claim(same + " ", value=30.0, unit="min")),
            payload(claim("Peak charging power is 205 kW.", value=205.0, unit="kW",
                          evidence=SENTENCES["curve"])),
        ])
        extractor = EvidenceExtractor(provider, settings(extraction_chunk_chars=7000))
        result = extractor.extract_from_page(page(relevant_text(18_000)))
        claims = [r.claim for r in result.records]
        self.assertEqual(len(claims), 2, claims)
        self.assertEqual(extractor.stats.records_merged_away, 1)

    def test_merge_keeps_the_more_complete_version(self):
        """The version carrying the number beats the vaguer one."""
        provider = FakeProvider([
            payload(claim("The i5 charges from 10 to 80 percent in 30 minutes.",
                          evidence=SENTENCES["route"])),
            payload(claim("The i5 charges from 10 to 80 percent in 30 minutes.",
                          value=30.0, unit="min", evidence=SENTENCES["precon"])),
        ])
        extractor = EvidenceExtractor(provider, settings(extraction_chunk_chars=7000))
        result = extractor.extract_from_page(page(relevant_text(12_000)))
        self.assertEqual(len(result.records), 1)
        self.assertEqual(result.records[0].numeric_value, 30.0)
        # "min" is canonicalized to "minutes" by the unit pass.
        self.assertEqual(result.records[0].numeric_unit, "minutes")

    @unittest.skipUnless(HAVE_RAPIDFUZZ, "near-duplicate matching needs rapidfuzz")
    def test_near_identical_claims_are_collapsed(self):
        provider = FakeProvider([
            payload(claim("Wind noise is noticeable above 130 km/h.",
                          topic="comfort", subtopic="cabin_noise", evidence=SENTENCES["curve"])),
            payload(claim("Above about 130 km/h wind noise becomes noticeable.",
                          topic="comfort", subtopic="cabin_noise", evidence=SENTENCES["precon"])),
        ])
        extractor = EvidenceExtractor(provider, settings(extraction_chunk_chars=7000))
        result = extractor.extract_from_page(page(relevant_text(12_000)))
        self.assertEqual(len(result.records), 1, [r.claim for r in result.records])

    def test_genuinely_different_claims_are_both_kept(self):
        provider = FakeProvider([payload(
            claim("Front seats are comfortable.", topic="comfort", subtopic="front_seat_comfort",
                  evidence=SENTENCES["peak"]),
            claim("Rear seat space is tight.", topic="comfort", subtopic="rear_seat_space",
                  evidence=SENTENCES["curve"]),
        )])
        extractor = EvidenceExtractor(provider, settings(extraction_chunk_chars=20_000))
        result = extractor.extract_from_page(page(relevant_text(2000)))
        self.assertEqual(len(result.records), 2)


# --------------------------------------------------------------------------- #
# 6b. Source span locators survive chunking
# --------------------------------------------------------------------------- #


class TestSourceSpans(unittest.TestCase):
    """Chunking must not corrupt source_start_char / source_end_char.

    Offsets are resolved against the whole captured page, not against the chunk
    the quote arrived in, so splitting a page into more chunks cannot move them.
    """

    def test_offsets_point_at_the_exact_quote(self):
        body = relevant_text(2000)
        provider = FakeProvider([payload(claim("Peak power is 205 kW.", value=205.0, unit="kW",
                                               evidence=SENTENCES["peak"]))])
        extractor = EvidenceExtractor(provider, settings(extraction_chunk_chars=20_000))
        record = extractor.extract_from_page(page(body)).records[0]
        self.assertEqual(
            body[record.source_start_char:record.source_end_char], SENTENCES["peak"]
        )
        self.assertEqual(record.source_end_char - record.source_start_char,
                         len(record.evidence_text))

    def test_offsets_stay_exact_when_the_page_is_split_into_many_chunks(self):
        body = relevant_text(18_000)
        provider = FakeProvider([
            payload(claim("Chunk one reports a 205 kW peak.", evidence=SENTENCES["peak"])),
            payload(claim("Chunk two reports the curve tapering.", subtopic="charging_curve",
                          evidence=SENTENCES["curve"])),
            payload(claim("Chunk three reports winter preconditioning.",
                          subtopic="battery_preconditioning", evidence=SENTENCES["precon"])),
        ])
        extractor = EvidenceExtractor(provider, settings(extraction_chunk_chars=7000))
        result = extractor.extract_from_page(page(body))
        self.assertGreater(result.chunks, 1, "fixture should span several chunks")
        self.assertTrue(result.records)
        for record in result.records:
            self.assertEqual(
                body[record.source_start_char:record.source_end_char],
                record.evidence_text,
                "offset must address the exact quote in the captured page",
            )

    def test_quote_the_model_invented_is_rejected(self):
        """A paraphrase is not a locatable span, so the record cannot be stored."""
        provider = FakeProvider([payload(
            claim("invented", evidence="This sentence is nowhere in the page."),
            claim("genuine", evidence=SENTENCES["peak"]),
        )])
        extractor = EvidenceExtractor(provider, settings(extraction_chunk_chars=20_000))
        result = extractor.extract_from_page(page(relevant_text(2000)))
        self.assertEqual(len(result.records), 1)
        self.assertEqual(result.records[0].claim, "genuine")
        self.assertEqual(extractor.stats.records_rejected, 1)


# --------------------------------------------------------------------------- #
# 7. Run statistics
# --------------------------------------------------------------------------- #


class TestRunStatistics(unittest.TestCase):
    def test_outcomes_are_counted_separately(self):
        thin = EvidenceExtractor(FakeProvider(), settings())
        thin.extract_from_page(page("Loading." * 5))
        self.assertEqual(thin.stats.pages_skipped_thin, 1)
        self.assertEqual(thin.stats.pages_skipped_irrelevant, 0)

        off = EvidenceExtractor(FakeProvider(), settings())
        off.extract_from_page(page("Bake the sponge for forty minutes until golden. " * 40))
        self.assertEqual(off.stats.pages_skipped_irrelevant, 1)
        self.assertEqual(off.stats.pages_skipped_thin, 0)

        failed = EvidenceExtractor(FakeProvider([LLMError("x")]), settings(extraction_chunk_chars=20_000))
        failed.extract_from_page(page(relevant_text(2000)))
        self.assertEqual(failed.stats.pages_failed, 1)
        self.assertEqual(failed.stats.pages_zero_evidence, 0)

        empty = EvidenceExtractor(FakeProvider([json.dumps({"evidence": []})]),
                                  settings(extraction_chunk_chars=20_000))
        empty.extract_from_page(page(relevant_text(2000)))
        self.assertEqual(empty.stats.pages_zero_evidence, 1)
        self.assertEqual(empty.stats.pages_failed, 0)

        good = EvidenceExtractor(FakeProvider([payload(claim("The i5 peaks at 205 kW.", value=205.0, unit="kW"))]),
                                 settings(extraction_chunk_chars=20_000))
        good.extract_from_page(page(relevant_text(2000)))
        self.assertEqual(good.stats.pages_with_evidence, 1)

    def test_run_record_exposes_every_new_metric(self):
        from models import ResearchRun
        fields = set(ResearchRun.model_fields)
        for name in (
            "pages_skipped_thin", "pages_skipped_irrelevant", "pages_extraction_failed",
            "pages_zero_evidence", "pages_with_evidence", "chunks_processed",
            "chunks_failed", "evidence_per_extracted_page",
        ):
            self.assertIn(name, fields)

    def test_evidence_schema_is_unchanged(self):
        from models import ProcessedEvidence
        self.assertEqual(
            list(ProcessedEvidence.model_fields),
            ["evidence_id", "source_url", "source_name", "source_title", "source_family",
             "published_at", "retrieved_at", "brand", "vehicle", "market", "topic",
             "subtopic", "claim", "evidence_text", "source_start_char", "source_end_char",
             "numeric_value", "numeric_unit", "source_quality", "independence_group",
             "duplicate_of"],
        )


# --------------------------------------------------------------------------- #
# 8. Cache-only retesting spends nothing
# --------------------------------------------------------------------------- #


class TestNoFirecrawlSpend(unittest.TestCase):
    def test_cached_page_is_served_without_any_scrape_call(self):
        tmp = pathlib.Path(tempfile.mkdtemp())
        cache = PageCache(tmp / "cache")
        url = "https://www.adac.de/bmw-i5-ladetest"
        cache.put(canonicalize_url(url), {"markdown": relevant_text(2000), "title": "ADAC",
                                          "source_name": "ADAC", "published_at": None})
        client = ExplodingScrapeClient()
        coordinator = ScrapeCoordinator(
            client=client, cache=cache, visited=VisitedUrlStore(tmp / "v.json"),
        )
        hit = SearchHit(url=url, canonical_url=canonicalize_url(url), topic="charging", query="q")
        self.assertIs(coordinator.plan(hit), ScrapeOutcome.CACHED)
        result = coordinator.resolve(hit)
        self.assertIs(result.outcome, ScrapeOutcome.CACHED)
        self.assertEqual(client.call_count, 0)
        self.assertEqual(coordinator.scrape_call_count, 0)

    def test_real_cached_pages_replay_through_extraction_for_free(self):
        pages = list(CACHE_DIR.glob("*.json"))
        if not pages:
            self.skipTest("data/cache/ is empty")
        provider = FakeProvider()
        extractor = EvidenceExtractor(provider, settings())
        outcomes = {}
        for path in pages:
            data = json.loads(path.read_text())
            result = extractor.extract_from_page(
                page(data.get("markdown", ""), url=data.get("canonical_url", "https://x.de/a"))
            )
            outcomes[data.get("canonical_url", "?")] = result.outcome
        # No scrape client was ever constructed, so no credit could be spent.
        self.assertTrue(outcomes)
        self.assertIn(ExtractionOutcome.SKIPPED_THIN, outcomes.values(),
                      "the 428-char BMW FAQ page should be skipped as thin")


# --------------------------------------------------------------------------- #
# 9. Cache-only reprocessing
# --------------------------------------------------------------------------- #


class ExplodingFirecrawlClient:
    """Stands in for both Firecrawl adapters and fails if anything builds one."""

    def __init__(self, *args, **kwargs):  # pragma: no cover - must never run
        raise AssertionError("a Firecrawl client was constructed in cache-only mode")


class SpanProvider(BaseLLMProvider):
    """Mock model that quotes real sentences from the chunk it is given."""

    name = "span-fake"

    def __init__(self):
        super().__init__(model="fake-1", api_key="not-a-real-key")

    def complete_json(self, *, system, user, schema, schema_name="x", max_output_tokens=0):
        self.call_count += 1
        chunk = user.split("<<<PAGE_CONTENT_START>>>")[1].split("<<<PAGE_CONTENT_END>>>")[0].strip()
        sentences = [t.strip() for t in chunk.replace("\n", " ").split(". ") if 40 < len(t.strip()) < 280]
        rows = [
            {
                "topic": "charging", "subtopic": "charging_time", "brand": "BMW",
                "vehicle": "BMW i5", "market": "DE",
                "claim": f"Claim {self.call_count}.{i}: {text[:60]}",
                "evidence_text": text, "numeric_value": None, "numeric_unit": None,
                "published_at": None, "source_family_hint": "other",
            }
            for i, text in enumerate(sentences[:3])
        ]
        return json.dumps({"evidence": rows})


class TestCacheOnlyReprocess(unittest.TestCase):
    """``--reprocess-cache`` must replay cached pages for zero Firecrawl credits.

    Every path config points at is redirected into a temp directory, and the
    real cache files are *copied* in, so the project's own data is only ever
    read.
    """

    def setUp(self):
        import main, scraper, search
        self.main, self.search, self.scraper = main, search, scraper
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self._saved = {
            name: getattr(config, name)
            for name in (
                "DATA_DIR", "RAW_DIR", "PROCESSED_DIR", "METADATA_DIR", "CACHE_DIR",
                "RAW_PAGES_PATH", "PROCESSED_EVIDENCE_PATH", "CACHE_REPROCESS_EVIDENCE_PATH",
                "VISITED_URLS_PATH", "RESEARCH_RUNS_PATH", "LOG_PATH", "ENV_PATH",
            )
        }
        config.DATA_DIR = self.tmp / "data"
        config.RAW_DIR = config.DATA_DIR / "raw"
        config.PROCESSED_DIR = config.DATA_DIR / "processed"
        config.METADATA_DIR = config.DATA_DIR / "metadata"
        config.CACHE_DIR = config.DATA_DIR / "cache"
        config.RAW_PAGES_PATH = config.RAW_DIR / "raw_pages.jsonl"
        config.PROCESSED_EVIDENCE_PATH = config.PROCESSED_DIR / "external_evidence.jsonl"
        config.CACHE_REPROCESS_EVIDENCE_PATH = config.PROCESSED_DIR / "cache_reprocess_evidence.jsonl"
        config.VISITED_URLS_PATH = config.METADATA_DIR / "visited_urls.json"
        config.RESEARCH_RUNS_PATH = config.METADATA_DIR / "research_runs.jsonl"
        config.LOG_PATH = self.tmp / "pipeline.log"
        config.ENV_PATH = self.tmp / ".env"
        config.ensure_directories()

        # Copy the real cached pages in, and build a matching ledger.
        ledger = {}
        self.copied = 0
        for path in sorted(CACHE_DIR.glob("*.json")):
            data = json.loads(path.read_text())
            (config.CACHE_DIR / path.name).write_text(json.dumps(data), encoding="utf-8")
            ledger[data.get("canonical_url", "")] = {
                "first_seen_at": "2026-10-10T00:00:00Z", "last_seen_at": "2026-10-10T00:00:00Z",
                "last_scraped_at": "2026-10-10T00:00:00Z", "status": "scraped",
                "attempts": 1, "topic": "charging", "query": "BMW i5 Ladegeschwindigkeit Test",
                "cache_file": path.name,
            }
            self.copied += 1
        config.VISITED_URLS_PATH.write_text(json.dumps(ledger), encoding="utf-8")

        # Neither Firecrawl adapter may be constructed in this mode.
        self._saved_clients = (
            self.main.FirecrawlSearchClient, self.main.FirecrawlScraperClient,
            self.search.FirecrawlSearchClient, self.scraper.FirecrawlScraperClient,
        )
        self.main.FirecrawlSearchClient = ExplodingFirecrawlClient
        self.main.FirecrawlScraperClient = ExplodingFirecrawlClient
        self.search.FirecrawlSearchClient = ExplodingFirecrawlClient
        self.scraper.FirecrawlScraperClient = ExplodingFirecrawlClient

        self.provider = SpanProvider()
        self._saved_get_provider = self.main.get_provider
        self.main.get_provider = lambda settings: self.provider

    def tearDown(self):
        for name, value in self._saved.items():
            setattr(config, name, value)
        (self.main.FirecrawlSearchClient, self.main.FirecrawlScraperClient,
         self.search.FirecrawlSearchClient, self.scraper.FirecrawlScraperClient) = self._saved_clients
        self.main.get_provider = self._saved_get_provider

    # -- helpers ---------------------------------------------------------- #

    def _run(self, *extra):
        return self.main.main(["--topic", "charging", "--reprocess-cache", *extra])

    def _rows(self):
        path = config.CACHE_REPROCESS_EVIDENCE_PATH
        if not path.is_file():
            return []
        return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]

    def _last_run_record(self):
        return [
            json.loads(line)
            for line in config.RESEARCH_RUNS_PATH.read_text().splitlines() if line.strip()
        ][-1]

    def _require_cache(self):
        if self.copied == 0:
            self.skipTest("data/cache/ is empty")

    # -- tests ------------------------------------------------------------ #

    def test_no_firecrawl_client_is_ever_constructed(self):
        self._require_cache()
        self.assertEqual(self._run(), 0, "a Firecrawl client would have raised")

    def test_run_record_reports_zero_firecrawl_calls(self):
        self._require_cache()
        self._run()
        record = self._last_run_record()
        self.assertEqual(record["mode"], "reprocess-cache")
        self.assertEqual(record["firecrawl_search_calls"], 0)
        self.assertEqual(record["firecrawl_scrape_calls"], 0)
        self.assertEqual(record["pages_loaded_from_cache"], self.copied)

    def test_bmw_faq_cached_page_is_skipped_as_thin(self):
        self._require_cache()
        self._run()
        self.assertGreaterEqual(self._last_run_record()["pages_skipped_thin"], 1)
        self.assertNotIn(
            "faq.bmwusa.com",
            " ".join(row["source_url"] for row in self._rows()),
            "the 428-char JS shell must not produce evidence",
        )

    def test_insideevs_page_is_chunked_and_yields_evidence(self):
        self._require_cache()
        self._run()
        record = self._last_run_record()
        self.assertGreater(record["chunks_processed"], record["pages_with_evidence"],
                           "the long article must span more than one chunk")
        self.assertIn("insideevs", " ".join(row["source_url"] for row in self._rows()))

    def test_adac_page_yields_evidence(self):
        self._require_cache()
        self._run()
        self.assertIn("adac.de", " ".join(row["source_url"] for row in self._rows()))

    def test_reruns_do_not_duplicate_output(self):
        self._require_cache()
        counts = []
        for _ in range(3):
            self._run()
            counts.append(len(self._rows()))
        self.assertEqual(len(set(counts)), 1, f"row count drifted across reruns: {counts}")
        self.assertGreater(counts[0], 0)
        ids = [row["evidence_id"] for row in self._rows()]
        self.assertEqual(len(ids), len(set(ids)), "duplicate evidence_id in the output")

    def test_main_evidence_store_is_untouched(self):
        self._require_cache()
        config.PROCESSED_EVIDENCE_PATH.write_text('{"evidence_id": "EXT-preexisting"}\n', encoding="utf-8")
        self._run()
        self.assertEqual(
            config.PROCESSED_EVIDENCE_PATH.read_text(), '{"evidence_id": "EXT-preexisting"}\n'
        )

    def test_visited_ledger_is_not_modified(self):
        self._require_cache()
        before = config.VISITED_URLS_PATH.read_text()
        self._run()
        self.assertEqual(config.VISITED_URLS_PATH.read_text(), before)

    def test_cache_files_are_not_modified(self):
        self._require_cache()
        before = {p.name: p.read_bytes() for p in config.CACHE_DIR.glob("*.json")}
        self._run()
        after = {p.name: p.read_bytes() for p in config.CACHE_DIR.glob("*.json")}
        self.assertEqual(before, after)

    def test_no_firecrawl_key_is_required(self):
        self._require_cache()
        import os
        saved = os.environ.pop("FIRECRAWL_API_KEY", None)
        try:
            self.assertEqual(self._run(), 0)
        finally:
            if saved is not None:
                os.environ["FIRECRAWL_API_KEY"] = saved

    def test_force_and_dry_run_are_rejected(self):
        self.assertEqual(self._run("--force"), 2)
        self.assertEqual(self._run("--dry-run"), 2)

    def test_topic_filter_excludes_pages_recorded_under_another_topic(self):
        self._require_cache()
        self.assertEqual(self.main.main(["--topic", "comfort", "--reprocess-cache"]), 0)
        self.assertEqual(self._last_run_record()["pages_loaded_from_cache"], 0)
        self.assertEqual(self.provider.call_count, 0, "no page matched, so no LLM call")


# --------------------------------------------------------------------------- #
# 10. Deprecated chunk-size variable
# --------------------------------------------------------------------------- #


class TestLegacyChunkSetting(unittest.TestCase):
    """An old MAX_CONTENT_CHARS line must not restore oversized chunking."""

    def setUp(self):
        import os
        self._saved = {k: os.environ.get(k) for k in ("EXTRACTION_CHUNK_CHARS", "MAX_CONTENT_CHARS")}
        self._saved_env_path = config.ENV_PATH
        config.ENV_PATH = pathlib.Path(tempfile.mkdtemp()) / ".env"   # no real .env
        for key in self._saved:
            os.environ.pop(key, None)

    def tearDown(self):
        import os
        config.ENV_PATH = self._saved_env_path
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_oversized_legacy_value_is_clamped_to_the_safe_default(self):
        import os
        os.environ["MAX_CONTENT_CHARS"] = "15000"
        self.assertEqual(
            config.load_settings().extraction_chunk_chars,
            config.DEFAULT_EXTRACTION_CHUNK_CHARS,
        )

    def test_small_legacy_value_is_honoured(self):
        import os
        os.environ["MAX_CONTENT_CHARS"] = "6000"
        self.assertEqual(config.load_settings().extraction_chunk_chars, 6000)

    def test_new_name_wins_outright(self):
        import os
        os.environ["MAX_CONTENT_CHARS"] = "15000"
        os.environ["EXTRACTION_CHUNK_CHARS"] = "20000"
        self.assertEqual(config.load_settings().extraction_chunk_chars, 20000)

    def test_default_when_neither_is_set(self):
        self.assertEqual(config.load_settings().extraction_chunk_chars, 7000)


# --------------------------------------------------------------------------- #
# 11. Semantic normalization, grounded in the real cached pages
# --------------------------------------------------------------------------- #


class RowProvider(BaseLLMProvider):
    """Returns one fixed set of rows, as a model would."""

    name = "row-fake"

    def __init__(self, rows):
        super().__init__(model="fake-1", api_key="not-a-real-key")
        self.rows = rows

    def complete_json(self, *, system, user, schema, schema_name="x", max_output_tokens=0):
        self.call_count += 1
        return json.dumps({"evidence": self.rows})


def row(claim, topic, subtopic, evidence, *, value=None, unit=None):
    """One model row. *evidence* must be a verbatim span of the page."""
    return {
        "topic": topic, "subtopic": subtopic, "brand": "Audi", "vehicle": "A6 e-tron",
        "market": "DE", "claim": claim, "evidence_text": evidence,
        "numeric_value": value, "numeric_unit": unit, "published_at": None,
        "source_family_hint": "other",
    }


class TestSemanticNormalization(unittest.TestCase):
    """Every fixture quote is taken from a real cached page.

    Synthetic quotes drift from the pages they claim to come from, and the span
    validator rightly rejects them. Pulling needles straight out of the cache
    keeps these tests honest - and costs nothing, because the pages are already
    bought.
    """

    #: Exact substrings of the real cached pages, asserted present in setUp.
    INSIDEEVS_NEEDLES = {
        "cockpit": "Einen billigen Eindruck macht das Cockpit nicht",
        "ac_dc": "| Ladeleistung AC/DC | 11 kW / 270 kW |",
        "wltp_range": "| WLTP-Reichweite | 627 - 720 km (Werksangabe) |",
        "wltp_consumption": "| WLTP-Verbrauch | 14,8 - 17,0 kWh/100 km (Werksangabe) |",
        "charge_time": "| DC-Ladedauer (10 - 80 %) | 21 Min. |",
        "measured_range": "Reichweiten von über 600 Kilometer",
    }
    ADAC_NEEDLES = {
        "test_consumption": "| Testverbrauch | 25,6 kWh/100km |",
        "wltp_range": "| WLTP Reichweite | 602 km |",
        "measured_range": "| Reichweite im Test | 351 km |",
        "recharged_range": "| Nachgeladene Reichweite in 20 Minuten | 184 km |",
    }

    def setUp(self):
        # Match distinctive URL *paths*, not domains: later runs cached more
        # adac.de and insideevs.de pages, and a domain match silently returned
        # the wrong page, failing every needle in this class.
        self.insideevs = self._page_containing("765911/audi-a6-etron-avant-test")
        self.adac = self._page_containing("elektroauto-reichweite-im-winter")
        if self.insideevs is None or self.adac is None:
            self.skipTest("the real cached pages are not in data/cache/")
        for name, needle in self.INSIDEEVS_NEEDLES.items():
            self.assertIn(needle, self.insideevs.markdown, f"InsideEVs needle {name!r} drifted")
        for name, needle in self.ADAC_NEEDLES.items():
            self.assertIn(needle, self.adac.markdown, f"ADAC needle {name!r} drifted")

    @staticmethod
    def _page_containing(fragment):
        """First cached page whose canonical URL contains *fragment*.

        *fragment* must identify one page: a bare domain is not enough once a
        later run has cached siblings on the same domain.
        """
        for path in sorted(CACHE_DIR.glob("*.json")):
            data = json.loads(path.read_text())
            if fragment in data.get("canonical_url", "") and data.get("markdown"):
                url = data["canonical_url"]
                return RawPage(
                    url=url, resolved_url=url, canonical_url=url,
                    title=data.get("title") or "", source_name=data.get("source_name") or "",
                    published_at=data.get("published_at"), query="Audi A6 e-tron Laden Erfahrungen",
                    topic="charging", retrieved_at="2026-10-10T00:00:00Z",
                    markdown=data["markdown"],
                )
        return None

    def _extract(self, page, rows, **overrides):
        provider = RowProvider(rows)
        extractor = EvidenceExtractor(provider, settings(extraction_chunk_chars=40_000, **overrides))
        return extractor.extract_from_page(page), extractor

    def _assert_spans_exact(self, page, records):
        for record in records:
            self.assertEqual(
                page.markdown[record.source_start_char:record.source_end_char],
                record.evidence_text,
                "offset must still address the exact quote",
            )

    # -- multilingual dedup ----------------------------------------------- #

    def test_english_and_german_wordings_of_one_claim_collapse(self):
        """The observed duplicate: both wordings quote the same German sentence."""
        quote = self.INSIDEEVS_NEEDLES["cockpit"]
        result, extractor = self._extract(self.insideevs, [
            row("The cockpit of the Audi A6 Avant e-tron does not give a cheap impression "
                "and is solidly built.", "comfort", "perceived_interior_quality", quote),
            row("Das Cockpit macht keinen billigen Eindruck und ist solide gefertigt.",
                "comfort", "perceived_interior_quality", quote),
        ])
        self.assertEqual(len(result.records), 1, [r.claim for r in result.records])
        self.assertEqual(extractor.stats.merged_by_span, 1)
        self.assertFalse(
            normalization.looks_non_english(result.records[0].claim),
            "the surviving claim should be the English one",
        )

    def test_two_distinct_facts_from_one_sentence_are_not_merged(self):
        quote = self.INSIDEEVS_NEEDLES["cockpit"]
        result, _ = self._extract(self.insideevs, [
            row("The cockpit does not look cheap.", "comfort", "perceived_interior_quality", quote),
            row("Build quality is solid to the knock test.", "comfort", "material_quality", quote),
        ])
        self.assertEqual(len(result.records), 2, "different subtopics must stay separate")

    # -- topic/subtopic correction ---------------------------------------- #

    def test_consumption_in_kwh_per_100km_becomes_range_energy_consumption(self):
        """25,6 kWh/100 km was classified charging/charging_reliability."""
        result, extractor = self._extract(self.adac, [
            row("Test consumption was 25.6 kWh/100 km.", "charging", "charging_reliability",
                self.ADAC_NEEDLES["test_consumption"], value=25.6, unit="kWh/100km"),
        ])
        self.assertEqual(len(result.records), 1)
        record = result.records[0]
        self.assertEqual((record.topic, record.subtopic), ("range", "energy_consumption"))
        self.assertEqual(record.numeric_value, 25.6)
        self.assertEqual(extractor.stats.records_reclassified, 1)
        self._assert_spans_exact(self.adac, result.records)

    def test_wltp_range_becomes_range_wltp_range(self):
        """WLTP range was classified charging/long_distance_charging."""
        for page, needle in ((self.insideevs, self.INSIDEEVS_NEEDLES["wltp_range"]),
                             (self.adac, self.ADAC_NEEDLES["wltp_range"])):
            result, _ = self._extract(page, [
                row("WLTP range is stated by the factory.", "charging",
                    "long_distance_charging", needle),
            ])
            self.assertEqual(len(result.records), 1, needle)
            self.assertEqual(
                (result.records[0].topic, result.records[0].subtopic),
                ("range", "wltp_range"), needle,
            )

    def test_wltp_consumption_is_consumption_not_range(self):
        """kWh/100 km wins over the WLTP label: it is a consumption figure."""
        result, _ = self._extract(self.insideevs, [
            row("WLTP consumption is 14.8 to 17.0 kWh/100 km.", "charging",
                "charging_reliability", self.INSIDEEVS_NEEDLES["wltp_consumption"]),
        ])
        self.assertEqual(
            (result.records[0].topic, result.records[0].subtopic),
            ("range", "energy_consumption"),
        )

    def test_measured_range_uses_page_context_for_winter(self):
        """The ADAC page is a winter range test; InsideEVs is a launch review."""
        adac_result, _ = self._extract(self.adac, [
            row("Measured range was 351 km.", "charging",
                "long_distance_charging", self.ADAC_NEEDLES["measured_range"]),
        ])
        self.assertEqual(
            (adac_result.records[0].topic, adac_result.records[0].subtopic),
            ("range", "winter_range"),
        )
        ie_result, _ = self._extract(self.insideevs, [
            row("Ranges above 600 km were not achieved in testing.", "charging",
                "long_distance_charging", self.INSIDEEVS_NEEDLES["measured_range"]),
        ])
        self.assertEqual(
            (ie_result.records[0].topic, ie_result.records[0].subtopic),
            ("range", "real_world_range"),
        )

    def test_range_gained_by_charging_is_left_as_a_charging_metric(self):
        """"Nachgeladene Reichweite" is charging speed in range units.

        The range rules must not claim it just because it says "Reichweite" and
        quotes kilometres on a range-test page.
        """
        result, extractor = self._extract(self.adac, [
            row("184 km of range was added in 20 minutes of charging.", "charging",
                "charging_speed", self.ADAC_NEEDLES["recharged_range"]),
        ])
        self.assertEqual(result.records[0].topic, "charging")
        self.assertEqual(extractor.stats.records_reclassified, 0)

    def test_charge_duration_row_stays_charging_time(self):
        result, _ = self._extract(self.insideevs, [
            row("DC charging from 10 to 80 percent takes 21 minutes.", "charging",
                "charging_reliability", self.INSIDEEVS_NEEDLES["charge_time"],
                value=21.0, unit="min"),
        ])
        self.assertEqual(
            (result.records[0].topic, result.records[0].subtopic),
            ("charging", "charging_time"),
        )

    # -- multi-value splitting -------------------------------------------- #

    def test_ac_dc_row_splits_into_two_atomic_records(self):
        """11 kW / 270 kW arrived as one record with numeric_value null."""
        quote = self.INSIDEEVS_NEEDLES["ac_dc"]
        result, extractor = self._extract(self.insideevs, [
            row("Charging power is 11 kW AC and 270 kW DC.", "charging", "charging_speed", quote),
        ])
        self.assertEqual(len(result.records), 2, [r.claim for r in result.records])
        self.assertEqual(extractor.stats.records_split, 1)
        by_current = {r.claim.split()[0]: r for r in result.records}
        self.assertEqual(set(by_current), {"AC", "DC"})
        self.assertEqual(by_current["AC"].numeric_value, 11.0)
        self.assertEqual(by_current["DC"].numeric_value, 270.0)
        for record in result.records:
            self.assertEqual(record.numeric_unit, "kW")
            self.assertEqual((record.topic, record.subtopic), ("charging", "charging_speed"))
            self.assertEqual(record.evidence_text, quote, "both halves keep the verbatim row")
        self._assert_spans_exact(self.insideevs, result.records)

    def test_a_value_range_is_not_split(self):
        """14,8 - 17,0 kWh/100 km is one fact with an interval, not two facts."""
        result, extractor = self._extract(self.insideevs, [
            row("WLTP consumption is 14.8 to 17.0 kWh/100 km.", "range",
                "energy_consumption", self.INSIDEEVS_NEEDLES["wltp_consumption"]),
        ])
        self.assertEqual(len(result.records), 1)
        self.assertEqual(extractor.stats.records_split, 0)

    # -- invariants ------------------------------------------------------- #

    def test_evidence_text_is_never_translated_and_offsets_hold(self):
        result, _ = self._extract(self.insideevs, [
            row("The cockpit does not give a cheap impression.", "comfort",
                "perceived_interior_quality", self.INSIDEEVS_NEEDLES["cockpit"]),
            row("Charging power is 11 kW AC and 270 kW DC.", "charging", "charging_speed",
                self.INSIDEEVS_NEEDLES["ac_dc"]),
        ])
        self.assertTrue(result.records)
        for record in result.records:
            self.assertNotEqual(record.claim, record.evidence_text)
            self.assertFalse(normalization.looks_non_english(record.claim),
                             f"claim should be English: {record.claim}")
        self.assertIn("Eindruck", " ".join(r.evidence_text for r in result.records))
        self._assert_spans_exact(self.insideevs, result.records)

    def test_non_english_claims_are_counted(self):
        result, extractor = self._extract(self.insideevs, [
            row("Das Cockpit macht keinen billigen Eindruck.", "comfort",
                "perceived_interior_quality", self.INSIDEEVS_NEEDLES["cockpit"]),
        ])
        self.assertEqual(extractor.stats.non_english_claims, 1)
        self.assertEqual(len(result.records), 1, "a non-English claim is flagged, not dropped")

    def test_no_firecrawl_client_is_used(self):
        """Normalization runs entirely on cached text."""
        import scraper, search
        for module, name in ((search, "FirecrawlSearchClient"), (scraper, "FirecrawlScraperClient")):
            client = getattr(module, name)("fc-test")
            self.assertEqual(client.call_count, 0)
        result, _ = self._extract(self.adac, [
            row("Test consumption was 25.6 kWh/100 km.", "charging", "charging_reliability",
                self.ADAC_NEEDLES["test_consumption"], value=25.6, unit="kWh/100km"),
        ])
        self.assertTrue(result.records)

    # -- taxonomy --------------------------------------------------------- #

    def test_canonical_taxonomy_covers_the_required_minimum(self):
        from models import SUBTOPICS
        required = {
            "charging": ("charging_speed", "charging_time", "charging_curve",
                         "battery_preconditioning", "route_planning", "charging_network",
                         "long_distance_charging"),
            "range": ("wltp_range", "real_world_range", "winter_range", "energy_consumption"),
            "comfort": ("ride_comfort", "seat_comfort", "rear_seat_comfort", "climate_comfort",
                        "cabin_noise", "interior_space", "perceived_interior_quality",
                        "material_quality"),
            "infotainment": ("display_usability", "physical_controls",
                             "climate_control_interaction", "navigation",
                             "smartphone_integration", "software_reliability"),
            "market_trend": ("infrastructure_growth", "customer_expectation",
                             "competitive_benchmark", "adoption_trend"),
        }
        for topic, subtopics in required.items():
            for subtopic in subtopics:
                self.assertIn(subtopic, SUBTOPICS[topic], f"{topic}/{subtopic}")

    def test_deprecated_subtopic_names_are_canonicalized(self):
        from models import RawEvidence
        quote = self.INSIDEEVS_NEEDLES["cockpit"]
        record = RawEvidence(
            source_url="https://insideevs.de/a", source_name="InsideEVs", source_title="T",
            source_family="professional_review", published_at=None, brand="Audi",
            vehicle="A6 e-tron", market="DE", topic="market_trend",
            subtopic="charging_network_growth", claim="Germany keeps adding fast chargers.",
            evidence_text=quote, source_start_char=0, source_end_char=len(quote),
        )
        canonical, changed = normalization.canonicalize_subtopic(record)
        self.assertTrue(changed)
        self.assertEqual(canonical.subtopic, "infrastructure_growth")

    def test_stored_rows_under_old_names_still_validate(self):
        """Renaming must not invalidate evidence already on disk."""
        from models import ProcessedEvidence
        path = pathlib.Path(__file__).resolve().parent / "data/processed/external_evidence.jsonl"
        if not path.is_file():
            self.skipTest("no stored evidence")
        rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
        for stored in rows:
            ProcessedEvidence.model_validate(stored)
        self.assertTrue(rows)


# --------------------------------------------------------------------------- #
# 12. Final semantic-quality cleanup
# --------------------------------------------------------------------------- #


class TestCanonicalUnits(unittest.TestCase):
    def test_minute_spellings_all_become_minutes(self):
        for raw in ("Min.", "Minuten", "min", "mins", "minute", "MINUTES"):
            self.assertEqual(normalization.normalize_unit(raw, ""), "minutes", raw)

    def test_other_canonical_mappings(self):
        for raw, want in (("%", "percent"), ("Prozent", "percent"), ("kw", "kW"),
                          ("Kilowatt", "kW"), ("Kilometer", "km"), ("kmh", "km/h"),
                          ("Euro", "EUR"), ("€", "EUR"), ("volt", "V"),
                          ("kWh/100km", "kWh/100 km")):
            self.assertEqual(normalization.normalize_unit(raw, ""), want, raw)

    def test_unknown_unit_is_left_alone(self):
        self.assertEqual(normalization.normalize_unit("furlongs", ""), "furlongs")
        self.assertIsNone(normalization.normalize_unit(None, ""))
        self.assertIsNone(normalization.normalize_unit("   ", ""))

    def test_consumption_kwh_becomes_per_100km(self):
        for quote, value in (
            ("In diese Regionen kann man bei konstantem Tempo 100 durchaus kommen, "
             "wir erreichten 16,3 kWh", 16.3),
            ("Unser Schnitt auf der Langstrecke: 18,5 kWh", 18.5),
            ("Der Verbrauch liegt bei 20,1 kWh", 20.1),
        ):
            self.assertEqual(
                normalization.normalize_unit("kWh", quote, value=value), "kWh/100 km", quote
            )

    def test_battery_capacity_kwh_stays_kwh(self):
        for quote, value in (("| Akku netto | 94,9 kWh |", 94.9),
                             ("| Batterie (netto) | 81,2 kWh |", 81.2),
                             ("Die Batterie fasst 83 kWh brutto", 83.0),
                             ("usable battery capacity of 94.9 kWh", 94.9)):
            self.assertEqual(normalization.normalize_unit("kWh", quote, value=value), "kWh", quote)

    def test_capacity_wins_when_both_signals_appear(self):
        self.assertEqual(
            normalization.normalize_unit(
                "kWh", "Der Verbrauch leert den 94,9 kWh Akku schnell", value=94.9,
                context="verbrauch test",
            ),
            "kWh",
        )

    def test_magnitude_breaks_the_tie_only_on_a_consumption_page(self):
        quote = "Ein Wert von 16,3 kWh"
        self.assertEqual(
            normalization.normalize_unit("kWh", quote, value=16.3, context="verbrauch im test"),
            "kWh/100 km",
        )
        self.assertEqual(
            normalization.normalize_unit("kWh", quote, value=16.3, context="infotainment review"),
            "kWh",
        )
        self.assertEqual(
            normalization.normalize_unit("kWh", "Ein Wert von 94,9 kWh", value=94.9,
                                         context="verbrauch im test"),
            "kWh",
            "too large to be consumption",
        )


class TestOutOfScopeFilter(unittest.TestCase):
    @staticmethod
    def _record(text):
        from models import RawEvidence
        return RawEvidence(
            source_url="https://insideevs.de/a", source_name="InsideEVs", source_title="T",
            source_family="professional_review", published_at=None, brand="Audi",
            vehicle="A6 e-tron", market="DE", topic="market_trend",
            subtopic="customer_expectation", claim=text, evidence_text=text,
            source_start_char=0, source_end_char=len(text),
        )

    def test_company_car_taxation_is_filtered(self):
        rejected, reason = normalization.is_out_of_scope(self._record(
            "In Germany the 0.25-percent company car taxation now applies up to 100,000 Euro."
        ))
        self.assertTrue(rejected, reason)

    def test_other_business_subjects_are_filtered(self):
        for text in ("Die Leasingrate betraegt 499 Euro im Monat.",
                     "Der Umweltbonus wurde gestrichen.",
                     "Die Versicherung ist in Kaskoeinstufung 21 eingeordnet.",
                     "Total cost of ownership over four years favours the diesel.",
                     "Die Typgenehmigung erfolgte nach europaeischer Homologation."):
            self.assertTrue(normalization.is_out_of_scope(self._record(text))[0], text)

    def test_customer_facing_price_and_quality_perception_is_kept(self):
        """A value-perception complaint must survive the filter."""
        for text in ("Fuer diesen Preis ist die Materialqualitaet enttaeuschend.",
                     "For this price the perceived quality disappoints.",
                     "Trotz des hohen Listenpreises ist die Verarbeitung gut."):
            rejected, reason = normalization.is_out_of_scope(self._record(text))
            self.assertFalse(rejected, f"{text} -> {reason}")

    def test_product_evidence_is_never_filtered(self):
        for text in ("Kunden erwarten schnelleres Laden in der naechsten Generation.",
                     "Die Bedienung ueber den Touchscreen ist umstaendlich.",
                     "Rear seat space is tight for tall passengers.",
                     "Der Verbrauch liegt bei 25,6 kWh/100 km.",
                     "Die Lenkung spricht direkt an.",
                     "Das Design polarisiert, die Optik wirkt wertig.",
                     "Competitors reach 300 kW charging power.",
                     "The software update improved the navigation."):
            self.assertFalse(normalization.is_out_of_scope(self._record(text))[0], text)

    def test_filtered_records_are_counted_and_dropped(self):
        quote = "Die Dienstwagenbesteuerung liegt bei 0,25 Prozent."
        page_text = relevant_text(1500) + " " + quote + " "
        provider = FakeProvider([payload(
            claim("Company car taxation is 0.25 percent.", topic="market_trend",
                  subtopic="customer_expectation", evidence=quote),
            claim("The i5 charges at 205 kW.", evidence=SENTENCES["peak"]),
        )])
        extractor = EvidenceExtractor(provider, settings(extraction_chunk_chars=40_000))
        result = extractor.extract_from_page(page(page_text))
        self.assertEqual(len(result.records), 1)
        self.assertEqual(extractor.stats.filtered_out_of_scope, 1)

    def test_run_record_exposes_the_scope_metric(self):
        from models import ResearchRun
        self.assertIn("records_filtered_out_of_scope", ResearchRun.model_fields)


class TestClaimTextCleanup(unittest.TestCase):
    def test_glued_words_are_separated(self):
        for raw, want in (("The A6e-tron charges quickly.", "The A6 e-tron charges quickly."),
                          ("Available onlyfor the top trim.", "Available only for the top trim."),
                          ("The cabin is veryquiet at speed.", "The cabin is very quiet at speed."),
                          ("Reaches 270 kW but onlybriefly.", "Reaches 270 kW but only briefly."),
                          ("The i5Touring has more space.", "The i5 Touring has more space.")):
            self.assertEqual(normalization.clean_claim_text(raw)[0], want, raw)

    def test_real_words_are_not_split(self):
        for text in ("A notable improvement over the predecessor.",
                     "Charging is available online.",
                     "The seats are comfortable.",
                     "Nothing to fix here at all."):
            cleaned, changed = normalization.clean_claim_text(text)
            self.assertEqual(cleaned, text)
            self.assertFalse(changed)

    def test_evidence_text_and_offsets_are_untouched_by_cleanup(self):
        """Cleanup touches the claim only - never the verbatim quote."""
        quote = SENTENCES["peak"]
        page_text = relevant_text(1500)
        provider = FakeProvider([payload(
            claim("The A6e-tron is veryquiet.", topic="comfort", subtopic="cabin_noise",
                  evidence=quote),
        )])
        extractor = EvidenceExtractor(provider, settings(extraction_chunk_chars=40_000))
        result = extractor.extract_from_page(page(page_text))
        record = result.records[0]
        self.assertEqual(record.claim, "The A6 e-tron is very quiet.")
        self.assertEqual(record.evidence_text, quote, "quote must be byte-for-byte unchanged")
        self.assertEqual(
            page_text[record.source_start_char:record.source_end_char], quote,
            "offsets must still address the quote",
        )
        self.assertEqual(extractor.stats.claims_cleaned, 1)


class TestSemanticRoles(unittest.TestCase):
    def test_role_detection(self):
        from models import RawEvidence

        def made(text):
            return RawEvidence(
                source_url="https://insideevs.de/a", source_name="InsideEVs", source_title="T",
                source_family="professional_review", published_at=None, brand="Audi",
                vehicle="A6 e-tron", market="DE", topic="charging", subtopic="charging_speed",
                claim=text, evidence_text=text, source_start_char=0, source_end_char=len(text),
            )

        self.assertEqual(normalization.semantic_role(made("Maximal 270 kW laut Hersteller")),
                         "capability")
        self.assertEqual(normalization.semantic_role(made("can reach 270 kW, but only briefly")),
                         "observed")
        self.assertEqual(normalization.semantic_role(made("Charging power is 270 kW.")),
                         "unspecified")

    def test_capability_and_observation_about_one_number_are_both_kept(self):
        """270 kW rated and 270 kW "only briefly" are different evidence."""
        quote = SENTENCES["peak"]
        provider = FakeProvider([payload(
            claim("DC charging power is 270 kW.", topic="charging", subtopic="charging_speed",
                  evidence=quote, value=270.0, unit="kW"),
            claim("The Audi A6 e-tron Avant can reach 270 kW in the test, but only briefly.",
                  topic="charging", subtopic="charging_speed", evidence=quote,
                  value=270.0, unit="kW"),
        )])
        extractor = EvidenceExtractor(provider, settings(extraction_chunk_chars=40_000))
        result = extractor.extract_from_page(page(relevant_text(1500)))
        self.assertEqual(len(result.records), 2, [r.claim for r in result.records])
        self.assertEqual(extractor.stats.kept_distinct_roles, 1)

    def test_the_same_proposition_twice_still_collapses(self):
        """Two capability statements of one fact are still one record."""
        quote = SENTENCES["peak"]
        provider = FakeProvider([payload(
            claim("DC charging power is rated at 270 kW.", topic="charging",
                  subtopic="charging_speed", evidence=quote, value=270.0, unit="kW"),
            claim("DC charging power is rated at 270 kW.", topic="charging",
                  subtopic="charging_speed", evidence=quote, value=270.0, unit="kW"),
        )])
        extractor = EvidenceExtractor(provider, settings(extraction_chunk_chars=40_000))
        result = extractor.extract_from_page(page(relevant_text(1500)))
        self.assertEqual(len(result.records), 1)


class TestExpandedTaxonomy(unittest.TestCase):
    def test_driving_experience_is_its_own_topic(self):
        from models import SUBTOPICS, TOPICS
        self.assertIn("driving_experience", TOPICS)
        for subtopic in ("steering_response", "handling", "braking_feel"):
            self.assertIn(subtopic, SUBTOPICS["driving_experience"])
        self.assertNotIn("steering_response", SUBTOPICS["comfort"],
                         "steering must not be folded into ride comfort")

    def test_charging_port_subtopics_exist(self):
        from models import SUBTOPICS
        for subtopic in ("charging_port_access", "charging_interface"):
            self.assertIn(subtopic, SUBTOPICS["charging"])

    def test_steering_and_port_records_validate(self):
        from models import RawEvidence
        for topic, subtopic, text in (
            ("driving_experience", "steering_response", "die direkt ansprechende Lenkung"),
            ("driving_experience", "braking_feel", "Beim Bremsen merkt man das Gewicht"),
            ("charging", "charging_port_access",
             "Es gibt Ladeanschluesse auf beiden Seiten des Fahrzeugs"),
        ):
            record = RawEvidence(
                source_url="https://insideevs.de/a", source_name="InsideEVs", source_title="T",
                source_family="professional_review", published_at=None, brand="Audi",
                vehicle="A6 e-tron", market="DE", topic=topic, subtopic=subtopic,
                claim="an English claim about the car", evidence_text=text,
                source_start_char=0, source_end_char=len(text),
            )
            self.assertEqual((record.topic, record.subtopic), (topic, subtopic))

    def test_every_topic_has_relevance_vocabulary(self):
        from models import TOPICS
        from search import TOPIC_KEYWORDS
        for topic in TOPICS:
            self.assertIn(topic, TOPIC_KEYWORDS,
                          f"{topic} would score zero in the relevance gate")

    def test_real_steering_and_port_quotes_are_on_the_cached_page(self):
        """The needles these subtopics exist for come from the real page."""
        page_text = None
        for path in sorted(CACHE_DIR.glob("*.json")):
            data = json.loads(path.read_text())
            if "765911/audi-a6-etron-avant-test" in data.get("canonical_url", ""):
                page_text = data["markdown"]
        if page_text is None:
            self.skipTest("InsideEVs page not cached")
        for needle in ("die direkt ansprechende Lenkung",
                       "Beim Bremsen hingegen merkt man das Gewicht",
                       "Es gibt Ladeanschlüsse auf beiden Seiten des Fahrzeugs"):
            self.assertIn(needle, page_text)

    def test_no_firecrawl_client_is_used_by_normalization(self):
        import scraper, search
        for module, name in ((search, "FirecrawlSearchClient"),
                             (scraper, "FirecrawlScraperClient")):
            self.assertEqual(getattr(module, name)("fc-test").call_count, 0)


# --------------------------------------------------------------------------- #
# 13. Quoted proper names must not make a claim look German
# --------------------------------------------------------------------------- #


class TestQuotedProperNames(unittest.TestCase):
    """A quoted option or package name stays in its source language by design.

    "Virtuelle Außenspiegel" is what Audi calls the option, so its umlauts say
    nothing about the language of the English sentence around it.
    """

    ENGLISH_WITH_GERMAN_NAMES = (
        "The option 'Virtuelle Außenspiegel' (Code PAF) costs 1.450 Euro.",
        "The option 'Virtuelle Außenspiegel' costs 1,450 EUR.",
        'The feature "Batterievorkonditionierung" is available.',
        'The package "M Sportpaket" includes adaptive dampers.',
        'The "Ausstattungspaket Komfort" adds heated rear seats.',
        "The trim called \u201eM Sportpaket\u201c is optional.",
        "The option \u2018Virtuelle Au\u00dfenspiegel\u2019 is pricey.",
        "The \u00abPaket Au\u00dfenspiegel\u00bb option is offered.",
    )

    def test_quoted_product_names_do_not_flag_an_english_claim(self):
        for claim_text in self.ENGLISH_WITH_GERMAN_NAMES:
            self.assertFalse(
                normalization.looks_non_english(claim_text),
                f"false positive: {claim_text}",
            )

    def test_apostrophes_are_not_mistaken_for_quotes(self):
        for claim_text in ("It's the car's best feature by far.",
                           "The driver's seat isn't comfortable enough.",
                           "The cabin's noise level isn't an issue."):
            self.assertFalse(normalization.looks_non_english(claim_text), claim_text)

    def test_unquoted_german_is_still_flagged(self):
        for claim_text in ("Das Cockpit macht keinen billigen Eindruck und ist solide gefertigt.",
                           "Die Ladeleistung faellt ab 60 Prozent ab.",
                           "Die Vorkonditionierung funktioniert gut.",
                           "Der Fahrkomfort ist auf schlechter Strasse nicht gut."):
            self.assertTrue(normalization.looks_non_english(claim_text), claim_text)

    def test_a_claim_that_is_only_a_german_quote_is_still_flagged(self):
        """Stripping must not turn a wholly German claim into an English one."""
        self.assertTrue(normalization.looks_non_english(
            '"Das Cockpit macht keinen billigen Eindruck und ist solide gefertigt."'
        ))

    def test_such_a_claim_is_kept_and_not_counted_as_non_english(self):
        """End to end: the record survives and the counter stays at zero."""
        quote = SENTENCES["peak"]
        provider = FakeProvider([payload(
            claim("The option 'Virtuelle Außenspiegel' (Code PAF) costs 1.450 Euro.",
                  topic="comfort", subtopic="perceived_interior_quality", evidence=quote),
        )])
        extractor = EvidenceExtractor(provider, settings(extraction_chunk_chars=40_000))
        page_text = relevant_text(1500)
        result = extractor.extract_from_page(page(page_text))
        self.assertEqual(len(result.records), 1)
        self.assertEqual(extractor.stats.non_english_claims, 0)
        record = result.records[0]
        self.assertIn("Virtuelle Außenspiegel", record.claim,
                      "the product name must not be translated or stripped")
        self.assertEqual(record.evidence_text, quote, "quote must be byte-for-byte unchanged")
        self.assertEqual(
            page_text[record.source_start_char:record.source_end_char], quote,
            "offsets must still address the quote",
        )


# --------------------------------------------------------------------------- #
# 14. Acquisition efficiency: fail fast, and stop re-spending on dead URLs
# --------------------------------------------------------------------------- #


class TestPermanentErrorsFailFast(unittest.TestCase):
    """A permanent provider error must cost exactly one Firecrawl attempt.

    The first live charging run spent three attempts being told by Firecrawl
    that Reddit is "Website Not Supported".
    """

    class _Err(Exception):
        def __init__(self, message="", **attrs):
            super().__init__(message)
            self.__dict__.update(attrs)

    def _attempts_for(self, exc, *, attempts=4):
        """How many times the retry executor calls through for *exc*."""
        from utils import call_with_rate_limit_retry
        calls = []

        def fail():
            calls.append(1)
            raise exc

        slept = []
        try:
            call_with_rate_limit_retry(
                fail, attempts=attempts, base_delay=2.0, max_sleep=60.0,
                label="firecrawl.scrape(https://www.reddit.com/r/BMW/)",
                sleeper=slept.append,
            )
        except Exception:
            pass
        return len(calls), len(slept)

    def test_website_not_supported_makes_exactly_one_attempt(self):
        calls, sleeps = self._attempts_for(self._Err("Website Not Supported"))
        self.assertEqual(calls, 1, "a permanent error must not be retried")
        self.assertEqual(sleeps, 0, "and must not sleep")

    def test_other_permanent_errors_make_exactly_one_attempt(self):
        for exc in (self._Err("Bad Request: invalid URL"),
                    self._Err("unsupported domain"),
                    self._Err("unsupported site"),
                    self._Err("Unauthorized", status_code=401),
                    self._Err("Forbidden", status_code=403),
                    self._Err("Not Found", status_code=404),
                    self._Err("Payment Required", status_code=402),
                    self._Err("Unprocessable Entity", status_code=422),
                    self._Err("invalid api key")):
            calls, _ = self._attempts_for(exc)
            self.assertEqual(calls, 1, f"{exc} should not be retried")

    def test_retryable_errors_still_use_the_whole_budget(self):
        for exc in (self._Err("429 rate limit exceeded"),
                    self._Err("Too Many Requests", status_code=429),
                    self._Err("Internal Server Error", status_code=500),
                    self._Err("Bad Gateway", status_code=502),
                    self._Err("Request Timeout", status_code=408),
                    self._Err("Connection reset by peer"),
                    self._Err("Read timed out")):
            calls, _ = self._attempts_for(exc)
            self.assertEqual(calls, 4, f"{exc} should still be retried")

    def test_rate_limit_is_never_classified_permanent(self):
        """429 is the one 4xx that succeeds later."""
        from utils import is_permanent_error
        for exc in (self._Err("429 rate limit"),
                    self._Err("Too Many Requests", status_code=429)):
            self.assertFalse(is_permanent_error(exc))

    def test_retry_after_is_still_honoured(self):
        """Existing rate-limit handling must be untouched."""
        from utils import call_with_rate_limit_retry

        class Resp:
            status_code = 429
            headers = {"Retry-After": "9"}

        attempts = []

        def flaky():
            attempts.append(1)
            if len(attempts) < 3:
                raise self._Err("rate limit", response=Resp())
            return "ok"

        slept = []
        result = call_with_rate_limit_retry(
            flaky, attempts=4, base_delay=2.0, max_sleep=60.0, label="s",
            sleeper=slept.append,
        )
        self.assertEqual(result, "ok")
        self.assertEqual(slept, [9.0, 9.0])

    def test_a_permanent_scrape_error_costs_one_sdk_call(self):
        """End to end through the coordinator."""
        tmp = pathlib.Path(tempfile.mkdtemp())
        calls = []

        class UnsupportedSDK:
            def scrape(self, url, **kwargs):
                calls.append(url)
                raise TestPermanentErrorsFailFast._Err("Website Not Supported")

        client = scraper.FirecrawlScraperClient("fc-test", delay_seconds=0, max_retries=4,
                                                sleeper=lambda _d: None)
        type(client).client = property(lambda self: UnsupportedSDK())
        try:
            visited = VisitedUrlStore(tmp / "v.json")
            coordinator = ScrapeCoordinator(
                client=client, cache=PageCache(tmp / "c"), visited=visited,
            )
            url = "https://www.reddit.com/r/BMW/comments/abc/i5_charging/"
            hit = SearchHit(url=url, canonical_url=canonicalize_url(url),
                            topic="charging", query="q")
            result = coordinator.resolve(hit)
            self.assertIs(result.outcome, ScrapeOutcome.FAILED)
            self.assertEqual(len(calls), 1, f"expected 1 Firecrawl call, got {len(calls)}")
            self.assertTrue(visited.is_terminal(url), "an unsupported site is terminal")
        finally:
            del type(client).client


class TestTerminalOutcomes(unittest.TestCase):
    """A deterministically dead URL must stop consuming page-budget slots."""

    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.visited = VisitedUrlStore(self.tmp / "v.json")
        self.cache = PageCache(self.tmp / "c")

    def _hit(self, url, *, topic="charging", position=1):
        return SearchHit(url=url, canonical_url=canonicalize_url(url), title="BMW i5 laden",
                         description="ladezeit", topic=topic, query="q", position=position)

    def _coordinator(self, client=None, **kwargs):
        return ScrapeCoordinator(client=client, cache=self.cache, visited=self.visited, **kwargs)

    def test_thin_and_unsupported_are_terminal(self):
        for status in ("thin", "unsupported"):
            url = f"https://example.invalid/{status}"
            self.visited.mark(url, status=status, terminal=True)
            self.assertTrue(self.visited.is_terminal(url), status)

    def test_recoverable_outcomes_are_not_terminal(self):
        """These may succeed on a later run and must stay eligible."""
        for status in ("failed", "scraped", "cached", "filtered"):
            url = f"https://example.invalid/{status}"
            self.visited.mark(url, status=status)
            self.assertFalse(self.visited.is_terminal(url), status)

    def test_the_terminal_flag_survives_a_later_cache_hit(self):
        url = "https://example.invalid/thin"
        self.visited.mark(url, status="thin", terminal=True)
        self.visited.mark(url, status="cached")
        self.assertTrue(self.visited.is_terminal(url),
                        "a status rewrite must not clear the flag")

    def test_the_terminal_flag_persists_across_processes(self):
        url = "https://example.invalid/thin"
        self.visited.mark(url, status="thin", terminal=True)
        self.visited.save()
        self.assertTrue(VisitedUrlStore(self.tmp / "v.json").is_terminal(url))

    def test_a_terminal_url_is_dropped_before_the_page_budget_is_spent(self):
        """The whole point: a dead URL must not take a slot from a live one."""
        import main
        dead = "https://example.invalid/dead-thin-page"
        self.visited.mark(dead, status="thin", terminal=True)
        hits = [self._hit(dead, position=1)] + [
            self._hit(f"https://site{i}.de/bmw-i5-laden-test", position=i + 2) for i in range(3)
        ]
        run = ResearchRun(run_id="r", started_at="t", topic="charging")
        plan = main.plan_run(hits, self._coordinator(), max_pages=3, run=run)
        selected = [hit.canonical_url for hit in plan.candidates]
        self.assertEqual(len(selected), 3)
        self.assertNotIn(canonicalize_url(dead), selected)
        self.assertEqual(run.urls_skipped_filtered, 1)

    def test_force_still_reconsiders_a_terminal_url(self):
        import main
        dead = "https://example.invalid/dead-thin-page"
        self.visited.mark(dead, status="thin", terminal=True)
        run = ResearchRun(run_id="r", started_at="t", topic="charging")
        plan = main.plan_run([self._hit(dead)], self._coordinator(force=True),
                             max_pages=3, run=run, force=True)
        self.assertEqual(len(plan.candidates), 1)

    def test_resolve_skips_a_terminal_url_without_touching_the_provider(self):
        dead = "https://example.invalid/dead-thin-page"
        self.visited.mark(dead, status="thin", terminal=True)
        self.cache.put(canonicalize_url(dead), {"markdown": "x" * 50, "title": "t"})
        coordinator = self._coordinator(client=ExplodingScrapeClient())
        self.assertIs(coordinator.plan(self._hit(dead)), ScrapeOutcome.SKIPPED)
        result = coordinator.resolve(self._hit(dead))
        self.assertIs(result.outcome, ScrapeOutcome.SKIPPED)
        self.assertEqual(coordinator.scrape_call_count, 0)

    def test_a_thin_page_is_recorded_terminal_by_the_run_loop(self):
        """collect_evidence must persist the extractor's thin verdict."""
        coordinator = self._coordinator()
        url = "https://example.invalid/js-shell"
        coordinator.mark_terminal(url, status="thin", detail="only 428 usable chars")
        self.assertTrue(self.visited.is_terminal(url))

    def test_off_topic_pages_are_not_suppressed(self):
        """The relevance vocabulary keeps changing, so off-topic is not final."""
        url = "https://example.invalid/off-topic"
        self.visited.mark(url, status="filtered")
        self.assertFalse(self.visited.is_terminal(url))


# --------------------------------------------------------------------------- #
# 15. Truncation with an empty body (observed in the live infotainment run)
# --------------------------------------------------------------------------- #


class TestEmptyTruncation(unittest.TestCase):
    """An empty body at the output ceiling is truncation, not an empty answer.

    gpt-5-mini is a reasoning model, so ``max_completion_tokens`` covers
    reasoning *and* output. The first live infotainment run saw it spend the
    whole budget reasoning and return nothing with ``finish_reason=length``.
    The empty-content guard fired first, so the chunk went down the retry path
    and truncated three more times instead of being split.
    """

    @staticmethod
    def _client(content, finish_reason, counter=None):
        class Msg:
            def __init__(self):
                self.content = content
                self.refusal = None

        class Choice:
            def __init__(self):
                self.message = Msg()
                self.finish_reason = finish_reason

        class Resp:
            def __init__(self):
                self.choices = [Choice()]

        class Completions:
            def create(self, **kwargs):
                if counter is not None:
                    counter.append(1)
                return Resp()

        class Chat:
            def __init__(self):
                self.completions = Completions()

        class Client:
            def __init__(self):
                self.chat = Chat()

        return Client()

    def _call(self, content, finish_reason, counter=None):
        from llm_provider import OpenAIProvider
        provider = OpenAIProvider(model="gpt-5-mini", api_key="not-a-real-key")
        client = self._client(content, finish_reason, counter)
        type(provider).client = property(lambda self: client)
        try:
            return provider.complete_json(system="s", user="u", schema={"type": "object"})
        finally:
            del type(provider).client

    def test_empty_body_at_the_ceiling_is_truncation(self):
        from llm_provider import LLMTruncatedError
        with self.assertRaises(LLMTruncatedError):
            self._call("", "length")

    def test_partial_body_at_the_ceiling_is_truncation(self):
        from llm_provider import LLMTruncatedError
        with self.assertRaises(LLMTruncatedError):
            self._call('{"evidence": [{"claim": "cut off mid', "length")

    def test_a_genuinely_empty_answer_is_still_a_plain_error(self):
        from llm_provider import LLMError, LLMTruncatedError
        with self.assertRaises(LLMError) as caught:
            self._call("", "stop")
        self.assertNotIsInstance(caught.exception, LLMTruncatedError)

    def test_a_normal_completion_is_unaffected(self):
        self.assertEqual(self._call('{"evidence": []}', "stop"), '{"evidence": []}')

    def test_truncation_does_not_burn_the_retry_budget(self):
        from llm_provider import LLMTruncatedError
        calls = []
        with self.assertRaises(LLMTruncatedError):
            self._call("", "length", counter=calls)
        self.assertEqual(len(calls), 1, "a truncated request must not be retried verbatim")

    def test_anthropic_empty_at_max_tokens_is_truncation(self):
        from llm_provider import AnthropicProvider, LLMTruncatedError
        provider = AnthropicProvider(model="claude-opus-5", api_key="not-a-real-key")
        provider._invoke = lambda params: ("", "max_tokens")
        with self.assertRaises(LLMTruncatedError):
            provider.complete_json(system="s", user="u", schema={"type": "object"})

    def test_a_truncated_chunk_is_still_recovered_by_splitting(self):
        """End to end: the page keeps its evidence instead of losing a chunk."""
        from llm_provider import LLMTruncatedError
        provider = FakeProvider([
            LLMTruncatedError("finish_reason=length, 0 chars returned"),
            payload(claim("First half: peak is 205 kW.", value=205.0, unit="kW")),
            payload(claim("Second half: 10-80 in 30 minutes.", value=30.0, unit="min",
                          evidence=SENTENCES["curve"])),
        ])
        extractor = EvidenceExtractor(provider, settings(extraction_chunk_chars=20_000))
        result = extractor.extract_from_page(page(relevant_text(9_000)))
        self.assertEqual(len(result.records), 2)
        self.assertEqual(extractor.stats.sub_chunk_recoveries, 1)

    def test_output_ceiling_leaves_room_for_reasoning(self):
        self.assertGreaterEqual(config.LLM_MAX_OUTPUT_TOKENS, 16_000)


# --------------------------------------------------------------------------- #
# 16. Crash-safe incremental persistence
# --------------------------------------------------------------------------- #


class TestIncrementalPersistence(unittest.TestCase):
    """A run killed mid-flight must keep everything it already finished.

    The first live infotainment run was SIGTERMed after 136 minutes on page 9
    of 10, with 7 pages extracted - and lost every record, because evidence,
    the ledger and the run record were only written at the end.
    """

    def setUp(self):
        import main
        self.main = main
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self._saved = {
            name: getattr(config, name)
            for name in ("DATA_DIR", "RAW_DIR", "PROCESSED_DIR", "METADATA_DIR", "CACHE_DIR",
                         "RAW_PAGES_PATH", "PROCESSED_EVIDENCE_PATH", "VISITED_URLS_PATH",
                         "RESEARCH_RUNS_PATH", "RUN_CHECKPOINT_PATH", "LOG_PATH", "ENV_PATH")
        }
        config.DATA_DIR = self.tmp / "data"
        config.RAW_DIR = config.DATA_DIR / "raw"
        config.PROCESSED_DIR = config.DATA_DIR / "processed"
        config.METADATA_DIR = config.DATA_DIR / "metadata"
        config.CACHE_DIR = config.DATA_DIR / "cache"
        config.RAW_PAGES_PATH = config.RAW_DIR / "raw_pages.jsonl"
        config.PROCESSED_EVIDENCE_PATH = config.PROCESSED_DIR / "external_evidence.jsonl"
        config.VISITED_URLS_PATH = config.METADATA_DIR / "visited_urls.json"
        config.RESEARCH_RUNS_PATH = config.METADATA_DIR / "research_runs.jsonl"
        config.RUN_CHECKPOINT_PATH = config.METADATA_DIR / "run_checkpoint.json"
        config.LOG_PATH = self.tmp / "pipeline.log"
        config.ENV_PATH = self.tmp / ".env"
        config.ensure_directories()

    def tearDown(self):
        for name, value in self._saved.items():
            setattr(config, name, value)

    # -- fixtures --------------------------------------------------------- #

    def _page_markdown(self, n):
        return relevant_text(1500) + f" Variante {n} der Messung. "

    def _hits(self, count):
        out = []
        for i in range(count):
            url = f"https://site{i}.de/bmw-i5-laden-test-{i}"
            out.append(SearchHit(url=url, canonical_url=canonicalize_url(url),
                                 title="BMW i5 Ladetest", description="ladezeit",
                                 topic="charging", query="q", position=i + 1,
                                 source_family="professional_review", priority=75))
        return out

    def _coordinator(self, hits, *, fail_after=None):
        """A coordinator serving synthetic pages, optionally dying after N."""
        tmp = self.tmp
        markdown = {h.canonical_url: self._page_markdown(i) for i, h in enumerate(hits)}

        class Client:
            call_count = 0

            def fetch(self, url):
                Client.call_count += 1
                canonical = canonicalize_url(url)
                return {"markdown": markdown[canonical], "title": "T",
                        "source_name": "site", "source_url": url, "published_at": None}

        coordinator = ScrapeCoordinator(
            client=Client(), cache=PageCache(tmp / "cache"),
            visited=VisitedUrlStore(config.VISITED_URLS_PATH),
        )
        if fail_after is not None:
            original = coordinator.resolve
            calls = []

            def resolve(hit):
                calls.append(1)
                if len(calls) > fail_after:
                    raise KeyboardInterrupt("simulated SIGTERM")
                return original(hit)

            coordinator.resolve = resolve
        return coordinator

    def _extractor(self, per_page=3):
        rows = [payload(*[
            claim(f"Claim {i} about charging time here.", value=float(10 + i), unit="min")
            for i in range(per_page)
        ])] * 60
        return EvidenceExtractor(FakeProvider(rows), settings(extraction_chunk_chars=40_000))

    def _plan(self, hits):
        from main import RunPlan
        return RunPlan(candidates=list(hits), to_scrape=list(hits), cached=[], skipped=[], deferred=[])

    def _run_record(self):
        return ResearchRun(run_id="run-test", started_at="2026-10-11T00:00:00Z", topic="charging")

    def _stored(self):
        path = config.PROCESSED_EVIDENCE_PATH
        if not path.is_file():
            return []
        return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]

    # -- tests ------------------------------------------------------------ #

    def test_evidence_is_persisted_after_each_page(self):
        hits = self._hits(4)
        run = self._run_record()
        self.main.collect_evidence(self._plan(hits), self._coordinator(hits),
                                   self._extractor(), run=run)
        self.assertEqual(run.pages_with_evidence, 4)
        self.assertGreaterEqual(len(self._stored()), 4)

    def test_interruption_after_two_pages_keeps_those_two_pages(self):
        """The whole point: work already done survives the signal."""
        hits = self._hits(5)
        run = self._run_record()
        coordinator = self._coordinator(hits, fail_after=2)
        with self.assertRaises(KeyboardInterrupt):
            self.main.collect_evidence(self._plan(hits), coordinator, self._extractor(), run=run)

        stored = self._stored()
        self.assertTrue(stored, "evidence from the first two pages must be on disk")
        urls = {row["source_url"] for row in stored}
        self.assertEqual(len(urls), 2, f"expected 2 pages' evidence, got {urls}")

        ledger = json.loads(config.VISITED_URLS_PATH.read_text())
        self.assertEqual(len(ledger), 2, "the ledger must record both fetched pages")

        raw = config.RAW_PAGES_PATH.read_text().splitlines()
        self.assertEqual(len([l for l in raw if l.strip()]), 2)

        checkpoint = json.loads(config.RUN_CHECKPOINT_PATH.read_text())
        self.assertEqual(checkpoint["pages_done"], 2)
        self.assertEqual(checkpoint["pages_total"], 5)
        self.assertEqual(checkpoint["pages_with_evidence"], 2)
        self.assertTrue(checkpoint["checkpoint_written_at"])

    def test_resume_after_interruption_does_not_duplicate_evidence(self):
        """Re-running the same pages must not grow the store."""
        hits = self._hits(4)
        interrupted = self._run_record()
        with self.assertRaises(KeyboardInterrupt):
            self.main.collect_evidence(self._plan(hits), self._coordinator(hits, fail_after=2),
                                       self._extractor(), run=interrupted)
        after_crash = len(self._stored())
        self.assertGreater(after_crash, 0)

        # Resume: same pages, same deterministic claims, no --force.
        resumed = self._run_record()
        self.main.collect_evidence(self._plan(hits), self._coordinator(hits),
                                   self._extractor(), run=resumed)
        after_resume = self._stored()
        ids = [row["evidence_id"] for row in after_resume]
        self.assertEqual(len(ids), len(set(ids)), "resume must not duplicate evidence_id")
        self.assertEqual(len({row["source_url"] for row in after_resume}), 4)

    def test_resume_serves_already_fetched_pages_from_cache(self):
        """A resume must not re-spend Firecrawl credits on cached pages."""
        hits = self._hits(3)
        with self.assertRaises(KeyboardInterrupt):
            self.main.collect_evidence(self._plan(hits), self._coordinator(hits, fail_after=2),
                                       self._extractor(), run=self._run_record())
        resumed_run = self._run_record()
        coordinator = self._coordinator(hits)
        self.main.collect_evidence(self._plan(hits), coordinator, self._extractor(),
                                   run=resumed_run)
        self.assertEqual(resumed_run.pages_loaded_from_cache, 2,
                         "the two pages fetched before the crash must come from cache")
        self.assertEqual(resumed_run.pages_scraped, 1, "only the unfetched page is scraped")

    def test_a_terminal_verdict_is_persisted_immediately(self):
        """A thin page must be flagged on disk before the next page starts."""
        hits = self._hits(2)
        markdown = {hits[0].canonical_url: "Loading. Sorry to interrupt.",
                    hits[1].canonical_url: self._page_markdown(1)}

        class Client:
            call_count = 0

            def fetch(self, url):
                Client.call_count += 1
                return {"markdown": markdown[canonicalize_url(url)], "title": "T",
                        "source_name": "site", "source_url": url, "published_at": None}

        coordinator = ScrapeCoordinator(
            client=Client(), cache=PageCache(self.tmp / "cache"),
            visited=VisitedUrlStore(config.VISITED_URLS_PATH),
        )
        run = self._run_record()
        self.main.collect_evidence(self._plan(hits), coordinator, self._extractor(), run=run)
        ledger = json.loads(config.VISITED_URLS_PATH.read_text())
        thin = [k for k, v in ledger.items() if v.get("terminal")]
        self.assertEqual(len(thin), 1, f"the thin page must be terminal on disk: {ledger}")
        self.assertEqual(run.pages_skipped_thin, 1)

    def test_checkpoint_writes_are_atomic(self):
        """Every checkpoint on disk is complete, parsable JSON."""
        hits = self._hits(3)
        run = self._run_record()
        self.main.collect_evidence(self._plan(hits), self._coordinator(hits),
                                   self._extractor(), run=run)
        payload = json.loads(config.RUN_CHECKPOINT_PATH.read_text())
        self.assertEqual(payload["pages_done"], 3)
        self.assertIn("run_id", payload)

    def test_checkpoint_is_cleared_once_the_run_record_is_durable(self):
        from storage import clear_run_checkpoint, write_run_checkpoint
        write_run_checkpoint(self._run_record(), pages_done=1, pages_total=2)
        self.assertTrue(config.RUN_CHECKPOINT_PATH.is_file())
        clear_run_checkpoint()
        self.assertFalse(config.RUN_CHECKPOINT_PATH.is_file())

    def test_collect_evidence_returns_already_finalized_records(self):
        """Regression: the caller must not finalize these a second time.

        collect_evidence stores each page's evidence as it goes and returns
        ProcessedEvidence. execute() used to call finalize_evidence on the
        result again; from_raw then received evidence_id both explicitly and via
        **model_dump(), raising TypeError *after* the pages summary and before
        the run record was written. A completed 10-page run lost its
        finalization that way.
        """
        from models import ProcessedEvidence
        hits = self._hits(2)
        run = self._run_record()
        returned = self.main.collect_evidence(self._plan(hits), self._coordinator(hits),
                                              self._extractor(), run=run)
        self.assertTrue(returned)
        for record in returned:
            self.assertIsInstance(record, ProcessedEvidence)

        # And re-finalizing them is exactly the error that aborted the run.
        with self.assertRaises(TypeError):
            self.main.finalize_evidence(returned, run=self._run_record())

    def test_execute_path_does_not_refinalize(self):
        """The source no longer contains the double-finalize call."""
        source = pathlib.Path(__file__).resolve().parent.joinpath("main.py").read_text()
        self.assertNotIn("finalize_evidence(raw_records, run=run)", source)
        self.assertIn("stored = collect_evidence(", source)

    def test_counters_accumulate_across_pages(self):
        """finalize_evidence runs per page, so counters must add up."""
        hits = self._hits(3)
        run = self._run_record()
        self.main.collect_evidence(self._plan(hits), self._coordinator(hits),
                                   self._extractor(per_page=2), run=run)
        self.assertEqual(run.pages_with_evidence, 3)
        self.assertGreaterEqual(run.evidence_records_created, 3,
                                "created count must cover every page, not just the last")
        self.assertAlmostEqual(
            run.evidence_per_extracted_page,
            round(run.evidence_records_created / run.pages_with_evidence, 2),
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
