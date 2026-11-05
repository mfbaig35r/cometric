"""Minimal valid inputs for every operation (tested), plus the conventions an agent needs."""

from __future__ import annotations

import copy
import json
from pathlib import Path

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def _engagement() -> dict:
    """The spec 8.2 example plus a small cost section, so margins and comparisons work."""
    e = json.loads((EXAMPLES / "spec_example.json").read_text())["engagement"]
    e["delivery_plan"] = {
        "cost_components": [
            {
                "id": "team",
                "category": "DEDICATED_LABOR",
                "behavior": "FIXED",
                "amount": "40000",
                "period": "MONTHLY",
            },
            {
                "id": "per_review",
                "category": "POOLED_LABOR",
                "behavior": "VARIABLE",
                "driver": "accepted_units",
                "rate": "40",
            },
        ]
    }
    return e


def _scenario(sid: str, units: str) -> dict:
    return {
        "id": sid,
        "assumptions": [
            {
                "name": "accepted_units",
                "value": units,
                "unit": "accepted_contract_review",
                "time_period": "TERM",
                "origin": "ESTIMATED",
            }
        ],
    }


CONVENTIONS = {
    "no_arithmetic": "Never compute commercial figures yourself; quote what the tools return.",
    "decimals": 'Money, rates, and quantities are decimal strings ("120.00"); JSON floats are rejected.',
    "quantities": "Assumption values are totals for their time_period: YYYY-MM is one month; YYYY, ranges, and TERM spread the total evenly (whole units for COUNT units).",
    "cost_policy": 'Pass "reference" for the shipped cost policy, or your own mapping. Without one, costs and margins are not computed (null, never zero).',
    "references": "describe_schema('paths') lists how quantities, constraint paths, rule paths, search pointers, and error paths are written.",
    "by_reference": 'On the stdio server with COMETRIC_ALLOWED_ROOT, pass a file path instead of an engagement object to save context, e.g. "src/cometric/examples/case_a.json".',
    "errors": "Every error has a code, a JSON Pointer path into your arguments, and often an example. Fix the field at the path and retry.",
    "results": "Read result['definitions'] before quoting a unit price or a threshold effect; recommendations need human review.",
}


def payloads() -> dict[str, dict]:
    e = _engagement()
    base, low, high = (
        _scenario("base", "12000"),
        _scenario("low", "9000"),
        _scenario("high", "15000"),
    )
    alt = copy.deepcopy(e)
    alt["engagement_id"] = "EX-ALT"
    alt["arrangement_versions"][0]["components"][0]["fixed_amount"] = "90000"
    alt["arrangement_versions"][0]["rate_schedules"][0]["tiers"][0]["rate"] = "140.00"
    return {
        "validate_engagement": {"engagement": e},
        "calculate_periods": {
            "engagement": e,
            "scenario": base,
            "cost_policy": "reference",
            "detail": "summary",
        },
        "explain_fee": {
            "engagement": e,
            "scenario": base,
            "cost_policy": "reference",
            "period": "2027-01",
        },
        "compare_arrangements": {
            "candidates": [
                {"id": "current", "engagement": e},
                {"id": "lower_base", "engagement": alt},
            ],
            "scenarios": [low, base, high],
            "cost_policy": "reference",
        },
        "search_structures": {
            "search_spec": {
                "engagement": e,
                "scenarios": [low, base, high],
                "cost_policy": "reference",
                "parameters": [
                    {
                        "name": "base_fee",
                        "pointer": "/arrangement_versions/0/components/0/fixed_amount",
                        "values": ["90000", "100000"],
                    },
                    {
                        "name": "overage_rate",
                        "pointer": "/arrangement_versions/0/rate_schedules/0/tiers/0/rate",
                        "values": ["110", "130"],
                    },
                ],
                "constraints": {"not": {"path": "scenarios.*.contribution_margin", "lt": "0.10"}},
                "objective": {
                    "metric": "contribution_profit",
                    "sense": "max",
                    "aggregation": "WORST",
                    "tie_breakers": [
                        {"metric": "contribution_profit", "sense": "max", "aggregation": "MEAN"}
                    ],
                },
            }
        },
        "price_floor": {
            "engagement": e,
            "scenarios": [base],
            "cost_policy": "reference",
            "target_margin": "0.20",
        },
        "break_even": {
            "engagement": e,
            "scenario": base,
            "cost_policy": "reference",
            "driver": "accepted_units",
        },
        "reconcile": {
            "engagement": e,
            "scenario": base,
            "cost_policy": "reference",
            "actuals": {
                "periods": {"2027-01": {"contractual_fee": "100000"}},
                "term": {"contractual_fee": "1200000"},
            },
        },
        "check_commercial_constraints": {"engagement": e},
    }


NOTES = {
    "search_dry_run": 'Add "dry_run": true to a search_spec to get grid size, calculation count, and estimated time; show it to the user before the real run.',
    "search_linked_parameters": 'One parameter can write several places: {"name": "uplift", "pointers": [p1, p2], "transform": "scale", "values": ["0", "0.05"]} applies base x (1 + uplift) at each pointer.',
    "detail_and_precision": "compare_arrangements and search_structures default to detail=summary and precision=display; ask for detail=full or precision=exact only when needed.",
    "derive_risk_exposure": 'Pass the list of calculate_periods results for low/base/high scenarios: {"results": [r_low, r_base, r_high], "base_scenario_id": "base", "tolerance_policy": {"provider_relative": "0", "client_relative": "0"}}.',
    "lookup_concept": '{"id_or_query": "PM-023"} or a phrase such as {"id_or_query": "take-or-pay"}.',
    "get_template": '{"template_id": "base_plus_overage"}; pack templates: {"template_id": "phased_fixed_fee", "pack": "consulting"}.',
}


def quickstart(tool: str | None = None) -> dict:
    p = payloads()
    if tool is None:
        return {
            "conventions": CONVENTIONS,
            "tools_with_examples": sorted(p),
            "notes": NOTES,
            "next": "Call quickstart(tool) for a complete, runnable argument object for that tool.",
        }
    if tool in p:
        return {"tool": tool, "arguments": p[tool], "conventions": CONVENTIONS}
    if tool in NOTES:
        return {"tool": tool, "how": NOTES[tool], "conventions": CONVENTIONS}
    raise KeyError(f"no quickstart for {tool!r}; available: {sorted([*p, *NOTES])}")
