"""The Cometric ontology as files: Turtle (OWL classes for the core model, SKOS concept schemes for
the core vocabularies and every pack) and a Markdown reference (spec 3.7).

Everything is generated from the input models, the core enums, and the pack data, so the published
files cannot drift from what the engine accepts. `cometric ontology --out docs/ontology` rewrites
them; a test fails when the committed copy is stale.
"""

from __future__ import annotations

import enum
import inspect
import json
import re
import types
from datetime import date
from decimal import Decimal
from typing import Annotated, Any, Literal, Union, get_args, get_origin

from annotated_types import MinLen
from pydantic import BaseModel
from pydantic_core import PydanticUndefined

from . import enums, models
from .glossary import GLOSSARY
from .packs import Pack, available_packs, load_pack, pack_chain

BASE = "https://github.com/mfbaig35r/cometric/ontology/"
CORE_NS = BASE + "core#"
VOCAB_NS = BASE + "vocab#"
ROOTS = (models.Engagement, models.Scenario, models.CostPolicy, models.TolerancePolicy)

CLASS_NOTES = {
    "Engagement": "An evaluated client-provider relationship: parties, services, effective-dated arrangement versions, and an optional delivery plan.",
    "MoneyPolicy": "Rounding mode, scale, and level for money amounts.",
    "PackRef": "A domain pack the engagement declares, optionally pinned to a version.",
    "Party": "A contract party: client, provider, or subcontractor.",
    "UnitDefinition": "An unambiguous measurable unit of work, with its counting and acceptance rules.",
    "WeightBand": "One complexity band of a weight table and its weight.",
    "ComplexityWeightTable": "Conversion from raw units to weighted units by complexity band.",
    "Service": "A defined operational obligation, priced in one unit.",
    "EffectivePeriod": "The date range in which a fee component or cost component applies.",
    "Tier": "One band of a rate schedule: lower bound, optional upper bound, and rate.",
    "RateSchedule": "Rates and tiers for one unit, with a tier method, tier scope, and accumulation period.",
    "RoleRate": "An hourly rate for one role.",
    "ResourceLine": "Dedicated staffing priced per FTE-month.",
    "PaymentLine": "One scheduled payment of a project fee.",
    "OutcomeTerms": "Terms of an outcome-based fee: form, measured metric, baseline or target, share, attribution, cap, and approval.",
    "FeeComponent": "One charge computed by one calculation method.",
    "Rollover": "What happens to unused entitlement at the end of its period.",
    "Entitlement": "What a base fee or commitment purchases: an included quantity of a unit per period.",
    "Commitment": "A minimum spend, minimum volume, reserved capacity, or prepaid credit, tested over a period with a shortfall rule.",
    "Adjustment": "A mechanism that modifies a named subtotal at a declared evaluation step: discount, rebate, collar, service credit, holdback, bonus, cap, or indexation.",
    "ArrangementVersion": "An effective-dated commercial configuration: fee components, entitlements, rate schedules, commitments, and adjustments.",
    "CostTier": "One band of a tiered variable cost.",
    "IncurredLine": "One month's incurred amount of a one-time cost.",
    "CostComponent": "A direct or allocated cost, classified into a margin layer by the cost policy.",
    "CapacityLimit": "A limit on a quantity per period, with the cost of overflow when it is exceeded.",
    "ResourceRole": "A staffing role with its FTE, available hours, productive ratio, and safe utilization ceiling.",
    "ProductionStandard": "Effort per unit of output, converting demand quantities to demand hours.",
    "DeliveryPlan": "How work is produced. Drives cost and capacity, not contractual fee.",
    "RiskAllocation": "An identified exposure and the party declared to bear it.",
    "Horizon": "The months a scenario covers.",
    "Scenario": "A time-indexed set of assumptions that one or more arrangements are evaluated against.",
    "CostPolicy": "Mapping from cost category to margin layer, plus the transition-cost view.",
    "TolerancePolicy": "Relative deviations treated as adverse when deriving who bears risk.",
}

# Fields that hold the id of another object. In the data they are strings; in the ontology they
# are object properties, because that is the relationship they express.
REFERENCES = {
    ("Service", "unit_definition_id"): "UnitDefinition",
    ("FeeComponent", "service_id"): "Service",
    ("FeeComponent", "rate_schedule_id"): "RateSchedule",
    ("FeeComponent", "entitlement_id"): "Entitlement",
    ("FeeComponent", "weight_table_id"): "ComplexityWeightTable",
    ("FeeComponent", "depends_on"): "FeeComponent",
    ("Entitlement", "granted_by"): "FeeComponent",
    ("Commitment", "component_ids"): "FeeComponent",
    ("Commitment", "service_id"): "Service",
    ("Adjustment", "applies_to"): "FeeComponent",
    ("Adjustment", "component_id"): "FeeComponent",
    ("Adjustment", "outside_rate_schedule_id"): "RateSchedule",
    ("ArrangementVersion", "supersedes_id"): "ArrangementVersion",
    ("CapacityLimit", "overflow_replaces"): "CostComponent",
}
REFERENCE_NOTES = {
    ("FeeComponent", "depends_on"): "Components or entitlements of the same version",
}
XSD = {
    str: "xsd:string",
    Decimal: "xsd:decimal",
    date: "xsd:date",
    int: "xsd:integer",
    bool: "xsd:boolean",
}
PREFIXES = {
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
    "owl": "http://www.w3.org/2002/07/owl#",
    "xsd": "http://www.w3.org/2001/XMLSchema#",
    "skos": "http://www.w3.org/2004/02/skos/core#",
    "dcterms": "http://purl.org/dc/terms/",
    "cm": CORE_NS,
    "cmv": VOCAB_NS,
}
_LOCAL = re.compile(r"^[A-Za-z0-9_]([A-Za-z0-9_.-]*[A-Za-z0-9_-])?$")


# --- model introspection -------------------------------------------------------------------


class Field:
    def __init__(self, owner: str, name: str, kind: str, target: Any, **kw: Any) -> None:
        self.owner, self.name, self.kind, self.target = owner, name, kind, target
        self.required: bool = kw.get("required", False)
        self.multiple: bool = kw.get("multiple", False)
        self.min_items: int = kw.get("min_items", 0)
        self.description: str | None = kw.get("description")
        self.default: str | None = kw.get("default")
        self.values: list[str] = kw.get("values", [])

    @property
    def type_text(self) -> str:
        t = {
            "model": f"{self.target}",
            "ref": f"→ {self.target} (by id)",
            "enum": f"{self.target}",
            "literal": "one of " + ", ".join(f"`{v}`" for v in self.values),
            "map": "object (map)",
        }.get(self.kind)
        if t is None:
            t = {
                "xsd:gYearMonth": "month (YYYY-MM)",
                "xsd:decimal": "decimal (string)",
                "xsd:date": "date",
                "xsd:string": "string",
                "xsd:integer": "integer",
                "xsd:boolean": "boolean",
            }[self.target]
        return f"list of {t}" if self.multiple else t

    @property
    def cardinality(self) -> str:
        if self.multiple:
            return f"{self.min_items}..*"
        return "1" if self.required else "0..1"


def _unwrap(ann: Any) -> Any:
    while get_origin(ann) is Annotated:
        ann = get_args(ann)[0]
    return ann


def _describe(owner: type[BaseModel], name: str, info: Any) -> Field:
    ann = info.annotation
    if get_origin(ann) in (Union, types.UnionType):
        ann = next(a for a in get_args(ann) if a is not type(None))
    is_month = ann is models.Month
    ann = _unwrap(ann)
    multiple = False
    if get_origin(ann) is list:
        multiple = True
        inner = get_args(ann)[0]
        is_month = inner is models.Month
        ann = _unwrap(inner)
    default = None
    if info.default is not PydanticUndefined and info.default not in (None, [], {}):
        d = info.default
        if isinstance(d, enum.Enum):
            default = d.value
        elif not isinstance(d, BaseModel):
            default = str(d)
    kw: dict[str, Any] = {
        "required": info.is_required(),
        "multiple": multiple,
        "min_items": next((m.min_length for m in info.metadata if isinstance(m, MinLen)), 0),
        "description": info.description,
        "default": default,
    }
    fname = info.alias or name
    oname = owner.__name__
    if (oname, name) in REFERENCES:
        return Field(oname, fname, "ref", REFERENCES[(oname, name)], **kw)
    if ann is dict or get_origin(ann) is dict:
        return Field(oname, fname, "map", None, **kw)
    if get_origin(ann) is Literal:
        return Field(oname, fname, "literal", "xsd:string", values=list(get_args(ann)), **kw)
    if inspect.isclass(ann) and issubclass(ann, BaseModel):
        return Field(oname, fname, "model", ann.__name__, **kw)
    if inspect.isclass(ann) and issubclass(ann, enum.Enum):
        return Field(oname, fname, "enum", ann.__name__, **kw)
    if is_month:
        return Field(oname, fname, "scalar", "xsd:gYearMonth", **kw)
    return Field(oname, fname, "scalar", XSD[ann], **kw)


def core_model() -> dict[str, list[Field]]:
    """Every input class reachable from the root documents, in discovery order."""
    out: dict[str, list[Field]] = {}
    queue: list[type[BaseModel]] = list(ROOTS)
    while queue:
        cls = queue.pop(0)
        if cls.__name__ in out:
            continue
        fields = [_describe(cls, n, i) for n, i in cls.model_fields.items()]
        out[cls.__name__] = fields
        for f in fields:
            if f.kind == "model":
                queue.append(getattr(models, f.target))
    return out


def class_note(name: str) -> str:
    doc = getattr(models, name).__doc__
    return inspect.cleandoc(doc).split("\n\n")[0].replace("\n", " ") if doc else CLASS_NOTES[name]


def core_vocabularies() -> dict[str, list[str]]:
    out = {}
    for name, cls in inspect.getmembers(enums, inspect.isclass):
        if issubclass(cls, enum.Enum) and cls.__module__ == enums.__name__:
            out[name] = [v.value for v in cls]
    return out


def _snake(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def vocab_note(name: str) -> str | None:
    return GLOSSARY.get(_snake(name))


# --- pack index ----------------------------------------------------------------------------


def packs() -> list[Pack]:
    return [load_pack(p) for p in available_packs()]


class _Index:
    """Ids are unique within a pack chain, not across packs, so references resolve through the
    referring pack's own chain (the pack first, then the packs it extends)."""

    def __init__(self) -> None:
        self.own: dict[str, dict[str, str]] = {}
        for p in packs():
            labels: dict[str, str] = {}
            entries = (
                [(c["id"], c.get("label")) for c in p.concepts()]
                + [(r["id"], (r.get("emit") or {}).get("code")) for r in p.rules]
                + [(c["id"], None) for c in p.claims]
                + [(x["id"], x.get("title")) for x in p.sources]
            )
            for key, label in entries:
                if str(key) in labels:
                    raise ValueError(f"pack {p.id}: id {key} is defined twice")
                labels[str(key)] = str(label or "")
            self.own[p.id] = labels

    def resolve(self, here: str, key: str) -> tuple[str, str]:
        for q in pack_chain(here):
            if key in self.own[q.id]:
                return q.id, self.own[q.id][key]
        raise ValueError(f"pack {here}: unknown reference {key!r}")


def _index() -> _Index:
    return _Index()


# --- Turtle --------------------------------------------------------------------------------


def _lit(value: Any, lang: str | None = "en", dtype: str | None = None) -> str:
    text = str(value)
    text = (
        text.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )
    if dtype:
        return f'"{text}"^^{dtype}'
    return f'"{text}"@{lang}' if lang else f'"{text}"'


def _q(prefix: str, local: str, ns: str) -> str:
    return f"{prefix}:{local}" if _LOCAL.match(local) else f"<{ns}{local}>"


def pack_ns(pack_id: str) -> str:
    return f"{BASE}pack/{pack_id}#"


def _pk(pack_id: str, local: str) -> str:
    return _q(f"pack-{pack_id}", local, pack_ns(pack_id))


def _cm(local: str) -> str:
    return _q("cm", local, CORE_NS)


def _cmv(local: str) -> str:
    return _q("cmv", local, VOCAB_NS)


class _Turtle:
    def __init__(self) -> None:
        self.blocks: list[str] = []

    def section(self, title: str) -> None:
        self.blocks.append(f"# --- {title} " + "-" * max(3, 86 - len(title)))

    def add(self, subject: str, *pairs: tuple[str, Any]) -> None:
        lines = []
        for pred, obj in pairs:
            if obj is None or obj == []:
                continue
            objs = obj if isinstance(obj, list) else [obj]
            lines.append(f"{pred} " + ", ".join(objs))
        self.blocks.append(subject + " " + " ;\n    ".join(lines) + " .")

    def text(self) -> str:
        return "\n\n".join(self.blocks) + "\n"


_CORE_TERMS: list[tuple[str, str, str, str | None]] = [
    # (local name, kind, label, comment)
    (
        "Pack",
        "owl:Class",
        "pack",
        "A versioned bundle of domain vocabulary, rules, evidence, and templates.",
    ),
    (
        "Overlay",
        "owl:Class",
        "overlay",
        "A pack's sector-specific prevalence, evidence, or caveats for a concept defined by a pack it extends.",
    ),
    (
        "Rule",
        "owl:Class",
        "rule",
        "A compatibility or reasoning rule. Evaluable rules fire on engagements whose data matches their condition.",
    ),
    ("Claim", "owl:Class", "claim", "An atomic proposition with an evidence class and prevalence."),
    ("Source", "owl:Class", "source", "An external source that supports claims."),
    (
        "pack",
        "owl:ObjectProperty",
        "pack",
        "The pack that defines this concept scheme, overlay, rule, claim, or source.",
    ),
    ("extends", "owl:ObjectProperty", "extends", "The pack this pack builds on."),
    ("overlays", "owl:ObjectProperty", "overlays", "The concept an overlay qualifies."),
    (
        "evidenceClass",
        "owl:ObjectProperty",
        "evidence class",
        "A_DIRECT, B_CORROBORATED, C_INFERENCE, or D_PROPOSED. Independent of prevalence.",
    ),
    ("prevalence", "owl:ObjectProperty", "prevalence", None),
    (
        "billingBasis",
        "owl:ObjectProperty",
        "billing basis",
        "Core billing bases a concept maps to.",
    ),
    (
        "calculationMethod",
        "owl:ObjectProperty",
        "calculation method",
        "Core calculation methods that execute a concept.",
    ),
    (
        "claim",
        "owl:ObjectProperty",
        "claim",
        "A claim that supports this concept, overlay, or rule.",
    ),
    ("source", "owl:ObjectProperty", "source", "A source that supports this claim."),
    ("severity", "owl:ObjectProperty", "severity", None),
    ("caveat", "owl:AnnotationProperty", "caveat", None),
    (
        "sourceRef",
        "owl:AnnotationProperty",
        "source reference",
        "Where in the originating research this entry comes from.",
    ),
    ("status", "owl:DatatypeProperty", "status", None),
    ("kind", "owl:DatatypeProperty", "kind", None),
    (
        "attributes",
        "owl:DatatypeProperty",
        "attributes",
        "Scheme-specific attributes as a JSON object.",
    ),
    ("assessment", "owl:DatatypeProperty", "assessment", None),
    (
        "evaluable",
        "owl:DatatypeProperty",
        "evaluable",
        "Whether the engine evaluates the rule's condition against engagements.",
    ),
    ("code", "owl:DatatypeProperty", "issue code", None),
    ("message", "owl:DatatypeProperty", "message", None),
    ("explanation", "owl:DatatypeProperty", "explanation", None),
    (
        "condition",
        "owl:DatatypeProperty",
        "condition",
        "The rule's predicate over the engagement document, as JSON.",
    ),
    ("statement", "owl:DatatypeProperty", "statement", None),
    ("url", "owl:DatatypeProperty", "URL", None),
    ("sourceType", "owl:DatatypeProperty", "source type", None),
    ("retrievedDate", "owl:DatatypeProperty", "retrieved date", None),
    ("publicationDate", "owl:DatatypeProperty", "publication date", None),
    ("verified", "owl:DatatypeProperty", "verified", None),
    (
        "required",
        "owl:AnnotationProperty",
        "required",
        "Whether an input document must supply this field.",
    ),
    ("multiple", "owl:AnnotationProperty", "multiple", "Whether the field holds a list."),
    ("minItems", "owl:AnnotationProperty", "minimum items", None),
    ("defaultValue", "owl:AnnotationProperty", "default value", None),
    ("allowedValue", "owl:AnnotationProperty", "allowed value", None),
    (
        "fieldName",
        "owl:AnnotationProperty",
        "field name",
        "The JSON key of this field in input documents.",
    ),
    (
        "referencedById",
        "owl:AnnotationProperty",
        "referenced by id",
        "In input documents the field holds the id of the related object.",
    ),
]


def to_turtle() -> str:
    ps = packs()
    idx = _index()
    t = _Turtle()
    prefixes = dict(PREFIXES)
    for p in ps:
        prefixes[f"pack-{p.id}"] = pack_ns(p.id)
    t.blocks.append("\n".join(f"@prefix {k}: <{v}> ." for k, v in prefixes.items()))
    versions = ", ".join(f"{p.id} {p.meta.get('version')}" for p in ps)
    t.add(
        f"<{BASE}>",
        ("a", "owl:Ontology"),
        ("rdfs:label", _lit("Cometric commercial ontology")),
        (
            "rdfs:comment",
            _lit(
                "Commercial arrangements, engagement economics, and domain knowledge: OWL classes "
                "for the input model, SKOS concept schemes for the core vocabularies and every pack, "
                "and the rules and evidence the packs carry. Generated from the cometric package."
            ),
        ),
        ("owl:versionInfo", _lit(f"schema {models.SCHEMA_VERSION}; packs {versions}", None)),
        ("dcterms:license", "<https://www.apache.org/licenses/LICENSE-2.0>"),
    )

    t.section("ontology terms")
    for local, kind, label, comment in _CORE_TERMS:
        t.add(
            _cm(local),
            ("a", kind),
            ("rdfs:label", _lit(label)),
            ("rdfs:comment", _lit(comment) if comment else None),
        )

    t.section("core vocabularies")
    for name, values in core_vocabularies().items():
        note = vocab_note(name)
        t.add(
            _cmv(name),
            ("a", ["owl:Class", "skos:ConceptScheme"]),
            ("rdfs:label", _lit(name)),
            ("skos:definition", _lit(note) if note else None),
        )
        for v in values:
            t.add(
                _cmv(f"{name}.{v}"),
                ("a", ["skos:Concept", _cmv(name)]),
                ("skos:prefLabel", _lit(v)),
                ("skos:notation", _lit(v, None)),
                ("skos:inScheme", _cmv(name)),
                ("skos:topConceptOf", _cmv(name)),
            )

    t.section("glossary")
    t.add(
        _cmv("Glossary"),
        ("a", "skos:ConceptScheme"),
        ("rdfs:label", _lit("Glossary of output terms")),
    )
    for term, definition in GLOSSARY.items():
        t.add(
            _cmv(f"term.{term}"),
            ("a", "skos:Concept"),
            ("skos:prefLabel", _lit(term)),
            ("skos:definition", _lit(definition)),
            ("skos:inScheme", _cmv("Glossary")),
        )

    t.section("core model")
    for cls, fields in core_model().items():
        t.add(
            _cm(cls),
            ("a", "owl:Class"),
            ("rdfs:label", _lit(cls)),
            ("rdfs:comment", _lit(class_note(cls))),
        )
        for f in fields:
            if f.kind in ("model", "ref"):
                kind, rng = "owl:ObjectProperty", _cm(f.target)
            elif f.kind == "enum":
                kind, rng = "owl:ObjectProperty", _cmv(f.target)
            elif f.kind == "map":
                kind, rng = "owl:DatatypeProperty", "rdf:JSON"
            else:
                kind, rng = "owl:DatatypeProperty", f.target
            comment = f.description or REFERENCE_NOTES.get((cls, f.name))
            t.add(
                _cm(f"{cls}.{f.name}"),
                ("a", kind),
                ("rdfs:label", _lit(f.name)),
                ("rdfs:domain", _cm(cls)),
                ("rdfs:range", rng),
                ("rdfs:comment", _lit(comment) if comment else None),
                ("cm:fieldName", _lit(f.name, None)),
                ("cm:required", _lit(str(f.required).lower(), dtype="xsd:boolean")),
                ("cm:multiple", _lit(str(f.multiple).lower(), dtype="xsd:boolean")),
                ("cm:minItems", _lit(f.min_items, dtype="xsd:integer") if f.min_items else None),
                ("cm:defaultValue", _lit(f.default, None) if f.default is not None else None),
                ("cm:allowedValue", [_lit(v, None) for v in f.values]),
                (
                    "cm:referencedById",
                    _lit("true", dtype="xsd:boolean") if f.kind == "ref" else None,
                ),
            )

    def ref(here: str, key: str) -> str:
        return _pk(idx.resolve(here, key)[0], key)

    for p in ps:
        t.section(f"pack {p.id}")
        t.add(
            _pk(p.id, "pack"),
            ("a", "cm:Pack"),
            ("rdfs:label", _lit(p.meta.get("title") or p.id)),
            (
                "rdfs:comment",
                _lit(p.meta.get("description")) if p.meta.get("description") else None,
            ),
            ("owl:versionInfo", _lit(p.meta.get("version"), None)),
            ("cm:extends", _pk(p.extends, "pack") if p.extends else None),
        )
        for scheme_name, doc in p.schemes.items():
            sid = _pk(p.id, f"scheme.{scheme_name}")
            t.add(
                sid,
                ("a", "skos:ConceptScheme"),
                ("rdfs:label", _lit(doc.get("title") or scheme_name)),
                ("skos:notation", _lit(scheme_name, None)),
                ("cm:pack", _pk(p.id, "pack")),
            )
            for c in doc.get("concepts", []) or []:
                cid = str(c["id"])
                attrs = c.get("attributes") or {}
                t.add(
                    _pk(p.id, cid),
                    ("a", "skos:Concept"),
                    ("skos:notation", _lit(cid, None)),
                    ("skos:prefLabel", _lit(c.get("label") or cid)),
                    ("skos:altLabel", [_lit(s) for s in c.get("synonyms") or []]),
                    ("skos:definition", _lit(c["definition"]) if c.get("definition") else None),
                    ("skos:inScheme", sid),
                    ("skos:broader", [ref(p.id, str(b)) for b in c.get("broader") or []]),
                    ("skos:related", [ref(p.id, str(r)) for r in c.get("related") or []]),
                    ("cm:kind", _lit(c["kind"], None) if c.get("kind") else None),
                    ("cm:billingBasis", [_cmv(f"BillingBasis.{b}") for b in c.get("bases") or []]),
                    (
                        "cm:calculationMethod",
                        [_cmv(f"CalculationMethod.{m}") for m in c.get("methods") or []],
                    ),
                    ("cm:evidenceClass", _evidence(c.get("evidence_class"))),
                    ("cm:prevalence", _prevalence(c.get("prevalence"))),
                    ("cm:claim", [ref(p.id, str(x)) for x in c.get("claims") or []]),
                    ("cm:caveat", [_lit(x) for x in c.get("caveats") or []]),
                    ("cm:sourceRef", _lit(c["source_ref"], None) if c.get("source_ref") else None),
                    ("cm:status", _lit(c["status"], None) if c.get("status") else None),
                    ("cm:attributes", _json(attrs) if attrs else None),
                )
        for rows in p.overlays.values():
            for o in rows:
                oid = str(o["id"])
                t.add(
                    _pk(p.id, f"overlay.{oid}"),
                    ("a", "cm:Overlay"),
                    ("cm:overlays", ref(p.id, oid)),
                    ("cm:pack", _pk(p.id, "pack")),
                    ("cm:evidenceClass", _evidence(o.get("evidence_class"))),
                    ("cm:prevalence", _prevalence(o.get("prevalence"))),
                    ("cm:claim", [ref(p.id, str(x)) for x in o.get("claims") or []]),
                    ("cm:caveat", [_lit(x) for x in o.get("caveats") or []]),
                )
        for r in p.rules:
            emit = r.get("emit") or {}
            t.add(
                _pk(p.id, str(r["id"])),
                ("a", "cm:Rule"),
                ("skos:notation", _lit(r["id"], None)),
                ("cm:pack", _pk(p.id, "pack")),
                ("cm:kind", _lit(r["kind"], None) if r.get("kind") else None),
                ("cm:assessment", _lit(r["assessment"], None) if r.get("assessment") else None),
                ("cm:evaluable", _lit(str(bool(r.get("evaluable"))).lower(), dtype="xsd:boolean")),
                ("cm:code", _lit(emit["code"], None) if emit.get("code") else None),
                (
                    "cm:severity",
                    _cmv(f"Severity.{emit['severity']}") if emit.get("severity") else None,
                ),
                ("cm:message", _lit(emit["message"]) if emit.get("message") else None),
                ("cm:explanation", _lit(r["explanation"]) if r.get("explanation") else None),
                ("cm:condition", _json(r["when"]) if r.get("when") is not None else None),
                ("cm:evidenceClass", _evidence(r.get("evidence_class"))),
                ("cm:claim", [ref(p.id, str(x)) for x in emit.get("claims") or []]),
                ("cm:sourceRef", _lit(r["source_ref"], None) if r.get("source_ref") else None),
            )
        for c in p.claims:
            t.add(
                _pk(p.id, str(c["id"])),
                ("a", "cm:Claim"),
                ("skos:notation", _lit(c["id"], None)),
                ("cm:pack", _pk(p.id, "pack")),
                ("cm:statement", _lit(c["statement"]) if c.get("statement") else None),
                ("cm:evidenceClass", _evidence(c.get("classification"))),
                ("cm:prevalence", _prevalence(c.get("prevalence"))),
                ("cm:source", [ref(p.id, str(s)) for s in c.get("sources") or []]),
                ("cm:caveat", [_lit(x) for x in c.get("caveats") or []]),
                ("cm:sourceRef", _lit(c["source_ref"], None) if c.get("source_ref") else None),
            )
        for s in p.sources:
            t.add(
                _pk(p.id, str(s["id"])),
                ("a", "cm:Source"),
                ("skos:notation", _lit(s["id"], None)),
                ("cm:pack", _pk(p.id, "pack")),
                ("rdfs:label", _lit(s["title"]) if s.get("title") else None),
                ("cm:url", _lit(s["url"], dtype="xsd:anyURI") if s.get("url") else None),
                ("cm:sourceType", _lit(s["source_type"], None) if s.get("source_type") else None),
                (
                    "cm:publicationDate",
                    _lit(s["publication_date"], None) if s.get("publication_date") else None,
                ),
                (
                    "cm:retrievedDate",
                    _lit(s["retrieved_date"], None) if s.get("retrieved_date") else None,
                ),
                ("cm:verified", _lit(str(bool(s.get("verified"))).lower(), dtype="xsd:boolean")),
            )
    return t.text()


def _evidence(value: Any) -> str | None:
    return _cmv(f"EvidenceClass.{value}") if value else None


def _prevalence(value: Any) -> str | None:
    return _cmv(f"Prevalence.{value}") if value else None


def _json(value: Any) -> str:
    return _lit(json.dumps(value, sort_keys=True, default=str), dtype="rdf:JSON")


# --- Markdown ------------------------------------------------------------------------------

GENERATED = "<!-- Generated by `cometric ontology --out docs/ontology`. Do not edit by hand. -->"


def _cell(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ").strip()


def _anchor(key: str) -> str:
    return key.lower()


def _link(key: str, idx: _Index, here: str, label: bool = True) -> str:
    pack_id, text = idx.resolve(here, key)
    target = f"#{_anchor(key)}" if pack_id == here else f"pack-{pack_id}.md#{_anchor(key)}"
    suffix = f" {text}" if label and text else ""
    return f"[{key}]({target}){suffix}"


def _mermaid(model: dict[str, list[Field]]) -> str:
    lines = ["```mermaid", "classDiagram", "    direction LR"]
    for cls, fields in model.items():
        for f in fields:
            if f.kind == "model":
                lines.append(f'    {cls} "1" *-- "{f.cardinality}" {f.target} : {f.name}')
    for cls, fields in model.items():
        for f in fields:
            if f.kind == "ref":
                lines.append(f'    {cls} ..> "{f.cardinality}" {f.target} : {f.name}')
    lines.append("```")
    return "\n".join(lines)


def readme_md() -> str:
    ps = packs()
    model = core_model()
    vocab = core_vocabularies()
    out = [
        GENERATED,
        "",
        "# Cometric ontology",
        "",
        "Cometric's ontology has three layers, all generated from the package so they match what the engine accepts:",
        "",
        "1. **Core model** ([core.md](core.md)): the classes and fields of an engagement, a scenario, and a cost policy. These are OWL classes and properties.",
        "2. **Core vocabularies** ([core.md#core-vocabularies](core.md#core-vocabularies)): the controlled values the engine executes, such as billing bases, calculation methods, accumulation periods, and evidence classes. These are SKOS concept schemes.",
        "3. **Packs**: domain knowledge as SKOS concept schemes, plus overlays, rules, claims, and sources. A pack can extend another and qualify its concepts with overlays.",
        "",
        "## Files",
        "",
        "| File | Contents |",
        "|---|---|",
        "| [cometric.ttl](cometric.ttl) | The whole ontology in Turtle (RDF): OWL for the core model, SKOS for vocabularies and packs, rules and evidence as typed resources. |",
        "| [core.md](core.md) | Core classes, fields, and vocabularies. |",
    ]
    for p in ps:
        out.append(f"| [pack-{p.id}.md](pack-{p.id}.md) | {_cell(p.meta.get('title'))}. |")
    out += [
        "",
        "## Packs",
        "",
        "| Pack | Version | Extends | Concept schemes | Concepts | Overlays | Rules | Claims | Sources |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for p in ps:
        out.append(
            f"| [{p.id}](pack-{p.id}.md) | {p.meta.get('version')} | {p.extends or ''} | "
            f"{len(p.schemes)} | {len(p.concepts())} | "
            f"{sum(len(v) for v in p.overlays.values())} | {len(p.rules)} | {len(p.claims)} | "
            f"{len(p.sources)} |"
        )
    out += [
        "",
        "## Core model",
        "",
        "Solid lines are containment (the field holds the object). Dotted lines are references by id.",
        "",
        _mermaid(model),
        "",
        "| Class | Meaning |",
        "|---|---|",
    ]
    for cls in model:
        out.append(f"| [{cls}](core.md#{cls.lower()}) | {_cell(class_note(cls))} |")
    out += [
        "",
        "## Core vocabularies",
        "",
        "| Vocabulary | Values |",
        "|---|---|",
    ]
    for name, values in vocab.items():
        out.append(f"| [{name}](core.md#{name.lower()}) | {', '.join(f'`{v}`' for v in values)} |")
    out += [
        "",
        "## Glossary",
        "",
        "| Term | Definition |",
        "|---|---|",
    ]
    for term, definition in GLOSSARY.items():
        out.append(f"| `{term}` | {_cell(definition)} |")
    out += [
        "",
        "## Using the Turtle file",
        "",
        "Namespaces:",
        "",
        "| Prefix | Namespace | Holds |",
        "|---|---|---|",
        f"| `cm:` | `{CORE_NS}` | Core classes (`cm:FeeComponent`), their fields (`cm:FeeComponent.billing_basis`), and the terms used to describe packs (`cm:Rule`, `cm:evidenceClass`). |",
        f"| `cmv:` | `{VOCAB_NS}` | Core vocabularies (`cmv:BillingBasis`) and their values (`cmv:BillingBasis.OUTPUT`), and the glossary. |",
    ]
    for p in ps:
        out.append(
            f"| `pack-{p.id}:` | `{pack_ns(p.id)}` | Concepts, schemes, overlays, rules, claims, and sources of the {p.id} pack. |"
        )
    out += [
        "",
        "The IRIs are identifiers; they are not served as web pages.",
        "",
        "Example: every pack concept that maps to the OUTPUT billing basis, with its evidence class.",
        "",
        "```python",
        "import rdflib",
        "",
        'g = rdflib.Graph().parse("docs/ontology/cometric.ttl")',
        'rows = g.query("""',
        "PREFIX skos: <http://www.w3.org/2004/02/skos/core#>",
        f"PREFIX cm: <{CORE_NS}>",
        f"PREFIX cmv: <{VOCAB_NS}>",
        "SELECT ?id ?label ?evidence WHERE {",
        "  ?c skos:notation ?id ; skos:prefLabel ?label ;",
        "     cm:billingBasis cmv:BillingBasis.OUTPUT ; cm:evidenceClass ?evidence .",
        "} ORDER BY ?id",
        '""")',
        "```",
        "",
        "The same knowledge is available at run time through the MCP server (`lookup_concept`, `list_vocabulary`, `describe_pack`, `list_applicable_evidence`) and the CLI (`cometric lookup`, `cometric packs`).",
        "",
    ]
    return "\n".join(out)


def core_md() -> str:
    model = core_model()
    out = [
        GENERATED,
        "",
        "# Core model and vocabularies",
        "",
        'Input documents are JSON. Decimal values are strings (`"1250.00"`); floats are rejected. Unknown fields are errors.',
        "",
        "Root documents: "
        + ", ".join(f"[{c.__name__}](#{c.__name__.lower()})" for c in ROOTS)
        + ".",
        "",
        "## Classes",
        "",
    ]
    for cls, fields in model.items():
        out += [f"### {cls}", "", class_note(cls), ""]
        out += ["| Field | Type | Required | Default | Notes |", "|---|---|---|---|---|"]
        for f in fields:
            if f.kind in ("model", "enum", "ref"):
                t = f.type_text.replace(f.target, f"[{f.target}](#{f.target.lower()})", 1)
            else:
                t = f.type_text
            req = "yes" if f.required else "no"
            if f.min_items:
                req += f" (at least {f.min_items})"
            notes = f.description or REFERENCE_NOTES.get((cls, f.name)) or ""
            default = f"`{f.default}`" if f.default is not None else ""
            out.append(f"| `{f.name}` | {t} | {req} | {default} | {_cell(notes)} |")
        out.append("")
    out += ["## Core vocabularies", ""]
    for name, values in core_vocabularies().items():
        out += [f"### {name}", ""]
        note = vocab_note(name)
        if note:
            out += [note, ""]
        out += [", ".join(f"`{v}`" for v in values), ""]
    return "\n".join(out)


def _scalar_attrs(attrs: dict) -> str:
    parts = []
    for k, v in attrs.items():
        if k == "row" or v in (None, "", [], {}):
            continue
        if isinstance(v, list):
            v = ", ".join(map(str, v))
        elif isinstance(v, dict):
            v = json.dumps(v, sort_keys=True, default=str)
        parts.append(f"{k}: {_cell(v)}")
    return "; ".join(parts)


def pack_md(p: Pack) -> str:
    idx = _index()
    out = [
        GENERATED,
        "",
        f"# Pack: {p.id}",
        "",
        f"{_cell(p.meta.get('title'))}, version {p.meta.get('version')}"
        + (f", extends [{p.extends}](pack-{p.extends}.md)." if p.extends else "."),
        "",
    ]
    if p.meta.get("description"):
        out += [str(p.meta["description"]).strip(), ""]
    out += [
        "Evidence classes: A_DIRECT (directly documented), B_CORROBORATED, C_INFERENCE, D_PROPOSED. C and D are inference or proposal, not observed fact.",
        "",
        "## Contents",
        "",
    ]
    for name, doc in p.schemes.items():
        n = len(doc.get("concepts") or [])
        out.append(f"- [{_cell(doc.get('title') or name)}](#scheme-{name.replace('_', '-')}) ({n})")
    for title, items in (
        ("Overlays", sum(len(v) for v in p.overlays.values())),
        ("Rules", len(p.rules)),
        ("Claims", len(p.claims)),
        ("Sources", len(p.sources)),
    ):
        if items:
            out.append(f"- [{title}](#{title.lower()}) ({items})")
    out.append("")
    for name, doc in p.schemes.items():
        out += [
            f'<a id="scheme-{name.replace("_", "-")}"></a>',
            "",
            f"## {_cell(doc.get('title') or name)}",
            "",
            f"Scheme `{name}`.",
            "",
        ]
        for c in doc.get("concepts", []) or []:
            cid = str(c["id"])
            tags = [x for x in (c.get("evidence_class"), c.get("prevalence")) if x]
            head = f"**{cid}** {_cell(c.get('label') or '')}"
            if tags:
                head += " (" + ", ".join(f"`{x}`" for x in tags) + ")"
            out += [f'<a id="{_anchor(cid)}"></a>', "", head, ""]
            if c.get("definition"):
                out += [_cell(c["definition"]), ""]
            facts = []
            if c.get("synonyms"):
                facts.append("Synonyms: " + ", ".join(map(_cell, c["synonyms"])))
            if c.get("kind"):
                facts.append(f"Kind: `{c['kind']}`")
            if c.get("bases"):
                facts.append("Billing bases: " + ", ".join(f"`{b}`" for b in c["bases"]))
            if c.get("methods"):
                facts.append("Methods: " + ", ".join(f"`{m}`" for m in c["methods"]))
            if c.get("broader"):
                facts.append(
                    "Broader: " + ", ".join(_link(str(b), idx, p.id) for b in c["broader"])
                )
            if c.get("related"):
                facts.append(
                    "Related: " + ", ".join(_link(str(r), idx, p.id) for r in c["related"])
                )
            if c.get("claims"):
                facts.append(
                    "Claims: " + ", ".join(_link(str(x), idx, p.id, False) for x in c["claims"])
                )
            attrs = _scalar_attrs(c.get("attributes") or {})
            if attrs:
                facts.append(f"Attributes: {attrs}")
            for cav in c.get("caveats") or []:
                facts.append(f"Caveat: {_cell(cav)}")
            out += [f"- {x}" for x in facts]
            if facts:
                out.append("")
    if p.overlays:
        out += [
            "## Overlays",
            "",
            "Sector-specific prevalence, evidence, and caveats for concepts defined by an extended pack.",
            "",
            "| Concept | Prevalence | Evidence | Claims | Caveats |",
            "|---|---|---|---|---|",
        ]
        for rows in p.overlays.values():
            for o in rows:
                claims = ", ".join(_link(str(x), idx, p.id, False) for x in o.get("claims") or [])
                out.append(
                    f"| {_link(str(o['id']), idx, p.id)} | {o.get('prevalence') or ''} | "
                    f"{o.get('evidence_class') or ''} | {claims} | "
                    f"{_cell(' '.join(o.get('caveats') or []))} |"
                )
        out.append("")
    if p.rules:
        out += ["## Rules", ""]
        for r in p.rules:
            emit = r.get("emit") or {}
            out += [
                f'<a id="{_anchor(str(r["id"]))}"></a>',
                "",
                f"**{r['id']}** `{emit.get('code') or ''}` ({r.get('kind') or ''}, "
                f"{emit.get('severity') or 'no issue'}"
                + (", evaluated" if r.get("evaluable") else ", not evaluated")
                + ")",
                "",
            ]
            if emit.get("message"):
                out += [_cell(emit["message"]), ""]
            facts = []
            if r.get("assessment"):
                facts.append(f"Assessment: `{r['assessment']}`")
            if r.get("explanation"):
                facts.append(f"Why: {_cell(r['explanation'])}")
            if r.get("evidence_class"):
                facts.append(f"Evidence: `{r['evidence_class']}`")
            if emit.get("claims"):
                facts.append(
                    "Claims: " + ", ".join(_link(str(x), idx, p.id, False) for x in emit["claims"])
                )
            out += [f"- {x}" for x in facts]
            if facts:
                out.append("")
            if r.get("when") is not None:
                out += [
                    "<details><summary>Condition</summary>",
                    "",
                    "```json",
                    json.dumps(r["when"], indent=1, default=str),
                    "```",
                    "",
                    "</details>",
                    "",
                ]
    if p.claims:
        out += [
            "## Claims",
            "",
            "| Claim | Statement | Evidence | Prevalence | Sources |",
            "|---|---|---|---|---|",
        ]
        for c in p.claims:
            srcs = ", ".join(_link(str(s), idx, p.id, False) for s in c.get("sources") or [])
            out.append(
                f'| <a id="{_anchor(str(c["id"]))}"></a>{c["id"]} | {_cell(c.get("statement") or "")} | '
                f"{c.get('classification') or ''} | {c.get('prevalence') or ''} | {srcs} |"
            )
        out.append("")
    if p.sources:
        out += [
            "## Sources",
            "",
            "| Source | Title | Type | Verified | Retrieved |",
            "|---|---|---|---|---|",
        ]
        for s in p.sources:
            title = _cell(s.get("title") or "")
            if s.get("url"):
                title = f"[{title}]({s['url']})"
            out.append(
                f'| <a id="{_anchor(str(s["id"]))}"></a>{s["id"]} | {title} | '
                f"{s.get('source_type') or ''} | {'yes' if s.get('verified') else 'no'} | "
                f"{s.get('retrieved_date') or ''} |"
            )
        out.append("")
    return "\n".join(out)


def ontology_files() -> dict[str, str]:
    files = {"README.md": readme_md(), "core.md": core_md(), "cometric.ttl": to_turtle()}
    for p in packs():
        files[f"pack-{p.id}.md"] = pack_md(p)
    return files
