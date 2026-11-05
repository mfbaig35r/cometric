"""Counting rules via RATE assumptions and derived quantities (spec V3-30)."""

import copy
import json
from pathlib import Path

import pytest
from builders import comp, engagement, scen, schedule
from conftest import D

from cometric import calculate_periods, search_structures

EXAMPLES = Path(__file__).resolve().parents[1] / "src" / "cometric" / "examples"


def _eng():
    return engagement(
        [
            comp(
                "u",
                "UNIT_OUTPUT",
                "OUTPUT",
                "USAGE_TRIGGERED",
                quantity_source="billable",
                unit="unit",
                rate_schedule_id="r",
            )
        ],
        schedules=[schedule("r", tiers=[{"from": "0", "to": None, "rate": "100"}])],
    )


def _scen(derived, extra=()):
    s = scen("s", [("submitted", "1200", "unit", "2027"), *extra])
    s["assumptions"].append(
        {
            "name": "reissue_rate",
            "value": "0.05",
            "unit": "ratio",
            "time_period": "TERM",
            "basis": "RATE",
            "origin": "ESTIMATED",
        }
    )
    s["derived"] = derived
    return s


BILLABLE = {
    "name": "billable",
    "unit": "unit",
    "rounding": "NONE",
    "expression": {
        "product": [{"q": "submitted"}, {"difference": [{"const": "1"}, {"q": "reissue_rate"}]}]
    },
}


def test_rate_applies_every_month_and_derived_prices():
    r = calculate_periods(_eng(), _scen([BILLABLE]), detail="periods")
    assert all(D(p["contractual_fee"]) == D("9500") for p in r["periods"])  # 100 x 0.95 x 100
    assert D(r["term"]["contractual_fee"]) == 114000
    assert r["definitions"]["rate_assumptions"] == ["reissue_rate"]
    assert (
        r["definitions"]["derived_quantities"][0]["formula"] == "(submitted x (1 - reissue_rate))"
    )


def test_rounding_rules():
    s = _scen(
        [
            {
                **BILLABLE,
                "rounding": "DOWN",
                "expression": {"product": [{"q": "submitted"}, {"const": "0.333"}]},
            }
        ]
    )
    r = calculate_periods(_eng(), s, detail="periods")
    assert D(r["periods"][0]["contractual_fee"]) == 3300  # floor(100 x 0.333) = 33 units
    missing = calculate_periods(
        _eng(), _scen([{k: v for k, v in BILLABLE.items() if k != "rounding"}])
    )
    assert missing["issues"]["errors"][0]["code"] == "ROUNDING_REQUIRED"


@pytest.mark.parametrize(
    "derived,code",
    [
        ([{**BILLABLE, "expression": {"power": [1, 2]}}], "BAD_EXPRESSION"),
        ([{**BILLABLE, "expression": {"q": "nope"}}], "UNKNOWN_QUANTITY"),
        (
            [{**BILLABLE, "expression": {"quotient": [{"q": "submitted"}, {"const": "0"}]}}],
            "DIVISION_BY_ZERO",
        ),
        (
            [{**BILLABLE, "expression": {"difference": [{"const": "0"}, {"q": "submitted"}]}}],
            "NEGATIVE_QUANTITY",
        ),
        ([{**BILLABLE, "name": "submitted"}], "DUPLICATE_ID"),
        (
            [
                {**BILLABLE, "expression": {"q": "other"}},
                {
                    "name": "other",
                    "unit": "unit",
                    "rounding": "NONE",
                    "expression": {"q": "billable"},
                },
            ],
            "DEPENDENCY_CYCLE",
        ),
    ],
)
def test_derived_errors_point_at_the_field(derived, code):
    r = calculate_periods(_eng(), _scen(derived))
    err = r["issues"]["errors"][0]
    assert err["code"] == code and err["path"].startswith("/scenario/derived/")


def test_search_over_an_assumption():
    d = json.loads((EXAMPLES / "pattern_counting_rules.json").read_text())
    spec = {
        "engagement": d["engagement"],
        "scenarios": d["scenarios"],
        "parameters": [
            {"name": "reissue", "assumption": "reissue_rate", "values": ["0", "0.05", "0.10"]}
        ],
        "objective": {"metric": "contractual_fee", "sense": "min"},
        "detail": "standard",
        "include_baseline": False,
    }
    out = search_structures(spec)
    assert out["counts"]["evaluated"] == 3
    assert out["best"][0]["parameters"] == {"reissue": "0.10"}
    assert out["best"][0]["grid_edges"][0]["edge"] == "upper"
    bad = search_structures(
        {**spec, "parameters": [{"name": "x", "assumption": "nope", "values": ["1"]}]}
    )
    assert bad["issues"]["errors"][0]["code"] == "UNKNOWN_QUANTITY"


def test_counting_rules_lower_the_fee_against_the_plain_pattern():
    plain = json.loads((EXAMPLES / "pattern_tiered_minimum.json").read_text())
    counted = json.loads((EXAMPLES / "pattern_counting_rules.json").read_text())
    p = calculate_periods(plain["engagement"], plain["scenarios"][1])
    c = calculate_periods(counted["engagement"], counted["scenarios"][0])
    assert D(c["term"]["contractual_fee"]) < D(p["term"]["contractual_fee"])
    assert copy.deepcopy(c["definitions"]["derived_quantities"])
