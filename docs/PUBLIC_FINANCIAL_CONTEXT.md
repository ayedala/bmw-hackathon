# Public financial context for the 1, 5 and 7 Series

Checked 10 October 2026 against BMW's own publications. These are **context for
planning discussions**, not approved inputs to `runs/all-series-business-cases.json`.
They remain outside the NPV calculation until a reviewer supplies matching
model, market, powertrain, year and feature assumptions.

| Public fact | Source | Why it cannot fill a feature business case |
|---|---|---|
| 2025 worldwide BMW 1/2 Series deliveries: 214,175; 5/6 Series: 299,582; 7/8 Series: 53,399. | [BMW Group Report 2025, model-series delivery table](https://www.bmwgroup.com/en/report/2025/downloads/BMW-Group-Report-2025-en.pdf?page=305) | These are paired model families, all markets and powertrains. They do not isolate F70, G60 or G70, a planning market, or an addressable feature population. |
| 2025 Automotive revenue: EUR 117,557 million; cost of sales: EUR 103,206 million; gross profit: EUR 14,351 million. Automotive EBIT margin: 5.3%. | [BMW Group Report 2025, segment income statement](https://www.bmwgroup.com/en/report/2025/financial-statements/income-statement/index.html), [management report](https://www.bmwgroup.com/en/report/2025/management-report/index.html) | Segment totals include many products, services, channels and costs. Dividing by deliveries would not yield the contribution margin on one extra vehicle or one update. |
| 2025 BMW Group R&D expenditure: EUR 8,319 million. | [BMW Group Report 2025, financial performance](https://www.bmwgroup.com/en/report/2025/downloads/BMW-Group-Report-2025-en.pdf?page=310) | The amount spans the portfolio, including cross-series digitalisation and electrification. It cannot be allocated to a specific proposed update from the public report. |
| German 2026 example list prices: BMW 120 EUR 39,150; i5 eDrive40 EUR 70,900; 740 xDrive EUR 117,900, each shown including 19% VAT. | [BMW 120 model comparison](https://www.bmw.de/de/bmw-modelle-vergleichen.html/1/F70/81GE/S02TF/content.q), [BMW 5 Series price list](https://www.bmw.de/content/dam/bmw/marketDE/bmw_de/new-vehicles/pricelists/preisliste-bmw5er.pdf.coredownload.inline.pdf), [BMW 7 Series price list](https://www.bmw.de/content/dam/bmw/marketDE/bmw_de/new-vehicles/pricelists/preisliste-bmw7er.pdf.asset.1779886010896.pdf) | Retail list prices are for different variants in Germany. They include VAT, omit discounts and dealer terms, and are not BMW's net incremental revenue or contribution margin. They also do not match the US G60/G70 feedback scope. |

The supplied private sales workbook has F70, G60/G68 and G70 market-level
scenario rows. It is more relevant than the paired worldwide public totals for
scope discussions, but G60/G68 are combined and no powertrain split is supplied.
The workbook still does not estimate feature adoption or extra sales caused by
an update. The calculator displays imported sales rows as review context and
does not silently promote them to `baseline_units`.

No source above provides a defensible value for a particular update's upfront
development/tooling cost, annual support cost, per-equipped-vehicle cost,
incremental or retained sales, adoption rate, price uplift, contribution margin,
discount rate or capital budget. Those fields remain blank in the private
worksheet. Public figures can frame ranges for a *reviewed* planning workshop,
but using them directly would create a false financial ranking.
