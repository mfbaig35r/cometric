"""T-016 casebook, T-015 annual = sum of months, T-022 risk labels, T-023 recognition, T-034 floor, break-even."""

from decimal import Decimal

import pytest
from conftest import D

from cometric import break_even, calculate_periods, derive_risk_exposure, price_floor

CASES = ["a", "b", "c", "d", "e", "f", "g", "h"]


@pytest.mark.parametrize("letter", CASES)
def test_casebook_reproduces_report(case, letter):
    c = case(letter)
    for policy_name, expected_by_scenario in c["expected"].items():
        if policy_name not in c["cost_policies"]:
            continue
        policy = c["cost_policies"][policy_name]
        for s in c["scenarios"]:
            exp = expected_by_scenario.get(s["id"])
            if not exp:
                continue
            r = calculate_periods(c["engagement"], s, policy)
            assert r["status"] == "ok", r["issues"]
            for k, v in exp.items():
                assert D(r["term"][k]) == D(v), (letter, policy_name, s["id"], k)


def test_case_a_margins_match_report_presentation(case):
    c = case("a")
    for s in c["scenarios"]:
        r = calculate_periods(c["engagement"], s, c["cost_policies"]["as_published"])
        gm, cm = c["expected"]["margins"][s["id"]]
        assert abs(D(r["term"]["gross_margin"]) - D(gm)) < Decimal("0.0005")
        assert abs(D(r["term"]["contribution_margin"]) - D(cm)) < Decimal("0.0005")
    low = calculate_periods(c["engagement"], c["scenarios"][0], "reference")
    assert D(low["term"]["effective_client_unit_price"]) == 200


def test_case_c_price_per_used_hour(case):
    c = case("c")
    for s in c["scenarios"]:
        r = calculate_periods(c["engagement"], s, c["cost_policies"]["as_published"])
        price = D(r["term"]["effective_client_price_per_used_hour"]).quantize(Decimal("0.01"))
        assert price == D(c["expected"]["price_per_used_hour"][s["id"]])
        assert D(r["term"]["productive_hours"]) == 12800


def test_case_f_weighted_units(case):
    c = case("f")
    for s in c["scenarios"]:
        r = calculate_periods(c["engagement"], s, "reference")
        assert D(r["term"]["client_consumed_quantity"]) == D(
            c["expected"]["weighted_units"][s["id"]]
        )


def test_case_g_overflow_in_november_and_december(case):
    c = case("g")
    r = calculate_periods(
        c["engagement"], c["scenarios"][0], c["cost_policies"]["as_published"], detail="line_items"
    )
    months = sorted(
        {ln["period"] for ln in r["line_items"]["costs"] if ln["ref"].endswith(":overflow")}
    )
    assert months == c["expected"]["overflow_months"]
    assert r["term"]["capacity"][0]["overflow"] == "2000"


@pytest.mark.parametrize("letter", CASES)
def test_annual_equals_sum_of_months(case, letter):  # T-015
    c = case(letter)
    r = calculate_periods(c["engagement"], c["scenarios"][-1], "reference", detail="periods")
    for k in (
        "contractual_fee",
        "direct_delivery_cost",
        "engagement_avoidable_cost",
        "contribution_profit",
    ):
        assert sum(D(p[k]) for p in r["periods"]) == D(r["years"]["2027"][k]) == D(r["term"][k])


@pytest.mark.parametrize(
    "letter,driver,exact_prefix,whole",
    [
        ("b", "contracts", "6418.6046", 6419),
        ("d", "delivery_hours", "9375", 9375),
        ("e", "documents", "2580.645", 2581),
    ],
)
def test_break_even(case, letter, driver, exact_prefix, whole):
    c = case(letter)
    r = break_even(c["engagement"], c["scenarios"][1], c["cost_policies"]["as_published"], driver)
    assert r["status"] == "ok"
    assert r["exact"].startswith(exact_prefix)
    assert r["whole"] == whole


def _labels(c, policy="as_published"):
    results = [
        calculate_periods(c["engagement"], s, c["cost_policies"][policy]) for s in c["scenarios"]
    ]
    exp = derive_risk_exposure(
        results,
        base_scenario_id="base",
        tolerance_policy={"provider_relative": "0", "client_relative": "0"},
    )
    return {d["scenario_id"]: d for d in exp["deviations"]}, exp


def test_derived_risk_labels_match_appendix_c(case):  # T-022
    a, _ = _labels(case("a"))
    assert (
        a["low"]["derived_bearer"] == "CLIENT"
        and D(a["low"]["provider_downside"]) == -72000
        and D(a["low"]["client_downside"]) == 80
    )
    assert a["high"]["derived_bearer"] == "NONE_ADVERSE"
    b, _ = _labels(case("b"))
    assert b["low"]["derived_bearer"] == "PROVIDER" and D(b["low"]["provider_downside"]) == 258000
    c, _ = _labels(case("c"))
    assert c["low"]["derived_bearer"] == "CLIENT"
    assert D(c["low"]["client_downside"]).quantize(Decimal("0.01")) == D("68.18")
    d, _ = _labels(case("d"))
    assert (
        d["overrun"]["derived_bearer"] == "PROVIDER"
        and D(d["overrun"]["provider_downside"]) == 200000
    )
    e, _ = _labels(case("e"))
    assert e["low"]["derived_bearer"] == "SHARED" and D(e["low"]["provider_downside"]) == 262500
    assert D(e["low"]["client_downside"]) == D("10.80")
    f, _ = _labels(case("f"))
    assert f["low"]["derived_bearer"] == "SHARED" and D(f["low"]["provider_downside"]) == 287000


def test_risk_labels_absent_without_tolerance(case):
    c = case("b")
    results = [calculate_periods(c["engagement"], s, "reference") for s in c["scenarios"]]
    exp = derive_risk_exposure(results)
    assert all(d["derived_bearer"] is None for d in exp["deviations"])


def test_risk_mismatch_warning(case):
    c = case("a")
    results = [calculate_periods(c["engagement"], s, "reference") for s in c["scenarios"]]
    exp = derive_risk_exposure(
        results,
        tolerance_policy={"provider_relative": "0", "client_relative": "0"},
        declared=[{"risk_type": "VOLUME", "declared_bearer": "PROVIDER"}],
    )
    assert any(w["code"] == "RISK_MISMATCH" for w in exp["warnings"])


def test_recognition_timing_same_annual_total(case):  # T-023
    c = case("a")
    high = c["scenarios"][2]
    cumulative = calculate_periods(c["engagement"], high, "reference", detail="periods")
    c["engagement"]["arrangement_versions"][0]["entitlements"][0]["overage_recognition"] = (
        "PERIOD_END"
    )
    period_end = calculate_periods(c["engagement"], high, "reference", detail="periods")
    assert (
        cumulative["term"]["contractual_fee"] == period_end["term"]["contractual_fee"] == "1440000"
    )
    cum_months = [p["period"] for p in cumulative["periods"] if D(p["overage_fee"]) > 0]
    pe_months = [p["period"] for p in period_end["periods"] if D(p["overage_fee"]) > 0]
    assert cum_months == ["2027-11", "2027-12"]
    assert pe_months == ["2027-12"]


def test_price_floor_case_b(case):  # T-034
    c = case("b")
    r = price_floor(
        c["engagement"], [c["scenarios"][1]], c["cost_policies"]["as_published"], "0.20"
    )
    row = r["floors"][0]
    assert D(row["costs_in_floor"]) == 900000
    assert D(row["price_floor"]) == 1125000
    assert D(row["unit_floor"]) == D("93.75")
    bad = price_floor(c["engagement"], [c["scenarios"][1]], "reference", "1")
    assert bad["status"] == "invalid"


def test_transition_payback_month_incurred_view(case):
    c = case("a")
    r = calculate_periods(c["engagement"], c["scenarios"][1], "reference", detail="periods")
    # transition of 80,000 is incurred in January under the incurred view; payback when cumulative recovers
    assert r["term"]["transition_payback_month"] is not None


def test_case_h_consulting_realization(case):
    c = case("h")
    for s in c["scenarios"]:
        t = calculate_periods(c["engagement"], s, "reference")["term"]
        assert D(t["standard_value"]) == D(c["expected"]["standard_value"])
        assert D(t["realization"]) == D(t["contractual_fee"]) / D(t["standard_value"])
