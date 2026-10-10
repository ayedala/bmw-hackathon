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

For a comparison spanning the 1, 5 and 7 Series, require a scoped case for each
model in both commands:

```powershell
python -m bmw_pm.cli run --profile configs/f70.json --provider baseline
python -m bmw_pm.cli run --profile configs/g70.json --provider baseline
python scripts/evaluate_business_cases.py --require-model F70 --require-model G60 --require-model G70 --template runs/all-series-business-cases.json
python scripts/evaluate_business_cases.py --require-model F70 --require-model G60 --require-model G70 --input runs/all-series-business-cases.json
```

Run the first two commands only after the supplied feedback has been ingested;
they create local baseline candidates and do not use a live LLM. Existing cards
are preserved by requirement ID. The final command will report missing inputs
until estimates are supplied.

The private database now has seven G60, six F70 and seven G70 baseline candidate
cards. They use separate vehicle profiles and evidence; none has PM or finance
approval. The required-model check stops a partial all-series comparison. A G60
case cannot stand in for another series. F70 cards leave country scope open
because that profile spans all supplied countries; the worksheet leaves their
`market` empty until a specific market and matching exposure estimate are
chosen and reviewed. For a F70 card with no country scope, set
`market_applicability_status` to `matched_reviewed` only after confirming that
the feature claim transfers to that market; otherwise it remains excluded.

BMW's public deliveries, segment accounts and German list prices were checked
for possible inputs. [PUBLIC_FINANCIAL_CONTEXT.md](PUBLIC_FINANCIAL_CONTEXT.md)
records the sourced figures and why none supplies feature development cost,
unit margin, adoption or causal sales lift. The worksheet therefore retains
unknowns rather than generating a financial order from these proxies.

An incomplete worksheet returns the missing JSON paths. The calculation reads
the active database without creating a PM decision or altering its scores. The
result includes a hash of each validated input, cash flow for each year,
discounted net present value (NPV) for downside/base/upside, and a break even
**flat incremental vehicle count per year** for the base case. Keep the input
file and output together if a reviewer relies on a result. The report also
lists potentially relevant imported sales rows and competitor candidates so
their exact model/market scope is visible; these rows are not silently used as
the plan's estimates.

The result also includes a driver sensitivity list. For each input, it swaps
that input's annual series (or upfront cost) from the supplied downside and
upside case into the base case while holding other base inputs fixed. The
largest absolute NPV change appears first. These are one-at-a-time diagnostics,
not independent forecasts; dependencies between assumptions can matter. The
standalone comparison also reports the NPV order under each whole scenario.

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

The calculator handles shared sales, mutually exclusive designs, dependencies
and a capital budget only when an optional reviewed `portfolio` block is
supplied. Example:

```json
"portfolio": {
  "schema_version": "1",
  "capital_budget": "10000000",
  "budget_review_status": "reviewed",
  "interaction_review_status": "reviewed_adjustments",
  "evidence_refs": ["internal:approved-capital-plan"],
  "dependencies": [{"selected": "requirement-a", "requires": "requirement-b"}],
  "mutually_exclusive": [],
  "interactions": [{
    "pair": {"first": "requirement-a", "second": "requirement-b"},
    "additional_upfront_cost": "0",
    "operating_npv_adjustment": {
      "downside": "-200000", "base": "-150000", "upside": "-100000"
    },
    "review_status": "reviewed",
    "evidence_refs": ["internal:shared-buyer-analysis"],
    "rationale": "Shared buyers reduce combined incremental sales."
  }]
}
```

These numbers are illustrative, not BMW estimates. Set
`interaction_review_status` to `reviewed_none` with no interactions only after
reviewing that no material pairwise overlap remains. Draft or unassessed status
yields no portfolio selection. `additional_upfront_cost` is signed: negative
means reviewed shared capital savings. Operating NPV adjustments exclude that
capital amount and must already be discounted to the same planning date,
currency and rate as the standalone cases. The calculator uses each option's
highest scenario upfront cost for budget enforcement, applies dependencies and
exclusions, and enumerates at most 15 commitment-ready options. It shows the
highest base NPV feasible subset and the best subset in each simultaneous
downside/upside stress view. Unreviewed or engineering-blocked options are
listed as excluded.

This bounded calculation cannot verify reviewer identity, estimate interactions,
infer retention or sales lift from feedback, or capture undeclared three-way
effects. PM and finance must review assumptions and competitor applicability;
the software cannot confer that approval.
