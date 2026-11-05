"""Schema and semantic validation with JSON Pointer issues (spec 4, 7.3, T-004, T-013, T-018, T-020)."""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import ValidationError

from .enums import (
    METHOD_BASES,
    POST_V1_METHODS,
    AccumulationPeriod,
    AdjustmentType,
    AggregationScope,
    CalculationMethod,
    ChargeCadence,
    ClassificationAuthority,
    CommitmentKind,
    CostBehavior,
    OutcomeForm,
    Recognition,
    ShortfallRule,
    TierMethod,
    TierScope,
)
from .issues import Issues, pointer
from .models import CostPolicy, Engagement, Scenario
from .periods import last_day
from .tiers import all_units_cliffs, check_contiguous

REQUIRED_MARKER = "<required>"


def _find_required(obj: Any, path: str, out: list[str]) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            _find_required(v, f"{path}/{str(k).replace('~', '~0').replace('/', '~1')}", out)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            _find_required(v, f"{path}/{i}", out)
    elif obj == REQUIRED_MARKER:
        out.append(path)


def pydantic_issues(
    exc: ValidationError, root: str, issues: Issues, skip: set[str] | None = None
) -> None:
    for err in exc.errors():
        path = root + "".join(f"/{p}" for p in err["loc"])
        if skip and any(path == s or path.startswith(s + "/") for s in skip):
            continue
        model = root.strip("/").split("/")[0] or "engagement"
        issues.error(
            "SCHEMA",
            err["msg"],
            path,
            hint=f"describe_schema('{model}') shows the expected shape; quickstart('calculate_periods') shows a valid {model}",
        )


def parse_engagement(raw: Any, issues: Issues, root: str = "/engagement") -> Engagement | None:
    if isinstance(raw, Engagement):
        return raw
    required: list[str] = []
    _find_required(raw, root, required)
    for p in required:
        issues.error("REQUIRED_FIELD", "this field must be filled in", p)
    try:
        return Engagement.model_validate(raw)
    except ValidationError as exc:
        pydantic_issues(exc, root, issues, set(required))
        return None


def parse_scenario(raw: Any, issues: Issues, root: str = "/scenario") -> Scenario | None:
    if isinstance(raw, Scenario):
        return raw
    try:
        return Scenario.model_validate(raw)
    except ValidationError as exc:
        pydantic_issues(exc, root, issues)
        return None


def parse_cost_policy(raw: Any, issues: Issues, root: str = "/cost_policy") -> CostPolicy | None:
    from .models import BUILTIN_COST_POLICIES, CostCategory

    if raw is None:
        return None
    if isinstance(raw, CostPolicy):
        policy = raw
    elif isinstance(raw, str):
        if raw not in BUILTIN_COST_POLICIES:
            issues.error(
                "UNKNOWN_COST_POLICY",
                f"no built-in cost policy named {raw!r}; built-ins: {sorted(BUILTIN_COST_POLICIES)}",
                root,
            )
            return None
        policy = BUILTIN_COST_POLICIES[raw]
    else:
        try:
            policy = CostPolicy.model_validate(raw)
        except ValidationError as exc:
            pydantic_issues(exc, root, issues)
            return None
    missing = [c for c in CostCategory if c not in policy.mapping]
    if missing:
        issues.error(
            "COST_POLICY_INCOMPLETE",
            f"cost policy does not map: {', '.join(missing)}",
            root + "/mapping",
        )
    return policy


def validate_cost_policy_mapping(raw: dict, issues: Issues, root: str = "/cost_policy") -> None:
    """T-021: a category listed twice (raw JSON duplicates) or unmapped fails."""
    if isinstance(raw, dict) and isinstance(raw.get("mapping"), list):
        seen = set()
        for i, item in enumerate(raw["mapping"]):
            cat = item.get("category")
            if cat in seen:
                issues.error(
                    "COST_POLICY_DUPLICATE",
                    f"category {cat} is mapped twice",
                    f"{root}/mapping/{i}",
                )
            seen.add(cat)


def validate_engagement_model(e: Engagement, issues: Issues, root: str = "/engagement") -> None:
    p = lambda *parts: root + pointer(*parts)  # noqa: E731
    if e.start_date > e.end_date:
        issues.error("DATE_ORDER", "start_date is after end_date", p("start_date"))
    _unique([u.code for u in e.unit_definitions], "unit_definitions", issues, p)
    _unique([s.id for s in e.services], "services", issues, p)
    _unique([v.id for v in e.arrangement_versions], "arrangement_versions", issues, p)
    units = {u.code: u for u in e.unit_definitions}
    services = {s.id for s in e.services}
    tables = {t.id: t for t in e.weight_tables}
    for si, s in enumerate(e.services):
        if s.unit_definition_id not in units:
            issues.error(
                "UNKNOWN_UNIT",
                f"service {s.id} references unit {s.unit_definition_id!r}",
                p("services", si, "unit_definition_id"),
            )
    if not e.packs:
        for si, s in enumerate(e.services):
            if s.service_category:
                issues.error(
                    "UNDECLARED_VOCABULARY",
                    "service_category comes from a domain pack; declare the pack in `packs`",
                    p("services", si, "service_category"),
                )
        for pi, party in enumerate(e.parties):
            if party.provider_type:
                issues.error(
                    "UNDECLARED_VOCABULARY",
                    "provider_type comes from a domain pack; declare the pack in `packs`",
                    p("parties", pi, "provider_type"),
                )
    for ti, t in enumerate(e.weight_tables):
        if t.raw_unit not in units:
            issues.error(
                "UNKNOWN_UNIT",
                f"weight table raw_unit {t.raw_unit!r} is not defined",
                p("weight_tables", ti, "raw_unit"),
            )
        if t.classification_authority == ClassificationAuthority.PROVIDER:
            issues.warn(
                "PROVIDER_CLASSIFIES_COMPLEXITY",
                "the provider alone assigns complexity bands; consider joint criteria and audit rights",
                p("weight_tables", ti, "classification_authority"),
            )

    spans = []
    for vi, v in enumerate(e.arrangement_versions):
        vp = lambda *parts, _vi=vi: p("arrangement_versions", _vi, *parts)  # noqa: E731
        start = max(v.effective_from, e.start_date)
        end = min(v.effective_to or e.end_date, e.end_date)
        if start > end:
            issues.error(
                "EMPTY_VERSION", "version has no days inside the engagement", vp("effective_from")
            )
            continue
        spans.append((start, end, v.id, vi))
        start_mid = start.day != 1
        end_mid = end != last_day((end.year, end.month))
        neighbours = e.arrangement_versions
        prev_has = any(
            x.proration_policy
            for x in neighbours
            if x is not v
            and (x.effective_to or e.end_date) == date.fromordinal(start.toordinal() - 1)
        )
        next_has = any(
            x.proration_policy
            for x in neighbours
            if x is not v and x.effective_from == date.fromordinal(end.toordinal() + 1)
        )
        if v.proration_policy is None and (
            (start_mid and not prev_has) or (end_mid and not next_has)
        ):
            issues.error(
                "PRORATION_POLICY_REQUIRED",
                "a contract boundary falls mid-month; declare proration_policy on the version that starts there",
                vp("proration_policy"),
            )
        if v.supersedes_id and v.supersedes_id not in {x.id for x in e.arrangement_versions}:
            issues.error(
                "UNKNOWN_VERSION",
                f"supersedes_id {v.supersedes_id!r} does not exist",
                vp("supersedes_id"),
            )
        _validate_version(e, v, vp, units, services, tables, issues)
    spans.sort()
    for (_s1, e1, id1, _), (s2, _e2, id2, i2) in zip(spans, spans[1:], strict=False):
        if s2 <= e1:
            issues.error(
                "VERSION_OVERLAP",
                f"versions {id1} and {id2} overlap; component-level coexistence is post-v1",
                p("arrangement_versions", i2, "effective_from"),
            )

    plan = e.delivery_plan
    if plan is not None:
        cost_ids = [c.id for c in plan.cost_components]
        _unique(cost_ids, "delivery_plan/cost_components", issues, p)
        for ci, c in enumerate(plan.cost_components):
            cp = lambda *parts, _ci=ci: p("delivery_plan", "cost_components", _ci, *parts)  # noqa: E731
            b = c.behavior
            if b == CostBehavior.FIXED and (c.amount is None or c.period is None):
                issues.error("COST_FIELDS", "FIXED cost needs amount and period", cp("amount"))
            if b == CostBehavior.VARIABLE and (c.driver is None or c.rate is None):
                issues.error("COST_FIELDS", "VARIABLE cost needs driver and rate", cp("driver"))
            if b == CostBehavior.STEP and (
                c.driver is None or not c.step_size or c.step_cost is None
            ):
                issues.error(
                    "COST_FIELDS",
                    "STEP cost needs driver, step_size, and step_cost",
                    cp("step_size"),
                )
            if b == CostBehavior.TIERED_VARIABLE:
                if c.driver is None:
                    issues.error("COST_FIELDS", "TIERED_VARIABLE cost needs a driver", cp("driver"))
                for prob in check_contiguous(c.tiers):
                    issues.error("TIER_INVALID", prob, cp("tiers"))
            if b == CostBehavior.ONE_TIME and c.amount is None and not c.incurred_schedule:
                issues.error(
                    "COST_FIELDS", "ONE_TIME cost needs amount or incurred_schedule", cp("amount")
                )
        for li, lim in enumerate(plan.capacity):
            for rid in lim.overflow_replaces:
                if rid not in cost_ids:
                    issues.error(
                        "UNKNOWN_COST_COMPONENT",
                        f"overflow_replaces references {rid!r}",
                        p("delivery_plan", "capacity", li, "overflow_replaces"),
                    )
        for ri, role in enumerate(plan.roles):
            if role.safe_utilization_ceiling is not None and not (
                0 < role.safe_utilization_ceiling <= 1
            ):
                issues.error(
                    "RANGE",
                    "safe_utilization_ceiling must be in (0, 1]",
                    p("delivery_plan", "roles", ri, "safe_utilization_ceiling"),
                )


def _unique(ids: list[str], where: str, issues: Issues, p) -> None:
    seen = set()
    for i, x in enumerate(ids):
        if x in seen:
            issues.error(
                "DUPLICATE_ID", f"id {x!r} appears twice in {where}", p(*where.split("/"), i)
            )
        seen.add(x)


def _validate_version(e: Engagement, v, vp, units, services, tables, issues: Issues) -> None:
    comp_ids = [c.id for c in v.components]
    ent_ids = [x.id for x in v.entitlements]
    _unique(
        comp_ids + ent_ids,
        f"version {v.id} components and entitlements",
        issues,
        lambda *_: vp("components"),
    )
    schedules = {r.id: r for r in v.rate_schedules}
    ents = {x.id: x for x in v.entitlements}
    comps = {c.id: c for c in v.components}
    weighted_units = {t.weighted_unit for t in tables.values()}

    for ri, r in enumerate(v.rate_schedules):
        if r.currency != e.currency:
            issues.error(
                "CURRENCY_MISMATCH",
                f"rate schedule currency {r.currency} differs from engagement currency {e.currency}",
                vp("rate_schedules", ri, "currency"),
            )
        for prob in check_contiguous(r.tiers):
            issues.error("TIER_INVALID", prob, vp("rate_schedules", ri, "tiers"))
        if r.tier_method == TierMethod.GRADUATED_BLOCK:
            issues.error(
                "METHOD_NOT_SUPPORTED",
                "GRADUATED_BLOCK tiers are post-v1",
                vp("rate_schedules", ri, "tier_method"),
            )
        if r.tier_method == TierMethod.ALL_UNITS:
            by_threshold: dict = {}
            for cliff in all_units_cliffs(r.tiers):
                by_threshold.setdefault(cliff["threshold"], []).append(cliff)
            for threshold, cliffs in by_threshold.items():
                bands = [
                    {
                        "lower": str(c["band_lower"]),
                        "lower_inclusive": c["band_lower_inclusive"],
                        "upper_exclusive": str(c["band_upper_exclusive"]),
                    }
                    for c in sorted(cliffs, key=lambda c: c["band_lower"])
                ]
                text = "; ".join(
                    f"{'from' if b['lower_inclusive'] else 'above'} {b['lower']} to below {b['upper_exclusive']}"
                    for b in bands
                )
                issues.warn(
                    "TIER_CLIFF",
                    f"under ALL_UNITS, these quantities cost more than {threshold} units: {text}",
                    vp("rate_schedules", ri, "tiers"),
                    threshold=str(threshold),
                    bands=bands,
                )

    for ci, c in enumerate(v.components):
        cp = lambda *parts, _ci=ci: vp("components", _ci, *parts)  # noqa: E731
        m = c.calculation_method
        if c.service_id not in services:
            issues.error(
                "UNKNOWN_SERVICE", f"service {c.service_id!r} is not defined", cp("service_id")
            )
        if c.currency != e.currency:
            issues.error(
                "CURRENCY_MISMATCH",
                f"component currency {c.currency} differs from engagement currency {e.currency}",
                cp("currency"),
            )
        if m in POST_V1_METHODS:
            issues.error(
                "METHOD_NOT_SUPPORTED", f"{m} is a post-v1 method", cp("calculation_method")
            )
            continue
        if c.billing_basis not in METHOD_BASES[m]:
            issues.error(
                "METHOD_BASIS_MISMATCH",
                f"{m} allows bases {sorted(METHOD_BASES[m])}, got {c.billing_basis}",
                cp("billing_basis"),
            )
        for dep in c.depends_on:
            if dep not in comps and dep not in ents:
                issues.error(
                    "DANGLING_DEPENDENCY",
                    f"depends_on references {dep!r}, which is not a component or entitlement in this version",
                    cp("depends_on"),
                )
        if m == CalculationMethod.FIXED_RECURRING:
            if c.fixed_amount is None:
                issues.error(
                    "METHOD_FIELDS", "FIXED_RECURRING needs fixed_amount", cp("fixed_amount")
                )
            if c.charge_cadence not in (
                ChargeCadence.MONTHLY,
                ChargeCadence.QUARTERLY,
                ChargeCadence.ANNUAL,
                ChargeCadence.ONE_TIME,
            ):
                issues.error(
                    "METHOD_FIELDS",
                    "FIXED_RECURRING cadence must be MONTHLY, QUARTERLY, ANNUAL, or ONE_TIME",
                    cp("charge_cadence"),
                )
        elif m == CalculationMethod.TIME:
            if not c.quantity_source or not c.role_rates:
                issues.error(
                    "METHOD_FIELDS", "TIME needs quantity_source and role_rates", cp("role_rates")
                )
        elif m == CalculationMethod.DEDICATED_RESOURCE:
            if not c.resources:
                issues.error("METHOD_FIELDS", "DEDICATED_RESOURCE needs resources", cp("resources"))
        elif m == CalculationMethod.OUTCOME_ADJUSTMENT:
            _validate_outcome(c, cp, issues)
        elif m == CalculationMethod.FIXED_PROJECT:
            if c.project_fee is None or not c.payment_schedule:
                issues.error(
                    "METHOD_FIELDS",
                    "FIXED_PROJECT needs project_fee and payment_schedule",
                    cp("payment_schedule"),
                )
            elif sum(x.amount for x in c.payment_schedule) != c.project_fee:
                issues.error(
                    "PAYMENT_SCHEDULE_MISMATCH",
                    "payment_schedule does not sum to project_fee",
                    cp("payment_schedule"),
                )
        elif m in (
            CalculationMethod.UNIT_OUTPUT,
            CalculationMethod.WEIGHTED_UNIT_OUTPUT,
            CalculationMethod.ALLOWANCE_OVERAGE,
        ):
            if not c.quantity_source:
                issues.error("METHOD_FIELDS", f"{m} needs quantity_source", cp("quantity_source"))
            if not c.unit:
                issues.error("METHOD_FIELDS", f"{m} needs unit", cp("unit"))
            sched = schedules.get(c.rate_schedule_id or "")
            if sched is None:
                issues.error(
                    "UNKNOWN_RATE_SCHEDULE",
                    f"rate_schedule_id {c.rate_schedule_id!r} is not defined in this version",
                    cp("rate_schedule_id"),
                )
            elif c.unit and sched.unit != c.unit:
                issues.error(
                    "UNIT_MISMATCH",
                    f"component prices {c.unit!r} but schedule {sched.id} is in {sched.unit!r}",
                    cp("unit"),
                )
            if c.unit and c.unit not in units and c.unit not in weighted_units:
                issues.error("UNKNOWN_UNIT", f"unit {c.unit!r} is not defined", cp("unit"))
            unit_def = units.get(c.unit or "")
            if unit_def is not None and not unit_def.counting_rule:
                issues.approval(
                    "MISSING_COUNTING_RULE",
                    f"unit {unit_def.code!r} has no counting rule; output pricing needs approval",
                    cp("unit"),
                )
            if m == CalculationMethod.WEIGHTED_UNIT_OUTPUT:
                table = (
                    tables.get(c.weight_table_id or "")
                    if c.weight_table_id
                    else (next(iter(tables.values())) if len(tables) == 1 else None)
                )
                if table is None:
                    issues.error(
                        "UNKNOWN_WEIGHT_TABLE",
                        "WEIGHTED_UNIT_OUTPUT needs a weight_table_id",
                        cp("weight_table_id"),
                    )
                elif c.unit != table.weighted_unit:
                    issues.error(
                        "UNIT_MISMATCH",
                        f"weighted component must price {table.weighted_unit!r}",
                        cp("unit"),
                    )
            if m == CalculationMethod.ALLOWANCE_OVERAGE:
                ent = ents.get(c.entitlement_id or "")
                if ent is None:
                    issues.error(
                        "UNKNOWN_ENTITLEMENT",
                        f"entitlement_id {c.entitlement_id!r} is not defined",
                        cp("entitlement_id"),
                    )
                else:
                    if ent.id not in c.depends_on:
                        issues.error(
                            "DEPENDENCY_MISSING",
                            f"ALLOWANCE_OVERAGE must list its entitlement {ent.id!r} in depends_on",
                            cp("depends_on"),
                        )
                    if c.unit and ent.unit != c.unit:
                        issues.error(
                            "UNIT_MISMATCH",
                            f"entitlement {ent.id} counts {ent.unit!r} but component prices {c.unit!r}",
                            cp("unit"),
                        )
                    if (
                        sched is not None
                        and sched.tier_scope == TierScope.ALL_ELIGIBLE
                        and (
                            sched.tier_method == TierMethod.ALL_UNITS
                            or ent.overage_recognition == Recognition.PERIOD_END
                        )
                        and len(sched.tiers) > 1
                    ):
                        issues.error(
                            "UNSUPPORTED_COMBINATION",
                            "tiered overage with ALL_ELIGIBLE scope needs MARGINAL tiers and non-PERIOD_END recognition in v1",
                            cp("rate_schedule_id"),
                        )

    # dependency cycles (components -> depends_on, entitlements -> granted_by)
    graph: dict[str, list[str]] = {c.id: list(c.depends_on) for c in v.components}
    for x in v.entitlements:
        graph[x.id] = [x.granted_by]
    _cycles(graph, issues, vp("components"))

    for ei, x in enumerate(v.entitlements):
        if x.granted_by not in comps:
            issues.error(
                "UNKNOWN_COMPONENT",
                f"granted_by {x.granted_by!r} is not a component",
                vp("entitlements", ei, "granted_by"),
            )
        if (
            x.overage_recognition == Recognition.PER_SEGMENT
            and x.accumulation_period != AccumulationPeriod.MONTH
        ):
            issues.error(
                "RECOGNITION_PERIOD",
                "PER_SEGMENT recognition requires accumulation_period MONTH",
                vp("entitlements", ei, "overage_recognition"),
            )

    caps = []
    for ai, a in enumerate(v.adjustments):
        ap = lambda *parts, _ai=ai: vp("adjustments", _ai, *parts)  # noqa: E731
        for ref in a.applies_to:
            if ref not in comps:
                issues.error(
                    "UNKNOWN_COMPONENT", f"applies_to references {ref!r}", ap("applies_to")
                )
        t = a.type
        if a.threshold is not None and t not in (AdjustmentType.DISCOUNT, AdjustmentType.REBATE):
            issues.error(
                "FIELD_NOT_USED",
                f"threshold applies only to DISCOUNT and REBATE, not {t}",
                ap("threshold"),
            )
        if a.threshold is not None and a.threshold_scope is None:
            issues.error(
                "THRESHOLD_SCOPE_REQUIRED",
                'a threshold needs threshold_scope: "EXCESS_ONLY" (percentage applies to the amount above the threshold) or "ENTIRE_SUBTOTAL" (once reached, it applies to the whole period subtotal)',
                ap("threshold_scope"),
                example={
                    "type": "DISCOUNT",
                    "percent": "0.10",
                    "threshold": "2500000",
                    "threshold_scope": "EXCESS_ONLY",
                    "accumulation_period": "CONTRACT_YEAR",
                },
            )
        if a.threshold_scope is not None and a.threshold is None:
            issues.error(
                "FIELD_NOT_USED", "threshold_scope needs a threshold", ap("threshold_scope")
            )
        needs_period = t in (AdjustmentType.CAP, AdjustmentType.REBATE) or (
            t == AdjustmentType.DISCOUNT and a.threshold is not None
        )
        if needs_period and a.accumulation_period is None:
            issues.error(
                "ACCUMULATION_PERIOD_REQUIRED",
                f"{t} needs accumulation_period (MONTH, QUARTER, YEAR, CONTRACT_YEAR, or TERM); there is no default",
                ap("accumulation_period"),
            )
        if (
            t
            in (
                AdjustmentType.DISCOUNT,
                AdjustmentType.REBATE,
                AdjustmentType.INDEXATION,
                AdjustmentType.HOLDBACK,
            )
            and a.percent is None
        ):
            issues.error("ADJUSTMENT_FIELDS", f"{t} needs percent", ap("percent"))
        if t in (AdjustmentType.SLA_CREDIT, AdjustmentType.BONUS) and (
            a.percent is None or a.trigger is None
        ):
            issues.error("ADJUSTMENT_FIELDS", f"{t} needs percent and trigger", ap("trigger"))
        if t in (AdjustmentType.SLA_CREDIT, AdjustmentType.BONUS) and a.cap_percent is None:
            issues.approval(
                "UNCAPPED_PERFORMANCE_ADJUSTMENT",
                f"{t} {a.id} has no cap_percent",
                ap("cap_percent"),
            )
        if t == AdjustmentType.CAP:
            if a.amount is None:
                issues.error("ADJUSTMENT_FIELDS", "CAP needs amount", ap("amount"))
            else:
                caps.append(a)
        if t == AdjustmentType.COLLAR:
            if a.component_id not in comps:
                issues.error("UNKNOWN_COMPONENT", "COLLAR needs component_id", ap("component_id"))
            if a.outside_rate_schedule_id not in schedules:
                issues.error(
                    "UNKNOWN_RATE_SCHEDULE",
                    "COLLAR needs outside_rate_schedule_id",
                    ap("outside_rate_schedule_id"),
                )
            if a.lower is None and a.upper is None:
                issues.error("ADJUSTMENT_FIELDS", "COLLAR needs lower or upper", ap("lower"))

    for mi, com in enumerate(v.commitments):
        mp = lambda *parts, _mi=mi: vp("commitments", _mi, *parts)  # noqa: E731
        if com.kind != CommitmentKind.MINIMUM_SPEND:
            issues.warn(
                "COMMITMENT_NOT_COMPUTED",
                f"{com.kind} commitments are recorded but not computed in v1",
                mp("kind"),
            )
        if (
            com.shortfall_rule == ShortfallRule.PER_SEGMENT
            and com.accumulation_period != AccumulationPeriod.MONTH
        ):
            issues.error(
                "RECOGNITION_PERIOD",
                "PER_SEGMENT shortfall requires accumulation_period MONTH",
                mp("shortfall_rule"),
            )
        if com.aggregation_scope == AggregationScope.COMPONENT:
            if not com.component_ids:
                issues.error(
                    "COMMITMENT_SCOPE", "COMPONENT scope needs component_ids", mp("component_ids")
                )
            for ref in com.component_ids:
                if ref not in comps:
                    issues.error(
                        "UNKNOWN_COMPONENT",
                        f"component_ids references {ref!r}",
                        mp("component_ids"),
                    )
        if com.aggregation_scope == AggregationScope.SERVICE and com.service_id not in services:
            issues.error(
                "COMMITMENT_SCOPE", "SERVICE scope needs a valid service_id", mp("service_id")
            )
        for cap in caps:
            same_scope = (
                not cap.applies_to and com.aggregation_scope == AggregationScope.ENGAGEMENT
            ) or (
                com.aggregation_scope == AggregationScope.COMPONENT
                and set(cap.applies_to) == set(com.component_ids)
            )
            if (
                same_scope
                and cap.accumulation_period == com.accumulation_period
                and com.amount > cap.amount
            ):
                issues.error(
                    "REQUIRES_CONTRACT_INTERPRETATION",
                    f"minimum {com.amount} exceeds cap {cap.amount} at the same scope and period; the contract must say which governs",
                    mp("amount"),
                )

    methods = {c.calculation_method for c in v.components}
    if (
        methods <= {CalculationMethod.FIXED_RECURRING}
        and not caps
        and not any(a.type == AdjustmentType.COLLAR for a in v.adjustments)
        and (e.delivery_plan is None or not e.delivery_plan.capacity)
    ):
        issues.approval(
            "UNBOUNDED_FIXED_FEE_VOLUME",
            "fixed recurring fee with no allowance, overage, cap, collar, or capacity limit: provider volume exposure is unbounded",
            vp("components"),
        )


def _validate_outcome(c, cp, issues: Issues) -> None:
    """Outcome fees need a measurable metric, baseline or target, attribution, cap, and approval."""
    o = c.outcome
    if o is None:
        issues.error("METHOD_FIELDS", "OUTCOME_ADJUSTMENT needs an outcome block", cp("outcome"))
        return
    for name in ("share_percent", "attribution_percent"):
        v = getattr(o, name)
        if v is not None and not (0 < v <= 1):
            issues.error("RANGE", f"{name} must be in (0, 1]", cp("outcome", name))
    if o.form == OutcomeForm.SHARE:
        if o.baseline is None:
            issues.error(
                "BASELINE_REQUIRED",
                "a shared-savings or gain-share fee needs an agreed baseline",
                cp("outcome", "baseline"),
            )
        if o.share_percent is None:
            issues.error(
                "METHOD_FIELDS", "SHARE needs share_percent", cp("outcome", "share_percent")
            )
    if o.form == OutcomeForm.SUCCESS and (o.target is None or o.success_amount is None):
        issues.error(
            "METHOD_FIELDS", "SUCCESS needs target and success_amount", cp("outcome", "target")
        )
    if o.form == OutcomeForm.PERCENT_OF_OUTCOME and o.share_percent is None:
        issues.error(
            "METHOD_FIELDS",
            "PERCENT_OF_OUTCOME needs share_percent",
            cp("outcome", "share_percent"),
        )
    if (
        o.form in (OutcomeForm.SHARE, OutcomeForm.PERCENT_OF_OUTCOME)
        and o.attribution_percent is None
    ):
        issues.error(
            "ATTRIBUTION_REQUIRED",
            "declare the share of the result attributed to the provider",
            cp("outcome", "attribution_percent"),
        )
    if o.attribution_percent is not None and not o.attribution_method:
        issues.warn(
            "ATTRIBUTION_METHOD",
            "describe how attribution is measured",
            cp("outcome", "attribution_method"),
        )
    if o.recognition != Recognition.PERIOD_END:
        issues.error(
            "RECOGNITION_PERIOD",
            "outcome fees are measured and charged at period end in v1",
            cp("outcome", "recognition"),
        )
    if o.cap_amount is None and o.form != OutcomeForm.SUCCESS:
        issues.approval(
            "UNCAPPED_OUTCOME_FEE", "outcome fee has no cap_amount", cp("outcome", "cap_amount")
        )
    if not o.approval_reference:
        issues.approval(
            "OUTCOME_FEE_APPROVAL",
            "outcome-based consideration needs recorded human approval and, for legal or regulated work, legal review",
            cp("outcome", "approval_reference"),
        )


def _cycles(graph: dict[str, list[str]], issues: Issues, path: str) -> None:
    WHITE, GREY, BLACK = 0, 1, 2
    color = dict.fromkeys(graph, WHITE)

    def visit(n: str, stack: list[str]) -> None:
        color[n] = GREY
        for d in graph.get(n, []):
            if d not in graph:
                continue
            if color[d] == GREY:
                issues.error(
                    "DEPENDENCY_CYCLE", f"dependency cycle: {' -> '.join(stack + [n, d])}", path
                )
            elif color[d] == WHITE:
                visit(d, stack + [n])
        color[n] = BLACK

    for n in list(graph):
        if color[n] == WHITE:
            visit(n, [])


def validate_scenario_model(
    e: Engagement, s: Scenario, issues: Issues, root: str = "/scenario"
) -> None:
    t = s.termination_date
    if t is not None:
        if not (e.start_date <= t < e.end_date):
            issues.error(
                "TERMINATION_DATE_RANGE",
                f"termination_date must be on or after {e.start_date} and before the end date {e.end_date}",
                root + "/termination_date",
            )
        elif t != last_day((t.year, t.month)):
            active = [
                v
                for v in e.arrangement_versions
                if v.effective_from <= t <= (v.effective_to or e.end_date)
            ]
            if active and active[0].proration_policy is None:
                issues.error(
                    "PRORATION_POLICY_REQUIRED",
                    "termination falls mid-month; declare proration_policy on the version in force, or terminate on a month end",
                    root + "/termination_date",
                )
    if s.horizon is not None:
        if s.horizon.from_ > s.horizon.to:
            issues.error("DATE_ORDER", "horizon from is after to", root + "/horizon")
        if s.horizon.to < e.start_date or s.horizon.from_ > e.end_date:
            issues.error(
                "HORIZON_OUTSIDE_TERM",
                "horizon does not overlap the engagement term",
                root + "/horizon",
            )


def status_for(issues: Issues) -> str:
    if any(i.code == "REQUIRES_CONTRACT_INTERPRETATION" for i in issues):
        return "requires_contract_interpretation"
    return "invalid" if issues.has_errors else "ok"


def validate_engagement(raw: Any) -> dict:
    """Public operation: validate_engagement(input) -> validation_report."""
    issues = Issues()
    e = parse_engagement(raw, issues)
    if e is not None:
        validate_engagement_model(e, issues)
        if e.packs:
            from .packs import check_engagement_vocabulary

            check_engagement_vocabulary(e, issues)
    return report(issues)


def report(issues: Issues) -> dict:
    return {
        "valid": not issues.has_errors,
        "status": status_for(issues),
        "errors": [i.as_dict() for i in issues if i.severity == "ERROR"],
        "approvals_required": [i.as_dict() for i in issues if i.severity == "APPROVAL_REQUIRED"],
        "warnings": [i.as_dict() for i in issues if i.severity == "WARNING"],
        "info": [i.as_dict() for i in issues if i.severity == "INFO"],
    }


_ = date  # re-exported type hint helper
