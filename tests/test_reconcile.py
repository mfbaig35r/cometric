"""M6 reconciliation: compare computed figures with recorded actuals."""

import json

import pytest
from conftest import D

from cometric import calculate_periods, reconcile


def _actuals_from(case_doc, scenario):
    r = calculate_periods(case_doc["engagement"], scenario, "reference", detail="periods")
    periods = {
        p["period"]: {"contractual_fee": p["contractual_fee"], "worked_hours": p["worked_hours"]}
        for p in r["periods"]
    }
    return {
        "periods": periods,
        "term": {
            "contractual_fee": r["term"]["contractual_fee"],
            "outcome_fee": r["term"]["outcome_fee"],
        },
    }


def test_identical_actuals_reconcile(case):
    c = case("h")
    s = c["scenarios"][1]
    out = reconcile(c["engagement"], s, "reference", _actuals_from(c, s))
    assert out["status"] == "reconciled"
    assert out["discrepancies"] == 0 and out["compared"] == 12 * 2 + 2
    assert out["publishable_summary"] == []


def test_discrepancy_is_located_and_explained(case):
    c = case("h")
    s = c["scenarios"][1]
    actuals = _actuals_from(c, s)
    actuals["periods"]["2027-07"]["contractual_fee"] = "245000"  # invoice was 5,000 lower
    out = reconcile(c["engagement"], s, "reference", actuals)
    assert out["status"] == "discrepancies" and out["discrepancies"] == 1
    row = next(r for r in out["rows"] if not r["within_tolerance"])
    assert row["scope"] == "2027-07" and D(row["difference"]) == 5000
    assert [li["kind"] for li in row["fee_line_items"]] == ["project_payment"]
    summary = out["publishable_summary"][0]
    assert summary == {
        "metric": "contractual_fee",
        "month": 7,
        "relative_difference": summary["relative_difference"],
        "direction": "cometric_higher",
        "mechanisms_priced": ["project_payment"],
    }


def test_publishable_summary_has_no_amounts_dates_or_names(case):
    c = case("h")
    s = c["scenarios"][1]
    actuals = _actuals_from(c, s)
    for ps in actuals["periods"]:
        actuals["periods"][ps]["contractual_fee"] = "1"
    out = reconcile(c["engagement"], s, "reference", actuals)
    text = json.dumps(out["publishable_summary"])
    assert "2027" not in text and "CASE-H" not in text and "250000" not in text
    assert all(
        set(x) == {"metric", "month", "relative_difference", "direction", "mechanisms_priced"}
        for x in out["publishable_summary"]
    )


def test_relative_tolerance(case):
    c = case("h")
    s = c["scenarios"][1]
    actuals = {"term": {"contractual_fee": "635500"}}
    assert reconcile(c["engagement"], s, "reference", actuals)["status"] == "discrepancies"
    assert (
        reconcile(c["engagement"], s, "reference", actuals, tolerance_relative="0.001")["status"]
        == "reconciled"
    )


def test_uncalculated_costs_are_not_compared_as_zero(case):  # review finding 1
    c = case("h")
    s = c["scenarios"][1]
    out = reconcile(
        c["engagement"], s, None, {"term": {"direct_delivery_cost": "0", "gross_profit": "635000"}}
    )
    assert out["costs_evaluated"] is False
    assert out["status"] == "discrepancies"
    assert all(r["computed"] is None and "not computed" in r["note"] for r in out["rows"])


def test_costs_blanked_for_every_consumer(case):  # review finding 6
    from cometric.core.api import run_calculation

    c = case("h")
    result, *_ = run_calculation(c["engagement"], c["scenarios"][1], None)
    assert result.extras["costs_evaluated"] is False
    assert result.data["term"]["gross_profit"] is None
    assert all(p["direct_delivery_cost"] is None for p in result.data["periods"])


@pytest.mark.parametrize(
    "actuals,tolerance,path",
    [
        ({"term": {"contractual_fee": 635000.0}}, "0.01", "/actuals/term/contractual_fee"),
        (
            {"periods": {"2027-07": {"contractual_fee": None}}},
            "0.01",
            "/actuals/periods/2027-07/contractual_fee",
        ),
        ({"term": {"contractual_fee": "635000"}}, "abc", "/tolerance_absolute"),
        ({"term": {"contractual_fee": "635000"}}, "-1", "/tolerance_absolute"),
        ({"periods": {"July": {"contractual_fee": "1"}}}, "0.01", "/actuals/periods/July"),
        ({"term": {"gross_proft": "1"}}, "0.01", "/actuals/term/gross_proft"),
        ([1, 2], "0.01", "/actuals"),
    ],
)
def test_bad_input_returns_issues_not_exceptions(
    case, actuals, tolerance, path
):  # findings 2, 4, 8
    c = case("h")
    out = reconcile(
        c["engagement"], c["scenarios"][1], "reference", actuals, tolerance_absolute=tolerance
    )
    assert out["status"] == "invalid"
    assert path in [e["path"] for e in out["issues"]["errors"]]


def test_infeasible_scenario_never_reconciles(case):  # review finding 3
    c = case("g")
    e = c["engagement"]
    e["delivery_plan"]["breach_mode"] = "INFEASIBLE"
    s = c["scenarios"][0]
    fee = calculate_periods(e, s, "reference")["term"]["contractual_fee"]
    out = reconcile(e, s, "reference", {"term": {"contractual_fee": fee}})
    assert out["status"] == "infeasible" and out["feasible"] is False


def test_fingerprint_covers_actuals_and_tolerance(case):  # review finding 5
    c = case("h")
    s = c["scenarios"][1]
    a = reconcile(c["engagement"], s, "reference", {"term": {"contractual_fee": "635000"}})
    b = reconcile(c["engagement"], s, "reference", {"term": {"contractual_fee": "600000"}})
    t = reconcile(
        c["engagement"],
        s,
        "reference",
        {"term": {"contractual_fee": "635000"}},
        tolerance_relative="0.5",
    )
    assert len({a["input_fingerprint"], b["input_fingerprint"], t["input_fingerprint"]}) == 3
    assert a["calculation_fingerprint"] == b["calculation_fingerprint"]
    for k in ("engine_version", "schema_version", "money_policy", "packs"):
        assert k in a


def test_month_numbers_count_from_engagement_start(case):  # review finding 10
    c = case("h")
    s = c["scenarios"][1]
    s["horizon"] = {"from": "2027-04-01", "to": "2027-12-31"}
    out = reconcile(
        c["engagement"], s, "reference", {"periods": {"2027-07": {"contractual_fee": "1"}}}
    )
    assert out["publishable_summary"][0]["month"] == 7
