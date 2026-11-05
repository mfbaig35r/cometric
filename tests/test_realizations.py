"""Realizations, priorities, signals, and composition rules in pack data (propose spec A7; P17)."""

import copy
import dataclasses
from decimal import Decimal

import pytest

from cometric.core import realizations as R
from cometric.core.api import calculate_periods
from cometric.core.issues import Issues
from cometric.core.models import Engagement
from cometric.core.packs import evaluate_rules, load_pack, validate_pack


def _pack_with(realizations):
    base = load_pack("base")
    return dataclasses.replace(base, realizations=realizations)


@pytest.mark.parametrize("pack", ["base", "alsp", "consulting"])
def test_packs_validate(pack):
    assert validate_pack(pack) == []


def test_p17_unknown_concept_and_bad_label_are_rejected():
    bad = copy.deepcopy(load_pack("base").realizations)
    model = next(r for r in bad if r["id"] == "PM-011")
    model["labels"]["volume_shortfall"] = "SOMEONE"
    bad.append({"id": "CL-NOPE", "kind": "lever", "effects": {"mood": {"A": "B"}}})
    problems = R.check_realizations(_pack_with(bad))
    assert any("PM-011" in p and "SOMEONE" in p for p in problems)
    assert any("CL-NOPE is not a lever" in p for p in problems)
    assert any("unknown effect axis 'mood'" in p for p in problems)


def test_p17_a_fragment_that_does_not_calculate_is_rejected():
    bad = copy.deepcopy(load_pack("base").realizations)
    model = next(r for r in bad if r["id"] == "PM-011")
    model["fragment"]["per_unit"]["components"][0]["rate_schedule_id"] = "missing_{u}"
    problems = R.check_realizations(_pack_with(bad))
    assert problems and all("PM-011" in p for p in problems)
    assert any("UNKNOWN_RATE_SCHEDULE" in p for p in problems)


def _shape(**kw):
    defaults = dict(
        kind="COUNT",
        tiers=["high", "low"],
        packs=["alsp"],
        service_category="CONTRACTS",
        cost_shape="MIXED",
        fixed_team=True,
        certainty="RANGE",
        expected=Decimal("1200"),
        low=Decimal("400"),
        high=Decimal("1500"),
        period="YEAR",
        term_months=24,
        early_exit=True,
    )
    defaults.update(kw)
    return R.Shape(**defaults)


def test_labels_follow_lever_effects_and_cost_shape():
    reals = R.realizations(["alsp"])
    unit, minimum, cap = reals["PM-011"], reals["CL-R01"], reals["CL-V07"]
    assert R.composition_labels(_shape(), unit, [])["volume_shortfall"] == "PROVIDER"
    variable = R.composition_labels(
        _shape(cost_shape="MOSTLY_VARIABLE", fixed_team=False), unit, []
    )
    assert variable["volume_shortfall"] == "NONE_ADVERSE"
    assert variable["early_exit"] == "NONE_ADVERSE"
    both = R.composition_labels(_shape(), unit, [cap, minimum])
    assert both["volume_shortfall"] == "SHARED"
    assert both["spend_variability"] == "BOUNDED"
    assert both["volume_excess"] == "PROVIDER"
    assert "mix" not in R.composition_labels(_shape(tiers=[]), unit, [])


def test_lever_applicability_uses_the_whole_composition():
    reals = R.realizations(["alsp"])
    prorated = reals["CL-P14.prorated"]
    assert R.lever_applies(prorated, reals["PM-011"], _shape())
    assert R.lever_applies(prorated, reals["PM-011"], _shape(), [reals["CL-R01"]]) is None
    assert R.lever_applies(reals["CL-R01"], reals["PM-007"], _shape())


def test_scenario_stubs_carry_profile_figures_and_placeholders():
    stubs = R.scenario_stubs(_shape(), [])
    assert [s["id"] for s in stubs] == ["low", "expected", "high", "early_exit"]
    expected = stubs[1]
    total = next(a for a in expected["assumptions"] if a["name"] == "units_total")
    assert total["value"] == "2400"  # 1,200 a year over 24 months
    assert [d["name"] for d in expected["derived"]] == ["units.high", "units.low"]
    assert stubs[3]["termination_date"].startswith("<required:")
    unknown = R.scenario_stubs(_shape(certainty="UNKNOWN", expected=None, low=None, high=None), [])
    assert [s["id"] for s in unknown] == ["expected", "early_exit"]
    assert unknown[0]["assumptions"][0]["value"].startswith("<required:")


def test_composition_rules_are_not_evaluated_against_engagements():
    reals = R.realizations(["alsp"])
    shape = _shape()
    eng = R.sample_fill(
        {"engagement": R.assemble_engagement(shape, reals["PM-011"], []), "scenarios": []}
    )["engagement"]
    fired = evaluate_rules(Engagement.model_validate(eng), Issues())
    assert not any(f["rule"].startswith("COMP-") for f in fired)


def test_filled_skeleton_calculates():
    reals = R.realizations(["alsp"])
    shape = _shape()
    levers = [reals["CL-R01"], reals["CL-P14.prorated"]]
    skel = {
        "engagement": R.assemble_engagement(shape, reals["PM-011"], levers),
        "scenarios": R.scenario_stubs(shape, R.extra_assumptions(levers)),
    }
    assert R.check_skeleton(skel) == []
    commitment = skel["engagement"]["arrangement_versions"][0]["commitments"][0]
    assert commitment["termination_rule"] == "PRORATE"
    filled = R.sample_fill(skel)
    r = calculate_periods(filled["engagement"], filled["scenarios"][1], "reference")
    assert r["status"] == "ok"
