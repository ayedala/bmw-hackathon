# Financial scenarios for proposed vehicle updates

The decision workbench now has a separate, deterministic scenario calculator in
`src/bmw_pm/decision/economics.py`. It compares **conditional, standalone** update
cases. It does not turn comment frequency into sales lift, certify engineering
feasibility, or pick a vehicle portfolio on its own.

## Prepare a private worksheet

From the repository root, with project dependencies installed:

```powershell
$env:PYTHONPATH = 'src'
python scripts/evaluate_business_cases.py --template runs/business-cases.json
```

The command makes one blank option per current requirement revision. The file is
ignored by Git. It will not overwrite an existing worksheet. Fill all `null`
fields for one or more options; delete the other options until their estimates
are available. Then run:

```powershell
python scripts/evaluate_business_cases.py --input runs/business-cases.json
```

An incomplete worksheet returns the missing JSON paths. The calculation reads
the active database without creating a PM decision or altering its scores. The
result includes a hash of each validated input, cash flow for each year,
discounted net present value (NPV) for downside/base/upside, and a break even
**flat incremental vehicle count per year** for the base case. Keep the input
file and output together if a reviewer relies on a result. The report also
lists potentially relevant imported sales rows and competitor candidates so
their exact model/market scope is visible; these rows are not silently used as
the plan's estimates.

## Inputs the company needs to provide

For each proposed update, identify its exact requirement revision and a model,
market and powertrain scope. Use one currency and discount rate, an upfront
engineering/tooling cost, and a set of planning years. For every year and case:

| Field | Meaning |
|---|---|
| `baseline_units` | Vehicle units expected without the update, in this exact scope |
| `incremental_units` | Additional vehicle units attributable to this update; an estimate, never inferred from feedback counts |
| `adoption_rate` | Share of baseline and incremental units receiving the update, from 0 to 1 |
| `net_revenue_per_incremental_vehicle` | Company revenue from an extra vehicle after discounts, before vehicle costs |
| `baseline_vehicle_cost_per_incremental_vehicle` | Production/sales cost of that extra vehicle before update-specific cost |
| `net_revenue_uplift_per_existing_adopter` | Added company revenue on existing baseline sales, such as a net price/take-rate effect |
| `variable_cost_per_adopter` | Update-specific cost per equipped vehicle |
| `annual_fixed_cost` | Ongoing support, licensing or other annual fixed expense |

All monetary fields are in the declared currency. Enter a real zero when a
channel does not apply; leave it `null` until an estimate is available. The
three cases must span the same years. Provide source references and assumptions
for the estimates. `finance_status`, `sales_scope_status`, and
`competitor_status` describe human review, not facts verified by the JSON file.

The annual calculation is:

```
incremental vehicle revenue
+ existing baseline adopters' revenue uplift
- baseline production/sales cost of the incremental vehicles
- update-specific cost on all adopters
- annual fixed cost
```

NPV subtracts upfront cost and discounts each annual cash flow, with the first
year at time 1. Break even reports the minimum *equal number of incremental
vehicles in every year* that would make base-case NPV nonnegative, replacing
the base case's entered incremental-unit series. It is `null` if an extra unit
has no positive net contribution. This is a sensitivity measure, not a sales
prediction.

## Evidence and decision gates

The saved G60/G68 sales figures are combined; they do not establish G60-only or
BEV-only exposure. Imported competitor cohorts are candidates, and the current
external claims are unassessed. In particular, the current US G60 cards do not
have a reviewed, matched US competitor cohort. A case with a combined sales
proxy, unreviewed competitor comparison, draft finance inputs or absent source
references remains **excluded from the comparison order**. Scenario cash flows
are still shown so reviewers can see the effect of each assumption. Unknown
engineering feasibility separately blocks `ready_for_commitment`; finance can
still compare conditional business cases while engineering reviews them.

Only cases with all gates cleared enter the financial comparison. Different
currencies, discount rates or planning years cannot be compared directly. Base NPV controls
display order; a pair is resolved only if one case's downside NPV exceeds the
other's upside NPV. Overlapping cases stay unresolved. The output also shows the
existing exploratory customer-value interval separately. A higher NPV does not
cancel a severe customer need, regulatory constraint or product objective.

This calculator does not yet model shared sales between two updates, mutually
exclusive designs, dependencies, a capital budget, or uncertainty in the
underlying forecasts. Those are required before calling the highest standalone
NPV the best portfolio choice. PM and finance must review the assumptions and
competitor applicability; the software cannot confer that approval.
