"""propose_structures: candidate commercial structures for a deal profile (propose spec Part A).

Lists, never ranks. The partner's inputs (priorities, constraints, lever preferences) and pack
structure (realizations, applicability, composition rules) decide what is listed; heuristics and
evidence only annotate. No figure is generated: skeletons carry labelled placeholders.
"""

from __future__ import annotations

import difflib
import itertools
from typing import Any, Literal

from pydantic import Field, ValidationError, field_validator

from .engine import ENGINE_VERSION
from .fingerprint import fingerprint
from .issues import Issues
from .models import SCHEMA_VERSION, Engagement, Model
from .money import Dec
from .packs import available_packs, evaluate_rules, pack_chain
from .predicates import evaluate
from .realizations import (
    Realization,
    Shape,
    assemble_engagement,
    composition_features,
    composition_labels,
    extra_assumptions,
    lever_applies,
    realizations,
    sample_fill,
    scenario_stubs,
    slug,
)
from .validation import find_placeholders, report, validate_engagement

ORDER_NOTE = "Candidates are grouped by who absorbs a volume shortfall, not ordered by preference."
GROUP_ORDER = ("CLIENT", "SHARED", "PROVIDER", "NONE_ADVERSE")
EXCLUDING_ASSESSMENTS = {
    "ECONOMICALLY_CONFLICTING",
    "NOT_ECONOMICALLY_DEFENSIBLE",
    "NOT_VALID_FOR_RIGOROUS_MODELING",
    "STRUCTURALLY_WEAK",
}
MAX_LEVERS = 3
RISK_LIMIT = {"NONE": {"CLIENT"}, "SHARED": {"CLIENT", "SHARED"}, "ANY": set(GROUP_ORDER)}
DEFINITIONS = {
    "volume_shortfall": "Who absorbs volume below expected (CLIENT pays for unused capacity; PROVIDER keeps its cost; SHARED up to a limit).",
    "volume_excess": "Who absorbs volume above expected (PROVIDER works more for a fixed or capped fee; NONE_ADVERSE is paid per unit).",
    "spend_variability": "How the client's spend moves with volume: FIXED, BOUNDED, or VARIABLE.",
    "mix": "Who absorbs a shift toward complex work.",
    "early_exit": "Who absorbs stranded cost if the client leaves early.",
    "evidence": "class A to D and prevalence as stored; WEAK when class C or D, UNVERIFIED, or no verified source.",
}


# --- inputs ---------------------------------------------------------------------------------


class UnitOfWork(Model):
    kind: Literal["COUNT", "HOURS", "FTE_MONTHS"]
    description: str | None = None
    tiers: list[str] = Field(
        default=[], description="Complexity tiers, each priced or weighted separately"
    )

    @field_validator("tiers")
    @classmethod
    def _tiers(cls, v: list[str]) -> list[str]:
        slugs = [slug(t) for t in v]
        if len(set(slugs)) != len(slugs):
            raise ValueError("tier names must be distinct")
        return v


class Volume(Model):
    certainty: Literal["KNOWN", "RANGE", "UNKNOWN"]
    expected: Dec | None = None
    low: Dec | None = None
    high: Dec | None = None
    period: Literal["MONTH", "YEAR"] | None = None


class CostProfile(Model):
    shape: Literal["MOSTLY_VARIABLE", "MOSTLY_FIXED", "MIXED"]
    fixed_team: bool = False
    setup_investment: bool = False


class ProviderConstraints(Model):
    max_volume_risk: Literal["NONE", "SHARED", "ANY"] = Field(
        default="ANY",
        description="Largest volume shortfall the provider accepts: NONE (client absorbs it), SHARED, or ANY",
    )


class Term(Model):
    months: int | None = Field(default=None, ge=1)
    client_can_terminate_early: bool = False
    notice_days: int | None = Field(default=None, ge=0)


class Flags(Model):
    automation_expected: bool = False
    continuity_required: bool = False


class DealProfile(Model):
    service_category: str
    unit_of_work: UnitOfWork
    volume: Volume
    cost_profile: CostProfile
    client_priorities: list[str] = Field(min_length=1, max_length=3)
    provider_constraints: ProviderConstraints = ProviderConstraints()
    term: Term | None = None
    flags: Flags = Flags()


class ProposeOptions(Model):
    max_candidates: int = Field(default=4, ge=1, le=6)
    include_levers: list[str] = []
    exclude_levers: list[str] = []
    expand: list[str] = []


def _nearest(value: str, choices: list[str]) -> str | None:
    hit = difflib.get_close_matches(str(value), [str(c) for c in choices], n=1, cutoff=0.5)
    return hit[0] if hit else None


def _model_at(cls: type[Model], loc: tuple) -> type[Model] | None:
    current: Any = cls
    for part in loc[:-1]:
        if isinstance(part, int):
            continue
        field = current.model_fields.get(part)
        if field is None:
            return None
        ann = field.annotation
        for arg in getattr(ann, "__args__", ()) or ():
            if isinstance(arg, type) and issubclass(arg, Model):
                ann = arg
        if not (isinstance(ann, type) and issubclass(ann, Model)):
            return None
        current = ann
    return current


def _parse(cls: type[Model], raw: Any, root: str, issues: Issues) -> Any:
    try:
        return cls.model_validate(raw)
    except ValidationError as exc:
        for err in exc.errors():
            path = root + "".join(f"/{p}" for p in err["loc"])
            detail: dict[str, Any] = {}
            if err["type"] == "extra_forbidden":
                owner = _model_at(cls, err["loc"])
                if owner is not None:
                    near = _nearest(str(err["loc"][-1]), list(owner.model_fields))
                    detail["expected"] = sorted(owner.model_fields)
                    if near:
                        detail["hint"] = f"did you mean {near!r}?"
            elif err["type"] == "literal_error":
                allowed = list(err.get("ctx", {}).get("expected", "").replace("'", "").split(", "))
                near = _nearest(str(err.get("input")), [a.replace(" or ", "") for a in allowed])
                if near:
                    detail["hint"] = f"did you mean {near!r}?"
            issues.error("SCHEMA", err["msg"], path, **detail)
        return None


def _vocab_error(issues: Issues, path: str, value: str, choices: list[str], what: str) -> None:
    near = _nearest(value, choices)
    detail: dict[str, Any] = {"expected": sorted(choices)}
    if near:
        detail["hint"] = f"did you mean {near!r}?"
    issues.error("UNKNOWN_VOCABULARY", f"{what} {value!r} is not defined", path, **detail)


# --- pack lookups ---------------------------------------------------------------------------


def _chain(pack_ids: list[str]) -> list:
    seen, out = set(), []
    for pid in pack_ids:
        for p in pack_chain(pid):
            if p.id not in seen:
                seen.add(p.id)
                out.append(p)
    return out


def _scheme(chain: list, name: str) -> dict[str, tuple[str, dict]]:
    out: dict[str, tuple[str, dict]] = {}
    for p in reversed(chain):
        for c in (p.schemes.get(name) or {}).get("concepts", []) or []:
            out[str(c["id"])] = (p.id, c)
    return out


def _service_categories(chain: list) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for p in chain:
        for c in (p.schemes.get("service_categories") or {}).get("concepts", []) or []:
            out.setdefault(str(c["id"]), []).append(p.id)
    return out


def _concept(chain: list, cid: str) -> tuple[str, dict] | None:
    for p in chain:
        for c in p.concepts():
            if str(c.get("id")) == cid:
                return p.id, c
    return None


def _evidence(chain: list, declared: list[str], cid: str) -> dict:
    found = _concept(chain, cid)
    pack_id, c = found if found else ("base", {})
    rec: dict[str, Any] = {
        "concept": f"{pack_id}:{cid}",
        "class": c.get("evidence_class"),
        "prevalence": c.get("prevalence"),
    }
    claims = list(c.get("claims") or [])
    for p in chain:
        if p.id not in declared:
            continue
        for rows in p.overlays.values():
            for o in rows:
                if o.get("id") == cid:
                    rec["class"] = o.get("evidence_class") or rec["class"]
                    rec["prevalence"] = o.get("prevalence") or rec["prevalence"]
                    rec["in"] = p.id
                    claims += list(o.get("claims") or [])
    all_claims = {x["id"]: x for p in chain for x in p.claims}
    sources = {x["id"]: x for p in chain for x in p.sources}
    claims = [x for x in dict.fromkeys(claims) if x in all_claims]
    src_ids = {s for x in claims for s in all_claims[x].get("sources") or []}
    rec["claims"] = len(claims)
    rec["verified"] = sum(1 for s in src_ids if (sources.get(s) or {}).get("verified"))
    if (
        rec["class"] in ("C_INFERENCE", "D_PROPOSED")
        or rec["prevalence"] == "UNVERIFIED"
        or rec["verified"] == 0
    ):
        rec["flag"] = "WEAK"
    return rec


# --- compositions ---------------------------------------------------------------------------


class Composition:
    def __init__(self, shape: Shape, model: Realization, levers: list[Realization]):
        self.model = model
        self.levers = sorted(levers, key=lambda r: r.key)
        self.id = "+".join([model.key, *(lv.key for lv in self.levers)])
        self.labels = composition_labels(shape, model, self.levers)
        self.features = composition_features(model, self.levers)
        self.fits: list[str] = []
        self.tensions: list[dict] = []

    @property
    def doc(self) -> dict:
        return {
            "base_model": self.model.concept,
            "levers": [lv.concept for lv in self.levers],
            "keys": [lv.key for lv in self.levers],
            "features": self.features,
            "labels": self.labels,
            "lever_count": len(self.levers),
        }

    def preference(self, priorities: list[str]) -> tuple:
        vector = tuple(0 if p in self.fits else 1 for p in priorities)
        return (-len(self.fits), vector, len(self.tensions), len(self.levers), self.id)


def _skeleton(shape: Shape, comp: Composition, extra: list[dict]) -> dict:
    engagement = assemble_engagement(shape, comp.model, comp.levers)
    engagement["engagement_id"] = comp.id
    return {"engagement": engagement, "scenarios": scenario_stubs(shape, extra)}


# --- operation ------------------------------------------------------------------------------


def propose_structures(packs: Any, deal_profile: Any, options: Any = None) -> dict:
    issues = Issues()
    if not isinstance(packs, list) or not packs or not all(isinstance(p, str) for p in packs):
        issues.error("SCHEMA", "packs is a non-empty list of pack ids", "/packs")
        return {"status": "invalid", "issues": report(issues)}
    for i, pid in enumerate(packs):
        if pid not in available_packs():
            _vocab_error(issues, f"/packs/{i}", pid, available_packs(), "pack")
    if issues.has_errors:
        return {"status": "invalid", "issues": report(issues)}
    declared = list(dict.fromkeys(["base", *packs]))
    chain = _chain(declared)
    profile = _parse(DealProfile, deal_profile, "/deal_profile", issues)
    opts = _parse(ProposeOptions, options or {}, "/options", issues)
    if profile is None or opts is None:
        return {"status": "invalid", "issues": report(issues)}

    reals = realizations(declared)
    lever_reals = {k: r for k, r in reals.items() if r.kind == "lever"}
    priorities = _scheme(chain, "client_priorities")
    categories = _service_categories(chain)

    category = profile.service_category
    if ":" in category:
        qual, _, bare = category.partition(":")
        if qual not in categories.get(bare, []):
            _vocab_error(
                issues,
                "/deal_profile/service_category",
                category,
                list(categories),
                "service_category",
            )
        category = bare
    elif category not in categories:
        _vocab_error(
            issues, "/deal_profile/service_category", category, list(categories), "service_category"
        )
    elif len(categories[category]) > 1:
        issues.error(
            "AMBIGUOUS_ID",
            f"service_category {category!r} is defined by {categories[category]}; qualify it, e.g. {categories[category][0]}:{category}",
            "/deal_profile/service_category",
        )
    for i, pr in enumerate(profile.client_priorities):
        if pr not in priorities:
            _vocab_error(
                issues, f"/deal_profile/client_priorities/{i}", pr, list(priorities), "priority"
            )
    if len(set(profile.client_priorities)) != len(profile.client_priorities):
        issues.error(
            "DUPLICATE_ID",
            "client_priorities repeats a priority",
            "/deal_profile/client_priorities",
        )
    lever_names = sorted(set(lever_reals) | {r.concept for r in lever_reals.values()})
    for key in ("include_levers", "exclude_levers"):
        for i, lv in enumerate(getattr(opts, key)):
            if lv not in lever_names:
                _vocab_error(issues, f"/options/{key}/{i}", lv, lever_names, "lever")
    v = profile.volume
    figures = {k: getattr(v, k) for k in ("low", "expected", "high") if getattr(v, k) is not None}
    if figures and v.period is None:
        issues.error(
            "SCHEMA", "volume figures need a period (MONTH or YEAR)", "/deal_profile/volume/period"
        )
    if v.certainty == "UNKNOWN" and figures:
        issues.warn(
            "VOLUME_FIGURES_IGNORED",
            "volume certainty is UNKNOWN, so the figures are not used",
            "/deal_profile/volume",
        )
        figures = {}
    ordered = [figures[k] for k in ("low", "expected", "high") if k in figures]
    if ordered != sorted(ordered):
        issues.error(
            "RANGE", "volume figures must satisfy low <= expected <= high", "/deal_profile/volume"
        )
    if any(x < 0 for x in ordered):
        issues.error("RANGE", "volume figures cannot be negative", "/deal_profile/volume")
    if issues.has_errors:
        return {"status": "invalid", "issues": report(issues)}

    term = profile.term or Term()
    shape = Shape(
        kind=profile.unit_of_work.kind,
        tiers=[slug(t) for t in profile.unit_of_work.tiers]
        if profile.unit_of_work.kind == "COUNT"
        else [],
        description=profile.unit_of_work.description,
        service_category=category,
        packs=list(packs),
        cost_shape=profile.cost_profile.shape,
        fixed_team=profile.cost_profile.fixed_team,
        setup_investment=profile.cost_profile.setup_investment,
        certainty=v.certainty,
        expected=figures.get("expected"),
        low=figures.get("low"),
        high=figures.get("high"),
        period=v.period,
        term_months=term.months,
        early_exit=term.client_can_terminate_early,
        automation_expected=profile.flags.automation_expected,
    )
    if profile.unit_of_work.tiers and shape.kind != "COUNT":
        issues.warn(
            "TIERS_IGNORED",
            "complexity tiers apply to COUNT work only",
            "/deal_profile/unit_of_work/tiers",
        )
    if v.certainty == "UNKNOWN":
        issues.warn(
            "VOLUME_UNKNOWN",
            "volume is unknown: scenario volumes are placeholders, and banded or collared structures are suggested",
            "/deal_profile/volume",
        )
    profile_doc = profile.model_dump(mode="json")

    # lever pool: suggested by the profile and the priorities, plus partner includes
    def keys_for(name: str) -> list[str]:
        return [k for k, r in lever_reals.items() if k == name or r.concept == name]

    pool: set[str] = set()
    for k, r in lever_reals.items():
        cond = r.data.get("suggested_when")
        if cond is not None and evaluate(cond, profile_doc):
            pool.add(k)
    for pr in profile.client_priorities:
        for name in (priorities[pr][1].get("attributes") or {}).get("suggests") or []:
            pool.update(keys_for(name))
    include_groups = [sorted(keys_for(name)) for name in opts.include_levers]
    included = {k for group in include_groups for k in group}
    excluded_keys = {k for name in opts.exclude_levers for k in keys_for(name)}
    pool = (pool | included) - excluded_keys

    models = [
        r
        for r in reals.values()
        if r.kind == "model"
        and shape.kind in (r.data.get("unit_kinds") or [])
        and (shape.tiers or not r.data.get("requires_tiers"))
    ]

    # compositions
    comps: list[Composition] = []
    not_applicable: dict[tuple[str, str], str] = {}
    pool_levers = [lever_reals[k] for k in sorted(pool)]
    for model in models:
        for n in range(0, MAX_LEVERS + 1):
            for subset in itertools.combinations(pool_levers, n):
                subset = list(subset)
                if any(lever_applies(lv, model, shape, subset) for lv in subset):
                    continue
                # an included lever named by concept is satisfied by any of its variants
                missing_include = False
                for group in include_groups:
                    if any(lever_reals[k] in subset for k in group):
                        continue
                    reasons = {
                        k: lever_applies(lever_reals[k], model, shape, [*subset, lever_reals[k]])
                        for k in group
                        if k not in excluded_keys
                    }
                    if any(r is None for r in reasons.values()):
                        missing_include = True
                        break
                    for k, reason in reasons.items():
                        not_applicable.setdefault((k, model.key), reason)
                if missing_include:
                    continue
                comps.append(Composition(shape, model, subset))

    # exclusion
    allowed = RISK_LIMIT[profile.provider_constraints.max_volume_risk]
    excluded: dict[str, dict] = {}

    def exclude(rule: str, reason: str, comp: Composition) -> None:
        rec = excluded.setdefault(
            rule, {"rule": rule, "reason": reason, "compositions": 0, "example": comp.id}
        )
        rec["compositions"] += 1
        rec["example"] = min(rec["example"], comp.id)

    comp_rules = [
        (p.id, r)
        for p in chain
        for r in p.rules
        if r.get("kind") == "composition" and r.get("evaluable")
    ]
    kept: list[Composition] = []
    for comp in comps:
        if comp.labels["volume_shortfall"] not in allowed:
            exclude(
                "provider_constraints.max_volume_risk",
                f"The provider accepts at most {profile.provider_constraints.max_volume_risk} volume risk.",
                comp,
            )
            continue
        hit = next(((pid, r) for pid, r in comp_rules if evaluate(r["when"], comp.doc)), None)
        if hit:
            pid, r = hit
            exclude(f"{pid}:{r['id']}", (r.get("emit") or {}).get("message") or "", comp)
            continue
        kept.append(comp)

    # engagement-level conflicts (rules whose assessment excludes) run on each skeleton
    excluding_rules = [
        r
        for p in chain
        for r in p.rules
        if r.get("kind") != "composition"
        and r.get("evaluable")
        and r.get("assessment") in EXCLUDING_ASSESSMENTS
    ]
    if excluding_rules:
        survivors = []
        for comp in kept:
            fired = _fired_rules(shape, comp)
            hit = next((f for f in fired if f["assessment"] in EXCLUDING_ASSESSMENTS), None)
            if hit:
                exclude(f"{hit['pack']}:{hit['rule']}", hit.get("message") or "", comp)
            else:
                survivors.append(comp)
        kept = survivors

    # fit and tension
    for comp in kept:
        for pr in profile.client_priorities:
            attrs = priorities[pr][1].get("attributes") or {}
            if evaluate(attrs["fits"], comp.doc):
                comp.fits.append(pr)
            elif evaluate(attrs["tension"], comp.doc):
                comp.tensions.append({"priority": pr, "note": attrs.get("tension_note")})

    selected = _select(kept, profile.client_priorities, opts.max_candidates)
    if not selected:
        issues.warn(
            "NO_CANDIDATES", "no structure satisfies the profile and constraints", "/deal_profile"
        )

    extra = extra_assumptions([lv for c in selected for lv in c.levers])
    known_ids = [c.id for c in selected]
    for i, eid in enumerate(opts.expand):
        if eid not in known_ids:
            near = _nearest(eid, known_ids)
            issues.error(
                "UNKNOWN_CANDIDATE",
                f"no candidate {eid!r} in this proposal",
                f"/options/expand/{i}",
                expected=known_ids,
                **({"hint": f"did you mean {near!r}?"} if near else {}),
            )
    if issues.has_errors:
        return {"status": "invalid", "issues": report(issues)}

    skeletons = {c.id: _skeleton(shape, c, extra) for c in selected}
    labels_by_id = {c.id: _input_labels(skeletons[c.id]) for c in selected}
    common = list(dict.fromkeys(lab for c in selected for lab in labels_by_id[c.id][1]))
    candidates = [
        _candidate(
            comp,
            shape,
            chain,
            declared,
            profile_doc,
            skeletons[comp.id],
            labels_by_id[comp.id],
            common,
            comp.id in opts.expand,
        )
        for comp in _ordered(selected)
    ]
    levers_na = [
        {"lever": f"{lever_reals[k].pack}:{k}", "model": f"{reals[m].pack}:{m}", "reason": reason}
        for (k, m), reason in sorted(not_applicable.items())
        if m in {c.model.key for c in selected}
    ]
    warnings = [
        {
            "code": "LABELS_ARE_PROPOSED",
            "message": "Risk labels are pack assertions (D_PROPOSED). Fill a skeleton and run derive_risk_exposure to check them.",
        }
    ]
    if len(selected) < opts.max_candidates:
        warnings.append(
            {
                "code": "FEWER_CANDIDATES",
                "message": f"{len(selected)} distinct structures satisfy the profile; asked for {opts.max_candidates}.",
            }
        )
    for i in issues:
        if i.severity == "WARNING":
            warnings.append({"code": i.code, "message": i.message})
    definitions = dict(DEFINITIONS)
    if figures and shape.term_months and shape.period:
        definitions["scenario volumes"] = (
            f"Term totals: the profile's {shape.period.lower()}ly figures times "
            + (f"{shape.term_months}/12" if shape.period == "YEAR" else str(shape.term_months))
            + (", rounded to whole units." if shape.kind == "COUNT" else ".")
        )
    payload = {
        "packs": [{"id": p.id, "version": p.meta.get("version")} for p in chain],
        "engine_version": ENGINE_VERSION,
        "schema_version": SCHEMA_VERSION,
        "deal_profile": profile_doc,
        "options": {k: v for k, v in opts.model_dump(mode="json").items() if k != "expand"},
    }
    return {
        "status": "ok",
        "record_type": "StructureProposal",
        "approval_state": "PENDING_HUMAN_REVIEW",
        "fingerprint": fingerprint(payload),
        "order_note": ORDER_NOTE,
        "candidates": candidates,
        "common_inputs": common,
        "excluded": sorted(excluded.values(), key=lambda e: e["rule"]),
        "levers_not_applicable": levers_na,
        "warnings": warnings,
        "next_step": {
            "tool": "propose_structures",
            "note": "Expand the candidates to compare (options.expand), fill their requires_inputs and common_inputs, then run compare_arrangements on the skeleton scenarios.",
        },
        "definitions": definitions,
    }


def _select(comps: list[Composition], priorities: list[str], limit: int) -> list[Composition]:
    """Round-robin across shortfall groups. Within a group, each further pick uses a different base
    model and, where possible, a different spend shape. Preference decides only what is listed."""
    groups = {
        g: sorted(
            [c for c in comps if c.labels["volume_shortfall"] == g],
            key=lambda c: c.preference(priorities),
        )
        for g in GROUP_ORDER
    }
    picked: dict[str, list[Composition]] = {g: [] for g in GROUP_ORDER}
    out: list[Composition] = []
    while len(out) < limit:
        progress = False
        for g in GROUP_ORDER:
            if len(out) >= limit:
                break
            used_models = {c.model.key for c in picked[g]}
            used_spend = {c.labels["spend_variability"] for c in picked[g]}
            options = [c for c in groups[g] if c.model.key not in used_models]
            choice = options[0] if options else None
            if choice is not None:
                # spend shape breaks ties on fit only; it never outranks a better fit
                fit = choice.preference(priorities)[:2]
                choice = next(
                    (
                        c
                        for c in options
                        if c.preference(priorities)[:2] == fit
                        and c.labels["spend_variability"] not in used_spend
                    ),
                    choice,
                )
            if choice is not None:
                picked[g].append(choice)
                out.append(choice)
                progress = True
        if not progress:
            break
    return out


def _ordered(selected: list[Composition]) -> list[Composition]:
    return sorted(selected, key=lambda c: (GROUP_ORDER.index(c.labels["volume_shortfall"]), c.id))


TERM_PATHS = ("/engagement/arrangement_versions/", "/engagement/weight_tables/")
SHARED_LABELS = {"currency (ISO code)", "start date"}


def _input_labels(skeleton: dict) -> tuple[list[str], list[str]]:
    """(the candidate's own terms, inputs every candidate shares: header, units, costs, and
    scenario volumes)."""
    own: dict[str, None] = {}
    shared: dict[str, None] = {}
    for path, label in find_placeholders(skeleton):
        if not label:
            continue
        if path.startswith(TERM_PATHS) and label not in SHARED_LABELS:
            own.setdefault(label, None)
        elif path.startswith("/engagement/unit_definitions/"):
            shared.setdefault(label.split(",")[0] + " for each unit", None)
        else:
            shared.setdefault(label, None)
    return _group_tiers(list(own)), _group_tiers(list(shared))


def _group_tiers(labels: list[str]) -> list[str]:
    """Collapse labels that differ only by their ", tier X" suffix into one "(each tier)" entry."""
    out: dict[str, None] = {}
    for label in labels:
        head, sep, _ = label.rpartition(", tier ")
        out.setdefault(f"{head} (each tier)" if sep else label, None)
    return list(out)


def _fired_rules(shape: Shape, comp: Composition) -> list[dict]:
    filled = sample_fill(
        {"engagement": assemble_engagement(shape, comp.model, comp.levers), "scenarios": []}
    )
    try:
        e = Engagement.model_validate(filled["engagement"])
    except ValidationError:
        return []
    return evaluate_rules(e, Issues())


def _candidate(
    comp: Composition,
    shape: Shape,
    chain: list,
    declared: list[str],
    profile_doc: dict,
    skeleton: dict,
    labels: tuple[list[str], list[str]],
    common: list[str],
    expand: bool,
) -> dict:
    lever_names = [lv.label[0].lower() + lv.label[1:] for lv in comp.levers]
    label = comp.model.label + (
        " with "
        + (
            ", ".join(lever_names[:-1]) + " and " + lever_names[-1]
            if len(lever_names) > 1
            else lever_names[0]
        )
        if lever_names
        else ""
    )
    tradeoffs = list(comp.model.data.get("tradeoffs") or [])
    for lv in comp.levers:
        tradeoffs += list(lv.data.get("tradeoffs") or [])
    if comp.labels.get("early_exit") == "PROVIDER":
        tradeoffs.append(
            "Early exit strands the provider's cost; a termination fee (CL-P14) shifts it."
        )
    notes = []
    heuristics = _scheme(chain, "selection_heuristics")
    for hid, (pid, h) in sorted(heuristics.items()):
        attrs = h.get("attributes") or {}
        signal = attrs.get("profile_signal")
        if signal is None or not evaluate(signal, profile_doc):
            continue
        if comp.model.concept in (attrs.get("favored_refs") or []):
            notes.append(f"{pid}:{hid} favors this for: {attrs.get('characteristic')}")
        mitigated = set(comp.model.data.get("mitigates") or [])
        if shape.tiers:
            mitigated |= set(comp.model.data.get("mitigates_when_tiers") or [])
        for lv in comp.levers:
            mitigated |= set(lv.data.get("mitigates") or [])
        if hid in mitigated:
            continue
        if comp.model.concept in (attrs.get("caution_refs") or []):
            caution = "; ".join(attrs.get("caution") or [])
            notes.append(f"{pid}:{hid} ({attrs.get('characteristic')}) cautions: {caution}")
    rules = [
        {"rule": f"{f['pack']}:{f['rule']}", "severity": f["severity"], "message": f["message"]}
        for f in _fired_rules(shape, comp)
        if f["severity"] != "INFO"
    ]
    filled = sample_fill({"engagement": skeleton["engagement"], "scenarios": []})["engagement"]
    for a in validate_engagement(filled)["approvals_required"]:
        rules.append(
            {
                "rule": f"validation:{a['code']}",
                "severity": "APPROVAL_REQUIRED",
                "message": a["message"],
            }
        )
    evidence = [_evidence(chain, declared, comp.model.concept)] + [
        _evidence(chain, declared, c) for c in dict.fromkeys(lv.concept for lv in comp.levers)
    ]
    return {
        "id": comp.id,
        "label": label,
        "composition": {
            "base_model": f"{comp.model.pack}:{comp.model.concept}",
            "levers": [f"{lv.pack}:{lv.key}" for lv in comp.levers],
        },
        "risk_allocation": comp.labels,
        **(
            {"label_assumes": assumes}
            if (
                assumes := [
                    x
                    for x in [comp.model.data.get("label_assumes")]
                    + [lv.data.get("label_assumes") for lv in comp.levers]
                    if x
                ]
            )
            else {}
        ),
        "fits_priorities": comp.fits,
        "tension_with_priorities": comp.tensions,
        "tradeoffs": tradeoffs,
        "notes": notes,
        "rules": rules,
        "requires_inputs": labels[0],
        "evidence": evidence,
        "similar_template": _similar_template(chain, comp),
        "skeleton": skeleton if expand else None,
    }


def _similar_template(chain: list, comp: Composition) -> str | None:
    for p in chain:
        for tid, t in sorted(p.templates.items()):
            c = t.get("composition") or {}
            if c.get("base_model") == comp.model.concept and sorted(
                c.get("levers") or []
            ) == sorted(lv.concept for lv in comp.levers):
                return f"{p.id}:{tid}"
    return None
