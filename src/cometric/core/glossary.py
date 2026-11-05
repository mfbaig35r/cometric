"""Plain-language definitions of the key output terms (served by the MCP glossary resource)."""

GLOSSARY = {
    "contractual_fee": "Contractual consideration computed under the arrangement for a period. Not recognized revenue.",
    "gross_profit": "contractual_fee minus DIRECT_DELIVERY costs.",
    "contribution_profit": "gross_profit minus ENGAGEMENT_AVOIDABLE costs. Layers partition costs, so nothing is subtracted twice.",
    "margin": "(price - cost) / price. Not the same as markup, (price - cost) / cost.",
    "accumulation_period": "The period over which an allowance, minimum, tier counter, or capacity limit accumulates: MONTH, QUARTER, YEAR, CONTRACT_YEAR, TERM.",
    "recognition": "When an accumulated effect is charged: CUMULATIVE (the month the threshold is crossed), PERIOD_END (true-up in the final month), PER_SEGMENT (monthly only).",
    "margin_layer": "DIRECT_DELIVERY, ENGAGEMENT_AVOIDABLE, PORTFOLIO_SHARED, CORPORATE_OVERHEAD. A cost policy maps every cost category to exactly one layer.",
    "cost_policy": "Mapping from cost category to margin layer plus the transition-cost view. 'reference' is shipped and must be named explicitly.",
    "dominance": "Candidate X dominates Y when X is at least as good on every comparison metric and strictly better on one.",
    "derived_bearer": "Who absorbs a deviation from the base scenario: PROVIDER (contribution falls), CLIENT (unit price rises), SHARED, or NONE_ADVERSE.",
    "realization": "contractual_fee / standard_value, where standard_value is hours worked at the delivery plan's standard rate card. Below 1 is a write-down.",
    "outcome_fee": "Fee from an OUTCOME_ADJUSTMENT component, measured over its accumulation period and charged at period end: SHARE of improvement against a baseline, SUCCESS amount at a target, or PERCENT_OF_OUTCOME. Needs attribution, a cap, and recorded approval.",
    "price_floor": "(DIRECT_DELIVERY + ENGAGEMENT_AVOIDABLE costs + risk premium) / (1 - target margin). A decision formula, not a benchmark.",
    "evidence_class": "A_DIRECT, B_CORROBORATED, C_INFERENCE, D_PROPOSED. Independent of prevalence.",
    "origin": "Every assumption is OBSERVED, CONTRACTED, ESTIMATED, ILLUSTRATIVE, or INTERNAL_POLICY.",
}
