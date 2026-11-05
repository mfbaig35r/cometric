"""Fixes from the LLM-driven pricing analysis report: wrong-number risks and blank errors."""

import asyncio
import json

import pytest
from builders import comp, engagement, scen, schedule, unit
from conftest import D

from cometric import (
    calculate_periods,
    compare_arrangements,
    describe_schema,
    search_structures,
    validate_engagement,
)
from cometric.core.quickstart import payloads
from cometric.mcp.server import build_server

UNITS = [unit("A"), unit("B"), unit("C")]
COMPS = [
    comp(
        f"u{c}", "UNIT_OUTPUT", "OUTPUT", quantity_source=f"q{c}", unit=c, rate_schedule_id=f"r{c}"
    )
    for c in "ABC"
]
SCHEDS = [
    schedule(f"r{c}", unit_code=c, tiers=[{"from": "0", "to": None, "rate": r}])
    for c, r in zip("ABC", ["4000", "2000", "1000"], strict=True)
]
VOLUMES = scen(
    "s", [("qA", "500", "A", "2027"), ("qB", "250", "B", "2027"), ("qC", "750", "C", "2027")]
)


def _with(adjustment, **extra):
    return engagement(COMPS, units=UNITS, schedules=SCHEDS, adjustments=[adjustment], **extra)


@pytest.mark.parametrize(
    "typ,scope,fee",
    [
        ("DISCOUNT", "EXCESS_ONLY", "3175000"),
        ("DISCOUNT", "ENTIRE_SUBTOTAL", "2925000"),
        ("REBATE", "EXCESS_ONLY", "3175000"),
        ("REBATE", "ENTIRE_SUBTOTAL", "2925000"),
    ],
)
def test_case_a_threshold_scope(typ, scope, fee):
    adj = {
        "id": "d",
        "type": typ,
        "percent": "0.10",
        "threshold": "2500000",
        "threshold_scope": scope,
        "accumulation_period": "CONTRACT_YEAR",
    }
    r = calculate_periods(_with(adj), VOLUMES, detail="periods")
    assert D(r["term"]["contractual_fee"]) == D(fee)
    assert r["definitions"]["thresholds"][0]["scope"] == scope


def test_excess_discount_starts_in_the_crossing_month():
    adj = {
        "id": "d",
        "type": "DISCOUNT",
        "percent": "0.10",
        "threshold": "2500000",
        "threshold_scope": "EXCESS_ONLY",
        "accumulation_period": "CONTRACT_YEAR",
    }
    r = calculate_periods(_with(adj), VOLUMES, detail="line_items")
    months = sorted({li["period"] for li in r["line_items"]["fees"] if li["kind"] == "discount"})
    assert months == ["2027-10", "2027-11", "2027-12"]


def test_threshold_needs_scope_and_period():
    rep = validate_engagement(
        _with({"id": "d", "type": "DISCOUNT", "percent": "0.10", "threshold": "2500000"})
    )
    codes = {e["code"]: e for e in rep["errors"]}
    assert "THRESHOLD_SCOPE_REQUIRED" in codes and "example" in codes["THRESHOLD_SCOPE_REQUIRED"]
    assert "ACCUMULATION_PERIOD_REQUIRED" in codes
    cap = validate_engagement(_with({"id": "c", "type": "CAP", "amount": "100"}))
    assert "ACCUMULATION_PERIOD_REQUIRED" in {e["code"] for e in cap["errors"]}
    misplaced = validate_engagement(
        _with(
            {
                "id": "c",
                "type": "CAP",
                "amount": "100",
                "accumulation_period": "YEAR",
                "threshold": "5",
                "threshold_scope": "EXCESS_ONLY",
            }
        )
    )
    assert "FIELD_NOT_USED" in {e["code"] for e in misplaced["errors"]}


def test_case_b_unit_price_with_several_units():
    s = scen(
        "s", [("qA", "400", "A", "2027"), ("qB", "200", "B", "2027"), ("qC", "600", "C", "2027")]
    )
    r = calculate_periods(engagement(COMPS, units=UNITS, schedules=SCHEDS), s)
    assert r["term"]["effective_client_unit_price"] is None
    assert "AMBIGUOUS_UNIT_PRICE" in [w["code"] for w in r["issues"]["warnings"]]
    assert r["definitions"]["client_unit_price_basis"].startswith("not reported")
    summed = calculate_periods(
        engagement(COMPS, units=UNITS, schedules=SCHEDS, client_value_unit="qA+qB+qC"), s
    )
    assert D(summed["term"]["effective_client_unit_price"]).quantize(D("0.01")) == D("2166.67")
    assert "MIXED_UNITS_IN_PRICE" in [w["code"] for w in summed["issues"]["warnings"]]


def test_single_unit_engagements_keep_their_unit_price(case):
    c = case("a")
    r = calculate_periods(c["engagement"], c["scenarios"][0], "reference")
    assert D(r["term"]["effective_client_unit_price"]) == 200
    assert r["definitions"]["client_unit_price_basis"] == "units"


def test_case_c_candidates_accept_bare_engagements_and_explain_bad_ones(case):
    c = case("a")
    out = compare_arrangements([c["engagement"]], c["scenarios"], "reference")
    assert out["status"] == "ok" and out["candidates"][0]["id"] == "CASE-A"
    bad = compare_arrangements([{"oops": 1}], c["scenarios"], "reference")
    err = bad["issues"]["errors"][0]
    assert bad["status"] == "invalid" and err["path"] == "/candidates/0" and "example" in err


def test_case_d_constraint_op_alias_and_errors(case):
    c = case("a")
    spec = {
        "engagement": c["engagement"],
        "scenarios": c["scenarios"],
        "cost_policy": "reference",
        "parameters": [
            {
                "name": "base",
                "pointer": "/arrangement_versions/0/components/0/fixed_amount",
                "values": ["100000"],
            }
        ],
        "constraints": {"path": "scenarios.*.contribution_margin", "op": ">=", "value": "0.1"},
    }
    assert search_structures(spec)["status"] == "ok"
    spec["constraints"] = {"path": "scenarios.base.contribution_margin", "op": "~", "value": "1"}
    bad = search_structures(spec)
    assert bad["status"] == "invalid" and "lte" in bad["issues"]["errors"][0]["message"]
    missing = search_structures({"engagement": c["engagement"]})
    assert {e["path"] for e in missing["issues"]["errors"]} >= {"/scenarios", "/parameters"}


def test_new_schema_models():
    for model in ("candidate", "constraint", "paths", "actuals"):
        assert describe_schema(model)
    assert "threshold_scope" in json.dumps(describe_schema("adjustment"))
    assert "TOTAL" in json.dumps(describe_schema("assumption"))


def test_fractional_count_message():
    e = engagement(
        [
            comp(
                "u", "UNIT_OUTPUT", "OUTPUT", quantity_source="q", unit="unit", rate_schedule_id="r"
            )
        ],
        schedules=[schedule("r")],
    )
    r = calculate_periods(e, scen("s", [("q", "400.5", "unit", "2027")]))
    assert "whole-number total" in r["issues"]["errors"][0]["message"]


def test_no_blank_errors_through_mcp():
    srv = build_server()

    async def call(name, args):
        res = await srv.call_tool(name, args)
        return res.structured_content or json.loads(res.content[0].text)

    for name, args in [
        ("describe_schema", {"model": "parts"}),
        ("get_template", {"template_id": "zzz"}),
        ("lookup_concept", {"id_or_query": ""}),
        (
            "compare_arrangements",
            {"candidates": [1], "scenarios": [{"id": "x"}], "cost_policy": "reference"},
        ),
        ("search_structures", {"search_spec": {}}),
        ("quickstart", {"tool_name": "nope"}),
        ("calculate_periods", {"engagement": "no/such/file.json", "scenario": {"id": "s"}}),
    ]:
        out = asyncio.run(call(name, args))
        if "issues" in out and out["issues"].get("errors"):
            err = out["issues"]["errors"][0]
            assert err["code"] and err["message"], (name, out)


def test_every_quickstart_payload_runs_through_mcp():
    srv = build_server()

    async def call(name, args):
        res = await srv.call_tool(name, args)
        return res.structured_content or json.loads(res.content[0].text)

    for name, args in payloads().items():
        out = asyncio.run(call(name, args))
        ok = out.get("valid") is True or out.get("status") in ("ok", "reconciled")
        assert ok, (name, out.get("status"), out.get("issues"))
