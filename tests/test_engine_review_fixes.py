"""Regression tests for the full-engine code review (one per finding)."""

import copy

from builders import comp, engagement, scen, schedule
from conftest import D

from cometric import calculate_periods, price_floor, validate_engagement


def _two_versions(policy, v1_component_to=None):
    c1 = comp("base", "FIXED_RECURRING", "FIXED", fixed_amount="1000")
    if v1_component_to:
        c1["effective_period"] = {"from": "2027-01-01", "to": v1_component_to}
    v1 = {
        "id": "v1",
        "effective_from": "2027-01-01",
        "effective_to": "2027-03-15",
        "proration_policy": policy,
        "components": [c1],
    }
    c2 = comp("base", "FIXED_RECURRING", "FIXED", fixed_amount="2000")
    c2["effective_period"] = {"from": "2027-03-16", "to": None}
    v2 = {
        "id": "v2",
        "effective_from": "2027-03-16",
        "proration_policy": policy,
        "components": [c2],
    }
    return engagement(None, versions=[v1, v2], end="2027-04-30")


def _march(e):
    r = calculate_periods(e, scen(), detail="periods")
    return D(next(p for p in r["periods"] if p["period"] == "2027-03")["contractual_fee"])


def test_full_month_policies_bill_the_whole_month():  # finding 1
    assert _march(_two_versions("FULL_MONTH_FROM_CURRENT")) == 2000
    assert _march(_two_versions("FULL_MONTH_FROM_NEXT", v1_component_to="2027-03-15")) == 1000


def test_project_payment_in_a_split_month_is_posted():  # finding 2
    v1 = {
        "id": "v1",
        "effective_from": "2027-01-01",
        "effective_to": "2027-03-15",
        "components": [comp("base", "FIXED_RECURRING", "FIXED", fixed_amount="1000")],
    }
    p = comp(
        "proj",
        "FIXED_PROJECT",
        "FIXED",
        "EVENT",
        project_fee="50000",
        payment_schedule=[{"month": "2027-03", "amount": "50000"}],
    )
    p["effective_period"] = {"from": "2027-03-16", "to": None}
    v2 = {
        "id": "v2",
        "effective_from": "2027-03-16",
        "proration_policy": "CALENDAR_DAYS",
        "components": [p],
    }
    e = engagement(None, versions=[v1, v2], end="2027-04-30")
    r = calculate_periods(e, scen())
    expected = (D(1000) * 2 + D(1000) * 15 / 31 + 50000).quantize(D("0.01"))
    assert D(r["term"]["contractual_fee"]) == expected


def _annual_allowance():
    return engagement(
        [
            comp("base", "FIXED_RECURRING", "FIXED", fixed_amount="0"),
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
                "included_quantity": "1200",
                "accumulation_period": "YEAR",
                "overage_recognition": "CUMULATIVE",
            }
        ],
        schedules=[schedule("r", scope="EXCESS_ONLY")],
    )


def test_horizon_after_start_carries_accumulators():  # finding 3
    e = _annual_allowance()
    r = calculate_periods(
        e, scen("s", [("q", "2400", "unit", "2027")], horizon=("2027-07-01", "2027-12-31"))
    )
    # Jan to Jun consume the 1,200 allowance, so every July to December unit is overage at 10
    assert D(r["term"]["overage_fee"]) == 12000
    assert r["horizon"] == {"from": "2027-07", "to": "2027-12"}
    assert any(i["code"] == "PRE_HORIZON_SIMULATED" for i in r["issues"]["info"])
    only_h2 = calculate_periods(
        e,
        scen(
            "s", [("q", "1200", "unit", "2027-07..2027-12")], horizon=("2027-07-01", "2027-12-31")
        ),
    )
    assert any(w["code"] == "PRE_HORIZON_QUANTITIES_MISSING" for w in only_h2["issues"]["warnings"])


def test_one_time_and_annual_fees_keep_their_totals():  # finding 4
    one = comp("setup", "FIXED_RECURRING", "FIXED", "ONE_TIME", fixed_amount="10000")
    one["effective_period"] = {"from": "2027-01-16", "to": None}
    annual = comp("annual", "FIXED_RECURRING", "FIXED", "ANNUAL", fixed_amount="120000")
    annual["effective_period"] = {"from": "2027-01-16", "to": None}
    r = calculate_periods(engagement([one, annual]), scen(), detail="periods")
    assert D(r["periods"][0]["contractual_fee"]) == 10000 + 10000
    assert D(r["term"]["contractual_fee"]) == 130000


def test_collar_reprices_at_the_cumulative_tier_position():  # finding 5
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
                    {"from": "1000", "to": None, "rate": "5"},
                ],
                period="YEAR",
            ),
            schedule("alt", tiers=[{"from": "0", "to": None, "rate": "8"}]),
        ],
        adjustments=[
            {
                "id": "collar",
                "type": "COLLAR",
                "component_id": "u",
                "upper": "100",
                "outside_rate_schedule_id": "alt",
            }
        ],
    )
    r = calculate_periods(e, scen("s", [("q", "1800", "unit", "TERM")]), detail="periods")
    by = {p["period"]: D(p["contractual_fee"]) for p in r["periods"]}
    # December: 150 units at 5 (750); 50 above the band move from 5 to 8 (+150)
    assert by["2027-12"] == 900
    # July straddles the annual tier break: 100 at 10 + 50 at 5, then +150
    assert by["2027-07"] == 1400


def _two_year(recognition, project=False):
    comps = [
        comp("base", "FIXED_RECURRING", "FIXED", fixed_amount="0"),
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
    ]
    if project:
        comps.append(
            comp(
                "proj",
                "FIXED_PROJECT",
                "FIXED",
                "EVENT",
                project_fee="10000",
                payment_schedule=[{"month": "2028-06", "amount": "10000"}],
            )
        )
    return engagement(
        comps,
        entitlements=[
            {
                "id": "ent",
                "granted_by": "base",
                "unit": "unit",
                "included_quantity": "1200",
                "accumulation_period": "YEAR",
                "overage_recognition": recognition,
            }
        ],
        schedules=[schedule("r", scope="EXCESS_ONLY")],
        adjustments=[{"id": "idx", "type": "INDEXATION", "percent": "0.10"}],
        end="2028-12-31",
    )


def test_indexation_treats_cumulative_and_period_end_alike():  # finding 6
    s = scen("s", [("q", "3600", "unit", "TERM")])
    cum = calculate_periods(_two_year("CUMULATIVE"), s)
    pe = calculate_periods(_two_year("PERIOD_END"), s)
    assert cum["term"]["contractual_fee"] == pe["term"]["contractual_fee"]
    proj = calculate_periods(_two_year("CUMULATIVE", project=True), s, detail="line_items")
    project_total = sum(
        D(li["amount"]) for li in proj["line_items"]["fees"] if li["component"] == "proj"
    )
    assert project_total == 10000  # project payments are not indexed


def test_term_cost_starting_later_keeps_its_total():  # finding 7
    e = engagement(
        [comp("base", "FIXED_RECURRING", "FIXED", fixed_amount="50000")],
        costs=[
            {
                "id": "impl",
                "category": "CLIENT_IMPLEMENTATION",
                "behavior": "FIXED",
                "amount": "120000",
                "period": "TERM",
                "effective_period": {"from": "2027-07-01", "to": None},
            }
        ],
    )
    r = calculate_periods(e, scen(), "reference")
    assert D(r["term"]["engagement_avoidable_cost"]) == 120000


def test_incurred_view_ignores_layers_outside_contribution():  # finding 8
    e = engagement(
        [comp("base", "FIXED_RECURRING", "FIXED", fixed_amount="50000")],
        costs=[
            {
                "id": "eng",
                "category": "REUSABLE_ENGINEERING",
                "behavior": "ONE_TIME",
                "amount": "120000",
                "amortize_months": 12,
            }
        ],
    )
    r = calculate_periods(e, scen(), "reference", detail="periods")
    jan = r["periods"][0]
    assert jan["cumulative_contribution_incurred"] == jan["cumulative_contribution"]


def test_missing_trigger_quantity_is_an_error():  # finding 9
    e = engagement(
        [comp("base", "FIXED_RECURRING", "FIXED", fixed_amount="1000")],
        adjustments=[
            {
                "id": "sla",
                "type": "SLA_CREDIT",
                "percent": "0.05",
                "cap_percent": "0.1",
                "trigger": "misses_typo",
            }
        ],
    )
    r = calculate_periods(e, scen("s", [("misses", "2", "count", "TERM")]))
    assert r["status"] == "invalid"
    assert (
        r["issues"]["errors"][0]["path"]
        == "/engagement/arrangement_versions/0/adjustments/0/trigger"
    )


def test_price_floor_without_costs_returns_an_issue():  # finding 10
    e = engagement([comp("base", "FIXED_RECURRING", "FIXED", fixed_amount="1000")])
    r = price_floor(e, [scen()], "reference", "0.2")
    assert r["status"] == "invalid" and r["issues"]["errors"][0]["code"] == "COSTS_NOT_EVALUATED"


def test_quarterly_share_is_anchored_at_component_start():  # lower severity
    q = comp("q", "FIXED_RECURRING", "FIXED", "QUARTERLY", fixed_amount="100")
    q["effective_period"] = {"from": "2027-02-01", "to": None}
    r = calculate_periods(engagement([q], end="2027-04-30"), scen(), detail="periods")
    # January precedes the component; the first quarter runs February to April
    assert [D(p["contractual_fee"]) for p in r["periods"]] == [
        0,
        D("33.34"),
        D("33.33"),
        D("33.33"),
    ]


def test_contract_year_honors_start_day():  # lower severity
    c = comp("base", "FIXED_RECURRING", "FIXED", fixed_amount="1000")
    c["effective_period"] = {"from": "2027-01-16", "to": None}
    e = engagement(
        [c],
        adjustments=[{"id": "idx", "type": "INDEXATION", "percent": "0.10"}],
        start="2027-01-16",
        end="2028-03-31",
    )
    e["arrangement_versions"][0]["proration_policy"] = "CALENDAR_DAYS"
    r = calculate_periods(e, scen(), detail="periods")
    by = {p["period"]: D(p["contractual_fee"]) for p in r["periods"]}
    assert by["2028-01"] == 1000 and by["2028-02"] == 1100


def test_rebate_settled_after_horizon_is_flagged():  # lower severity
    e = engagement(
        [comp("base", "FIXED_RECURRING", "FIXED", fixed_amount="1000")],
        adjustments=[
            {"id": "reb", "type": "REBATE", "percent": "0.05", "accumulation_period": "YEAR"}
        ],
    )
    r = calculate_periods(e, scen(horizon=("2027-01-01", "2027-06-30")))
    assert any(w["code"] == "TRUE_UP_OUTSIDE_HORIZON" for w in r["issues"]["warnings"])


def test_component_order_does_not_change_results():  # lower severity (fingerprint sorts components)
    def build(order):
        comps = [
            comp("base", "FIXED_RECURRING", "FIXED", fixed_amount="0"),
            comp(
                "a",
                "ALLOWANCE_OVERAGE",
                "OUTPUT",
                quantity_source="qa",
                unit="unit",
                entitlement_id="ent",
                rate_schedule_id="ra",
                depends_on=["ent"],
            ),
            comp(
                "b",
                "ALLOWANCE_OVERAGE",
                "OUTPUT",
                quantity_source="qb",
                unit="unit",
                entitlement_id="ent",
                rate_schedule_id="rb",
                depends_on=["ent"],
            ),
        ]
        return engagement(
            [comps[i] for i in order],
            entitlements=[
                {
                    "id": "ent",
                    "granted_by": "base",
                    "unit": "unit",
                    "included_quantity": "100",
                    "accumulation_period": "MONTH",
                    "overage_recognition": "PER_SEGMENT",
                }
            ],
            schedules=[
                schedule("ra", tiers=[{"from": "0", "to": None, "rate": "1"}]),
                schedule("rb", tiers=[{"from": "0", "to": None, "rate": "9"}]),
            ],
        )

    s = scen(
        "s",
        [("qa", "80", "unit", "2027-01"), ("qb", "80", "unit", "2027-01")],
        horizon=("2027-01-01", "2027-01-31"),
    )
    r1 = calculate_periods(build([0, 1, 2]), s)
    r2 = calculate_periods(build([0, 2, 1]), s)
    assert r1["input_fingerprint"] == r2["input_fingerprint"]
    assert r1["term"]["contractual_fee"] == r2["term"]["contractual_fee"]


_ = (copy, validate_engagement)
