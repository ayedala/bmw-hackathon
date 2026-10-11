# BMW Group Report 2025 in the decision workbench

The curated snapshot is `configs/bmw_group_report_2025_context.json`. Each item records a report fact, printed-page locator, decision consideration, applicability and limitation. The official report URL and publication date are retained with every database row. `bmw-pm sync-report-context` inserts the five rows immutably and logs the additions in the audit chain. Repeating an unchanged import inserts nothing; changing an existing item requires a new ID or report version.

The context applies in two ways:

- Portfolio entries appear on every requirement card: China exposure, margin and cash generation, and tariffs/outlook.
- Domain entries appear only when the card's domain and powertrain match: electric delivery mix for charging/range and electric software cards, plus climate context for charging/range cards.

The model extractor continues to receive the scoped customer record only. Report context enters the **review and decision layer**, where it prompts a PM to check applicability, market gaps, costs and dated assumptions. It does not create customer signals, change recurrence, fill strategic-contribution or outlook criterion values, or imply feature economics. New score snapshots list matched context IDs in assumptions so the sources considered can be traced without silently altering scores. Existing immutable score snapshots are unchanged.

The 2026 outlook is the forecast published with the 2025 report. Recheck it before current decisions. The local supplied feedback has no China verbatims and no verified feature-level finance inputs, so neither China demand nor feature profitability can be inferred from this report alone.
