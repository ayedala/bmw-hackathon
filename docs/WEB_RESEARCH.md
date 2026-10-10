# Web evidence and enrichment plan

Sources below were searched and opened on **10 October 2026**. The tagged Deep Research connector was not callable, so research used the available web tool. This is a curated research pass, not an exhaustive market study or an implemented scraper.

## Sources actually inspected

| ID | Opened source | What it supports | Limitation and use |
|---|---|---|---|
| W01 | [BMW: China-specific 5 Series and i5, 8 August 2023](https://www.press.bmwgroup.com/global/article/detail/T0427958EN/the-new-bmw-5-series-sedan-and-the-new-bmw-i5-%E2%80%93-exclusively-from-china-for-china?language=en) | Manufacturer describes an extended-wheelbase variant and China-specific rear comfort/digital features | Historical OEM positioning; not a quantified survey of all Chinese customers |
| W02 | [BMW: new 5 Series Sedan, 2023 launch](https://www.press.bmwgroup.com/global/article/detail/T0416261EN/the-new-bmw-5-series-sedan) | Multiple powertrains and market-dependent offerings at launch | Current equipment requires a newer matched source; not every global spec applies to every market |
| W03 | [ADAC: BMW i5 test](https://www.adac.de/rund-ums-fahrzeug/autokatalog/marken-modelle/bmw/bmw-i5/) | Tested i5 eDrive40 range of 500 km, 10–80% charging in 30 minutes, and reviewer criticism of touchscreen climate operation | First-party test, bounded by tested version and method; inspect linked test PDF for full conditions before a quantitative comparison |
| W04 | [Mercedes-Benz USA: 2026 EQE 320 4MATIC Sedan](https://www.mbusa.com/en/vehicles/model/eqe/sedan/eqe320v4) | Manufacturer lists DC charging from 10–80% in 32 minutes | US, specific trim/year, specification not independent test; no direct superiority claim against W03 |
| W05 | [Euro NCAP: 2026 protocol changes](https://www.euroncap.com/press-media/euro-ncap-announces-2026-protocol-changes-to-tackle-modern-driving-risks/) | HMI assessment considers essential-control usability and physical controls | Safety-rating context, not proof that all touchscreen designs are unsafe or a legal mandate |
| W06 | [Euro NCAP: Safe Driving protocol index](https://www.euroncap.com/safe-driving/) | Links to current test procedures, including SD 203 version 1.1 | Index establishes available procedure version; the app must read the procedure before asserting detailed compliance criteria |
| W07 | [IEA Global EV Outlook 2026](https://www.iea.org/reports/global-ev-outlook-2026) | Current annual report, published 20 May 2026, distinguishes historical information and projections | Overview inspected; no numerical market forecast extracted for ranking yet |
| W08 | [IEA 2025 charging chapter](https://www.iea.org/reports/global-ev-outlook-2025/electric-vehicle-charging) | Historical charging context and scenario-based outlook | Prior edition retained as historical context, not called latest; refresh applicable facts against the 2026 chapter |
| M01 | [Government Analysis Function: MCDA guide](https://analysisfunction.civilservice.gov.uk/policy-store/an-introductory-guide-to-mcda/) | Anchored criteria, stakeholder swing weighting and sensitivity analysis | Methodological support, not an endorsement of this app's proposed scores |
| M02 | [NIST AI RMF](https://www.nist.gov/itl/ai-risk-management-framework) | Risk-management framework and generative-AI profile reference | General governance context; following this plan is not a certification |
| M03 | [W3C PROV overview](https://www.w3.org/TR/prov-overview/) | Provenance concepts linking entities, activities and responsible agents | Inspiration for lineage; full RDF/PROV implementation is unnecessary for the MVP |
| M04 | [RFC 9309](https://www.rfc-editor.org/info/rfc9309/) | Robots exclusion protocol | Technical crawler convention; robots permission alone does not establish content reuse rights |
| O01 | [OpenAI: AGENTS.md](https://learn.chatgpt.com/docs/agent-configuration/agents-md) | Repository instructions and scoped agent guidance | Exact behavior depends on the coding tool; other tools should read the root contract explicitly |
| O02 | [OpenAI: Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs) | Schema-constrained model responses and edge cases | Structure alone does not guarantee factual correctness |
| O03 | [OpenAI: evaluation best practices](https://developers.openai.com/api/docs/guides/evaluation-best-practices) | Task-specific evaluations, representative cases and repeated measurement | Does not validate the proposed metrics or thresholds before actual testing |
| O04 | [OpenAI: revisiting skills and prompts](https://developers.openai.com/blog/rethinking-skills-and-prompts-for-gpt-6-astra) | Avoid unnecessary instruction bloat | Basis for a concise root AGENTS.md and task-specific reference documents |

## Small evidence seed supplied with this pack

`research/web_evidence_seed.jsonl` contains five curated assertions from W01, W03, W04 and W05. It records source URLs, access date, scope and limits. Capture method is explicitly `web_tool_parsed_page_curated`; original HTML/PDF snapshots and cryptographic hashes were not captured in this research pass. These records seed the future collector and examples, not a claim of a completed automated ingestion pipeline. Re-fetch, snapshot where permitted, and validate locators before production use.

## 24-hour collection scope

Collect **6–10 well-chosen pages/documents**: provided BMW baseline plus current official vehicle page; one or two matched competitor pages; one independent instrumented review; one market/trend source; and a focused human-factors source. Match vehicle class, year, region, powertrain, trim and measurement conditions before combining facts.

The EQE is a plausible segment comparator for i5; confirm the chosen cohort with the PM. Do not scrape a trendy unrelated vehicle just to produce an impressive charging number. An unmatched source can inform technology possibilities but should be labelled a cross-segment reference.

Use public pages or permitted APIs. Check access/robots/terms; throttle requests; respect 429 responses; avoid login-protected, paywalled or blocked resources rather than bypassing them. Fetch only public approved hosts, with redirect and private-network checks. Do not upload supplied private comments to public search queries. Search by public vehicle/topic descriptors.

## Collector record and cleaning

Store URL, canonical URL, acquired_at, publication/last-updated date when explicit, HTTP status, content type, parser/version, document hash, page/section locator, short excerpt/claim, source method, vehicle/market/year scope, origin-family ID and rights/access note. A failed fetch is a failed fetch, not missing customer demand.

Strip navigation/boilerplate while preserving headings, table labels and footnotes. Keep original values and units; store conversions separately. Record the original test standard (WLTP/EPA/ADAC/etc.), state-of-charge window, conditions and trim. Reject numeric comparisons with unknown or incompatible methods. Keep manufacturer claims separate from measured tests.

Source dates and vehicle dates are different. A page retrieved in 2026 may describe a 2023 launch or an older test. Recency is not a global exponential penalty; old facts can remain valid until the relevant version changes. Cite publication and observation dates where known.

## Demo pipeline evidence

Show one page as collected → extracted fact with locator → cleaning/mapping log → applicability check → linked claim on a requirement card. Show an incompatible comparator being excluded from a numerical gap. This proves disciplined enrichment more effectively than a list of URLs or a claim that “we scraped the internet.”

Collection success, schema validity, factual accuracy and business relevance are four separate checks. Record each. Public-web search is a retrieval aid, not a ground-truth authority.
