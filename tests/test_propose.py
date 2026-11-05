"""propose_structures acceptance tests (propose spec A10, P01 to P16)."""

import copy
import json
import re

import pytest

from cometric.core import api
from cometric.core.packs import pack_chain
from cometric.core.propose import propose_structures
from cometric.core.realizations import check_skeleton, sample_fill
from cometric.core.validation import find_placeholders, validate_engagement

PROFILE = {
    "service_category": "CONTRACTS",
    "unit_of_work": {
        "kind": "COUNT",
        "description": "Contract review requests",
        "tiers": ["high", "medium", "low"],
    },
    "volume": {
        "certainty": "RANGE",
        "expected": "1200",
        "low": "400",
        "high": "1500",
        "period": "YEAR",
    },
    "cost_profile": {"shape": "MIXED", "fixed_team": True},
    "client_priorities": ["budget_certainty", "pay_for_use"],
    "provider_constraints": {"max_volume_risk": "SHARED"},
    "term": {"months": 24, "client_can_terminate_early": True, "notice_days": 90},
}


def propose(profile=None, **options):
    return propose_structures(["alsp"], profile or copy.deepcopy(PROFILE), options)


def profile(**changes):
    p = copy.deepcopy(PROFILE)
    for path, value in changes.items():
        *head, last = path.split("__")
        node = p
        for h in head:
            node = node[h]
        node[last] = value
    return p


# Values a partner might supply, keyed by placeholder label (prefix match). Used to fill
# skeletons for the comparison and risk checks; they are test fixtures, not proposals.
FIXTURE = [
    ("number of FTE", "6"),
    ("rate per FTE-month", "15000"),
    ("monthly fee", "100000"),
    ("monthly base fee", "60000"),
    ("included volume per month", "100"),
    ("overage rate", "1200"),
    ("unit rate below the band boundary", "1100"),
    ("unit rate above the band boundary", "900"),
    ("unit rate outside the volume band", "1300"),
    ("unit rate", "1000"),
    ("rate per weighted unit", "800"),
    ("complexity weight, tier high", "2"),
    ("complexity weight, tier medium", "1"),
    ("complexity weight, tier low", "0.5"),
    ("volume band boundary", "300"),
    ("lower volume bound", "18"),
    ("upper volume bound", "60"),
    ("minimum spend per contract year", "800000"),
    ("fee cap per contract year", "1400000"),
    ("what the minimum owes", "PRORATE"),
    ("termination fee", "50000"),
    ("delivery team cost per month", "30000"),
    ("delivery cost per unit", "300"),
    ("share of volume as a fraction, tier high", "0.2"),
    ("share of volume as a fraction, tier medium", "0.3"),
    ("share of volume as a fraction, tier low", "0.5"),
]


def fixture_fill(skeleton):
    def fill(obj):
        if isinstance(obj, dict):
            return {k: fill(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [fill(v) for v in obj]
        if isinstance(obj, str) and obj.startswith("<required:"):
            label = obj[len("<required:") : -1].strip()
            for prefix, value in FIXTURE:
                if label.startswith(prefix):
                    return value
        return obj

    return sample_fill(fill(skeleton))


@pytest.fixture(scope="module")
def a4():
    r = propose()
    assert r["status"] == "ok", r
    return r


def test_p01_spans_groups_with_a_unit_structure_and_a_bounded_alternative(a4):
    groups = {c["risk_allocation"]["volume_shortfall"] for c in a4["candidates"]}
    assert len(groups) >= 2
    unit_models = ("base:PM-011", "base:PM-014", "base:PM-015")
    assert any(
        c["composition"]["base_model"] in unit_models
        and "base:CL-R01" in c["composition"]["levers"]
        for c in a4["candidates"]
    )
    assert any(c["risk_allocation"]["spend_variability"] == "BOUNDED" for c in a4["candidates"])


def test_p02_expanded_skeletons_validate_except_placeholders(a4):
    ids = [c["id"] for c in a4["candidates"]]
    r = propose(expand=ids)
    for c in r["candidates"]:
        assert c["skeleton"] is not None
        assert check_skeleton(c["skeleton"]) == [], c["id"]
        errors = validate_engagement(c["skeleton"]["engagement"])["errors"]
        assert errors and {e["code"] for e in errors} == {"REQUIRED_FIELD"}
        labels = {lab for _, lab in find_placeholders(c["skeleton"])}
        assert all(labels), "every placeholder is labelled"


def test_p03_compare_rejects_unfilled_skeleton(a4):
    r = propose(expand=[a4["candidates"][0]["id"]])
    skel = r["candidates"][0]["skeleton"]
    out = api.compare_arrangements([skel["engagement"]], skel["scenarios"], "reference")
    cand = out["candidates"][0]
    assert cand["valid"] is False
    assert all(e["code"] == "REQUIRED_FIELD" for e in cand["errors"])


def test_p04_filled_skeletons_compare_on_the_shared_scenarios(a4):
    r = propose(expand=[c["id"] for c in a4["candidates"]])
    filled = [fixture_fill(c["skeleton"]) for c in r["candidates"]]
    scenarios = filled[0]["scenarios"]
    assert all(f["scenarios"] == scenarios for f in filled)
    out = api.compare_arrangements([f["engagement"] for f in filled], scenarios, "reference")
    assert out["status"] == "ok"
    for c in out["candidates"]:
        assert c["valid"] and c["feasible"], c


def test_p05_deterministic_and_pack_version_changes_fingerprint(a4):
    again = propose()
    assert again == a4
    meta = pack_chain("alsp")[0].meta
    old = meta["version"]
    try:
        meta["version"] = "9.9.9"
        assert propose()["fingerprint"] != a4["fingerprint"]
    finally:
        meta["version"] = old


def test_p06_no_money_or_percentages(a4):
    r = propose(expand=[c["id"] for c in a4["candidates"]])
    strings = []

    def walk(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k not in ("schema_version", "fingerprint", "id", "engagement_id"):
                    walk(v)
        elif isinstance(obj, list):
            for v in obj:
                walk(v)
        elif isinstance(obj, str):
            strings.append(obj)

    walk(r)
    text = " ".join(strings)
    assert "%" not in text and "$" not in text
    supplied = {"1200", "400", "1500", "24", "90"}
    term_totals = {"2400", "800", "3000"}  # the supplied yearly volumes over 24 months
    text = re.sub(r"\b[A-Z]+(?:-[A-Z]+)?-\d+\w*", "", text)  # concept, rule, claim ids
    numbers = set(re.findall(r"(?<![\w.])\d+(?:\.\d+)?(?![\w.])", text))
    # "0" is a tier's lower bound and "12" the months in a year; neither is a price
    assert numbers <= supplied | term_totals | {"0", "12"}, numbers


def test_p07_composition_rule_exclusions_are_reported(a4):
    rules = {e["rule"]: e for e in a4["excluded"]}
    assert "base:COMP-002" in rules
    assert rules["base:COMP-002"]["compositions"] > 0
    assert "+" in rules["base:COMP-002"]["example"]


def test_p08_partner_lever_preferences():
    r = propose(exclude_levers=["CL-R01"])
    assert all("base:CL-R01" not in c["composition"]["levers"] for c in r["candidates"])
    r = propose(include_levers=["CL-V07"])
    for c in r["candidates"]:
        unit = c["composition"]["base_model"] in ("base:PM-011", "base:PM-014", "base:PM-015")
        assert unit == ("base:CL-V07" in c["composition"]["levers"])
    na = {(x["lever"], x["model"]) for x in r["levers_not_applicable"]}
    assert ("base:CL-V07", "base:PM-007") in na or ("base:CL-V07", "base:PM-004") in na


def test_p08_include_by_concept_accepts_any_variant():
    r = propose(include_levers=["CL-P14"])
    assert r["candidates"]
    for c in r["candidates"]:
        assert any(lv.startswith("base:CL-P14") for lv in c["composition"]["levers"])
        assert c["risk_allocation"]["early_exit"] in ("CLIENT", "SHARED")


def test_p09_unknown_volume():
    p = profile(volume={"certainty": "UNKNOWN"}, client_priorities=["pay_for_use"])
    p["provider_constraints"] = {"max_volume_risk": "ANY"}
    r = propose(p)
    assert any(w["code"] == "VOLUME_UNKNOWN" for w in r["warnings"])
    assert any(
        "base:CL-V08" in c["composition"]["levers"]
        or c["composition"]["base_model"] == "base:PM-014"
        for c in r["candidates"]
    )
    r = propose(p, expand=[r["candidates"][0]["id"]])
    scenarios = r["candidates"][0]["skeleton"]["scenarios"]
    assert [s["id"] for s in scenarios] == ["expected", "early_exit"]
    assert scenarios[0]["assumptions"][0]["value"].startswith("<required:")


def test_p10_early_exit(a4):
    r = propose(expand=[c["id"] for c in a4["candidates"]])
    for c in r["candidates"]:
        assert c["skeleton"]["scenarios"][-1]["id"] == "early_exit"
        assert "early_exit" in c["risk_allocation"]
    no_exit = propose(profile(term={"months": 24}))
    assert all("early_exit" not in c["risk_allocation"] for c in no_exit["candidates"])


def test_p11_evidence_on_every_candidate(a4):
    for c in a4["candidates"]:
        concepts = [e["concept"] for e in c["evidence"]]
        assert concepts[0] == c["composition"]["base_model"]
        for e in c["evidence"]:
            assert e["class"] and e["prevalence"]
            weak = e["class"] in ("C_INFERENCE", "D_PROPOSED") or e["prevalence"] == "UNVERIFIED"
            assert (e.get("flag") == "WEAK") >= weak


@pytest.mark.parametrize(
    "change,path,hint",
    [
        ({"unit_of_wrk": {}}, "/deal_profile/unit_of_wrk", "unit_of_work"),
        (
            {"client_priorities": ["budget_certanty"]},
            "/deal_profile/client_priorities/0",
            "budget_certainty",
        ),
        ({"service_category": "CONTRCTS"}, "/deal_profile/service_category", "CONTRACTS"),
    ],
)
def test_p12_unknown_values_name_the_nearest(change, path, hint):
    p = copy.deepcopy(PROFILE)
    p.update(change)
    r = propose(p)
    assert r["status"] == "invalid"
    err = next(e for e in r["issues"]["errors"] if e["path"] == path)
    assert hint in err.get("hint", ""), err


def test_p12_unknown_unit_kind_and_lever():
    r = propose(profile(unit_of_work__kind="COUNTS"), include_levers=["CL-V77"])
    paths = {e["path"]: e for e in r["issues"]["errors"]}
    assert "COUNT" in paths["/deal_profile/unit_of_work/kind"].get("hint", "")
    assert "/options/include_levers/0" not in paths  # profile errors stop before options checks
    r = propose(include_levers=["CL-V77"])
    assert "CL-V07" in r["issues"]["errors"][0]["hint"]


def test_p13_summary_size(a4):
    assert len(a4["candidates"]) == 4
    assert len(json.dumps(a4, separators=(",", ":"))) < 8000


def test_p14_order_note_and_no_ranking_language(a4):
    assert a4["order_note"].startswith("Candidates are grouped")
    text = json.dumps({k: v for k, v in a4.items() if k != "order_note"}).lower()
    for word in ("rank", "recommend", "best ", "preferred"):
        assert word not in text, word
    order = ["CLIENT", "SHARED", "PROVIDER", "NONE_ADVERSE"]
    groups = [order.index(c["risk_allocation"]["volume_shortfall"]) for c in a4["candidates"]]
    assert groups == sorted(groups)


def test_p15_max_volume_risk_none():
    r = propose(profile(provider_constraints={"max_volume_risk": "NONE"}))
    assert r["candidates"]
    assert {c["risk_allocation"]["volume_shortfall"] for c in r["candidates"]} == {"CLIENT"}


def test_p16_labels_agree_with_derived_exposure():
    p = profile(provider_constraints={"max_volume_risk": "ANY"})
    r = propose(p, max_candidates=6)
    r = propose(p, max_candidates=6, expand=[c["id"] for c in r["candidates"]])
    seen = set()
    for c in r["candidates"]:
        filled = fixture_fill(c["skeleton"])
        results = [
            {"scenario_id": s["id"], **api.calculate_periods(filled["engagement"], s, "reference")}
            for s in filled["scenarios"]
            if s["id"] in ("expected", "low")
        ]
        assert all(x["status"] == "ok" for x in results), c["id"]
        exposure = api.derive_risk_exposure(
            results, "expected", {"provider_relative": "0.05", "client_relative": "0.05"}
        )
        derived = exposure["deviations"][0]["derived_bearer"]
        declared = c["risk_allocation"]["volume_shortfall"]
        assert derived == declared, (c["id"], declared, derived)
        seen.add(declared)
    assert {"CLIENT", "SHARED", "PROVIDER"} <= seen


def test_expand_unknown_candidate_suggests_nearest(a4):
    first = a4["candidates"][0]["id"]
    r = propose(expand=[first + "x"])
    assert r["status"] == "invalid"
    assert first in r["issues"]["errors"][0]["hint"]
