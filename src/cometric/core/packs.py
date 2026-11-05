"""Pack loading, validation, vocabulary checks, rule evaluation, and lookup (spec 3.4 to 3.6)."""

from __future__ import annotations

import functools
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .enums import BillingBasis, CalculationMethod, EvidenceClass, Prevalence, Severity
from .fingerprint import to_jsonable
from .issues import Issues, pointer
from .predicates import check as check_predicate
from .predicates import evaluate

PACK_ROOT = Path(__file__).resolve().parents[1] / "packs"
CORE_VERSION = "0.1"


@dataclass
class Pack:
    id: str
    meta: dict
    path: Path
    schemes: dict[str, dict] = field(default_factory=dict)
    overlays: dict[str, list[dict]] = field(default_factory=dict)
    rules: list[dict] = field(default_factory=list)
    sources: list[dict] = field(default_factory=list)
    claims: list[dict] = field(default_factory=list)
    coverage: list[dict] = field(default_factory=list)
    excluded: list[dict] = field(default_factory=list)
    templates: dict[str, dict] = field(default_factory=dict)
    realizations: list[dict] = field(default_factory=list)
    load_problems: list[str] = field(default_factory=list)

    @property
    def extends(self) -> str | None:
        return self.meta.get("extends")

    def concepts(self) -> list[dict]:
        return [c for s in self.schemes.values() for c in s.get("concepts", [])]


def _read(path: Path, problems: list[str]) -> Any:
    try:
        return yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError as exc:
        problems.append(f"{path.name}: YAML error: {exc}")
        return {}


def available_packs() -> list[str]:
    if not PACK_ROOT.exists():
        return []
    return sorted(p.name for p in PACK_ROOT.iterdir() if (p / "pack.yaml").exists())


@functools.lru_cache(maxsize=32)
def load_pack(pack_id: str, root: str | None = None) -> Pack:
    base = Path(root) if root else PACK_ROOT
    path = base / pack_id
    problems: list[str] = []
    if not (path / "pack.yaml").exists():
        raise KeyError(f"no pack named {pack_id!r}")
    meta = _read(path / "pack.yaml", problems)
    pack = Pack(pack_id, meta, path, load_problems=problems)
    for f in sorted((path / "concepts").glob("*.yaml")) if (path / "concepts").exists() else []:
        doc = _read(f, problems)
        scheme = doc.get("scheme") or f.stem
        pack.schemes[scheme] = doc
    for f in sorted((path / "overlays").glob("*.yaml")) if (path / "overlays").exists() else []:
        doc = _read(f, problems)
        pack.overlays[doc.get("scheme") or f.stem] = doc.get("overlays", [])
    for f in sorted((path / "rules").glob("*.yaml")) if (path / "rules").exists() else []:
        pack.rules += _read(f, problems).get("rules", []) or []
    ev = path / "evidence"
    if (ev / "sources.yaml").exists():
        pack.sources = _read(ev / "sources.yaml", problems).get("sources", []) or []
    if (ev / "claims.yaml").exists():
        pack.claims = _read(ev / "claims.yaml", problems).get("claims", []) or []
    if (path / "coverage.yaml").exists():
        pack.coverage = _read(path / "coverage.yaml", problems).get("areas", []) or []
    if (path / "excluded.yaml").exists():
        pack.excluded = _read(path / "excluded.yaml", problems).get("excluded", []) or []
    for f in (
        sorted((path / "realizations").glob("*.yaml")) if (path / "realizations").exists() else []
    ):
        pack.realizations += _read(f, problems).get("realizations", []) or []
    for f in sorted((path / "templates").glob("*.json")) if (path / "templates").exists() else []:
        import json

        pack.templates[f.stem] = json.loads(f.read_text())
    return pack


def pack_chain(pack_id: str, root: str | None = None) -> list[Pack]:
    """The pack and every pack it extends, nearest first."""
    chain = []
    seen = set()
    current: str | None = pack_id
    while current and current not in seen:
        seen.add(current)
        p = load_pack(current, root)
        chain.append(p)
        current = p.extends
    return chain


def validate_pack(pack_id: str, root: str | None = None) -> list[str]:
    """Static validation of a pack and its chain (T-032)."""
    chain = pack_chain(pack_id, root)
    pack = chain[0]
    problems = list(pack.load_problems)
    py = [str(p.relative_to(pack.path)) for p in pack.path.rglob("*.py")]
    if py:
        problems.append(f"packs are data only; found Python files: {py}")
    for k in ("id", "version", "title"):
        if k not in pack.meta:
            problems.append(f"pack.yaml missing {k}")
    if pack.meta.get("id") not in (None, pack.id):
        problems.append(
            f"pack.yaml id {pack.meta.get('id')!r} does not match directory {pack.id!r}"
        )
    own_ids: dict[str, str] = {}
    all_ids: set[str] = set()
    for p in chain:
        for c in p.concepts():
            all_ids.add(str(c.get("id")))
        for r in p.rules:
            all_ids.add(str(r.get("id")))
    claim_ids = {c.get("id") for p in chain for c in p.claims}
    source_ids = {s.get("id") for p in chain for s in p.sources}
    bases = {b.value for b in BillingBasis}
    methods = {m.value for m in CalculationMethod}
    classes = {c.value for c in EvidenceClass}
    prev = {p.value for p in Prevalence}
    for scheme, doc in pack.schemes.items():
        for i, c in enumerate(doc.get("concepts", []) or []):
            where = f"{scheme}[{i}]"
            cid = c.get("id")
            if not cid:
                problems.append(f"{where}: concept without id")
                continue
            if cid in own_ids:
                problems.append(f"{where}: id {cid} reused (also in {own_ids[cid]})")
            own_ids[cid] = scheme
            if any(cid in {x.get("id") for x in q.concepts()} for q in chain[1:]):
                problems.append(
                    f"{where}: id {cid} redefines a concept from an extended pack; use an overlay"
                )
            for b in c.get("bases", []) or []:
                if b not in bases:
                    problems.append(f"{where}: unknown core billing basis {b!r}")
            for m in c.get("methods", []) or []:
                if m not in methods:
                    problems.append(f"{where}: unknown core method {m!r}")
            if c.get("evidence_class") and c["evidence_class"] not in classes:
                problems.append(f"{where}: unknown evidence_class {c['evidence_class']!r}")
            if c.get("prevalence") and c["prevalence"] not in prev:
                problems.append(f"{where}: unknown prevalence {c['prevalence']!r}")
            for ref_key in ("broader", "related"):
                for ref in c.get(ref_key, []) or []:
                    if ref not in all_ids:
                        problems.append(f"{where}: {ref_key} references unknown id {ref!r}")
            for ref in c.get("claims", []) or []:
                if ref not in claim_ids:
                    problems.append(f"{where}: claims references unknown claim {ref!r}")
    for scheme, rows in pack.overlays.items():
        for i, o in enumerate(rows):
            if o.get("id") not in all_ids:
                problems.append(
                    f"overlay {scheme}[{i}]: id {o.get('id')!r} is not a concept in this pack chain"
                )
            for ref in o.get("claims", []) or []:
                if ref not in claim_ids:
                    problems.append(f"overlay {scheme}[{i}]: unknown claim {ref!r}")
    seen_rules = set()
    for i, r in enumerate(pack.rules):
        rid = r.get("id")
        if rid in seen_rules:
            problems.append(f"rules[{i}]: id {rid} reused")
        seen_rules.add(rid)
        if r.get("evaluable") and r.get("when") is not None:
            for prob in check_predicate(r["when"]):
                problems.append(f"rules[{i}] {rid}: {prob}")
        sev = (r.get("emit") or {}).get("severity")
        if sev and sev not in ("INFO", "WARNING", "APPROVAL_REQUIRED"):
            problems.append(f"rules[{i}] {rid}: bad severity {sev!r}")
        for ref in (r.get("emit") or {}).get("claims", []) or []:
            if ref not in claim_ids:
                problems.append(f"rules[{i}] {rid}: unknown claim {ref!r}")
    if pack.realizations:
        from .realizations import check_realizations

        problems += check_realizations(pack)
    keys = {str(r.get("id")) for q in chain for r in q.realizations}
    concepts_and_keys = keys | all_ids
    for c in pack.schemes.get("client_priorities", {}).get("concepts", []) or []:
        attrs = c.get("attributes") or {}
        for k in ("fits", "tension"):
            if attrs.get(k) is None:
                problems.append(f"client_priorities {c.get('id')}: {k} is required")
            else:
                problems += [
                    f"client_priorities {c.get('id')}.{k}: {p}" for p in check_predicate(attrs[k])
                ]
        for ref in attrs.get("suggests") or []:
            if ref not in concepts_and_keys:
                problems.append(f"client_priorities {c.get('id')}: suggests unknown lever {ref!r}")
    for c in pack.schemes.get("selection_heuristics", {}).get("concepts", []) or []:
        signal = (c.get("attributes") or {}).get("profile_signal")
        if signal is not None:
            problems += [
                f"selection_heuristics {c.get('id')}.profile_signal: {p}"
                for p in check_predicate(signal)
            ]
    seen_claims = set()
    for i, c in enumerate(pack.claims):
        if c.get("id") in seen_claims:
            problems.append(f"claims[{i}]: id {c.get('id')} reused")
        seen_claims.add(c.get("id"))
        for s in c.get("sources", []) or []:
            if s not in source_ids:
                problems.append(f"claims[{i}] {c.get('id')}: unknown source {s!r}")
    return problems


# --- engagement checks ------------------------------------------------------------------


def _declared_chain(e) -> list[Pack]:
    chain: list[Pack] = []
    for ref in e.packs:
        try:
            for p in pack_chain(ref.id):
                if p.id not in {x.id for x in chain}:
                    chain.append(p)
        except KeyError:
            continue
    return chain


def _scheme_ids(chain: list[Pack], scheme: str) -> set[str]:
    return {
        str(c.get("id"))
        for p in chain
        for c in (p.schemes.get(scheme, {}).get("concepts", []) or [])
    }


def check_engagement_vocabulary(e, issues: Issues) -> None:
    for i, ref in enumerate(e.packs):
        if ref.id not in available_packs():
            issues.error(
                "UNKNOWN_PACK",
                f"pack {ref.id!r} is not installed; installed: {available_packs()}",
                pointer("engagement", "packs", i, "id"),
            )
        elif ref.version and load_pack(ref.id).meta.get("version") != ref.version:
            issues.warn(
                "PACK_VERSION",
                f"pack {ref.id} is version {load_pack(ref.id).meta.get('version')}, engagement asks for {ref.version}",
                pointer("engagement", "packs", i, "version"),
            )
    chain = _declared_chain(e)
    cats = _scheme_ids(chain, "service_categories")
    ptypes = _scheme_ids(chain, "provider_types")
    for si, s in enumerate(e.services):
        if s.service_category and s.service_category not in cats:
            issues.error(
                "UNKNOWN_VOCABULARY",
                f"service_category {s.service_category!r} is not defined by the declared packs",
                pointer("engagement", "services", si, "service_category"),
            )
    for pi, party in enumerate(e.parties):
        if party.provider_type and party.provider_type not in ptypes:
            issues.error(
                "UNKNOWN_VOCABULARY",
                f"provider_type {party.provider_type!r} is not defined by the declared packs",
                pointer("engagement", "parties", pi, "provider_type"),
            )
    dims = {}
    for p in chain:
        for c in p.schemes.get("dimensions", {}).get("concepts", []) or []:
            attrs = c.get("attributes") or {}
            if attrs.get("key"):
                dims[attrs["key"]] = set(attrs.get("values") or [])
    for k, v in e.descriptors.items():
        if dims and k not in dims:
            issues.error(
                "UNKNOWN_DESCRIPTOR",
                f"descriptor {k!r} is not a commercial dimension",
                pointer("engagement", "descriptors", k),
            )
        elif dims and dims[k] and v not in dims[k]:
            issues.error(
                "UNKNOWN_VOCABULARY",
                f"descriptor {k}={v!r} is not one of {sorted(dims[k])}",
                pointer("engagement", "descriptors", k),
            )


def evaluate_rules(e, issues: Issues) -> list[dict]:
    doc = to_jsonable(e)
    fired = []
    for p in _declared_chain(e):
        for r in p.rules:
            if not r.get("evaluable") or r.get("when") is None or r.get("kind") == "composition":
                continue
            try:
                hit = evaluate(r["when"], doc)
            except Exception:  # noqa: BLE001 - a malformed rule must not break a calculation
                continue
            if not hit:
                continue
            emit = r.get("emit") or {}
            sev = Severity(emit.get("severity", "INFO"))
            issues.add(
                emit.get("code", r["id"]),
                sev,
                emit.get("message", r.get("explanation", "")),
                "",
                rule=r["id"],
                pack=p.id,
                evidence_class=r.get("evidence_class"),
                claims=emit.get("claims", []),
            )
            fired.append(
                {
                    "rule": r["id"],
                    "pack": p.id,
                    "kind": r.get("kind"),
                    "assessment": r.get("assessment"),
                    "code": emit.get("code"),
                    "severity": str(sev),
                    "message": emit.get("message"),
                    "evidence_class": r.get("evidence_class"),
                }
            )
    return fired


# --- discovery --------------------------------------------------------------------------


def list_packs() -> list[dict]:
    out = []
    for pid in available_packs():
        p = load_pack(pid)
        out.append(
            {
                "id": pid,
                "version": p.meta.get("version"),
                "title": p.meta.get("title"),
                "extends": p.extends,
                "summary": p.meta.get("description"),
            }
        )
    return out


def describe_pack(pack_id: str) -> dict:
    p = load_pack(pack_id)
    return {
        "id": pack_id,
        "meta": p.meta,
        "schemes": {
            k: {"title": v.get("title"), "count": len(v.get("concepts", []) or [])}
            for k, v in p.schemes.items()
        },
        "overlays": {k: len(v) for k, v in p.overlays.items()},
        "rules": len(p.rules),
        "claims": len(p.claims),
        "sources": len(p.sources),
        "sources_verified": sum(1 for s in p.sources if s.get("verified")),
        "templates": sorted(p.templates),
        "coverage": p.coverage,
    }


def scheme(pack_id: str, name: str) -> dict:
    p = load_pack(pack_id)
    if name not in p.schemes:
        raise KeyError(f"pack {pack_id} has no scheme {name!r}; schemes: {sorted(p.schemes)}")
    return p.schemes[name]


def lookup_concept(id_or_query: str, pack: str | None = None, limit: int = 20) -> list[dict]:
    """Exact id match first; otherwise case-insensitive search in labels, synonyms, definitions."""
    packs = [pack] if pack else available_packs()
    q = id_or_query.strip().lower()
    exact, fuzzy = [], []
    overlays: dict[str, list[dict]] = {}
    claims: dict[str, dict] = {}
    for pid in available_packs():
        p = load_pack(pid)
        for rows in p.overlays.values():
            for o in rows:
                overlays.setdefault(o["id"], []).append({"pack": pid, **o})
        for c in p.claims:
            claims[c["id"]] = {"pack": pid, **c}
    for pid in packs:
        p = load_pack(pid)
        for scheme_name, doc in p.schemes.items():
            for c in doc.get("concepts", []) or []:
                rec = {"pack": pid, "scheme": scheme_name, **c}
                text = " ".join(
                    [
                        str(c.get("id", "")),
                        str(c.get("label", "")),
                        " ".join(map(str, c.get("synonyms", []) or [])),
                        str(c.get("definition", "")),
                    ]
                ).lower()
                if str(c.get("id", "")).lower() == q:
                    exact.append(rec)
                elif q and q in text:
                    fuzzy.append(rec)
        for r in p.rules:
            rec = {"pack": pid, "scheme": "rules", **r}
            if str(r.get("id", "")).lower() == q:
                exact.append(rec)
            elif (
                q
                and q
                in (
                    str(r.get("explanation", "")) + str((r.get("emit") or {}).get("message", ""))
                ).lower()
            ):
                fuzzy.append(rec)
    hits = (exact or fuzzy)[:limit]
    for h in hits:
        h["overlays"] = overlays.get(h.get("id"), [])
        h["claim_records"] = [claims[c] for c in (h.get("claims") or []) if c in claims]
        if h.get("evidence_class") in ("C_INFERENCE", "D_PROPOSED"):
            h["label_note"] = "Inference or proposal, not an observed industry fact."
    return hits


def list_vocabulary(name: str, pack: str | None = None) -> list[dict]:
    from . import enums

    core = {
        "billing_basis": enums.BillingBasis,
        "charge_cadence": enums.ChargeCadence,
        "calculation_method": enums.CalculationMethod,
        "tier_method": enums.TierMethod,
        "accumulation_period": enums.AccumulationPeriod,
        "recognition": enums.Recognition,
        "cost_category": enums.CostCategory,
        "margin_layer": enums.MarginLayer,
        "cost_behavior": enums.CostBehavior,
        "breach_mode": enums.BreachMode,
        "origin": enums.Origin,
        "evidence_class": enums.EvidenceClass,
        "prevalence": enums.Prevalence,
        "adjustment_type": enums.AdjustmentType,
        "commitment_kind": enums.CommitmentKind,
    }
    if name in core:
        return [{"value": v.value, "source": "core"} for v in core[name]]
    for pid in [pack] if pack else available_packs():
        p = load_pack(pid)
        if name in p.schemes:
            return [
                {
                    "value": c.get("id"),
                    "label": c.get("label"),
                    "definition": c.get("definition"),
                    "source": pid,
                }
                for c in p.schemes[name].get("concepts", []) or []
            ]
    raise KeyError(f"no vocabulary named {name!r}; core: {sorted(core)}")
