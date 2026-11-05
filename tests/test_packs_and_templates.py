"""T-011, T-027, T-028, T-029, T-032, T-033; pack rules and lookup."""

import ast
import hashlib
import json
import re
import shutil
from pathlib import Path

import pytest
import yaml
from builders import comp, engagement

from cometric import (
    calculate_periods,
    check_commercial_constraints,
    describe_pack,
    describe_schema,
    get_template,
    list_templates,
    list_vocabulary,
    lookup_concept,
    validate_engagement,
)
from cometric.core import packs as packs_mod
from cometric.core.templates import fill_template

SRC = Path(__file__).resolve().parents[1] / "src" / "cometric"
REPORT = Path(__file__).resolve().parents[1] / "docs" / "alsp-commercial-models-deep-research.md"


def test_t032_shipped_packs_validate():
    for p in ("base", "alsp", "consulting"):
        assert packs_mod.validate_pack(p) == []


def test_t032_broken_pack_fails(tmp_path):
    root = tmp_path / "packs"
    shutil.copytree(SRC / "packs" / "base", root / "base")
    f = root / "base" / "concepts" / "pricing_models.yaml"
    doc = yaml.safe_load(f.read_text())
    doc["concepts"][0]["related"] = ["NOPE-1"]
    doc["concepts"][1]["id"] = doc["concepts"][0]["id"]
    doc["concepts"][2]["bases"] = ["NOT_A_BASIS"]
    f.write_text(yaml.safe_dump(doc))
    (root / "base" / "evil.py").write_text("print('x')")
    packs_mod.load_pack.cache_clear()
    problems = packs_mod.validate_pack("base", str(root))
    packs_mod.load_pack.cache_clear()
    text = "\n".join(problems)
    assert "unknown id 'NOPE-1'" in text
    assert "reused" in text
    assert "NOT_A_BASIS" in text
    assert "Python files" in text


def test_t028_import_boundaries():
    for path in (SRC / "core").rglob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert not node.module.startswith(
                    ("cometric.mcp", "cometric.cli", "cometric.advisory")
                ), path
                if node.level == 2:
                    assert node.module not in ("mcp", "cli"), path
    assert not list((SRC / "packs").rglob("*.py"))


def test_t027_core_runs_without_packs(case, monkeypatch, tmp_path):
    monkeypatch.setattr(packs_mod, "PACK_ROOT", tmp_path)
    packs_mod.load_pack.cache_clear()
    try:
        c = case("b")
        r = calculate_periods(c["engagement"], c["scenarios"][1], "reference")
        assert r["status"] == "ok" and r["term"]["contribution_profit"] == "240000"
        assert packs_mod.available_packs() == []
    finally:
        packs_mod.load_pack.cache_clear()


@pytest.mark.parametrize("tid", [t["template_id"] for t in list_templates()])
def test_t029_template_round_trip(tid):
    t = get_template(tid)
    unfilled = validate_engagement(t["engagement"])
    required = [e for e in unfilled["errors"] if e["code"] == "REQUIRED_FIELD"]
    assert required and all(e["path"].startswith("/engagement/") for e in required)
    filled = fill_template(t, t["examples"])
    rep = validate_engagement(filled["engagement"])
    assert rep["valid"], rep["errors"]
    r = calculate_periods(filled["engagement"], filled["scenario"])
    assert r["status"] == "ok", r["issues"]


@pytest.mark.parametrize("tid", sorted(packs_mod.load_pack("consulting").templates))
def test_t029_consulting_template_round_trip(tid):
    t = get_template(tid, "consulting")
    assert any(
        e["code"] == "REQUIRED_FIELD" for e in validate_engagement(t["engagement"])["errors"]
    )
    filled = fill_template(t, t["examples"])
    assert validate_engagement(filled["engagement"])["valid"]
    assert calculate_periods(filled["engagement"], filled["scenario"])["status"] == "ok"


def test_consulting_rules_fire(case):
    out = check_commercial_constraints(case("h")["engagement"])
    fired = {f["rule"] for f in out["rules_fired"]}
    assert {"CONS-R-001", "CONS-R-003"} <= fired
    assert "CONSULTING_OUTCOME_FEE_REVIEW" in {a["code"] for a in out["approvals_required"]}


def test_describe_schema():
    s = describe_schema("engagement")
    assert "arrangement_versions" in s["properties"]
    assert describe_schema("search_spec")["title"] == "SearchSpec"


def test_pack_vocabulary_checks():
    e = engagement([comp("base", "FIXED_RECURRING", "FIXED", fixed_amount="1000")])
    e["services"][0]["service_category"] = "CONTRACTS"
    assert "UNDECLARED_VOCABULARY" in [x["code"] for x in validate_engagement(e)["errors"]]
    e["packs"] = [{"id": "alsp"}]
    assert validate_engagement(e)["valid"]
    e["services"][0]["service_category"] = "NOT_A_CATEGORY"
    assert "UNKNOWN_VOCABULARY" in [x["code"] for x in validate_engagement(e)["errors"]]


def test_pack_rules_fire_on_outcome_fee_with_legal_work():
    e = engagement(
        [comp("base", "FIXED_RECURRING", "FIXED", fixed_amount="1000")], packs=[{"id": "alsp"}]
    )
    e["services"][0]["service_category"] = "LEGAL_OPERATIONS"
    e["parties"] = [{"id": "p", "role": "PROVIDER", "provider_type": "NONLAW_ALSP"}]
    e["arrangement_versions"][0]["components"].append(
        comp("success", "FIXED_RECURRING", "OUTCOME", fixed_amount="0")
    )
    out = check_commercial_constraints(e)
    fired = {f["rule"] for f in out["rules_fired"]}
    assert fired, out
    assert any(f["severity"] == "APPROVAL_REQUIRED" for f in out["rules_fired"])


def test_t011_inference_never_serialized_as_verified_fact():
    hits = lookup_concept("SEL-001")
    assert hits and hits[0]["evidence_class"] == "C_INFERENCE" and "label_note" in hits[0]
    for pid in ("base", "alsp"):
        p = packs_mod.load_pack(pid)
        claims = {c["id"]: c for c in p.claims}
        for c in p.claims:
            if c["classification"] in ("C_INFERENCE", "D_PROPOSED"):
                assert c.get("verified") is not True
        for s in p.sources:
            if s.get("verified"):
                assert s.get("retrieved_date"), s["id"]
        assert claims


def test_lookup_and_vocab():
    pm = lookup_concept("PM-023")[0]
    assert pm["scheme"] == "pricing_models" and pm["label"]
    assert lookup_concept("take-or-pay")
    assert {v["value"] for v in list_vocabulary("billing_basis")} >= {"TIME", "OUTPUT"}
    assert any(v["value"] == "CONTRACTS" for v in list_vocabulary("service_categories", "alsp"))
    d = describe_pack("alsp")
    assert d["meta"]["extends"] == "base" and d["sources_verified"] > 0


# Names that must never appear in shipped data, stored as SHA-256 digests of lowercase words.
FORBIDDEN_DIGESTS = {
    "aacd63902e8368143bc81218bd3356e7d6daf36ec3082f78cc8fe7c1ca8d6b2d",
    "a8407220cbbe2cec6764bb907d33f2658ccb7f1b95077790e8d393677ef7b598",
}


def _words(text: str) -> set[str]:
    return set(re.findall(r"[a-z]+", text.lower()))


def test_no_forbidden_names_or_dashes_in_packs():
    for f in [*(SRC / "packs").rglob("*.yaml"), *(SRC / "examples").glob("*.json")]:
        text = f.read_text()
        digests = {hashlib.sha256(w.encode()).hexdigest() for w in _words(text)}
        assert not digests & FORBIDDEN_DIGESTS, f
        assert "\u2014" not in text and "\u2013" not in text, f


@pytest.mark.skipif(not REPORT.exists(), reason="private research report not present")
def test_t033_every_report_identifier_is_captured():
    report = REPORT.read_text()
    ids = set(
        re.findall(
            r"\*\*((?:BB-[A-Z]+|PM-\d{3}|CL-[A-Z]+\d{2}|FM-\d{3}|CHI-\d{3}|EC-\d{3}|REL-\d{3}|RULE-\d{3}|E0\d{2}))\*\*",
            report,
        )
    )
    present = set()
    excluded = set()
    for pid in ("base", "alsp"):
        p = packs_mod.load_pack(pid)
        present |= {str(c.get("id")) for c in p.concepts()}
        present |= {str(r.get("id")) for r in p.rules}
        present |= {str(s.get("id")) for s in p.sources}
        excluded |= {str(x.get("ref")) for x in p.excluded}
    missing = sorted(i for i in ids if i not in present and i not in excluded)
    assert not missing, missing
    counts = {
        pre: sum(1 for i in present if i.startswith(pre))
        for pre in ("COMPAT-", "SEL-", "NEG-", "MECH-", "DIM-")
    }
    assert counts == {"COMPAT-": 17, "SEL-": 11, "NEG-": 10, "MECH-": 11, "DIM-": 16}


def test_examples_are_valid_json():
    for f in (SRC / "examples").glob("*.json"):
        json.loads(f.read_text())
