"""Outcome pricing (SHARE, SUCCESS, PERCENT_OF_OUTCOME) and realization against standard rates."""

import copy

import pytest
from builders import comp, engagement, scen
from conftest import D

from cometric import calculate_periods, validate_engagement


def _outcome_engagement(form, **terms):
    o = {
        "form": form,
        "metric": "savings",
        "unit": "USD",
        "attribution_percent": "0.8",
        "attribution_method": "Audited spend baseline",
        "approval_reference": "APPROVAL-1",
    }
    o.update(terms)
    return engagement(
        [
            comp("base", "FIXED_RECURRING", "FIXED", fixed_amount="10000"),
            comp("success", "OUTCOME_ADJUSTMENT", "OUTCOME", "EVENT", outcome=o),
        ],
        adjustments=[
            {"id": "cap", "type": "CAP", "amount": "10000000", "accumulation_period": "YEAR"}
        ],
    )


def test_share_of_savings_against_baseline_charged_at_year_end():
    e = _outcome_engagement(
        "SHARE",
        baseline="1000000",
        share_percent="0.25",
        cap_amount="100000",
        direction="HIGHER_IS_BETTER",
    )
    r = calculate_periods(e, scen("s", [("savings", "1300000", "USD", "TERM")]), detail="periods")
    assert r["status"] == "ok"
    outcome = {p["period"]: D(p["outcome_fee"]) for p in r["periods"] if D(p["outcome_fee"]) != 0}
    # 0.25 x 0.8 x (1,300,000 - 1,000,000) = 60,000 in December only
    assert outcome == {"2027-12": D(60000)}
    assert D(r["term"]["contractual_fee"]) == 120000 + 60000


def test_share_is_capped_and_never_negative():
    e = _outcome_engagement("SHARE", baseline="1000000", share_percent="0.25", cap_amount="50000")
    high = calculate_periods(e, scen("s", [("savings", "2000000", "USD", "TERM")]))
    assert D(high["term"]["outcome_fee"]) == 50000
    low = calculate_periods(e, scen("s", [("savings", "500000", "USD", "TERM")]))
    assert D(low["term"]["outcome_fee"]) == 0


def test_lower_is_better_baseline():
    e = _outcome_engagement(
        "SHARE",
        baseline="900000",
        share_percent="0.5",
        cap_amount="1000000",
        direction="LOWER_IS_BETTER",
        metric="spend",
    )
    r = calculate_periods(e, scen("s", [("spend", "800000", "USD", "TERM")]))
    assert D(r["term"]["outcome_fee"]) == D("0.5") * D("0.8") * 100000


@pytest.mark.parametrize("savings,fee", [("999999", 0), ("1000000", 75000)])
def test_success_fee_at_target_boundary(savings, fee):
    e = _outcome_engagement("SUCCESS", target="1000000", success_amount="75000")
    r = calculate_periods(e, scen("s", [("savings", savings, "USD", "TERM")]))
    assert D(r["term"]["outcome_fee"]) == fee


def test_percent_of_outcome():
    e = _outcome_engagement(
        "PERCENT_OF_OUTCOME", share_percent="0.1", cap_amount="1000000", metric="recovery"
    )
    r = calculate_periods(e, scen("s", [("recovery", "500000", "USD", "TERM")]))
    assert D(r["term"]["outcome_fee"]) == D("0.1") * D("0.8") * 500000


def test_outcome_prerequisites():
    e = _outcome_engagement("SHARE", share_percent="0.25")
    e["arrangement_versions"][0]["components"][1]["outcome"].pop("approval_reference")
    rep = validate_engagement(e)
    errors = {x["code"] for x in rep["errors"]}
    approvals = {x["code"] for x in rep["approvals_required"]}
    assert "BASELINE_REQUIRED" in errors
    assert {"UNCAPPED_OUTCOME_FEE", "OUTCOME_FEE_APPROVAL"} <= approvals
    e2 = _outcome_engagement("PERCENT_OF_OUTCOME", share_percent="0.1", cap_amount="1")
    e2["arrangement_versions"][0]["components"][1]["outcome"].pop("attribution_percent")
    assert "ATTRIBUTION_REQUIRED" in {x["code"] for x in validate_engagement(e2)["errors"]}
    e3 = _outcome_engagement("SUCCESS", target="1", success_amount="1")
    e3["arrangement_versions"][0]["components"][1]["outcome"]["recognition"] = "CUMULATIVE"
    assert "RECOGNITION_PERIOD" in {x["code"] for x in validate_engagement(e3)["errors"]}


def test_outcome_true_up_outside_horizon_is_flagged():
    e = _outcome_engagement("SUCCESS", target="1", success_amount="1")
    r = calculate_periods(
        e, scen("s", [("savings", "5", "USD", "TERM")], horizon=("2027-01-01", "2027-06-30"))
    )
    assert D(r["term"]["outcome_fee"]) == 0
    assert any(w["code"] == "TRUE_UP_OUTSIDE_HORIZON" for w in r["issues"]["warnings"])


def test_realization_on_fixed_project(case):
    c = case("d")
    e = copy.deepcopy(c["engagement"])
    e["delivery_plan"]["standard_rate_card"] = [{"role": "consultant", "rate": "200"}]
    e["delivery_plan"]["worked_hours_source"] = "worked"
    s = copy.deepcopy(c["scenarios"][1])
    s["assumptions"].append(
        {
            "name": "worked.consultant",
            "value": "6000",
            "unit": "hours",
            "time_period": "TERM",
            "origin": "ILLUSTRATIVE",
        }
    )
    r = calculate_periods(e, s, "reference")
    t = r["term"]
    assert D(t["standard_value"]) == 1200000
    assert D(t["realization"]) == D("0.75")
    assert D(t["write_down"]) == 300000
    assert D(t["effective_billing_rate"]) == 150


def test_realization_needs_worked_hours(case):
    c = case("d")
    e = copy.deepcopy(c["engagement"])
    e["delivery_plan"]["standard_rate_card"] = [{"role": "consultant", "rate": "200"}]
    e["delivery_plan"]["worked_hours_source"] = "worked"
    r = calculate_periods(e, c["scenarios"][1], "reference")
    assert r["status"] == "invalid"
    assert r["issues"]["errors"][0]["path"] == "/engagement/delivery_plan/worked_hours_source"


def test_no_rate_card_means_no_realization(case):
    c = case("b")
    t = calculate_periods(c["engagement"], c["scenarios"][1], "reference")["term"]
    assert t["realization"] is None and t["write_down"] is None
