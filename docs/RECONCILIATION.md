# Reconciling a real engagement (milestone M6)

Reconciliation checks Cometric's figures against what actually happened on a real engagement: what was invoiced, what was worked, and what it cost. It is the only evidence that the engine is right outside the illustrative casebook.

## What stays private and what is published

- **Private:** the engagement file, the scenario of actual quantities, the actuals, and the full reconciliation output. Keep them outside this repository.
- **Published:** only the `publishable_summary` from `cometric reconcile --summary-only`. Each entry carries a metric name, a month number (1, 2, 3, not a date), a relative difference, a direction, and the pricing mechanisms active that month. No amounts, dates, names, or identifiers. A test enforces this.

## What to gather

1. **Terms.** Fee structure from the engagement letter or SOW: fixed fee and payment schedule, rates by role, any cap, retainer and included hours, any success or gain-share terms (metric, baseline or target, share, attribution, cap).
2. **Actual quantities by month.** Hours worked by role; for outcome fees, the measured outcome; any units the fee depends on.
3. **Actuals by month** (any subset):

   | Metric | Meaning |
   |---|---|
   | `contractual_fee` | Invoiced fees for the month, before tax |
   | `outcome_fee` | Success or gain-share fee, if any |
   | `direct_delivery_cost` | Delivery labor and other direct cost under your cost policy |
   | `engagement_avoidable_cost` | Engagement-specific overhead |
   | `worked_hours` | Total hours worked |
   | `standard_value` | Hours valued at your standard rates |

4. **Standard rates by role**, if you want realization checked.
5. **A cost policy**: `reference`, or your own mapping of cost categories to margin layers.

## Steps

```bash
# 1. Start from the closest consulting template and fill it in (private folder)
cometric templates --pack consulting
cometric template phased_fixed_fee --pack consulting > engagement.json

# 2. Validate until clean
cometric validate engagement.json

# 3. Reconcile
cometric reconcile engagement.json --scenarios actual-quantities.json --cost-policy reference \
    --actuals actuals.json --tolerance-absolute 0.01

# 4. Publish only the summary
cometric reconcile engagement.json --scenarios actual-quantities.json --cost-policy reference \
    --actuals actuals.json --summary-only > discrepancies.json
```

`actuals.json`:

```json
{
  "periods": {
    "2027-03": {"contractual_fee": "150000", "worked_hours": "640"},
    "2027-07": {"contractual_fee": "250000", "worked_hours": "710"}
  },
  "term": {"contractual_fee": "600000"}
}
```

## Reading the result

- `reconciled`: every compared figure is within tolerance.
- `discrepancies`: each failing row shows the computed and actual figures and, for monthly rows, the fee line items Cometric produced that month, so the cause can be traced to a mechanism (fixed fee timing, overage, cap, outcome fee).
- Typical causes: invoice timing that differs from the contract schedule, write-offs or discounts not in the terms, hours recorded in a different month, or a contract term Cometric models differently. Each one is either an input correction, a documented limitation, or a defect to fix.
