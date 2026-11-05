"""M6 reconciliation: compare computed figures with recorded actuals."""

import json

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


def test_relative_tolerance_and_unknown_metrics(case):
    c = case("h")
    s = c["scenarios"][1]
    actuals = {"term": {"contractual_fee": "635500", "made_up_metric": "1"}}
    strict = reconcile(c["engagement"], s, "reference", actuals)
    assert strict["status"] == "discrepancies" and strict["unknown_metrics"] == ["made_up_metric"]
    loose = reconcile(c["engagement"], s, "reference", actuals, tolerance_relative="0.001")
    assert loose["status"] == "reconciled"
