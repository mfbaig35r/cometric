"""Items 3 and 4 of the LLM feedback: search answers the question; results are compact."""

import copy
import json

from builders import comp, engagement, scen, schedule
from conftest import D

from cometric import calculate_periods, compare_arrangements, search_structures

BASE_PTR = "/arrangement_versions/0/components/0/fixed_amount"
RATE_PTR = "/arrangement_versions/0/rate_schedules/0/tiers/0/rate"


def _spec(case, **extra):
    c = case("a")
    spec = {
        "engagement": c["engagement"],
        "scenarios": c["scenarios"],
        "cost_policy": "reference",
        "parameters": [
            {"name": "base_fee", "pointer": BASE_PTR, "values": ["90000", "100000", "110000"]},
            {"name": "overage_rate", "pointer": RATE_PTR, "values": ["100", "120", "140"]},
        ],
        "objective": {"metric": "contribution_profit", "sense": "max", "aggregation": "WORST"},
    }
    spec.update(extra)
    return spec


def test_best_has_full_figures_constraints_edges_and_baseline(case):
    out = search_structures(
        _spec(case, constraints={"not": {"path": "scenarios.*.contribution_margin", "lt": "0.10"}})
    )
    best = out["best"][0]
    assert list(out)[:4] == ["status", "approval_state", "record_type", "best"]
    assert set(best["scenarios"]) == {"low", "base", "high"}
    assert best["scenarios"]["base"]["contractual_fee"]
    assert best["fingerprints"] and best["constraints"][0]["path"].startswith("scenarios.")
    # the winner charges the highest base fee in the grid: flagged as an edge
    assert {"parameter": "base_fee", "edge": "upper", "value": "110000"} in best["grid_edges"]
    assert out["warnings"][0]["code"] == "BEST_AT_GRID_EDGE"
    # baseline is the engagement as given (base fee 100000): +10,000/month in every scenario
    assert D(best["vs_baseline"]["base"]["contractual_fee"]) == 120000


def test_tie_breakers_resolve_ties(case):
    plain = search_structures(_spec(case))
    assert len(plain["best"]) == 3  # overage rate never matters in the worst (low) scenario
    tb = _spec(case)
    tb["objective"]["tie_breakers"] = [
        {"metric": "contribution_profit", "sense": "max", "aggregation": "MEAN"}
    ]
    broken = search_structures(tb)
    assert len(broken["best"]) == 1 and broken["best"][0]["parameters"]["overage_rate"] == "140"


def test_linked_and_scaled_parameters():
    e = engagement(
        [
            comp(
                "a",
                "UNIT_OUTPUT",
                "OUTPUT",
                quantity_source="qa",
                unit="unit",
                rate_schedule_id="ra",
            ),
            comp(
                "b",
                "UNIT_OUTPUT",
                "OUTPUT",
                quantity_source="qb",
                unit="unit",
                rate_schedule_id="rb",
            ),
        ],
        schedules=[
            schedule("ra", tiers=[{"from": "0", "to": None, "rate": "100"}]),
            schedule("rb", tiers=[{"from": "0", "to": None, "rate": "50"}]),
        ],
        client_value_unit="qa+qb",
    )
    s = scen("base", [("qa", "10", "unit", "TERM"), ("qb", "10", "unit", "TERM")])
    spec = {
        "engagement": e,
        "scenarios": [s],
        "parameters": [
            {
                "name": "uplift",
                "pointers": [
                    "/arrangement_versions/0/rate_schedules/0/tiers/0/rate",
                    "/arrangement_versions/0/rate_schedules/1/tiers/0/rate",
                ],
                "transform": "scale",
                "values": ["0", "0.10"],
            }
        ],
        "objective": {"metric": "contractual_fee", "sense": "max"},
        "include_baseline": False,
    }
    out = search_structures(spec)
    assert out["counts"]["enumerated"] == 2
    # 10% on both tiers: (100 + 50) x 10 x 1.1
    assert D(out["best"][0]["scenarios"]["base"]["contractual_fee"]) == 1650
    assert out["baseline"] is None


def test_dry_run_sizes_without_running(case):
    out = search_structures(_spec(case, dry_run=True))
    assert out["status"] == "dry_run" and out["grid_size"] == 9 and out["calculations"] == 27
    assert out["values_per_parameter"] == {"base_fee": 3, "overage_rate": 3}


def test_bad_pointer_and_transform_are_clear(case):
    bad = search_structures(
        _spec(case, parameters=[{"name": "x", "pointer": "/nope/0", "values": ["1"]}])
    )
    assert bad["status"] == "invalid" and bad["issues"]["errors"][0]["code"] == "BAD_POINTER"
    bad2 = search_structures(
        _spec(
            case,
            parameters=[{"name": "x", "pointer": BASE_PTR, "transform": "cube", "values": ["1"]}],
        )
    )
    assert bad2["issues"]["errors"][0]["path"] == "/parameters/0/transform"


def test_summary_is_compact_and_full_keeps_everything(case):
    summary = search_structures(_spec(case))
    full = search_structures(_spec(case, detail="full", precision="exact"))
    assert len(json.dumps(summary)) < len(json.dumps(full)) / 2
    assert set(summary["frontier"][0]) == {"parameters"}
    assert "risk_exposure" in full["frontier"][0]


def test_display_precision(case):
    c = case("a")
    r = compare_arrangements([c["engagement"]], c["scenarios"], "reference")
    margin = r["candidates"][0]["scenarios"]["base"]["contribution_margin"]
    assert len(margin.split(".")[1]) <= 4
    exact = compare_arrangements([c["engagement"]], c["scenarios"], "reference", precision="exact")
    assert len(exact["candidates"][0]["scenarios"]["base"]["contribution_margin"].split(".")[1]) > 4


def test_compare_detail_levels(case):
    c = case("a")
    alt = copy.deepcopy(c["engagement"])
    alt["engagement_id"] = "ALT"
    summary = compare_arrangements([c["engagement"], alt], c["scenarios"], "reference")
    full = compare_arrangements([c["engagement"], alt], c["scenarios"], "reference", detail="full")
    assert "risk_exposure" not in summary["candidates"][0]
    assert "risk_exposure" in full["candidates"][0]
    assert set(summary["candidates"][0]["scenarios"]["base"]) <= {
        "contractual_fee",
        "contribution_profit",
        "contribution_margin",
        "effective_client_unit_price",
        "overage_fee",
        "commitment_shortfall",
    }


def test_calculate_precision_option(case):
    c = case("a")
    exact = calculate_periods(c["engagement"], c["scenarios"][1], "reference")
    display = calculate_periods(
        c["engagement"], c["scenarios"][1], "reference", precision="display"
    )
    assert len(exact["term"]["contribution_margin"]) > len(display["term"]["contribution_margin"])
    assert exact["input_fingerprint"] == display["input_fingerprint"]
