"""ALSP template and worked patterns: expected figures are hand-computed in scripts/build_alsp.py."""

import json
from pathlib import Path

import pytest
from conftest import D

from cometric import calculate_periods, validate_engagement
from cometric.core.templates import fill_template, get_template

EXAMPLES = Path(__file__).resolve().parents[1] / "src" / "cometric" / "examples"
PATTERNS = sorted(EXAMPLES.glob("pattern_*.json"))


@pytest.mark.parametrize("path", PATTERNS, ids=[p.stem for p in PATTERNS])
def test_pattern_matches_hand_computed_figures(path):
    d = json.loads(path.read_text())
    policy = next(iter(d["cost_policies"].values()), None)
    for s in d["scenarios"]:
        r = calculate_periods(d["engagement"], s, policy)
        assert r["status"] == "ok", r["issues"]
        for metric, value in d["expected"][s["id"]].items():
            assert D(r["term"][metric]) == D(value), (path.stem, s["id"], metric)


def test_alsp_template_round_trip():
    t = get_template("tiered_units_annual_minimum", "alsp")
    assert any(
        e["code"] == "REQUIRED_FIELD" for e in validate_engagement(t["engagement"])["errors"]
    )
    filled = fill_template(t, t["examples"])
    assert validate_engagement(filled["engagement"])["valid"]
    r = calculate_periods(filled["engagement"], filled["scenario"])
    assert (
        r["status"] == "ok"
        and r["definitions"]["client_unit_price_basis"] == "tier_1+tier_2+tier_3+tier_4"
    )
    assert r["definitions"]["thresholds"][0]["scope"] == "EXCESS_ONLY"


def test_termination_pattern_reports_its_cost():
    d = json.loads((EXAMPLES / "pattern_termination.json").read_text())
    r = calculate_periods(d["engagement"], d["scenarios"][0])
    t = r["termination"]
    assert t["date"] == "2027-09-30" and t["months_run"] == 9 and D(t["termination_fee"]) == 100000
