"""Labelled placeholders and the pack-aware template index (propose_structures B0; P03, P18)."""

import copy

import pytest

from cometric.core import api
from cometric.core.templates import fill_template, get_template, list_templates
from cometric.core.validation import find_placeholders, validate_engagement


def _filled(template_id="tiered_units_annual_minimum", pack="alsp"):
    t = get_template(template_id, pack)
    return fill_template(t, t["examples"])


def test_labelled_placeholder_is_reported_with_its_label():
    doc = _filled()
    doc["engagement"]["arrangement_versions"][0]["commitments"][0]["amount"] = (
        "<required: minimum spend per year>"
    )
    errors = validate_engagement(doc["engagement"])["errors"]
    assert errors == [
        {
            "code": "REQUIRED_FIELD",
            "severity": "ERROR",
            "message": "this field must be filled in: minimum spend per year",
            "path": "/engagement/arrangement_versions/0/commitments/0/amount",
            "detail": {"required_input": "minimum spend per year"},
        }
    ]


def test_unlabelled_placeholder_unchanged():
    t = get_template("time_and_materials")
    required = [
        e for e in validate_engagement(t["engagement"])["errors"] if e["code"] == "REQUIRED_FIELD"
    ]
    assert required and all(e["message"] == "this field must be filled in" for e in required)
    assert all("detail" not in e for e in required)


def test_find_placeholders_ignores_lookalikes():
    doc = {"a": "<required: x>", "b": ["<required>", "<required"], "c": "required: y"}
    assert find_placeholders(doc) == [("/a", "x"), ("/b/0", "")]


def test_scenario_placeholders_are_reported():
    doc = _filled()
    sc = copy.deepcopy(doc["scenario"])
    sc["assumptions"][0]["value"] = "<required: expected volume, tier 1>"
    r = api.calculate_periods(doc["engagement"], sc, "reference")
    assert r["status"] == "invalid"
    errs = [e for e in r["issues"]["errors"] if e["code"] == "REQUIRED_FIELD"]
    assert [e["path"] for e in errs] == ["/scenario/assumptions/0/value"]
    assert errs[0]["detail"]["required_input"] == "expected volume, tier 1"


def test_p03_compare_lists_every_placeholder():
    doc = _filled()
    eng = copy.deepcopy(doc["engagement"])
    eng["arrangement_versions"][0]["commitments"][0]["amount"] = "<required: minimum spend>"
    eng["arrangement_versions"][0]["rate_schedules"][0]["tiers"][0]["rate"] = (
        "<required: unit rate, tier 1>"
    )
    r = api.compare_arrangements([eng], [doc["scenario"]], "reference")
    cand = r["candidates"][0]
    assert cand["valid"] is False
    labels = sorted(e["detail"]["required_input"] for e in cand["errors"])
    assert labels == ["minimum spend", "unit rate, tier 1"]


def test_p03_search_rejects_placeholders_unless_a_parameter_writes_them():
    doc = _filled()
    eng = copy.deepcopy(doc["engagement"])
    ptr = "/arrangement_versions/0/commitments/0/amount"
    eng["arrangement_versions"][0]["commitments"][0]["amount"] = "<required: minimum spend>"
    spec = {
        "engagement": eng,
        "scenarios": [doc["scenario"]],
        "cost_policy": "reference",
        "parameters": [{"name": "rate", "pointer": "/currency", "values": ["USD"]}],
    }
    r = api.search_structures(spec)
    assert r["status"] == "invalid"
    assert [e["path"] for e in r["issues"]["errors"]] == ["/engagement" + ptr]
    spec["parameters"] = [{"name": "minimum", "pointer": ptr, "values": ["100000", "150000"]}]
    assert api.search_structures(spec)["status"] == "ok"


def test_p18_list_templates_includes_pack_templates():
    entries = {(t["template_id"], t["source"]) for t in list_templates()}
    assert ("tiered_units_annual_minimum", "alsp") in entries
    assert ("role_based_tm", "consulting") in entries
    assert ("time_and_materials", "core") in entries
    assert {t["source"] for t in list_templates("consulting")} == {"consulting"}
    with pytest.raises(KeyError):
        list_templates("nope")


@pytest.mark.parametrize(
    "tid,pack", [(t["template_id"], t["source"]) for t in list_templates() if t["source"] != "core"]
)
def test_pack_template_round_trip(tid, pack):
    doc = _filled(tid, pack)
    assert validate_engagement(doc["engagement"])["valid"]
    assert api.calculate_periods(doc["engagement"], doc["scenario"], "reference")["status"] == "ok"
