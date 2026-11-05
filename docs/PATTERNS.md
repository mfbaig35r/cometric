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
