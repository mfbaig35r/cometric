"""Termination scenarios (spec 4.4, V3-28)."""

from decimal import Decimal

import pytest
from builders import comp, engagement, scen, schedule
from conftest import D

from cometric import calculate_periods, validate_engagement


def _eng(rule="PRORATE", end="2027-12-31", fee=None, outcome=False, transition=False):
    comps = [
        comp("base", "FIXED_RECURRING", "FIXED", fixed_amount="10000"),
        comp(
            "units",
            "UNIT_OUTPUT",
            "OUTPUT",
            "USAGE_TRIGGERED",
            quantity_source="q",
            unit="unit",
            rate_schedule_id="r",
        ),
    ]
    if outcome:
        comps.append(
            comp(
                "success",
                "OUTCOME_ADJUSTMENT",
                "OUTCOME",
                "EVENT",
                outcome={
                    "form": "SUCCESS",
                    "metric": "savings",
                    "unit": "USD",
                    "target": "1",
                    "success_amount": "5000",
                    "attribution_method": "x",
                    "approval_reference": "A",
                },
            )
        )
    e = engagement(
        comps,
        schedules=[schedule("r", tiers=[{"from": "0", "to": None, "rate": "0"}])],
        commitments=[
            {
                "id": "annual_min",
                "kind": "MINIMUM_SPEND",
                "amount": "150000",
                "accumulation_period": "CONTRACT_YEAR",
                "tested_against": "GROSS",
                "shortfall_rule": "PERIOD_END_TRUE_UP",
                "termination_rule": rule,
            }
        ],
        costs=[
            {
                "id": "t",
                "category": "TRANSITION",
                "behavior": "ONE_TIME",
                "amount": "12000",
                "amortize_months": 12,
            }
        ]
        if transition
        else None,
        end=end,
    )
    if fee:
        e["arrangement_versions"][0]["termination_fee"] = fee
    return e


def _run(e, date="2027-06-30", extra=(), policy=None, detail="periods"):
    s = scen("s", [("q", "1200", "unit", "2027"), *extra])
    s["termination_date"] = date
    return calculate_periods(e, s, policy, detail=detail)


def test_prorated_minimum():
    r = _run(_eng("PRORATE"))
    assert [p["period"] for p in r["periods"]][-1] == "2027-06"
    required = Decimal(150000) * Decimal(181) / Decimal(365)
    assert D(r["termination"]["minimum_charges"]) == (required - 60000).quantize(D("0.01"))
    assert r["termination"]["months_run"] == 6 and r["termination"]["months_not_run"] == 6


def test_remainder_due_and_waived():
    assert D(_run(_eng("REMAINDER_DUE"))["termination"]["minimum_charges"]) == 90000
    two_years = _run(_eng("REMAINDER_DUE", end="2028-12-31"))
    assert D(two_years["termination"]["minimum_charges"]) == 90000 + 150000
    waived = _run(_eng("WAIVED"))
    assert D(waived["termination"]["minimum_charges"]) == 0
    assert D(waived["term"]["contractual_fee"]) == 60000


def test_remainder_due_on_a_period_end_still_owes_later_periods():
    r = _run(_eng("REMAINDER_DUE", end="2028-12-31"), date="2027-12-31")
    # year 1 runs fully (120,000 vs 150,000 minimum: 30,000 true-up) plus year 2 owed in full
    assert D(r["termination"]["minimum_charges"]) == 30000 + 150000


def test_termination_fee_and_quantities_over_the_original_term():
    r = _run(_eng("WAIVED", fee="25000"), detail="line_items")
    assert D(r["termination"]["termination_fee"]) == 25000
    # 1,200 units declared for 2027 are 100 a month, so 600 by the end of June
    assert D(r["term"]["client_consumed_quantity"]) == 600
    assert D(r["term"]["contractual_fee"]) == 60000 + 25000


def test_unamortized_transition_is_written_off():
    r = _run(_eng("WAIVED", transition=True), policy="reference")
    assert D(r["termination"]["unamortized_written_off"]) == 6000
    assert D(r["term"]["engagement_avoidable_cost"]) == 12000


def test_outcome_cut_short_is_not_charged():
    r = _run(_eng("WAIVED", outcome=True), extra=[("savings", "10", "USD", "2027")])
    assert D(r["term"]["outcome_fee"]) == 0
    assert "TERMINATED_MID_PERIOD" in [w["code"] for w in r["issues"]["warnings"]]


def test_missing_rule_and_bad_dates():
    e = _eng("PRORATE")
    del e["arrangement_versions"][0]["commitments"][0]["termination_rule"]
    r = _run(e)
    assert r["issues"]["errors"][0]["code"] == "TERMINATION_RULE_REQUIRED"
    assert r["issues"]["errors"][0]["path"].endswith("/commitments/0/termination_rule")
    assert validate_engagement(e)["valid"]  # a rule is only needed when a scenario terminates
    late = _run(_eng(), date="2028-02-01")
    assert late["issues"]["errors"][0]["code"] == "TERMINATION_DATE_RANGE"
    mid = _run(_eng(), date="2027-06-15")
    assert mid["issues"]["errors"][0]["code"] == "PRORATION_POLICY_REQUIRED"


@pytest.mark.parametrize("rule", ["PRORATE", "REMAINDER_DUE", "WAIVED"])
def test_no_termination_means_no_change(rule):
    s = scen("s", [("q", "1200", "unit", "2027")])
    r = calculate_periods(_eng(rule), s)
    assert "termination" not in r
    assert D(r["term"]["contractual_fee"]) == 150000
