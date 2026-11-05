"""Generate the consulting pack's engagement templates and the Case H example.

Run: uv run python scripts/build_consulting.py
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

from cometric.core.templates import COMMON_EXAMPLES, R, _base, _comp, _schedule

ROOT = Path(__file__).resolve().parents[1] / "src" / "cometric"
TEMPLATES = ROOT / "packs" / "consulting" / "templates"
EXAMPLES = ROOT / "examples"

RATE_CARD = [{"role": "partner", "rate": R}, {"role": "consultant", "rate": R}]
RATE_EXAMPLES = {
    "/engagement/delivery_plan/standard_rate_card/0/rate": "400",
    "/engagement/delivery_plan/standard_rate_card/1/rate": "175",
}


def _consulting(engagement: dict) -> dict:
    engagement["packs"] = [{"id": "consulting"}]
    engagement["services"][0]["service_category"] = R
    return engagement


def _worked_scenario(extra: list[dict] | None = None) -> dict:
    a = [
        {"name": "worked.partner", "value": R, "unit": "hours", "time_period": R, "origin": R},
        {"name": "worked.consultant", "value": R, "unit": "hours", "time_period": R, "origin": R},
    ]
    return {"id": "base", "assumptions": [*(extra or []), *a]}


def _examples(engagement: dict, scenario: dict, specific: dict, category: str) -> dict:
    ex = dict(COMMON_EXAMPLES)
    ex["/engagement/services/0/service_category"] = category
    for i, _c in enumerate(engagement["arrangement_versions"][0]["components"]):
        ex[f"/engagement/arrangement_versions/0/components/{i}/currency"] = "USD"
        ex[f"/engagement/arrangement_versions/0/components/{i}/effective_period/from"] = (
            "2027-01-01"
        )
    for i, _r in enumerate(engagement["arrangement_versions"][0]["rate_schedules"]):
        ex[f"/engagement/arrangement_versions/0/rate_schedules/{i}/currency"] = "USD"
    for i, a in enumerate(scenario["assumptions"]):
        ex[f"/scenario/assumptions/{i}/time_period"] = "TERM"
        ex[f"/scenario/assumptions/{i}/origin"] = "ESTIMATED"
        if a["name"] == "worked.partner":
            ex[f"/scenario/assumptions/{i}/value"] = "300"
        if a["name"] == "worked.consultant":
            ex[f"/scenario/assumptions/{i}/value"] = "1700"
    ex.update(specific)
    return ex


def _template(
    tid: str, description: str, engagement: dict, scenario: dict, specific: dict, category: str
) -> dict:
    return {
        "template_id": tid,
        "description": description,
        "pack": "consulting",
        "engagement": engagement,
        "scenario": scenario,
        "examples": _examples(engagement, scenario, specific, category),
    }


def templates() -> dict[str, dict]:
    out = {}

    # role-based time and materials
    e = _consulting(
        _base(
            "CONSULTING-TM",
            "hour",
            [
                _comp(
                    "time",
                    "TIME",
                    "TIME",
                    "MONTHLY",
                    quantity_source="scenario.worked",
                    role_rates=[{"role": "partner", "rate": R}, {"role": "consultant", "rate": R}],
                )
            ],
        )
    )
    e["unit_definitions"][0]["kind"] = "HOURS"
    e["delivery_plan"] = {
        "standard_rate_card": copy.deepcopy(RATE_CARD),
        "worked_hours_source": "worked",
        "cost_components": [],
    }
    s = _worked_scenario()
    out["role_based_tm"] = _template(
        "role_based_tm",
        "Hourly rates by role; realization compares billed rates with the standard rate card.",
        e,
        s,
        {
            "/engagement/arrangement_versions/0/components/0/role_rates/0/rate": "380",
            "/engagement/arrangement_versions/0/components/0/role_rates/1/rate": "165",
            **RATE_EXAMPLES,
        },
        "STRATEGY",
    )

    # capped time and materials
    e = copy.deepcopy(out["role_based_tm"]["engagement"])
    e["engagement_id"] = "CONSULTING-CAPPED-TM"
    e["arrangement_versions"][0]["adjustments"] = [
        {"id": "cap", "type": "CAP", "amount": R, "accumulation_period": "TERM"}
    ]
    out["capped_tm"] = _template(
        "capped_tm",
        "Hourly rates by role with a not-to-exceed amount over the term; the provider bears effort above the cap.",
        e,
        _worked_scenario(),
        {
            "/engagement/arrangement_versions/0/components/0/role_rates/0/rate": "380",
            "/engagement/arrangement_versions/0/components/0/role_rates/1/rate": "165",
            "/engagement/arrangement_versions/0/adjustments/0/amount": "350000",
            **RATE_EXAMPLES,
        },
        "TRANSFORMATION",
    )

    # phased fixed fee
    phases = [{"month": R, "amount": R} for _ in range(3)]
    e = _consulting(
        _base(
            "CONSULTING-PHASED",
            "accepted_deliverable",
            [
                _comp(
                    "phases",
                    "FIXED_PROJECT",
                    "FIXED",
                    "EVENT",
                    project_fee=R,
                    payment_schedule=phases,
                )
            ],
        )
    )
    e["delivery_plan"] = {
        "standard_rate_card": copy.deepcopy(RATE_CARD),
        "worked_hours_source": "worked",
        "cost_components": [],
    }
    out["phased_fixed_fee"] = _template(
        "phased_fixed_fee",
        "A fixed fee paid by phase; realization shows the write-down if hours run over.",
        e,
        _worked_scenario(),
        {
            "/engagement/arrangement_versions/0/components/0/project_fee": "600000",
            "/engagement/arrangement_versions/0/components/0/payment_schedule/0/month": "2027-03",
            "/engagement/arrangement_versions/0/components/0/payment_schedule/0/amount": "150000",
            "/engagement/arrangement_versions/0/components/0/payment_schedule/1/month": "2027-07",
            "/engagement/arrangement_versions/0/components/0/payment_schedule/1/amount": "250000",
            "/engagement/arrangement_versions/0/components/0/payment_schedule/2/month": "2027-12",
            "/engagement/arrangement_versions/0/components/0/payment_schedule/2/amount": "200000",
            **RATE_EXAMPLES,
        },
        "TRANSFORMATION",
    )

    # hours-drawdown retainer
    e = _consulting(
        _base(
            "CONSULTING-RETAINER",
            "hour",
            [
                _comp("retainer", "FIXED_RECURRING", "FIXED", "MONTHLY", fixed_amount=R),
                _comp(
                    "extra_hours",
                    "ALLOWANCE_OVERAGE",
                    "OUTPUT",
                    "MONTHLY",
                    quantity_source="scenario.hours",
                    unit="hour",
                    entitlement_id="included_hours",
                    rate_schedule_id="hourly",
                    depends_on=["included_hours"],
                ),
            ],
            entitlements=[
                {
                    "id": "included_hours",
                    "granted_by": "retainer",
                    "unit": "hour",
                    "included_quantity": R,
                    "accumulation_period": "MONTH",
                    "overage_recognition": "PER_SEGMENT",
                    "rollover": {"policy": "NEXT_PERIOD", "ceiling": R},
                }
            ],
            schedules=[_schedule("hourly", "hour")],
        )
    )
    e["unit_definitions"][0]["kind"] = "HOURS"
    s = {
        "id": "base",
        "assumptions": [
            {"name": "hours", "value": R, "unit": "hour", "time_period": R, "origin": R}
        ],
    }
    out["retainer_hours_drawdown"] = _template(
        "retainer_hours_drawdown",
        "Monthly retainer including hours, unused hours rolling forward up to a ceiling, extra hours at an hourly rate.",
        e,
        s,
        {
            "/engagement/arrangement_versions/0/components/0/fixed_amount": "20000",
            "/engagement/arrangement_versions/0/entitlements/0/included_quantity": "80",
            "/engagement/arrangement_versions/0/entitlements/0/rollover/ceiling": "20",
            "/engagement/arrangement_versions/0/rate_schedules/0/tiers/0/rate": "275",
            "/scenario/assumptions/0/value": "1100",
        },
        "ADVISORY_RETAINER",
    )

    # fixed fee plus success
    outcome = {
        "form": "SUCCESS",
        "metric": "annual_savings",
        "unit": "USD",
        "direction": "HIGHER_IS_BETTER",
        "target": R,
        "success_amount": R,
        "attribution_method": R,
        "accumulation_period": "YEAR",
        "recognition": "PERIOD_END",
        "approval_reference": None,
    }
    e = _consulting(
        _base(
            "CONSULTING-FIXED-SUCCESS",
            "accepted_deliverable",
            [
                _comp(
                    "project",
                    "FIXED_PROJECT",
                    "FIXED",
                    "EVENT",
                    project_fee=R,
                    payment_schedule=[{"month": R, "amount": R}],
                ),
                _comp("success", "OUTCOME_ADJUSTMENT", "OUTCOME", "EVENT", outcome=outcome),
            ],
        )
    )
    e["delivery_plan"] = {
        "standard_rate_card": copy.deepcopy(RATE_CARD),
        "worked_hours_source": "worked",
        "cost_components": [],
    }
    s = _worked_scenario(
        [{"name": "annual_savings", "value": R, "unit": "USD", "time_period": R, "origin": R}]
    )
    out["fixed_fee_plus_success"] = _template(
        "fixed_fee_plus_success",
        "Fixed project fee plus a success fee when a measured result meets its target; needs a target, attribution method, and recorded approval.",
        e,
        s,
        {
            "/engagement/arrangement_versions/0/components/0/project_fee": "400000",
            "/engagement/arrangement_versions/0/components/0/payment_schedule/0/month": "2027-06",
            "/engagement/arrangement_versions/0/components/0/payment_schedule/0/amount": "400000",
            "/engagement/arrangement_versions/0/components/1/outcome/target": "2000000",
            "/engagement/arrangement_versions/0/components/1/outcome/success_amount": "100000",
            "/engagement/arrangement_versions/0/components/1/outcome/attribution_method": "Savings measured against the agreed spend baseline by the client's finance team",
            "/scenario/assumptions/0/value": "2400000",
            **RATE_EXAMPLES,
        },
        "OPERATIONS_IMPROVEMENT",
    )
    return out


def case_h() -> dict:
    """Illustrative consulting engagement: phased fixed fee plus gain-share, with realization."""
    unit = {
        "code": "accepted_deliverable",
        "kind": "COUNT",
        "counting_rule": "One phase deliverable accepted against its criteria",
        "acceptance_rule": "Steering committee sign-off",
    }
    comps = [
        {
            "id": "phases",
            "service_id": "svc",
            "calculation_method": "FIXED_PROJECT",
            "billing_basis": "FIXED",
            "charge_cadence": "EVENT",
            "currency": "USD",
            "quantity_source": None,
            "unit": None,
            "effective_period": {"from": "2027-01-01", "to": None},
            "depends_on": [],
            "project_fee": "600000",
            "payment_schedule": [
                {"month": "2027-03", "amount": "150000"},
                {"month": "2027-07", "amount": "250000"},
                {"month": "2027-12", "amount": "200000"},
            ],
        },
        {
            "id": "gain_share",
            "service_id": "svc",
            "calculation_method": "OUTCOME_ADJUSTMENT",
            "billing_basis": "OUTCOME",
            "charge_cadence": "EVENT",
            "currency": "USD",
            "quantity_source": None,
            "unit": None,
            "effective_period": {"from": "2027-01-01", "to": None},
            "depends_on": [],
            "outcome": {
                "form": "SHARE",
                "metric": "addressable_spend",
                "unit": "USD",
                "direction": "LOWER_IS_BETTER",
                "baseline": "10000000",
                "share_percent": "0.10",
                "attribution_percent": "0.70",
                "attribution_method": "Spend against the agreed 2026 baseline, adjusted for volume",
                "cap_amount": "100000",
                "accumulation_period": "YEAR",
                "recognition": "PERIOD_END",
                "approval_reference": None,
            },
        },
    ]
    e = {
        "schema_version": "0.2",
        "engagement_id": "CASE-H",
        "name": "Procurement transformation with gain-share",
        "currency": "USD",
        "start_date": "2027-01-01",
        "end_date": "2027-12-31",
        "packs": [{"id": "consulting"}],
        "money_policy": {
            "rounding_mode": "HALF_UP",
            "rounding_scale": 2,
            "rounding_level": "LINE_ITEM",
        },
        "parties": [
            {"id": "client", "role": "CLIENT"},
            {"id": "provider", "role": "PROVIDER", "provider_type": "BOUTIQUE"},
        ],
        "unit_definitions": [unit],
        "services": [
            {
                "id": "svc",
                "unit_definition_id": "accepted_deliverable",
                "service_category": "TRANSFORMATION",
            }
        ],
        "arrangement_versions": [{"id": "v1", "effective_from": "2027-01-01", "components": comps}],
        "delivery_plan": {
            "standard_rate_card": [
                {"role": "partner", "rate": "400"},
                {"role": "consultant", "rate": "175"},
            ],
            "worked_hours_source": "worked",
            "cost_components": [
                {
                    "id": "team",
                    "category": "DEDICATED_LABOR",
                    "behavior": "VARIABLE",
                    "driver": "delivery_hours",
                    "rate": "90",
                    "origin": "ILLUSTRATIVE",
                },
                {
                    "id": "engagement_overhead",
                    "category": "ENGAGEMENT_OVERHEAD",
                    "behavior": "FIXED",
                    "amount": "30000",
                    "period": "TERM",
                    "origin": "ILLUSTRATIVE",
                },
            ],
        },
        "client_value_unit": "delivery_hours",
    }

    def scen(sid: str, spend: str) -> dict:
        a = [
            ("addressable_spend", spend, "USD"),
            ("delivery_hours", "4000", "hours"),
            ("worked.partner", "500", "hours"),
            ("worked.consultant", "3500", "hours"),
        ]
        return {
            "id": sid,
            "assumptions": [
                {"name": n, "value": v, "unit": u, "time_period": "TERM", "origin": "ILLUSTRATIVE"}
                for n, v, u in a
            ],
        }

    return {
        "case": "H",
        "title": "Consulting: phased fixed fee plus gain-share (illustrative, not from the research)",
        "engagement": e,
        "scenarios": [scen("low", "9900000"), scen("base", "9500000"), scen("high", "9000000")],
        "cost_policies": {"reference": "reference"},
        "expected": {
            "reference": {
                "low": {
                    "contractual_fee": "607000",
                    "outcome_fee": "7000",
                    "contribution_profit": "217000",
                },
                "base": {
                    "contractual_fee": "635000",
                    "outcome_fee": "35000",
                    "contribution_profit": "245000",
                },
                "high": {
                    "contractual_fee": "670000",
                    "outcome_fee": "70000",
                    "contribution_profit": "280000",
                },
            },
            "standard_value": "812500",
        },
    }


def main() -> None:
    TEMPLATES.mkdir(parents=True, exist_ok=True)
    for tid, t in templates().items():
        (TEMPLATES / f"{tid}.json").write_text(json.dumps(t, indent=2) + "\n")
        print("wrote template", tid)
    (EXAMPLES / "case_h.json").write_text(json.dumps(case_h(), indent=2) + "\n")
    print("wrote case_h.json")


if __name__ == "__main__":
    main()
