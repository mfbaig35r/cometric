"""Fee semantics: T-001 to T-009, T-013, T-014, T-017, T-018, T-020, T-024, T-025, T-026."""

from decimal import Decimal

from builders import codes, comp, engagement, scen, schedule, unit
from conftest import D

from cometric import calculate_periods, explain_fee, validate_engagement
from cometric.core.money import allocate_exact, margin_and_markup
from cometric.core.tiers import price


def test_t001_t026_spec_example(spec_example):
    e, s = spec_example["engagement"], spec_example["scenarios"][0]
    assert validate_engagement(e)["valid"]
    r = calculate_periods(e, s)
    assert r["status"] == "ok"
    assert D(r["term"]["contractual_fee"]) == 124000
    # costs omitted: margin metrics are unavailable with an explicit reason
    assert r["term"]["contribution_margin"] is None
    assert "COSTS_NOT_EVALUATED" in codes(r)


def _minimum_engagement(scope="ENGAGEMENT", period="MONTH", rule="PER_SEGMENT", tested="GROSS"):
    return engagement(
        [
            comp(
                "units",
                "UNIT_OUTPUT",
                "OUTPUT",
                "USAGE_TRIGGERED",
                quantity_source="q",
                unit="unit",
                rate_schedule_id="r",
            )
        ],
        schedules=[schedule("r", tiers=[{"from": "0", "to": None, "rate": "10"}])],
        commitments=[
            {
                "id": "min",
                "kind": "MINIMUM_SPEND",
                "amount": "5000",
                "aggregation_scope": scope,
                "component_ids": ["units"] if scope == "COMPONENT" else [],
                "accumulation_period": period,
                "tested_against": tested,
                "shortfall_rule": rule,
            }
        ],
    )


def test_t002_minimum_with_zero_consumption():
    e = _minimum_engagement()
    r = calculate_periods(
        e, scen("zero", [("q", "0", "unit", "2027-01")], horizon=("2027-01-01", "2027-01-31"))
    )
    assert D(r["term"]["contractual_fee"]) == 5000
    assert D(r["term"]["commitment_shortfall"]) == 5000
    assert r["term"]["effective_client_unit_price"] is None


def test_t003_marginal_vs_all_units_at_threshold_crossing():
    tiers = [{"from": "0", "to": "1000", "rate": "10"}, {"from": "1000", "to": None, "rate": "9"}]
    results = {}
    for method in ("MARGINAL", "ALL_UNITS"):
        e = engagement(
            [
                comp(
                    "u",
                    "UNIT_OUTPUT",
                    "OUTPUT",
                    quantity_source="q",
                    unit="unit",
                    rate_schedule_id="r",
                )
            ],
            schedules=[schedule("r", tiers=tiers, method=method)],
        )
        r = calculate_periods(
            e, scen("s", [("q", "1500", "unit", "2027-01")], horizon=("2027-01-01", "2027-01-31"))
        )
        results[method] = D(r["term"]["contractual_fee"])
    assert results["MARGINAL"] == 1000 * 10 + 500 * 9
    assert results["ALL_UNITS"] == 1500 * 9


def test_t003_tier_boundaries():
    from cometric.core.models import Tier

    tiers = [
        Tier.model_validate(t)
        for t in ({"from": "0", "to": "100", "rate": "2"}, {"from": "100", "to": None, "rate": "1"})
    ]
    from cometric.core.enums import TierMethod

    assert price(D(99), tiers, TierMethod.MARGINAL) == 198
    assert price(D(100), tiers, TierMethod.MARGINAL) == 200
    assert price(D(101), tiers, TierMethod.MARGINAL) == 201
    assert price(D(99), tiers, TierMethod.ALL_UNITS) == 198
    assert price(D(100), tiers, TierMethod.ALL_UNITS) == 100
    assert price(D(101), tiers, TierMethod.ALL_UNITS) == 101


def test_t004_unit_mismatch_is_rejected():
    e = engagement(
        [
            comp(
                "u",
                "UNIT_OUTPUT",
                "OUTPUT",
                quantity_source="q",
                unit="document",
                rate_schedule_id="r",
            )
        ],
        units=[unit("document"), unit("contract")],
        schedules=[schedule("r", unit_code="contract")],
    )
    rep = validate_engagement(e)
    assert not rep["valid"]
    err = next(x for x in rep["errors"] if x["code"] == "UNIT_MISMATCH")
    assert err["path"] == "/engagement/arrangement_versions/0/components/0/unit"


def test_t005_amendment_keeps_prior_terms():
    v1 = {
        "id": "v1",
        "effective_from": "2027-01-01",
        "effective_to": "2027-03-31",
        "components": [comp("base", "FIXED_RECURRING", "FIXED", fixed_amount="1000")],
    }
    v2_comp = comp("base", "FIXED_RECURRING", "FIXED", fixed_amount="2000")
    v2_comp["effective_period"] = {"from": "2027-04-01", "to": None}
    v2 = {
        "id": "v2",
        "effective_from": "2027-04-01",
        "supersedes_id": "v1",
        "components": [v2_comp],
    }
    e = engagement(None, versions=[v1, v2], end="2027-06-30")
    r = calculate_periods(e, scen(), detail="periods")
    fees = [D(p["contractual_fee"]) for p in r["periods"]]
    assert fees == [1000, 1000, 1000, 2000, 2000, 2000]


def test_t006_rollover_ledger_exactly_once():
    e = engagement(
        [
            comp("base", "FIXED_RECURRING", "FIXED", fixed_amount="1000"),
            comp(
                "over",
                "ALLOWANCE_OVERAGE",
                "OUTPUT",
                quantity_source="q",
                unit="unit",
                entitlement_id="ent",
                rate_schedule_id="r",
                depends_on=["ent"],
            ),
        ],
        entitlements=[
            {
                "id": "ent",
                "granted_by": "base",
                "unit": "unit",
                "included_quantity": "100",
                "accumulation_period": "MONTH",
                "overage_recognition": "PER_SEGMENT",
                "rollover": {"policy": "NEXT_PERIOD", "ceiling": "50"},
            }
        ],
        schedules=[schedule("r")],
        end="2027-03-31",
    )
    s = scen(
        "s",
        [
            ("q", "60", "unit", "2027-01"),
            ("q", "170", "unit", "2027-02"),
            ("q", "0", "unit", "2027-03"),
        ],
    )
    r = calculate_periods(e, s, detail="line_items")
    ledger = r["ledger"]
    by = lambda t: [(x["period"], D(x["quantity"])) for x in ledger if x["entry_type"] == t]  # noqa: E731
    # Jan: 40 unused, 40 roll (ceiling 50). Feb: 140 available, 170 used -> 30 overage
    assert ("2027-01", D(40)) in by("ROLLOVER_OUT")
    over = [x for x in r["line_items"]["fees"] if x["kind"] == "overage" and D(x["quantity"]) > 0]
    assert [(x["period"], D(x["quantity"])) for x in over] == [("2027-02", D(30))]
    # March grant of 100 is unused and expires at engagement end; nothing is double counted
    assert ("2027-03", D(100)) in by("EXPIRE")
    granted = sum(q for _, q in by("GRANT")) + sum(q for _, q in by("ROLLOVER_IN"))
    out = (
        sum(q for _, q in by("CONSUME"))
        + sum(q for _, q in by("ROLLOVER_OUT"))
        + sum(q for _, q in by("EXPIRE"))
    )
    assert granted == out


def test_t007_minimum_applied_at_declared_scope_only():
    e = _minimum_engagement(scope="COMPONENT")
    e["arrangement_versions"][0]["components"].append(
        comp("other", "FIXED_RECURRING", "FIXED", fixed_amount="9000")
    )
    r = calculate_periods(
        e, scen("s", [("q", "100", "unit", "2027-01")], horizon=("2027-01-01", "2027-01-31"))
    )
    # component spend 1000 vs minimum 5000 -> shortfall 4000, even though total spend 10000 exceeds it
    assert D(r["term"]["commitment_shortfall"]) == 4000
    assert D(r["term"]["contractual_fee"]) == 1000 + 9000 + 4000


def test_minimum_period_end_true_up():
    e = _minimum_engagement(period="YEAR", rule="PERIOD_END_TRUE_UP")
    e["arrangement_versions"][0]["commitments"][0]["amount"] = "100000"
    r = calculate_periods(e, scen("s", [("q", "6000", "unit", "TERM")]), detail="periods")
    shortfall_months = [p["period"] for p in r["periods"] if D(p["commitment_shortfall"]) > 0]
    assert shortfall_months == ["2027-12"]
    assert D(r["term"]["contractual_fee"]) == 100000


def test_t008_zero_fee_margin_is_null():
    e = engagement(
        [
            comp(
                "u", "UNIT_OUTPUT", "OUTPUT", quantity_source="q", unit="unit", rate_schedule_id="r"
            )
        ],
        schedules=[schedule("r")],
        costs=[
            {
                "id": "c",
                "category": "POOLED_LABOR",
                "behavior": "FIXED",
                "amount": "100",
                "period": "MONTHLY",
            }
        ],
    )
    r = calculate_periods(e, scen("s", [("q", "0", "unit", "TERM")]), "reference")
    assert r["term"]["contractual_fee"] == "0"
    assert r["term"]["gross_margin"] is None and r["term"]["contribution_margin"] is None
    assert "margin_note" in r["term"]


def test_t009_dedicated_fte_fee_and_cost_fixed(case):
    c = case("c")
    fees = {
        calculate_periods(c["engagement"], s, "reference")["term"]["contractual_fee"]
        for s in c["scenarios"]
    }
    costs = {
        calculate_periods(c["engagement"], s, "reference")["term"]["direct_delivery_cost"]
        for s in c["scenarios"]
    }
    assert len(fees) == 1 and len(costs) == 1


def test_t013_missing_counting_rule_requires_approval():
    e = engagement(
        [
            comp(
                "u", "UNIT_OUTPUT", "OUTPUT", quantity_source="q", unit="unit", rate_schedule_id="r"
            )
        ],
        units=[{"code": "unit", "kind": "COUNT"}],
        schedules=[schedule("r")],
    )
    rep = validate_engagement(e)
    assert rep["valid"]
    assert "MISSING_COUNTING_RULE" in [a["code"] for a in rep["approvals_required"]]


def test_t014_margin_vs_markup():
    mm = margin_and_markup(D(75), D(100))
    assert mm["margin"] == D("0.25")
    assert mm["markup"].quantize(D("0.0001")) == D("0.3333")


def test_t017_all_units_cliff_warning():
    e = engagement(
        [
            comp(
                "u", "UNIT_OUTPUT", "OUTPUT", quantity_source="q", unit="unit", rate_schedule_id="r"
            )
        ],
        schedules=[
            schedule(
                "r",
                tiers=[
                    {"from": "0", "to": "1000", "rate": "10"},
                    {"from": "1000", "to": None, "rate": "9"},
                ],
                method="ALL_UNITS",
            )
        ],
    )
    rep = validate_engagement(e)
    cliff = next(w for w in rep["warnings"] if w["code"] == "TIER_CLIFF")
    assert cliff["detail"]["band"] == ["900", "1000"]


def test_t018_proration_calendar_days():
    v1 = {
        "id": "v1",
        "effective_from": "2027-01-01",
        "effective_to": "2027-03-15",
        "components": [comp("base", "FIXED_RECURRING", "FIXED", fixed_amount="3100")],
    }
    c2 = comp("base", "FIXED_RECURRING", "FIXED", fixed_amount="6200")
    c2["effective_period"] = {"from": "2027-03-16", "to": None}
    v2 = {
        "id": "v2",
        "effective_from": "2027-03-16",
        "supersedes_id": "v1",
        "proration_policy": "CALENDAR_DAYS",
        "components": [c2],
    }
    e = engagement(None, versions=[v1, v2], end="2027-04-30")
    r = calculate_periods(e, scen(), detail="periods")
    march = next(p for p in r["periods"] if p["period"] == "2027-03")
    assert D(march["contractual_fee"]) == D(3100) * 15 / 31 + D(6200) * 16 / 31
    del e["arrangement_versions"][1]["proration_policy"]
    rep = validate_engagement(e)
    assert "PRORATION_POLICY_REQUIRED" in [x["code"] for x in rep["errors"]]
    assert any(
        x["path"] == "/engagement/arrangement_versions/1/proration_policy" for x in rep["errors"]
    )


def test_proration_full_month_from_next():
    v1 = {
        "id": "v1",
        "effective_from": "2027-01-01",
        "effective_to": "2027-03-15",
        "components": [comp("base", "FIXED_RECURRING", "FIXED", fixed_amount="1000")],
    }
    c2 = comp("base", "FIXED_RECURRING", "FIXED", fixed_amount="2000")
    c2["effective_period"] = {"from": "2027-03-16", "to": None}
    v2 = {
        "id": "v2",
        "effective_from": "2027-03-16",
        "proration_policy": "FULL_MONTH_FROM_NEXT",
        "components": [c2],
    }
    v1["proration_policy"] = "FULL_MONTH_FROM_NEXT"
    e = engagement(None, versions=[v1, v2], end="2027-04-30")
    r = calculate_periods(e, scen(), detail="periods")
    assert [D(p["contractual_fee"]) for p in r["periods"]] == [1000, 1000, 1000, 2000]


def test_t020_dependency_rules():
    e = engagement(
        [
            comp("base", "FIXED_RECURRING", "FIXED", fixed_amount="1000", depends_on=["over"]),
            comp(
                "over",
                "ALLOWANCE_OVERAGE",
                "OUTPUT",
                quantity_source="q",
                unit="unit",
                entitlement_id="ent",
                rate_schedule_id="r",
                depends_on=["base"],
            ),
        ],
        entitlements=[
            {
                "id": "ent",
                "granted_by": "base",
                "unit": "unit",
                "included_quantity": "1",
                "accumulation_period": "MONTH",
                "overage_recognition": "PER_SEGMENT",
            }
        ],
        schedules=[schedule("r")],
    )
    err = [x["code"] for x in validate_engagement(e)["errors"]]
    assert "DEPENDENCY_CYCLE" in err
    assert "DEPENDENCY_MISSING" in err


def test_t024_floor_cap_conflict():
    e = _minimum_engagement()
    e["arrangement_versions"][0]["adjustments"] = [
        {"id": "cap", "type": "CAP", "amount": "4000", "accumulation_period": "MONTH"}
    ]
    rep = validate_engagement(e)
    assert rep["status"] == "requires_contract_interpretation"
    r = calculate_periods(e, scen("s", [("q", "1", "unit", "2027-01")]))
    assert r["status"] == "requires_contract_interpretation"


def test_t025_exact_allocation():
    shares = allocate_exact(D("880000"), 12, 2)
    assert sum(shares) == D("880000")
    assert shares[:4] == [D("73333.34")] * 4 and shares[4:] == [D("73333.33")] * 8


def test_floats_rejected():
    e = engagement([comp("base", "FIXED_RECURRING", "FIXED", fixed_amount=100.5)])
    rep = validate_engagement(e)
    assert not rep["valid"]
    assert any(x["path"].endswith("/fixed_amount") for x in rep["errors"])


def test_adjustments_discount_credit_cap():
    e = engagement(
        [comp("base", "FIXED_RECURRING", "FIXED", fixed_amount="10000")],
        adjustments=[
            {"id": "disc", "type": "DISCOUNT", "percent": "0.10"},
            {
                "id": "sla",
                "type": "SLA_CREDIT",
                "percent": "0.05",
                "cap_percent": "0.08",
                "trigger": "misses",
            },
            {"id": "cap", "type": "CAP", "amount": "20000", "accumulation_period": "YEAR"},
        ],
    )
    s = scen("s", [("misses", "3", "count", "2027-01")], horizon=("2027-01-01", "2027-04-30"))
    r = calculate_periods(e, s, detail="periods")
    jan = D(r["periods"][0]["contractual_fee"])
    # 10000 - 1000 discount = 9000; credit 3 x 5% = 15% capped at 8% -> 720
    assert jan == 9000 - 720
    # cap of 20000 per year binds in the third month
    assert D(r["term"]["contractual_fee"]) == 20000


def test_holdback_and_bonus():
    e = engagement(
        [comp("base", "FIXED_RECURRING", "FIXED", fixed_amount="10000")],
        adjustments=[
            {"id": "hold", "type": "HOLDBACK", "percent": "0.10", "trigger": "released"},
            {
                "id": "bonus",
                "type": "BONUS",
                "percent": "0.02",
                "cap_percent": "0.02",
                "trigger": "hits",
            },
        ],
    )
    s = scen(
        "s",
        [("released", "1", "flag", "2027-02"), ("hits", "1", "count", "2027-02")],
        horizon=("2027-01-01", "2027-02-28"),
    )
    r = calculate_periods(e, s, detail="periods")
    assert [D(p["contractual_fee"]) for p in r["periods"]] == [9000, 10200]


def test_collar_reprices_above_band():
    e = engagement(
        [
            comp(
                "u", "UNIT_OUTPUT", "OUTPUT", quantity_source="q", unit="unit", rate_schedule_id="r"
            )
        ],
        schedules=[schedule("r"), schedule("alt", tiers=[{"from": "0", "to": None, "rate": "8"}])],
        adjustments=[
            {
                "id": "collar",
                "type": "COLLAR",
                "component_id": "u",
                "lower": "50",
                "upper": "100",
                "outside_rate_schedule_id": "alt",
            }
        ],
    )
    r = calculate_periods(
        e, scen("s", [("q", "120", "unit", "2027-01")], horizon=("2027-01-01", "2027-01-31"))
    )
    assert D(r["term"]["contractual_fee"]) == 100 * 10 + 20 * 8


def test_indexation_from_second_contract_year():
    e = engagement(
        [comp("base", "FIXED_RECURRING", "FIXED", fixed_amount="1000")],
        adjustments=[{"id": "idx", "type": "INDEXATION", "percent": "0.03"}],
        end="2028-12-31",
    )
    r = calculate_periods(e, scen(), detail="periods")
    assert D(r["years"]["2027"]["contractual_fee"]) == 12000
    assert D(r["years"]["2028"]["contractual_fee"]) == 12360


def test_explain_fee_traces_steps(spec_example):
    r = explain_fee(spec_example["engagement"], spec_example["scenarios"][0], period="2027-01")
    assert D(r["fee_total"]) == 124000
    kinds = [li["kind"] for li in r["line_items"]]
    assert kinds == ["fixed", "overage"]
    assert any(e["entry_type"] == "CONSUME" for e in r["ledger"])


def test_missing_assumption_points_at_component():
    e = engagement(
        [
            comp(
                "u",
                "UNIT_OUTPUT",
                "OUTPUT",
                quantity_source="scenario.nothing",
                unit="unit",
                rate_schedule_id="r",
            )
        ],
        schedules=[schedule("r")],
    )
    r = calculate_periods(e, scen())
    assert r["status"] == "invalid"
    err = r["issues"]["errors"][0]
    assert err["code"] == "MISSING_ASSUMPTION" and err["path"].endswith(
        "/components/0/quantity_source"
    )


def test_rounding_half_even_period_total():
    e = engagement(
        [
            comp(
                "u", "UNIT_OUTPUT", "OUTPUT", quantity_source="q", unit="unit", rate_schedule_id="r"
            )
        ],
        schedules=[schedule("r", tiers=[{"from": "0", "to": None, "rate": "0.125"}])],
    )
    e["money_policy"] = {
        "rounding_mode": "HALF_EVEN",
        "rounding_scale": 2,
        "rounding_level": "PERIOD_TOTAL",
    }
    r = calculate_periods(
        e, scen("s", [("q", "1", "unit", "2027-01")], horizon=("2027-01-01", "2027-01-31"))
    )
    assert r["term"]["contractual_fee"] == "0.12"
    assert r["money_policy"]["rounding_mode"] == "HALF_EVEN"


def test_unbounded_fixed_fee_needs_approval():
    e = engagement([comp("base", "FIXED_RECURRING", "FIXED", fixed_amount="1000")])
    rep = validate_engagement(e)
    assert "UNBOUNDED_FIXED_FEE_VOLUME" in [a["code"] for a in rep["approvals_required"]]


def test_post_v1_method_rejected():
    e = engagement([comp("x", "OUTCOME_ADJUSTMENT", "OUTCOME")])
    assert "METHOD_NOT_SUPPORTED" in [x["code"] for x in validate_engagement(e)["errors"]]


_ = Decimal
