"""Generate the casebook fixtures (spec Appendix C) as JSON under src/cometric/examples/.

Run: uv run python scripts/build_fixtures.py
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "src" / "cometric" / "examples"
PERIOD = {"from": "2027-01-01", "to": None}
MONEY = {"rounding_mode": "HALF_UP", "rounding_scale": 2, "rounding_level": "LINE_ITEM"}

REFERENCE_MAPPING = {
    "DEDICATED_LABOR": "DIRECT_DELIVERY",
    "POOLED_LABOR": "DIRECT_DELIVERY",
    "DELIVERY_MANAGEMENT": "DIRECT_DELIVERY",
    "QA_REWORK": "DIRECT_DELIVERY",
    "AI_INFERENCE": "DIRECT_DELIVERY",
    "PLATFORM_OPERATIONS": "DIRECT_DELIVERY",
    "THIRD_PARTY": "DIRECT_DELIVERY",
    "CLIENT_IMPLEMENTATION": "ENGAGEMENT_AVOIDABLE",
    "TRANSITION": "ENGAGEMENT_AVOIDABLE",
    "ENGAGEMENT_OVERHEAD": "ENGAGEMENT_AVOIDABLE",
    "REUSABLE_ENGINEERING": "PORTFOLIO_SHARED",
    "IDLE_POOLED_CAPACITY": "PORTFOLIO_SHARED",
    "CORPORATE_OVERHEAD": "CORPORATE_OVERHEAD",
}


def policy(pid: str, overrides: dict | None = None) -> dict:
    mapping = dict(REFERENCE_MAPPING)
    mapping.update(overrides or {})
    return {
        "id": pid,
        "version": "1",
        "owner": "casebook",
        "mapping": mapping,
        "transition_view": "AMORTIZED",
    }


def engagement(
    eid: str,
    name: str,
    units: list[dict],
    components: list[dict],
    *,
    entitlements=None,
    schedules=None,
    costs=None,
    capacity=None,
    roles=None,
    breach=None,
    weight_tables=None,
    client_value_unit=None,
    demand_hours_source=None,
    risks=None,
) -> dict:
    e = {
        "schema_version": "0.2",
        "engagement_id": eid,
        "name": name,
        "currency": "USD",
        "start_date": "2027-01-01",
        "end_date": "2027-12-31",
        "money_policy": MONEY,
        "unit_definitions": units,
        "services": [{"id": "svc", "unit_definition_id": units[0]["code"]}],
        "arrangement_versions": [
            {
                "id": "v1",
                "effective_from": "2027-01-01",
                "components": components,
                "entitlements": entitlements or [],
                "rate_schedules": schedules or [],
            }
        ],
        "delivery_plan": {
            "breach_mode": breach,
            "capacity": capacity or [],
            "roles": roles or [],
            "demand_hours_source": demand_hours_source,
            "cost_components": costs or [],
        },
        "risk_allocations": risks or [],
    }
    if weight_tables:
        e["weight_tables"] = weight_tables
    if client_value_unit:
        e["client_value_unit"] = client_value_unit
    return e


def comp(cid: str, method: str, basis: str, cadence: str = "MONTHLY", **kw) -> dict:
    c = {
        "id": cid,
        "service_id": "svc",
        "calculation_method": method,
        "billing_basis": basis,
        "charge_cadence": cadence,
        "currency": "USD",
        "quantity_source": None,
        "unit": None,
        "effective_period": PERIOD,
        "depends_on": [],
    }
    c.update(kw)
    return c


def flat(rid: str, unit: str, rate: str) -> dict:
    return {
        "id": rid,
        "currency": "USD",
        "unit": unit,
        "tier_method": "MARGINAL",
        "tier_scope": "ALL_ELIGIBLE",
        "accumulation_period": "MONTH",
        "tiers": [{"from": "0", "to": None, "rate": rate}],
    }


def cost(cid: str, category: str, behavior: str, **kw) -> dict:
    c = {"id": cid, "category": category, "behavior": behavior, "origin": "ILLUSTRATIVE"}
    c.update(kw)
    return c


def scen(sid: str, assumptions: list[tuple[str, str, str]], **kw) -> dict:
    s = {
        "id": sid,
        "assumptions": [
            {"name": n, "value": v, "unit": u, "time_period": "TERM", "origin": "ILLUSTRATIVE"}
            for n, v, u in assumptions
        ],
    }
    s.update(kw)
    return s


COUNT = {"kind": "COUNT"}


def unit(code: str, rule: str, kind: str = "COUNT") -> dict:
    return {
        "code": code,
        "kind": kind,
        "counting_rule": rule,
        "acceptance_rule": "Accepted on client sign-off",
    }


def case_a(demand_high: str = "14000") -> dict:
    u = unit("unit", "One completed and accepted unit of the managed service")
    e = engagement(
        "CASE-A",
        "Annual managed-services commitment",
        [u],
        [
            comp("base", "FIXED_RECURRING", "FIXED", fixed_amount="100000"),
            comp(
                "overage",
                "ALLOWANCE_OVERAGE",
                "OUTPUT",
                quantity_source="scenario.units",
                unit="unit",
                entitlement_id="allowance",
                rate_schedule_id="overage_rate",
                depends_on=["allowance"],
            ),
        ],
        entitlements=[
            {
                "id": "allowance",
                "granted_by": "base",
                "unit": "unit",
                "included_quantity": "12000",
                "accumulation_period": "YEAR",
                "overage_recognition": "CUMULATIVE",
                "rollover": {"policy": "NONE"},
            }
        ],
        schedules=[flat("overage_rate", "unit", "120")],
        costs=[
            cost(
                "labor",
                "DEDICATED_LABOR",
                "FIXED",
                amount="540000",
                period="ANNUAL",
                avoidability="UNAVOIDABLE",
            ),
            cost("platform", "PLATFORM_OPERATIONS", "FIXED", amount="120000", period="ANNUAL"),
            cost("variable", "POOLED_LABOR", "VARIABLE", driver="units", rate="18"),
            cost("governance", "ENGAGEMENT_OVERHEAD", "FIXED", amount="60000", period="ANNUAL"),
            cost("transition", "TRANSITION", "ONE_TIME", amount="80000", amortize_months=12),
        ],
        capacity=[
            {
                "id": "annual_capacity",
                "quantity": "units",
                "amount": "14000",
                "accumulation_period": "YEAR",
                "overflow_cost_rate": "40",
                "overflow_replaces": ["variable"],
            }
        ],
        breach="OVERFLOW_COST",
        risks=[{"risk_type": "VOLUME", "declared_bearer": "SHARED", "driver": "units"}],
    )
    return {
        "case": "A",
        "title": "Annual managed-services commitment with included volume and overage",
        "engagement": e,
        "scenarios": [
            scen("low", [("units", "6000", "unit")]),
            scen("base", [("units", "10000", "unit")]),
            scen("high", [("units", demand_high, "unit")]),
        ],
        "cost_policies": {"as_published": policy("as_published"), "reference": policy("reference")},
        "expected": {
            "as_published": {
                "low": {
                    "contractual_fee": "1200000",
                    "direct_delivery_cost": "768000",
                    "gross_profit": "432000",
                    "contribution_profit": "292000",
                },
                "base": {
                    "contractual_fee": "1200000",
                    "direct_delivery_cost": "840000",
                    "gross_profit": "360000",
                    "contribution_profit": "220000",
                },
                "high": {
                    "contractual_fee": "1440000",
                    "direct_delivery_cost": "912000",
                    "gross_profit": "528000",
                    "contribution_profit": "388000",
                },
            },
            "margins": {
                "low": ["0.360", "0.243"],
                "base": ["0.300", "0.183"],
                "high": ["0.367", "0.269"],
            },
            "client_unit_price": {"low": "200", "base": "120"},
        },
    }


def case_b() -> dict:
    u = unit("contract", "One completed review of one eligible contract")
    e = engagement(
        "CASE-B",
        "Variable-volume contract review",
        [u],
        [
            comp(
                "per_contract",
                "UNIT_OUTPUT",
                "OUTPUT",
                cadence="USAGE_TRIGGERED",
                quantity_source="scenario.contracts",
                unit="contract",
                rate_schedule_id="unit_rate",
            )
        ],
        schedules=[flat("unit_rate", "contract", "95")],
        costs=[
            cost("unit_cost", "POOLED_LABOR", "VARIABLE", driver="contracts", rate="52"),
            cost("qa_platform", "QA_REWORK", "FIXED", amount="216000", period="ANNUAL"),
            cost("account_mgmt", "ENGAGEMENT_OVERHEAD", "FIXED", amount="60000", period="ANNUAL"),
        ],
    )
    return {
        "case": "B",
        "title": "Variable-volume contract review priced per contract",
        "engagement": e,
        "scenarios": [
            scen("low", [("contracts", "6000", "contract")]),
            scen("base", [("contracts", "12000", "contract")]),
            scen("high", [("contracts", "18000", "contract")]),
        ],
        "cost_policies": {"as_published": policy("as_published"), "reference": policy("reference")},
        "expected": {
            "as_published": {
                "low": {
                    "contractual_fee": "570000",
                    "direct_delivery_cost": "528000",
                    "contribution_profit": "-18000",
                },
                "base": {
                    "contractual_fee": "1140000",
                    "direct_delivery_cost": "840000",
                    "contribution_profit": "240000",
                },
                "high": {
                    "contractual_fee": "1710000",
                    "direct_delivery_cost": "1152000",
                    "contribution_profit": "498000",
                },
            },
            "break_even": {"driver": "contracts", "exact_prefix": "6418.6046", "whole": "6419"},
        },
    }


def case_c() -> dict:
    u = unit("fte_month", "One dedicated FTE for one month", kind="FTE_MONTHS")
    e = engagement(
        "CASE-C",
        "Dedicated legal-operations team priced per FTE",
        [u],
        [
            comp(
                "team",
                "DEDICATED_RESOURCE",
                "RESOURCE",
                resources=[{"role": "analyst", "fte": "8", "rate_per_fte_month": "16000"}],
            )
        ],
        costs=[
            cost(
                "labor",
                "DEDICATED_LABOR",
                "FIXED",
                amount="880000",
                period="ANNUAL",
                avoidability="UNAVOIDABLE",
            ),
            cost("delivery_mgmt", "DELIVERY_MANAGEMENT", "FIXED", amount="120000", period="ANNUAL"),
            cost(
                "platform_support", "PLATFORM_OPERATIONS", "FIXED", amount="60000", period="ANNUAL"
            ),
            cost("transition", "TRANSITION", "ONE_TIME", amount="40000", amortize_months=12),
        ],
        roles=[{"role": "analyst", "fte": "8", "available_hours_per_fte_year": "1600"}],
        client_value_unit="hours_used",
        demand_hours_source="hours_used",
        risks=[{"risk_type": "VOLUME", "declared_bearer": "CLIENT", "driver": "hours_used"}],
    )
    return {
        "case": "C",
        "title": "Dedicated team priced per FTE",
        "engagement": e,
        "scenarios": [
            scen("low", [("hours_used", "7040", "hours")]),
            scen("base", [("hours_used", "10240", "hours")]),
            scen("high", [("hours_used", "12160", "hours")]),
        ],
        "cost_policies": {
            "as_published": policy("as_published", {"PLATFORM_OPERATIONS": "ENGAGEMENT_AVOIDABLE"}),
            "reference": policy("reference"),
        },
        "expected": {
            "as_published": {
                s: {
                    "contractual_fee": "1536000",
                    "direct_delivery_cost": "1000000",
                    "gross_profit": "536000",
                    "contribution_profit": "436000",
                }
                for s in ("low", "base", "high")
            },
            "reference": {"base": {"gross_profit": "476000", "contribution_profit": "436000"}},
            "price_per_used_hour": {"low": "218.18", "base": "150.00", "high": "126.32"},
        },
    }


def case_d() -> dict:
    u = unit("project", "The migration project accepted as complete")
    schedule = [{"month": f"2027-{i:02d}", "amount": "75000"} for i in range(1, 13)]
    e = engagement(
        "CASE-D",
        "Fixed-fee CLM migration",
        [u],
        [
            comp(
                "project",
                "FIXED_PROJECT",
                "FIXED",
                cadence="EVENT",
                project_fee="900000",
                payment_schedule=schedule,
            )
        ],
        costs=[
            cost("delivery", "DEDICATED_LABOR", "VARIABLE", driver="delivery_hours", rate="80"),
            cost("licenses", "THIRD_PARTY", "FIXED", amount="100000", period="TERM"),
            cost("engagement_cost", "ENGAGEMENT_OVERHEAD", "FIXED", amount="50000", period="TERM"),
        ],
        client_value_unit="delivery_hours",
        risks=[{"risk_type": "EFFORT", "declared_bearer": "PROVIDER", "driver": "delivery_hours"}],
    )
    return {
        "case": "D",
        "title": "Fixed-fee migration project",
        "engagement": e,
        "scenarios": [
            scen("efficient", [("delivery_hours", "4000", "hours")]),
            scen("base", [("delivery_hours", "6000", "hours")]),
            scen("overrun", [("delivery_hours", "8500", "hours")]),
        ],
        "cost_policies": {"as_published": policy("as_published"), "reference": policy("reference")},
        "expected": {
            "as_published": {
                "efficient": {
                    "contractual_fee": "900000",
                    "direct_delivery_cost": "420000",
                    "contribution_profit": "430000",
                },
                "base": {
                    "contractual_fee": "900000",
                    "direct_delivery_cost": "580000",
                    "contribution_profit": "270000",
                },
                "overrun": {
                    "contractual_fee": "900000",
                    "direct_delivery_cost": "780000",
                    "contribution_profit": "70000",
                },
            },
            "break_even": {"driver": "delivery_hours", "exact_prefix": "9375", "whole": "9375"},
        },
    }


def case_e() -> dict:
    u = unit("document", "One reviewed document")
    e = engagement(
        "CASE-E",
        "AI-enabled document review",
        [u],
        [
            comp("platform_fee", "FIXED_RECURRING", "FIXED", fixed_amount="15000"),
            comp(
                "per_document",
                "UNIT_OUTPUT",
                "OUTPUT",
                cadence="USAGE_TRIGGERED",
                quantity_source="scenario.documents",
                unit="document",
                rate_schedule_id="doc_rate",
            ),
        ],
        schedules=[flat("doc_rate", "document", "25")],
        costs=[
            cost("platform_ops", "PLATFORM_OPERATIONS", "FIXED", amount="120000", period="ANNUAL"),
            cost("inference", "AI_INFERENCE", "VARIABLE", driver="documents", rate="1.50"),
            cost(
                "qa",
                "QA_REWORK",
                "TIERED_VARIABLE",
                driver="documents",
                accumulation_period="YEAR",
                tiers=[
                    {"from": "0", "to": "10000", "rate": "8"},
                    {"from": "10000", "to": "30000", "rate": "6"},
                    {"from": "30000", "to": None, "rate": "4"},
                ],
            ),
            cost("engineering", "REUSABLE_ENGINEERING", "FIXED", amount="100000", period="ANNUAL"),
        ],
    )
    return {
        "case": "E",
        "title": "AI-enabled review with declining marginal QA cost",
        "engagement": e,
        "scenarios": [
            scen("low", [("documents", "10000", "document")]),
            scen("base", [("documents", "25000", "document")]),
            scen("high", [("documents", "50000", "document")]),
        ],
        "cost_policies": {
            "as_published": policy(
                "as_published", {"REUSABLE_ENGINEERING": "ENGAGEMENT_AVOIDABLE"}
            ),
            "reference": policy("reference"),
        },
        "expected": {
            "as_published": {
                "low": {
                    "contractual_fee": "430000",
                    "direct_delivery_cost": "215000",
                    "contribution_profit": "115000",
                },
                "base": {
                    "contractual_fee": "805000",
                    "direct_delivery_cost": "327500",
                    "contribution_profit": "377500",
                },
                "high": {
                    "contractual_fee": "1430000",
                    "direct_delivery_cost": "475000",
                    "contribution_profit": "855000",
                },
            },
            "reference": {"low": {"contribution_profit": "215000"}},
            "break_even": {"driver": "documents", "exact_prefix": "2580.645", "whole": "2581"},
        },
    }


def case_f() -> dict:
    raw = unit("item", "One completed item of work, classified into a complexity band")
    e = engagement(
        "CASE-F",
        "Recurring base plus complexity-weighted volume",
        [
            raw,
            {
                "code": "weighted_item",
                "kind": "WEIGHTED",
                "counting_rule": "Raw items multiplied by band weight",
            },
        ],
        [
            comp("base", "FIXED_RECURRING", "FIXED", fixed_amount="25000"),
            comp(
                "weighted",
                "WEIGHTED_UNIT_OUTPUT",
                "OUTPUT",
                cadence="USAGE_TRIGGERED",
                quantity_source="scenario.items",
                unit="weighted_item",
                rate_schedule_id="wu_rate",
                weight_table_id="complexity",
            ),
        ],
        schedules=[flat("wu_rate", "weighted_item", "70")],
        weight_tables=[
            {
                "id": "complexity",
                "raw_unit": "item",
                "weighted_unit": "weighted_item",
                "classification_authority": "JOINT",
                "bands": [
                    {"code": "standard", "weight": "1.0"},
                    {"code": "medium", "weight": "1.8"},
                    {"code": "complex", "weight": "3.0"},
                ],
            }
        ],
        costs=[
            cost("fixed_direct", "DEDICATED_LABOR", "FIXED", amount="270000", period="ANNUAL"),
            cost(
                "variable",
                "POOLED_LABOR",
                "VARIABLE",
                driver="weighted:items:complexity",
                rate="35",
            ),
            cost("transition", "TRANSITION", "ONE_TIME", amount="40000", amortize_months=12),
        ],
    )

    def mix(total: int, s: int, md: int, c: int) -> list[tuple[str, str, str]]:
        return [
            ("items.standard", str(total * s // 100), "item"),
            ("items.medium", str(total * md // 100), "item"),
            ("items.complex", str(total * c // 100), "item"),
        ]

    return {
        "case": "F",
        "title": "Base plus complexity-weighted volume",
        "engagement": e,
        "scenarios": [
            scen("low", mix(5000, 70, 20, 10)),
            scen("base", mix(10000, 60, 25, 15)),
            scen("high", mix(16000, 50, 30, 20)),
        ],
        "cost_policies": {"as_published": policy("as_published"), "reference": policy("reference")},
        "expected": {
            "as_published": {
                "low": {
                    "contractual_fee": "776000",
                    "direct_delivery_cost": "508000",
                    "contribution_profit": "228000",
                },
                "base": {
                    "contractual_fee": "1350000",
                    "direct_delivery_cost": "795000",
                    "contribution_profit": "515000",
                },
                "high": {
                    "contractual_fee": "2136800",
                    "direct_delivery_cost": "1188400",
                    "contribution_profit": "908400",
                },
            },
            "weighted_units": {"low": "6800", "base": "15000", "high": "26240"},
        },
    }


def case_g() -> dict:
    a = case_a()
    g = copy.deepcopy(a)
    g["case"] = "G"
    g["title"] = "Capacity breach (Case A at 16,000 units)"
    g["engagement"]["engagement_id"] = "CASE-G"
    g["scenarios"] = [scen("breach", [("units", "16000", "unit")])]
    g["expected"] = {
        "as_published": {
            "breach": {
                "contractual_fee": "1680000",
                "direct_delivery_cost": "992000",
                "gross_profit": "688000",
                "contribution_profit": "548000",
            }
        },
        "overflow_months": ["2027-11", "2027-12"],
    }
    return g


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for fn in (case_a, case_b, case_c, case_d, case_e, case_f, case_g):
        data = fn()
        path = OUT / f"case_{data['case'].lower()}.json"
        path.write_text(json.dumps(data, indent=2) + "\n")
        print("wrote", path.name)


if __name__ == "__main__":
    main()
