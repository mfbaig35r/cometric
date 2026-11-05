"""Generate the ALSP pack template and the worked patterns (docs/PATTERNS.md).

Expected figures are computed by hand here, independently of the engine, so the tests check it.
Run: uv run python scripts/build_alsp.py
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

from cometric.core.templates import COMMON_EXAMPLES, R, fill_template

ROOT = Path(__file__).resolve().parents[1] / "src" / "cometric"
TIERS = ["tier_1", "tier_2", "tier_3", "tier_4"]
RATES = {"tier_1": "4000", "tier_2": "2000", "tier_3": "1000", "tier_4": "500"}


def _comp(cid, method, basis, cadence, **kw):
    c = {
        "id": cid,
        "service_id": "service",
        "calculation_method": method,
        "billing_basis": basis,
        "charge_cadence": cadence,
        "currency": R,
        "quantity_source": None,
        "unit": None,
        "effective_period": {"from": R, "to": None},
        "depends_on": [],
    }
    c.update(kw)
    return c


def template() -> dict:
    units = [{"code": t, "kind": "COUNT", "counting_rule": R, "acceptance_rule": R} for t in TIERS]
    comps = [
        _comp(
            f"price_{t}",
            "UNIT_OUTPUT",
            "OUTPUT",
            "USAGE_TRIGGERED",
            quantity_source=f"scenario.{t}",
            unit=t,
            rate_schedule_id=f"rate_{t}",
        )
        for t in TIERS
    ]
    schedules = [
        {
            "id": f"rate_{t}",
            "currency": R,
            "unit": t,
            "tier_method": "MARGINAL",
            "tier_scope": "ALL_ELIGIBLE",
            "accumulation_period": "CONTRACT_YEAR",
            "tiers": [{"from": "0", "to": None, "rate": R}],
        }
        for t in TIERS
    ]
    engagement = {
        "schema_version": "0.2",
        "engagement_id": "ALSP-TIERED-MINIMUM",
        "name": R,
        "currency": R,
        "start_date": R,
        "end_date": R,
        "packs": [{"id": "alsp"}],
        "unit_definitions": units,
        "services": [{"id": "service", "unit_definition_id": "tier_1", "service_category": R}],
        "arrangement_versions": [
            {
                "id": "v1",
                "effective_from": R,
                "components": comps,
                "rate_schedules": schedules,
                "commitments": [
                    {
                        "id": "annual_minimum",
                        "kind": "MINIMUM_SPEND",
                        "amount": R,
                        "aggregation_scope": "ENGAGEMENT",
                        "accumulation_period": "CONTRACT_YEAR",
                        "tested_against": "GROSS",
                        "shortfall_rule": "PERIOD_END_TRUE_UP",
                        "termination_rule": R,
                    }
                ],
                "adjustments": [
                    {
                        "id": "discount_above_minimum",
                        "type": "DISCOUNT",
                        "applies_to": [f"price_{t}" for t in TIERS],
                        "percent": R,
                        "threshold": R,
                        "threshold_scope": "EXCESS_ONLY",
                        "accumulation_period": "CONTRACT_YEAR",
                    }
                ],
            }
        ],
        "client_value_unit": "+".join(TIERS),
        "delivery_plan": {"cost_components": []},
    }
    scenario = {
        "id": "base",
        "assumptions": [
            {"name": t, "value": R, "unit": t, "time_period": R, "origin": R} for t in TIERS
        ],
    }
    ex = dict(COMMON_EXAMPLES)
    ex.pop("/engagement/unit_definitions/0/counting_rule")
    ex.pop("/engagement/unit_definitions/0/acceptance_rule")
    ex.pop("/scenario/assumptions/0/time_period")
    ex.pop("/scenario/assumptions/0/origin")
    ex.update(
        {
            "/engagement/name": "Tiered contract review with an annual minimum",
            "/engagement/services/0/service_category": "CONTRACTS",
            "/engagement/arrangement_versions/0/commitments/0/amount": "3000000",
            "/engagement/arrangement_versions/0/commitments/0/termination_rule": "PRORATE",
            "/engagement/arrangement_versions/0/adjustments/0/percent": "0.10",
            "/engagement/arrangement_versions/0/adjustments/0/threshold": "3000000",
        }
    )
    volumes = {"tier_1": "600", "tier_2": "240", "tier_3": "720", "tier_4": "960"}
    for i, t in enumerate(TIERS):
        ex[f"/engagement/unit_definitions/{i}/counting_rule"] = (
            f"One completed {t.replace('_', ' ')} review of one eligible document, classified by the agreed complexity criteria"
        )
        ex[f"/engagement/unit_definitions/{i}/acceptance_rule"] = (
            "Accepted on client sign-off or 5 business days after delivery without rejection"
        )
        ex[f"/engagement/arrangement_versions/0/components/{i}/currency"] = "USD"
        ex[f"/engagement/arrangement_versions/0/components/{i}/effective_period/from"] = (
            "2027-01-01"
        )
        ex[f"/engagement/arrangement_versions/0/rate_schedules/{i}/currency"] = "USD"
        ex[f"/engagement/arrangement_versions/0/rate_schedules/{i}/tiers/0/rate"] = RATES[t]
        ex[f"/scenario/assumptions/{i}/value"] = volumes[t]
        ex[f"/scenario/assumptions/{i}/time_period"] = "2027"
        ex[f"/scenario/assumptions/{i}/origin"] = "ESTIMATED"
    return {
        "template_id": "tiered_units_annual_minimum",
        "description": "Per-unit prices for four complexity tiers, an annual minimum, and a discount on charges above the minimum (excess only). Set termination_rule for early-exit analysis.",
        "pack": "alsp",
        "engagement": engagement,
        "scenario": scenario,
        "examples": ex,
    }


def _scenario(sid: str, volumes: dict) -> dict:
    return {
        "id": sid,
        "assumptions": [
            {
                "name": t,
                "value": volumes[t],
                "unit": t,
                "time_period": "2027",
                "origin": "ILLUSTRATIVE",
            }
            for t in TIERS
        ],
    }


BASE = {"tier_1": "600", "tier_2": "240", "tier_3": "720", "tier_4": "960"}  # 50/20/60/80 a month
LOW = {"tier_1": "360", "tier_2": "120", "tier_3": "480", "tier_4": "600"}  # 30/10/40/50 a month


def _gross(vol: dict) -> int:
    return sum(int(vol[t]) * int(RATES[t]) for t in TIERS)


def patterns(t: dict) -> dict[str, dict]:
    filled = fill_template(t, t["examples"])["engagement"]
    out = {}

    # 1. tiered units, annual minimum, discount on the excess
    base_gross, low_gross = _gross(BASE), _gross(LOW)  # 4,080,000 and 2,460,000
    base_fee = base_gross - (base_gross - 3_000_000) // 10  # 10% off the excess
    out["pattern_tiered_minimum"] = {
        "case": "pattern_tiered_minimum",
        "title": "Tiered unit prices, annual minimum, 10% off charges above the minimum",
        "engagement": filled,
        "scenarios": [_scenario("low", LOW), _scenario("base", BASE)],
        "cost_policies": {},
        "expected": {
            "low": {
                "contractual_fee": "3000000",
                "commitment_shortfall": str(3_000_000 - low_gross),
            },
            "base": {"contractual_fee": str(base_fee), "commitment_shortfall": "0"},
        },
    }

    # 2. a transition fee that counts toward the first year's minimum
    e2 = copy.deepcopy(filled)
    e2["engagement_id"] = "PATTERN-TRANSITION-CREDIT"
    e2["arrangement_versions"][0]["components"].append(
        {
            "id": "transition_fee",
            "service_id": "service",
            "calculation_method": "FIXED_RECURRING",
            "billing_basis": "FIXED",
            "charge_cadence": "ONE_TIME",
            "currency": "USD",
            "quantity_source": None,
            "unit": None,
            "effective_period": {"from": "2027-01-01", "to": None},
            "depends_on": [],
            "fixed_amount": "200000",
        }
    )
    out["pattern_transition_credit"] = {
        "case": "pattern_transition_credit",
        "title": "A transition fee that counts toward the annual minimum (ENGAGEMENT-scope minimum); the discount applies to unit charges only",
        "engagement": e2,
        "scenarios": [_scenario("low", LOW), _scenario("base", BASE)],
        "cost_policies": {},
        "expected": {
            "low": {
                "contractual_fee": "3000000",
                "commitment_shortfall": str(3_000_000 - low_gross - 200_000),
            },
            "base": {"contractual_fee": str(base_fee + 200_000)},
        },
    }

    # 3. partial billing for work handed back part-way, and 4. cost from hours x blended rate
    single = {
        "schema_version": "0.2",
        "engagement_id": "PATTERN-PARTIAL-AND-HOURS",
        "currency": "USD",
        "start_date": "2027-01-01",
        "end_date": "2027-12-31",
        "packs": [{"id": "alsp"}],
        "unit_definitions": [
            {
                "code": "review",
                "kind": "COUNT",
                "counting_rule": "One completed review of one eligible contract",
                "acceptance_rule": "Client sign-off",
            },
            {
                "code": "returned_review",
                "kind": "COUNT",
                "counting_rule": "One review handed back part-way at the client's request",
                "acceptance_rule": "Client confirms the hand-back",
            },
        ],
        "services": [
            {"id": "service", "unit_definition_id": "review", "service_category": "CONTRACTS"}
        ],
        "arrangement_versions": [
            {
                "id": "v1",
                "effective_from": "2027-01-01",
                "components": [
                    {
                        "id": "reviews",
                        "service_id": "service",
                        "calculation_method": "UNIT_OUTPUT",
                        "billing_basis": "OUTPUT",
                        "charge_cadence": "USAGE_TRIGGERED",
                        "currency": "USD",
                        "quantity_source": "scenario.reviews",
                        "unit": "review",
                        "effective_period": {"from": "2027-01-01", "to": None},
                        "depends_on": [],
                        "rate_schedule_id": "review_rate",
                    },
                    {
                        "id": "returned",
                        "service_id": "service",
                        "calculation_method": "UNIT_OUTPUT",
                        "billing_basis": "OUTPUT",
                        "charge_cadence": "USAGE_TRIGGERED",
                        "currency": "USD",
                        "quantity_source": "scenario.returned",
                        "unit": "returned_review",
                        "effective_period": {"from": "2027-01-01", "to": None},
                        "depends_on": [],
                        "rate_schedule_id": "returned_rate",
                    },
                ],
                "rate_schedules": [
                    {
                        "id": "review_rate",
                        "currency": "USD",
                        "unit": "review",
                        "tier_method": "MARGINAL",
                        "tier_scope": "ALL_ELIGIBLE",
                        "accumulation_period": "MONTH",
                        "tiers": [{"from": "0", "to": None, "rate": "1000"}],
                    },
                    {
                        "id": "returned_rate",
                        "currency": "USD",
                        "unit": "returned_review",
                        "tier_method": "MARGINAL",
                        "tier_scope": "ALL_ELIGIBLE",
                        "accumulation_period": "MONTH",
                        "tiers": [{"from": "0", "to": None, "rate": "400"}],
                    },
                ],
            }
        ],
        "client_value_unit": "reviews",
        "delivery_plan": {
            "production_standards": [
                {"unit": "reviews", "hours_per_unit": "2.5"},
                {"unit": "returned", "hours_per_unit": "1"},
            ],
            "cost_components": [
                {
                    "id": "review_hours",
                    "category": "POOLED_LABOR",
                    "behavior": "VARIABLE",
                    "driver": "demand_hours",
                    "rate": "80",
                },
                {
                    "id": "account_management",
                    "category": "ENGAGEMENT_OVERHEAD",
                    "behavior": "FIXED",
                    "amount": "50000",
                    "period": "ANNUAL",
                },
            ],
        },
    }
    s3 = {
        "id": "base",
        "assumptions": [
            {
                "name": "reviews",
                "value": "1200",
                "unit": "review",
                "time_period": "2027",
                "origin": "ILLUSTRATIVE",
            },
            {
                "name": "returned",
                "value": "60",
                "unit": "returned_review",
                "time_period": "2027",
                "origin": "ILLUSTRATIVE",
            },
        ],
    }
    fee3 = 1200 * 1000 + 60 * 400  # 1,224,000
    hours = 1200 * 2.5 + 60 * 1  # 3,060 hours
    direct = int(hours * 80)  # 244,800
    out["pattern_partial_and_hours"] = {
        "case": "pattern_partial_and_hours",
        "title": "Partial billing for reviews handed back part-way (40% of the rate), and delivery cost from hours per unit x a blended rate",
        "engagement": single,
        "scenarios": [s3],
        "cost_policies": {"reference": "reference"},
        "expected": {
            "base": {
                "contractual_fee": str(fee3),
                "direct_delivery_cost": str(direct),
                "contribution_profit": str(fee3 - direct - 50_000),
            }
        },
    }

    # 5. early termination of the tiered minimum
    e5 = copy.deepcopy(filled)
    e5["engagement_id"] = "PATTERN-TERMINATION"
    e5["arrangement_versions"][0]["termination_fee"] = "100000"
    base9, low9 = base_gross * 9 // 12, low_gross * 9 // 12  # nine months of flat volumes
    prorated_minimum = 3_000_000 * 273 / 365  # Jan 1 to Sep 30
    low_shortfall = round(prorated_minimum - low9, 2)
    s_base, s_low = _scenario("base", BASE), _scenario("low", LOW)
    for s in (s_base, s_low):
        s["termination_date"] = "2027-09-30"
    out["pattern_termination"] = {
        "case": "pattern_termination",
        "title": "The tiered minimum terminated on 30 September: minimum prorated by days, 100,000 termination fee",
        "engagement": e5,
        "scenarios": [s_low, s_base],
        "cost_policies": {},
        "expected": {
            "low": {
                "contractual_fee": f"{low9 + low_shortfall + 100_000:.2f}",
                "commitment_shortfall": f"{low_shortfall:.2f}",
            },
            "base": {"contractual_fee": str(base9 - (base9 - 3_000_000) // 10 + 100_000)},
        },
    }
    # 6. counting rules: re-issues counted once, bundles billed once at the highest tier
    from decimal import Decimal as Dm

    e6 = copy.deepcopy(filled)
    e6["engagement_id"] = "PATTERN-COUNTING-RULES"
    monthly = {"tier_1": Dm(50), "tier_2": Dm(20), "tier_3": Dm(60), "tier_4": Dm(80)}
    reissue, share, per_bundle = Dm("0.05"), Dm("0.10"), Dm(4)
    unique = {t: v * (1 - reissue) for t, v in monthly.items()}
    bundled = {t: unique[t] * share for t in TIERS[:3]}
    billable = {t: unique[t] - bundled[t] for t in TIERS[:3]}
    billable["tier_4"] = unique["tier_4"] + sum(bundled.values()) / per_bundle
    month_fee = sum(billable[t] * Dm(RATES[t]) for t in TIERS)
    gross6 = month_fee * 12
    fee6 = gross6 - (gross6 - 3_000_000) * Dm("0.10")
    sub = {"submitted_" + t.split("_")[1]: str(int(v) * 12) for t, v in monthly.items()}
    assumptions = [
        {
            "name": n,
            "value": v,
            "unit": "tier_" + n.split("_")[1],
            "time_period": "2027",
            "origin": "ILLUSTRATIVE",
        }
        for n, v in sub.items()
    ]
    assumptions += [
        {
            "name": "reissue_rate",
            "value": "0.05",
            "unit": "ratio",
            "time_period": "TERM",
            "basis": "RATE",
            "origin": "ESTIMATED",
        },
        {
            "name": "bundle_share",
            "value": "0.10",
            "unit": "ratio",
            "time_period": "TERM",
            "basis": "RATE",
            "origin": "ESTIMATED",
        },
        {
            "name": "docs_per_bundle",
            "value": "4",
            "unit": "ratio",
            "time_period": "TERM",
            "basis": "RATE",
            "origin": "ESTIMATED",
        },
    ]
    derived = []
    for t in TIERS:
        k = t.split("_")[1]
        derived.append(
            {
                "name": f"unique_{k}",
                "unit": t,
                "rounding": "NONE",
                "description": "submitted less re-issues (re-issued documents are billed once)",
                "expression": {
                    "product": [
                        {"q": f"submitted_{k}"},
                        {"difference": [{"const": "1"}, {"q": "reissue_rate"}]},
                    ]
                },
            }
        )
    for t in TIERS[:3]:
        k = t.split("_")[1]
        derived.append(
            {
                "name": f"bundled_{k}",
                "unit": t,
                "rounding": "NONE",
                "description": "documents that arrive inside a bundle",
                "expression": {"product": [{"q": f"unique_{k}"}, {"q": "bundle_share"}]},
            }
        )
        derived.append(
            {
                "name": t,
                "unit": t,
                "rounding": "NONE",
                "description": "billable documents in this tier",
                "expression": {"difference": [{"q": f"unique_{k}"}, {"q": f"bundled_{k}"}]},
            }
        )
    derived.append(
        {
            "name": "bundles",
            "unit": "tier_4",
            "rounding": "NONE",
            "description": "bundles, each billed once at the highest tier",
            "expression": {
                "quotient": [
                    {"sum": [{"q": "bundled_1"}, {"q": "bundled_2"}, {"q": "bundled_3"}]},
                    {"q": "docs_per_bundle"},
                ]
            },
        }
    )
    derived.append(
        {
            "name": "tier_4",
            "unit": "tier_4",
            "rounding": "NONE",
            "description": "billable highest-tier documents plus bundles",
            "expression": {"sum": [{"q": "unique_4"}, {"q": "bundles"}]},
        }
    )
    out["pattern_counting_rules"] = {
        "case": "pattern_counting_rules",
        "title": "The tiered minimum with counting rules: 5% re-issues billed once; 10% of lower-tier documents arrive in bundles of 4, each billed once at the highest tier",
        "engagement": e6,
        "scenarios": [{"id": "base", "assumptions": assumptions, "derived": derived}],
        "cost_policies": {},
        "expected": {"base": {"contractual_fee": format(fee6, "f")}},
    }
    return out


def main() -> None:
    t = template()
    (ROOT / "packs" / "alsp" / "templates").mkdir(parents=True, exist_ok=True)
    (ROOT / "packs" / "alsp" / "templates" / "tiered_units_annual_minimum.json").write_text(
        json.dumps(t, indent=2) + "\n"
    )
    print("wrote template tiered_units_annual_minimum")
    for name, doc in patterns(t).items():
        (ROOT / "examples" / f"{name}.json").write_text(json.dumps(doc, indent=2) + "\n")
        print("wrote", name)


if __name__ == "__main__":
    main()
