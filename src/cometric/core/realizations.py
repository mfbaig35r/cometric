"""Realizations: how a pack's pricing models and levers become engagement terms, and the skeleton
assembler that turns a deal profile plus a composition into an engagement and shared scenarios
(propose_structures spec A7, A8).

A realization is pack data. A model realization declares its unit kinds, its risk labels, and an
engagement fragment; a lever realization declares where it applies, how it shifts the labels, and
the terms it adds. Fragments use placeholders ("<required: label>") for every figure and a few
tokens that the assembler expands:

  {u} {q} {t}        a priced unit's code, its scenario quantity, and its label suffix (per_unit)
  {c} {c_unit} {c_t} a variable component's id, unit, and label suffix (per_variable)
  {volume_q}         the scenario quantity holding total volume
  {volume_unit}      the unit definition code for total volume
  "{variable_ids}"   (as a whole value) the list of variable component ids
"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from .packs import Pack, pack_chain

AXES = ("volume_shortfall", "volume_excess", "spend_variability", "mix", "early_exit")
BEARERS = ("CLIENT", "SHARED", "PROVIDER", "NONE_ADVERSE")
SPEND = ("FIXED", "BOUNDED", "VARIABLE")
AXIS_VALUES = {
    "volume_shortfall": BEARERS,
    "volume_excess": BEARERS,
    "spend_variability": SPEND,
    "mix": BEARERS,
    "early_exit": BEARERS,
}
UNIT_KINDS = ("COUNT", "HOURS", "FTE_MONTHS")
PRICING_UNITS = ("per_tier", "total", "weighted", "hours", "fte")
VARIABLE_METHODS = {"UNIT_OUTPUT", "WEIGHTED_UNIT_OUTPUT", "TIME", "ALLOWANCE_OVERAGE"}
COLLECTIONS = ("components", "rate_schedules", "entitlements", "commitments", "adjustments")


def R(label: str) -> str:
    return f"<required: {label}>"


@dataclass
class Realization:
    key: str
    pack: str
    data: dict

    @property
    def concept(self) -> str:
        return str(self.data.get("concept") or self.key)

    @property
    def kind(self) -> str:
        return str(self.data.get("kind"))

    @property
    def label(self) -> str:
        return str(self.data.get("label") or self.key)

    @property
    def features(self) -> list[str]:
        return list(self.data.get("features") or [])


def realizations(pack_ids: list[str]) -> dict[str, Realization]:
    """Every realization visible from the declared packs (and the packs they extend)."""
    out: dict[str, Realization] = {}
    for pid in pack_ids:
        for p in reversed(pack_chain(pid)):
            for r in p.realizations:
                key = str(r.get("id"))
                if key not in out:
                    out[key] = Realization(key, p.id, r)
    return dict(sorted(out.items()))


# --- profile shape ---------------------------------------------------------------------------


@dataclass
class Shape:
    """What the assembler needs from a deal profile."""

    kind: str = "COUNT"
    tiers: list[str] = field(default_factory=list)
    description: str | None = None
    service_category: str | None = None
    packs: list[str] = field(default_factory=list)
    cost_shape: str = "MIXED"
    fixed_team: bool = False
    setup_investment: bool = False
    certainty: str = "UNKNOWN"
    expected: Decimal | None = None
    low: Decimal | None = None
    high: Decimal | None = None
    period: str | None = None
    term_months: int | None = None
    early_exit: bool = False
    automation_expected: bool = False

    @property
    def volume_q(self) -> str:
        return {"COUNT": "units_total", "HOURS": "hours.delivery", "FTE_MONTHS": "fte_months"}[
            self.kind
        ]

    @property
    def volume_unit(self) -> str:
        return {"COUNT": "units", "HOURS": "hour", "FTE_MONTHS": "fte_month"}[self.kind]

    @property
    def volume_generic_unit(self) -> str:
        return {"COUNT": "count", "HOURS": "hours", "FTE_MONTHS": "fte"}[self.kind]

    @property
    def volume_word(self) -> str:
        return {"COUNT": "units", "HOURS": "hours", "FTE_MONTHS": "FTE-months"}[self.kind]


def slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", str(text).lower()).strip("_")
    return s or "tier"


# --- composition labels ----------------------------------------------------------------------


def composition_labels(shape: Shape, model: Realization, levers: list[Realization]) -> dict:
    base = dict(model.data.get("labels") or {})
    labels = {
        "volume_shortfall": base.get("volume_shortfall"),
        "volume_excess": base.get("volume_excess"),
        "spend_variability": base.get("spend_variability"),
    }
    if shape.cost_shape == "MOSTLY_VARIABLE" and base.get("variable_cost_shortfall"):
        labels["volume_shortfall"] = base["variable_cost_shortfall"]
    if shape.tiers:
        labels["mix"] = base.get("mix")
    if shape.early_exit:
        stranded = (
            shape.fixed_team or shape.setup_investment or shape.cost_shape != "MOSTLY_VARIABLE"
        )
        labels["early_exit"] = "PROVIDER" if stranded else "NONE_ADVERSE"
    for lever in sorted(levers, key=lambda r: r.key):
        for axis, mapping in (lever.data.get("effects") or {}).items():
            if axis in labels and labels[axis] in (mapping or {}):
                labels[axis] = mapping[labels[axis]]
    return labels


def composition_features(model: Realization, levers: list[Realization]) -> list[str]:
    feats = set(model.features)
    for lever in levers:
        feats |= set(lever.data.get("adds_features") or [])
    return sorted(feats)


def lever_applies(
    lever: Realization, model: Realization, shape: Shape, others: list[Realization] | None = None
) -> str | None:
    """None when the lever applies to this model (with the other levers of the composition);
    otherwise the reason it does not."""
    need = lever.data.get("requires_features") or []
    feats = set(composition_features(model, [o for o in others or [] if o.key != lever.key]))
    missing = [f for f in need if f not in feats]
    if missing:
        why = lever.data.get("not_applicable_reason") or "needs " + ", ".join(missing)
        return f"{why} ({model.concept} has none)"
    if any(f in feats for f in lever.data.get("excludes_features") or []):
        return lever.data.get("not_applicable_reason") or f"does not apply to {model.concept}"
    kinds = lever.data.get("unit_kinds")
    if kinds and shape.kind not in kinds:
        return f"does not apply to {shape.kind} work"
    return None


# --- assembly --------------------------------------------------------------------------------


def _expand(obj: Any, tokens: dict[str, Any]) -> Any:
    if isinstance(obj, dict):
        return {k: _expand(v, tokens) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_expand(v, tokens) for v in obj]
    if isinstance(obj, str):
        if obj in ("{variable_ids}",) and obj[1:-1] in tokens:
            return list(tokens[obj[1:-1]])
        out = obj
        for k, v in tokens.items():
            if isinstance(v, str):
                out = out.replace("{" + k + "}", v)
        return out
    return obj


COMPONENT_DEFAULTS = {
    "service_id": "service",
    "depends_on": [],
}
SCHEDULE_DEFAULTS = {
    "tier_method": "MARGINAL",
    "tier_scope": "ALL_ELIGIBLE",
    "accumulation_period": "MONTH",
}


def _priced_units(shape: Shape, model: Realization) -> list[tuple[str, str, str]]:
    """(unit code, scenario quantity, label suffix) for each separately priced unit."""
    pu = model.data.get("pricing_unit", "total")
    if pu == "per_tier" and shape.tiers:
        return [(f"units_{t}", f"units.{t}", f", tier {t}") for t in shape.tiers]
    return [(shape.volume_unit, shape.volume_q, "")]


def _unit_definitions(shape: Shape, model: Realization) -> list[dict]:
    pu = model.data.get("pricing_unit", "total")
    kind = {"COUNT": "COUNT", "HOURS": "HOURS", "FTE_MONTHS": "FTE_MONTHS"}[shape.kind]
    name = shape.description

    def unit(code: str, label: str = "") -> dict:
        d = {"code": code, "kind": kind}
        if name:
            d["name"] = name + label
        d["counting_rule"] = R("counting rule" + label)
        d["acceptance_rule"] = R("acceptance rule" + label)
        return d

    if pu == "per_tier" and shape.tiers:
        return [unit(f"units_{t}", f", tier {t}") for t in shape.tiers]
    return [unit(shape.volume_unit)]


def _weight_table(shape: Shape) -> dict:
    return {
        "id": "complexity",
        "raw_unit": shape.volume_unit,
        "weighted_unit": "weighted_units",
        "bands": [{"code": t, "weight": R(f"complexity weight, tier {t}")} for t in shape.tiers],
        "classification_authority": R("who classifies complexity: PROVIDER, CLIENT, or JOINT"),
    }


def _costs(shape: Shape) -> list[dict]:
    out = []
    if shape.cost_shape in ("MOSTLY_FIXED", "MIXED") or shape.fixed_team:
        out.append(
            {
                "id": "delivery_team",
                "category": "DEDICATED_LABOR" if shape.fixed_team else "POOLED_LABOR",
                "behavior": "FIXED",
                "amount": R("delivery team cost per month"),
                "period": "MONTHLY",
            }
        )
    if shape.cost_shape in ("MOSTLY_VARIABLE", "MIXED"):
        word = {"COUNT": "unit", "HOURS": "hour", "FTE_MONTHS": "FTE-month"}[shape.kind]
        out.append(
            {
                "id": "variable_delivery",
                "category": "POOLED_LABOR",
                "behavior": "VARIABLE",
                "driver": shape.volume_q,
                "rate": R(f"delivery cost per {word}"),
            }
        )
    if shape.setup_investment:
        out.append(
            {
                "id": "setup",
                "category": "TRANSITION",
                "behavior": "ONE_TIME",
                "amount": R("setup cost"),
            }
        )
    return out


def assemble_engagement(shape: Shape, model: Realization, levers: list[Realization]) -> dict:
    levers = sorted(levers, key=lambda r: r.key)
    version: dict[str, Any] = {"id": "v1", "effective_from": R("start date")}
    for coll in COLLECTIONS:
        version[coll] = []
    units = _priced_units(shape, model)
    frag = model.data.get("fragment") or {}
    base_tokens = {
        "volume_q": shape.volume_q,
        "volume_unit": shape.volume_unit,
        "volume_basis": "USAGE" if shape.kind == "HOURS" else "OUTPUT",
    }
    for coll in COLLECTIONS:
        for u, q, t in units:
            for item in (frag.get("per_unit") or {}).get(coll, []):
                version[coll].append(_expand(item, {**base_tokens, "u": u, "q": q, "t": t}))
        for item in (frag.get("once") or {}).get(coll, []):
            version[coll].append(_expand(item, base_tokens))

    def variable_components() -> list[dict]:
        return [c for c in version["components"] if c.get("calculation_method") in VARIABLE_METHODS]

    # adds first (in lever order), then patches, so a patch sees every lever's terms
    for lever in levers:
        lf = lever.data.get("fragment") or {}
        tokens = {**base_tokens, "variable_ids": [c["id"] for c in variable_components()]}
        for coll in COLLECTIONS:
            for item in (lf.get("once") or {}).get(coll, []):
                version[coll].append(_expand(item, tokens))
            for c in variable_components():
                ct = {
                    **tokens,
                    "c": c["id"],
                    "c_unit": str(c.get("unit") or shape.volume_unit),
                    "c_t": _suffix_for(c, units),
                }
                for item in (lf.get("per_variable") or {}).get(coll, []):
                    version[coll].append(_expand(item, ct))
    for lever in levers:
        patch = (lever.data.get("fragment") or {}).get("patch") or {}
        for key, values in patch.items():
            if key == "version":
                version.update(copy.deepcopy(values))
            elif key in COLLECTIONS:
                for item in version[key]:
                    item.update(copy.deepcopy(values))
    if shape.early_exit:
        for com in version["commitments"]:
            com.setdefault(
                "termination_rule",
                R("what the minimum owes on early exit: PRORATE, REMAINDER_DUE, or WAIVED"),
            )
    for c in version["components"]:
        for k, v in COMPONENT_DEFAULTS.items():
            c.setdefault(k, copy.deepcopy(v))
        c.setdefault("currency", R("currency (ISO code)"))
        c.setdefault("effective_period", {"from": R("start date"), "to": None})
    for s in version["rate_schedules"]:
        for k, v in SCHEDULE_DEFAULTS.items():
            s.setdefault(k, v)
        s.setdefault("currency", R("currency (ISO code)"))
    for coll in COLLECTIONS:
        if not version[coll] and coll != "components":
            del version[coll]

    unit_defs = _unit_definitions(shape, model)
    service: dict[str, Any] = {"id": "service", "unit_definition_id": unit_defs[0]["code"]}
    if shape.service_category:
        service["service_category"] = shape.service_category
    engagement: dict[str, Any] = {
        "schema_version": "0.2",
        "engagement_id": "proposal",
        "name": R("engagement name"),
        "currency": R("currency (ISO code)"),
        "start_date": R("start date"),
        "end_date": R("end date"),
        "packs": [{"id": p} for p in shape.packs],
        "unit_definitions": unit_defs,
        "services": [service],
        "arrangement_versions": [version],
        "delivery_plan": {"cost_components": _costs(shape)},
        "client_value_unit": shape.volume_q,
    }
    if model.data.get("pricing_unit") == "weighted":
        engagement["weight_tables"] = [_weight_table(shape)]
    if shape.automation_expected:
        engagement["descriptors"] = {
            "automation_benefit": R(
                "who keeps automation savings: PROVIDER_RETAINED, CLIENT_RETAINED, SHARED, "
                "GLIDE_PATH, or REINVESTED"
            )
        }
    return engagement


def _suffix_for(component: dict, units: list[tuple[str, str, str]]) -> str:
    for u, _, t in units:
        if component.get("unit") == u:
            return t
    return ""


# --- scenario stubs --------------------------------------------------------------------------


def _term_total(shape: Shape, value: Decimal | None) -> str | None:
    if value is None or shape.term_months is None or shape.period is None:
        return None
    total = value * shape.term_months / (12 if shape.period == "YEAR" else 1)
    return str(total.quantize(Decimal(1)) if shape.kind == "COUNT" else total.normalize())


def scenario_stubs(shape: Shape, extra_assumptions: list[dict]) -> list[dict]:
    """Shared scenarios: low, expected, and high where the profile gave figures (term totals),
    otherwise one with a volume placeholder; plus an early-exit scenario when relevant."""
    figures = [
        ("low", shape.low),
        ("expected", shape.expected),
        ("high", shape.high),
    ]
    given = [(sid, _term_total(shape, v)) for sid, v in figures]
    given = [(sid, v) for sid, v in given if v is not None]
    if not any(sid == "expected" for sid, _ in given):
        given = [(sid, v) for sid, v in given if sid != "expected"]
        given.insert(
            len([g for g in given if g[0] == "low"]),
            ("expected", R(f"expected {shape.volume_word} over the term")),
        )

    def shares() -> tuple[list[dict], list[dict]]:
        if shape.kind != "COUNT" or not shape.tiers:
            return [], []
        assumptions = [
            {
                "name": f"share.{t}",
                "value": R(f"share of volume in tier {t}, as a fraction"),
                "unit": "ratio",
                "time_period": "TERM",
                "basis": "RATE",
                "origin": "ESTIMATED",
            }
            for t in shape.tiers
        ]
        derived = [
            {
                "name": f"units.{t}",
                "unit": "count",
                "rounding": "NONE",
                "expression": {"product": [{"q": shape.volume_q}, {"q": f"share.{t}"}]},
                "description": f"volume in tier {t}: total volume times the tier's share",
            }
            for t in shape.tiers
        ]
        return assumptions, derived

    share_assumptions, derived = shares()
    out = []
    for sid, value in given:
        sc: dict[str, Any] = {
            "id": sid,
            "assumptions": [
                {
                    "name": shape.volume_q,
                    "value": value,
                    "unit": shape.volume_generic_unit,
                    "time_period": "TERM",
                    "origin": "ESTIMATED",
                }
            ]
            + copy.deepcopy(share_assumptions)
            + copy.deepcopy(extra_assumptions),
        }
        if derived:
            sc["derived"] = copy.deepcopy(derived)
        out.append(sc)
    if shape.early_exit:
        base = copy.deepcopy(next(s for s in out if s["id"] == "expected"))
        base["id"] = "early_exit"
        base["termination_date"] = R("early-exit date (term midpoint suggested)")
        out.append(base)
    return out


def extra_assumptions(levers: list[Realization]) -> list[dict]:
    seen: dict[str, dict] = {}
    for lever in sorted(levers, key=lambda r: r.key):
        for a in lever.data.get("scenario_assumptions") or []:
            seen.setdefault(a["name"], copy.deepcopy(a))
    return [seen[k] for k in sorted(seen)]


# --- sample fill (pack validation and tests) --------------------------------------------------

SAMPLE_BY_FIELD = {
    "currency": "USD",
    "termination_rule": "PRORATE",
    "classification_authority": "JOINT",
    "automation_benefit": "SHARED",
    "origin": "ESTIMATED",
}


def sample_fill(doc: Any, start: str = "2027-01-01", months: int = 24) -> Any:
    """Replace every placeholder with a structurally valid sample value, so a skeleton's terms can
    be checked by the full validator. Sample values are not proposals."""
    from .periods import last_day

    y, m = int(start[:4]), int(start[5:7])

    def month(offset: int) -> tuple[int, int]:
        idx = m - 1 + offset
        return (y + idx // 12, idx % 12 + 1)

    end_date = last_day(month(months - 1))
    mid_date = last_day(month(months // 2 - 1))

    def fill(obj: Any, key: str | None) -> Any:
        from .validation import placeholder_label

        if isinstance(obj, dict):
            return {k: fill(v, k) for k, v in obj.items()}
        if isinstance(obj, list):
            return [fill(v, key) for v in obj]
        label = placeholder_label(obj)
        if label is None:
            return obj
        if key in SAMPLE_BY_FIELD:
            return SAMPLE_BY_FIELD[key]
        if key == "termination_date":
            return mid_date.isoformat()
        if key == "end_date":
            return end_date.isoformat()
        if "date" in label:
            return start
        if key in ("name", "counting_rule", "acceptance_rule"):
            return f"sample {label}"
        if "share of volume" in label:
            return "0.5"
        if "fraction" in label or "weight" in label:
            return "1"
        if "1 if" in label:
            return "0"
        return "1000"

    return fill(doc, None)


def pack_realizations(pack: Pack) -> list[dict]:
    return pack.realizations


# --- pack validation -------------------------------------------------------------------------


def _sample_shapes(model: dict, pack_id: str) -> list[Shape]:
    shapes = []
    for kind in model.get("unit_kinds") or []:
        tier_sets = [["a", "b"]] if model.get("requires_tiers") else [[]]
        if kind == "COUNT" and not model.get("requires_tiers"):
            tier_sets.append(["a", "b"])
        for tiers in tier_sets:
            shapes.append(
                Shape(
                    kind=kind,
                    tiers=tiers,
                    packs=[pack_id],
                    cost_shape="MIXED",
                    fixed_team=True,
                    setup_investment=True,
                    certainty="RANGE",
                    expected=Decimal("1200"),
                    low=Decimal("600"),
                    period="YEAR",
                    term_months=24,
                    early_exit=True,
                )
            )
    return shapes


def check_skeleton(skeleton: dict) -> list[str]:
    """Problems with a skeleton: anything but placeholders before filling, and any failure to
    calculate after a sample fill."""
    from .api import calculate_periods
    from .validation import validate_engagement

    problems = []
    report = validate_engagement(skeleton["engagement"])
    for e in report["errors"]:
        if e["code"] not in ("REQUIRED_FIELD",):
            problems.append(f"{e['path']}: {e['code']} {e['message']}")
    filled = sample_fill(skeleton)
    for sc in filled["scenarios"]:
        r = calculate_periods(filled["engagement"], sc, "reference")
        if r["status"] == "invalid" or r["status"] == "error":
            errs = (r.get("issues") or {}).get("errors") or []
            problems += [
                f"scenario {sc['id']}: {e['path']}: {e['code']} {e['message']}" for e in errs
            ]
            break
    return problems


def check_realizations(pack: Pack) -> list[str]:
    from .predicates import check as check_predicate

    problems: list[str] = []
    chain = pack_chain(pack.id)
    models = {
        str(c["id"])
        for p in chain
        for c in (p.schemes.get("pricing_models", {}).get("concepts") or [])
    }
    lever_ids = {
        str(c["id"]) for p in chain for c in (p.schemes.get("levers", {}).get("concepts") or [])
    }
    keys: set[str] = set()
    model_rs, lever_rs = [], []
    for i, r in enumerate(pack.realizations):
        where = f"realizations[{i}] {r.get('id')}"
        key = r.get("id")
        if not key:
            problems.append(f"realizations[{i}]: realization without id")
            continue
        if key in keys:
            problems.append(f"{where}: id reused")
        keys.add(key)
        concept = str(r.get("concept") or key)
        kind = r.get("kind")
        if kind == "model":
            model_rs.append(Realization(key, pack.id, r))
            if concept not in models:
                problems.append(f"{where}: {concept} is not a pricing model in this pack chain")
            if not r.get("unit_kinds") or not set(r["unit_kinds"]) <= set(UNIT_KINDS):
                problems.append(f"{where}: unit_kinds must be a non-empty subset of {UNIT_KINDS}")
            if r.get("pricing_unit") not in PRICING_UNITS:
                problems.append(f"{where}: pricing_unit must be one of {PRICING_UNITS}")
            labels = r.get("labels") or {}
            for axis in ("volume_shortfall", "volume_excess", "spend_variability"):
                if axis not in labels:
                    problems.append(f"{where}: labels.{axis} is required")
            for axis, value in labels.items():
                allowed = AXIS_VALUES.get(
                    "volume_shortfall" if axis == "variable_cost_shortfall" else axis
                )
                if allowed is None:
                    problems.append(f"{where}: unknown label axis {axis!r}")
                elif value not in allowed:
                    problems.append(f"{where}: labels.{axis} {value!r} is not one of {allowed}")
        elif kind == "lever":
            lever_rs.append(Realization(key, pack.id, r))
            if concept not in lever_ids:
                problems.append(f"{where}: {concept} is not a lever in this pack chain")
            for axis, mapping in (r.get("effects") or {}).items():
                allowed = AXIS_VALUES.get(axis)
                if allowed is None:
                    problems.append(f"{where}: unknown effect axis {axis!r}")
                    continue
                for a, b in (mapping or {}).items():
                    if a not in allowed or b not in allowed:
                        problems.append(f"{where}: effects.{axis} {a}->{b} outside {allowed}")
            if r.get("suggested_when") is not None:
                problems += [
                    f"{where}: suggested_when: {p}" for p in check_predicate(r["suggested_when"])
                ]
        else:
            problems.append(f"{where}: kind must be model or lever")
    if problems:
        return problems
    all_models = [m for m in realizations([pack.id]).values() if m.kind == "model"]
    checked: list[int] = []
    for model in model_rs:
        for shape in _sample_shapes(model.data, pack.id):
            for lever in [None, *lever_rs]:
                levers = [lever] if lever else []
                if lever is not None and lever_applies(lever, model, shape):
                    # a lever may need a feature another lever provides (a prorated minimum
                    # needs a minimum): check it with the first lever that provides it
                    providers = [
                        o
                        for o in lever_rs
                        if set(lever.data.get("requires_features") or [])
                        <= set(composition_features(model, [o]))
                        and lever_applies(o, model, shape) is None
                    ]
                    if not providers or lever_applies(lever, model, shape, providers[:1]):
                        continue
                    levers = [providers[0], lever]
                skel = {
                    "engagement": assemble_engagement(shape, model, levers),
                    "scenarios": scenario_stubs(shape, extra_assumptions(levers)),
                }
                checked.append(1)
                tag = f"{model.key}{''.join('+' + x.key for x in levers)} ({shape.kind}{', tiers' if shape.tiers else ''})"
                problems += [f"realization {tag}: {p}" for p in check_skeleton(skel)]
    for lever in lever_rs:
        if not any(
            lever_applies(lever, m, s, lever_rs) is None
            for m in all_models
            for s in _sample_shapes(m.data, pack.id)
        ):
            problems.append(f"realization {lever.key}: applies to no model")
    return problems
