# Commercial patterns

Worked engagements for structures that are common in managed legal services and easy to get wrong. Each file is in `src/cometric/examples/`, is served by the MCP server at `cometric://examples/<name>`, and is checked by the test suite against figures computed by hand in `scripts/build_alsp.py`.

The template behind patterns 1, 2, and 5 is `tiered_units_annual_minimum` in the ALSP pack:

```bash
cometric template tiered_units_annual_minimum --pack alsp
```

## 1. Tiered unit prices, an annual minimum, and a discount on the excess

`pattern_tiered_minimum`. Four complexity tiers priced per unit (4,000 / 2,000 / 1,000 / 500), an annual minimum of 3,000,000, and 10% off charges above the minimum.

- The minimum is a `MINIMUM_SPEND` commitment per `CONTRACT_YEAR`, trued up at year end.
- The discount is a `DISCOUNT` with `threshold` 3,000,000, `threshold_scope: EXCESS_ONLY`, and `applies_to` the four tier components. It starts in the month cumulative charges pass the minimum.
- `client_value_unit: "tier_1+tier_2+tier_3+tier_4"` makes the unit price an average over all tiers. Without it the unit price is not reported, because several units are priced.

| Scenario | Gross | Shortfall | Discount | Fee |
|---|---|---|---|---|
| low | 2,460,000 | 540,000 | 0 | 3,000,000 |
| base | 4,080,000 | 0 | 108,000 | 3,972,000 |

## 2. A transition fee that counts toward the minimum

`pattern_transition_credit`. Pattern 1 plus a one-time 200,000 transition fee in January. Because the minimum's `aggregation_scope` is `ENGAGEMENT`, the transition fee counts toward it; because the discount's `applies_to` lists only the tier components, the fee is not discounted and does not count toward the discount threshold.

| Scenario | Shortfall | Fee |
|---|---|---|
| low | 340,000 | 3,000,000 |
| base | 0 | 4,172,000 |

To keep a transition fee outside the minimum, give the minimum `aggregation_scope: COMPONENT` with the tier components.

## 3 and 4. Partial billing and cost from hours

`pattern_partial_and_hours`.

- **Partial billing:** reviews handed back part-way are their own unit (`returned_review`) with a component priced at 40% of the full rate. 1,200 reviews at 1,000 plus 60 returned at 400 gives 1,224,000.
- **Cost from hours:** `production_standards` set hours per unit (2.5 for a review, 1 for a returned one), which the engine turns into `demand_hours`. A `VARIABLE` cost on `demand_hours` at a blended 80 an hour gives 3,060 hours and 244,800 of delivery cost; with 50,000 of account management, contribution is 929,200.

## 5. Early termination

`pattern_termination`. Pattern 1 terminated on 30 September, with `termination_rule: PRORATE` and a 100,000 termination fee.

- Fees stop after September. Quantities declared for 2027 are still spread over the whole year, so nine months of volume are billed.
- `PRORATE` requires 3,000,000 × 273 / 365 = 2,243,835.62 for the nine months. The low scenario billed 1,845,000, so 398,835.62 is due; the base scenario billed more than the prorated minimum.
- The discount threshold is not prorated: in the base scenario, nine months of charges (3,060,000) pass the annual threshold by 60,000, so 6,000 of discount applies.
- The result's `termination` block reports months run, minimum charges, the termination fee, and any unamortized one-time cost written off.

| Scenario | Fee |
|---|---|
| low | 2,343,835.62 |
| base | 3,154,000 |

Other termination rules: `REMAINDER_DUE` charges this period's full minimum and every later period's; `WAIVED` charges none. Outcome fees and rebates whose period termination cuts short are not charged, with a `TERMINATED_MID_PERIOD` warning, because the contract decides what is owed.

## 6. Counting rules

`pattern_counting_rules`. Pattern 1's volumes with two counting rules, written as derived quantities so every assumption is visible:

- **Re-issues billed once:** a `RATE` assumption `reissue_rate` of 5%, and `unique_k = submitted_k x (1 - reissue_rate)` for each tier.
- **Bundles billed once at the highest tier:** `bundle_share` (10% of lower-tier documents arrive in bundles) and `docs_per_bundle` (4) as `RATE` assumptions. Each lower tier keeps `unique_k - bundled_k`; tier 4 gets `unique_4 + bundles`, where `bundles = (bundled_1 + bundled_2 + bundled_3) / docs_per_bundle`.

Monthly billable units become 42.75 / 17.1 / 51.3 / 79.0875 instead of 50 / 20 / 60 / 80, so the year bills 3,552,525 before the discount and 3,497,272.50 after it, against 3,972,000 without the rules. The counts are fractional expected values (`rounding: NONE`); use `HALF_UP`, `DOWN`, or `UP` to bill whole units each month.

Monthly totals cannot show which documents arrive together, so the bundle share and size are assumptions, not facts. Search them by adding a parameter such as `{"name": "reissue", "assumption": "reissue_rate", "values": ["0", "0.05", "0.10"]}`.

## 7. Starting from a deal profile

`quickstart("propose_structures")`. A contract-review deal: three complexity tiers, 400 to 1,500 requests a year (1,200 expected), a fixed team, a 24-month term the client can exit early, and the client wants budget certainty first and to pay for use second; the provider accepts at most a shared volume risk. The proposal lists four candidates:

| Candidate | Volume shortfall | Spend | Serves | Falls short on |
|---|---|---|---|---|
| Dedicated team priced per FTE (PM-004) | CLIENT | FIXED | budget certainty | pay for use |
| Fixed-fee managed service (PM-007) | CLIENT | FIXED | budget certainty | pay for use |
| Per-unit pricing with a minimum and an annual cap (PM-011 + CL-R01 + CL-V07) | SHARED | BOUNDED | both | |
| Volume-banded unit pricing with an annual cap (PM-014 + CL-V07) | SHARED | BOUNDED | both | |

Per-unit pricing alone is excluded because the provider would carry the whole shortfall. The fixed fee carries a validation approval: nothing bounds the provider's volume exposure. The minimum's label assumes it sits below expected spend, and the banded structure's assumes expected volume reaches the cheaper band. Expanding two candidates gives skeletons with identical scenarios (low, expected, high as term totals, tier shares as derived quantities, and an early-exit case); once their rates, minimum, cap, and costs are filled, `compare_arrangements` runs on them unchanged, and `derive_risk_exposure` confirms each shortfall label. The figures are the partner's; the tool supplies none.
