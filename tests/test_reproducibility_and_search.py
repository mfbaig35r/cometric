"""T-012, T-019 fingerprints; T-030 dominance; T-031 structure search; T-021 cost policy; T-010 capacity."""

import copy

from builders import comp, engagement, scen, schedule
from conftest import D

from cometric import calculate_periods, compare_arrangements, search_structures
from cometric.core.fingerprint import canonical_json


def test_t012_same_inputs_same_outputs(case):
    c = case("e")
    a = calculate_periods(c["engagement"], c["scenarios"][1], "reference", detail="line_items")
    b = calculate_periods(
        copy.deepcopy(c["engagement"]),
        copy.deepcopy(c["scenarios"][1]),
        "reference",
        detail="line_items",
    )
    assert a["input_fingerprint"] == b["input_fingerprint"]
    assert canonical_json(a) == canonical_json(b)


def test_t019_fingerprint_normalization(spec_example):
    e, s = spec_example["engagement"], spec_example["scenarios"][0]
    base = calculate_periods(e, s)["input_fingerprint"]
    e2 = copy.deepcopy(e)
    e2["arrangement_versions"][0]["components"][0]["fixed_amount"] = "100000"
    assert calculate_periods(e2, s)["input_fingerprint"] == base
    e3 = copy.deepcopy(e)
    e3["arrangement_versions"][0]["components"].reverse()
    assert calculate_periods(e3, s)["input_fingerprint"] == base
    e4 = copy.deepcopy(e)
    e4["arrangement_versions"][0]["components"][0]["fixed_amount"] = "100001"
    assert calculate_periods(e4, s)["input_fingerprint"] != base


def test_t021_cost_policy_must_map_every_category(case):
    c = case("a")
    policy = copy.deepcopy(c["cost_policies"]["reference"])
    del policy["mapping"]["TRANSITION"]
    r = calculate_periods(c["engagement"], c["scenarios"][0], policy)
    assert r["status"] == "invalid"
    assert any(e["code"] == "COST_POLICY_INCOMPLETE" for e in r["issues"]["errors"])
    bad = copy.deepcopy(c["cost_policies"]["reference"])
    bad["mapping"]["TRANSITION"] = "NOT_A_LAYER"
    assert calculate_periods(c["engagement"], c["scenarios"][0], bad)["status"] == "invalid"


def test_t010_capacity_breach_modes(case):
    c = case("g")
    s = c["scenarios"][0]
    over = calculate_periods(c["engagement"], s, "reference")
    assert over["status"] == "ok" and any(
        w["code"] == "CAPACITY_BREACH" for w in over["issues"]["warnings"]
    )
    backlog = copy.deepcopy(c["engagement"])
    backlog["delivery_plan"]["breach_mode"] = "BACKLOG"
    r = calculate_periods(backlog, s, "reference")
    assert r["status"] == "ok"
    assert D(r["term"]["capacity"][0]["backlog_end"]) == 2000
    assert D(r["term"]["contractual_fee"]) == 1200000 + 2000 * 120
    for mode in ("INFEASIBLE", None):
        e = copy.deepcopy(c["engagement"])
        e["delivery_plan"]["breach_mode"] = mode
        r = calculate_periods(e, s, "reference")
        assert r["status"] == "infeasible" and r["feasible"] is False


def test_capacity_at_limit_is_not_a_breach(case):
    c = case("a")
    r = calculate_periods(c["engagement"], c["scenarios"][2], "reference")
    assert not any(w["code"] == "CAPACITY_BREACH" for w in r["issues"]["warnings"])


def _three_candidates(case):
    a = case("a")["engagement"]
    worse = copy.deepcopy(a)
    worse["engagement_id"] = "WORSE"
    worse["delivery_plan"]["cost_components"][0]["amount"] = "640000"  # same price, more cost
    alt = copy.deepcopy(a)
    alt["engagement_id"] = "ALT"
    alt["arrangement_versions"][0]["components"][0]["fixed_amount"] = "90000"
    return [
        {"id": "a", "engagement": a},
        {"id": "worse", "engagement": worse},
        {"id": "alt", "engagement": alt},
    ]


def test_t030_dominance_without_ranking(case):
    c = case("a")
    out = compare_arrangements(_three_candidates(case), c["scenarios"], "reference")
    by = {x["id"]: x for x in out["candidates"]}
    # 'worse' charges the same as 'a' but costs more, so 'a' dominates it; 'alt' trades price for contribution
    assert by["worse"]["dominated_by"] == ["a"]
    assert by["alt"]["dominated_by"] == []
    assert set(out["non_dominated"]) == {"a", "alt"}
    assert out["ranking"] is None
    assert "best_under_objective" not in out
    out2 = compare_arrangements(
        _three_candidates(case),
        c["scenarios"],
        "reference",
        objective={"metric": "contribution_profit", "sense": "max", "aggregation": "WORST"},
    )
    assert out2["best_under_objective"] == ["a"]


def test_t031_structure_search(case):
    c = case("a")
    spec = {
        "engagement": c["engagement"],
        "scenarios": c["scenarios"],
        "cost_policy": "reference",
        "parameters": [
            {
                "name": "base_fee",
                "pointer": "/arrangement_versions/0/components/0/fixed_amount",
                "values": ["75000", "100000", "125000"],
            },
            {
                "name": "overage_rate",
                "pointer": "/arrangement_versions/0/rate_schedules/0/tiers/0/rate",
                "values": ["100", "120", "140"],
            },
        ],
    }
    r1 = search_structures(spec)
    r2 = search_structures(copy.deepcopy(spec))
    assert r1["counts"]["enumerated"] == 9
    assert [f["parameters"] for f in r1["frontier"]] == [f["parameters"] for f in r2["frontier"]]
    assert r1["approval_state"] == "PENDING_HUMAN_REVIEW"
    too_big = copy.deepcopy(spec)
    too_big["max_candidates"] = 5
    rej = search_structures(too_big)
    assert rej["status"] == "rejected" and rej["grid_size"] == 9
    constrained = copy.deepcopy(spec)
    constrained["constraints"] = {"not": {"path": "scenarios.*.contribution_margin", "lt": "0.15"}}
    constrained["objective"] = {
        "metric": "contribution_profit",
        "sense": "max",
        "aggregation": "BASE",
    }
    rc = search_structures(constrained)
    assert rc["counts"]["failing_constraints"] > 0
    # base demand (10,000) never reaches overage, so the overage rate ties: all ties are returned
    assert rc["best_under_objective"] == [
        {"base_fee": "125000", "overage_rate": r} for r in ("100", "120", "140")
    ]
    assert rc["best"][0]["constraints"]
    full = search_structures({**constrained, "detail": "full"})
    assert full["frontier"][0]["binding_constraints"]
    invalid = copy.deepcopy(spec)
    invalid["parameters"][0]["values"] = ["100000", "-5", "abc"]
    ri = search_structures(invalid)
    assert ri["counts"]["invalid"] == 3 and sum(ri["invalid_reasons"].values()) >= 3


def test_search_with_range_parameter():
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
                "behavior": "VARIABLE",
                "driver": "q",
                "rate": "5",
            }
        ],
    )
    spec = {
        "engagement": e,
        "scenarios": [
            scen("base", [("q", "1000", "unit", "TERM")]),
            scen("low", [("q", "500", "unit", "TERM")]),
        ],
        "cost_policy": "reference",
        "parameters": [
            {
                "name": "rate",
                "pointer": "/arrangement_versions/0/rate_schedules/0/tiers/0/rate",
                "range": {"from": "6", "to": "8", "step": "1"},
            }
        ],
    }
    r = search_structures(spec)
    assert r["counts"]["enumerated"] == 3
    # higher rate: more contribution, higher client price, so every candidate is on the frontier
    assert r["counts"]["on_frontier"] == 3
