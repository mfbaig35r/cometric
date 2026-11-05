"""Turn scenario assumptions into exact monthly quantities (spec 4.7, 6.1)."""

from __future__ import annotations

import re
from decimal import ROUND_DOWN, ROUND_HALF_UP, ROUND_UP, Decimal

from .enums import AssumptionBasis, DerivedRounding, Distribution, Origin, UnitKind
from .issues import Issues, pointer
from .models import Engagement, Scenario
from .money import ZERO, allocate_exact, allocate_weighted
from .periods import Month, months_between, parse_month

GENERIC_UNITS = {"hours": 2, "fte": 4, "flag": 0, "count": 0, "currency": 2, "ratio": 6}


def _scale_for(unit: str, value: Decimal, engagement: Engagement) -> int:
    exponent_scale = (
        max(0, -value.as_tuple().exponent) if isinstance(value.as_tuple().exponent, int) else 0
    )
    for u in engagement.unit_definitions:
        if u.code == unit:
            if u.kind == UnitKind.COUNT:
                return 0
            if u.kind == UnitKind.HOURS:
                return max(2, exponent_scale)
            return max(4, exponent_scale)
    if unit in GENERIC_UNITS:
        return max(GENERIC_UNITS[unit], exponent_scale)
    if unit == engagement.currency:
        return max(2, exponent_scale)
    return max(4, exponent_scale)


def known_units(engagement: Engagement) -> set[str]:
    units = (
        {u.code for u in engagement.unit_definitions} | set(GENERIC_UNITS) | {engagement.currency}
    )
    for wt in engagement.weight_tables:
        units.add(wt.weighted_unit)
    return units


def _months_for(period: str, months: list[Month]) -> list[Month]:
    if period == "TERM":
        return list(months)
    if re.match(r"^\d{4}$", period):
        return [m for m in months if m[0] == int(period)]
    if ".." in period:
        a, b = period.split("..")
        span = set(months_between(parse_month(a), parse_month(b)))
        return [m for m in months if m in span]
    m = parse_month(period)
    return [m] if m in months else []


class Quantities:
    """name -> month -> Decimal, plus provenance."""

    def __init__(self) -> None:
        self.values: dict[str, dict[Month, Decimal]] = {}
        self.units: dict[str, str] = {}
        self.origins: dict[str, set[Origin]] = {}

    def get(self, name: str, m: Month) -> Decimal | None:
        series = self.values.get(name)
        if series is None:
            return None
        return series.get(m, ZERO)

    def has(self, name: str) -> bool:
        return name in self.values

    def total(self, name: str) -> Decimal:
        return sum(self.values.get(name, {}).values(), ZERO)

    def set(self, name: str, m: Month, value: Decimal) -> None:
        self.values.setdefault(name, {})[m] = value


def build_quantities(
    engagement: Engagement, scenario: Scenario, months: list[Month], issues: Issues
) -> Quantities:
    q = Quantities()
    seen: dict[str, set[Month]] = {}
    units = known_units(engagement)
    for i, a in enumerate(scenario.assumptions):
        path = pointer("scenario", "assumptions", i)
        if a.unit not in units:
            issues.error(
                "UNKNOWN_UNIT",
                f"assumption {a.name!r} uses unit {a.unit!r}, which is not defined",
                path + "/unit",
            )
            continue
        targets = _months_for(a.time_period, months)
        if not targets:
            issues.warn(
                "ASSUMPTION_OUTSIDE_HORIZON",
                f"assumption {a.name!r} covers no month in the horizon",
                path + "/time_period",
            )
            continue
        overlap = seen.setdefault(a.name, set()) & set(targets)
        if overlap:
            issues.error(
                "ASSUMPTION_OVERLAP",
                f"assumption {a.name!r} is given twice for the same month",
                path + "/time_period",
            )
            continue
        seen[a.name] |= set(targets)
        if a.value < 0:
            issues.error("NEGATIVE_QUANTITY", f"assumption {a.name!r} is negative", path + "/value")
            continue
        scale = _scale_for(a.unit, a.value, engagement)
        try:
            if a.basis == AssumptionBasis.RATE:
                shares = [a.value] * len(targets)
            elif len(targets) == 1:
                shares = [a.value]
            elif a.distribution == Distribution.PROFILE:
                if len(a.profile) != len(targets):
                    issues.error(
                        "PROFILE_LENGTH",
                        f"profile for {a.name!r} needs {len(targets)} weights",
                        path + "/profile",
                    )
                    continue
                shares = allocate_weighted(a.value, list(a.profile), scale)
            else:
                shares = allocate_exact(a.value, len(targets), scale)
        except ValueError:
            issues.error(
                "NOT_ALLOCATABLE",
                f"{a.value} {a.unit} cannot be spread exactly over {len(targets)} months at {scale} decimal places; "
                + (
                    "COUNT units need a whole-number total: round it, give monthly values, or use a non-COUNT unit kind"
                    if scale == 0
                    else "give monthly values or a total with fewer decimals"
                ),
                path + "/value",
            )
            continue
        for m, s in zip(targets, shares, strict=True):
            q.set(a.name, m, s)
        q.units[a.name] = a.unit
        q.origins.setdefault(a.name, set()).add(a.origin)
    if scenario.derived and not issues.has_errors:
        _derive(engagement, scenario, months, q, issues)
    return q


# --- derived quantities (counting rules and other monthly transforms) ---------------------

EXPR_OPS = ("q", "const", "sum", "difference", "product", "quotient")
EXPR_HELP = 'an expression is {"q": name}, {"const": "1"}, {"sum": [e, ...]}, {"difference": [a, b]}, {"product": [e, ...]}, or {"quotient": [a, b]}'


def expr_refs(expr) -> set[str]:
    if not isinstance(expr, dict) or len(expr) != 1:
        return set()
    ((op, arg),) = expr.items()
    if op == "q":
        return {str(arg).removeprefix("scenario.")}
    if op in ("sum", "difference", "product", "quotient") and isinstance(arg, list):
        return set().union(*(expr_refs(a) for a in arg)) if arg else set()
    return set()


def expr_problems(expr, path: str = "") -> list[tuple[str, str]]:
    if not isinstance(expr, dict) or len(expr) != 1:
        return [(path, f"expected one operator; {EXPR_HELP}")]
    ((op, arg),) = expr.items()
    if op not in EXPR_OPS:
        return [(path, f"unknown operator {op!r}; {EXPR_HELP}")]
    if op == "q":
        return [] if isinstance(arg, str) and arg else [(path + "/q", "q needs a quantity name")]
    if op == "const":
        try:
            from .money import to_decimal

            to_decimal(arg)
            return []
        except ValueError:
            return [(path + "/const", 'const needs a decimal string such as "1" or "0.05"')]
    if not isinstance(arg, list) or not arg:
        return [(path + f"/{op}", f"{op} needs a list of expressions")]
    if op in ("difference", "quotient") and len(arg) != 2:
        return [(path + f"/{op}", f"{op} takes exactly two expressions")]
    out = []
    for i, a in enumerate(arg):
        out += expr_problems(a, f"{path}/{op}/{i}")
    return out


def expr_value(expr, m, q: Quantities) -> Decimal:
    ((op, arg),) = expr.items()
    if op == "q":
        return q.get(str(arg).removeprefix("scenario."), m) or ZERO
    if op == "const":
        from .money import to_decimal

        return to_decimal(arg)
    vals = [expr_value(a, m, q) for a in arg]
    if op == "sum":
        return sum(vals, ZERO)
    if op == "difference":
        return vals[0] - vals[1]
    if op == "product":
        out = Decimal(1)
        for v in vals:
            out *= v
        return out
    if vals[1] == 0:
        raise ZeroDivisionError
    return vals[0] / vals[1]


def expr_text(expr) -> str:
    ((op, arg),) = expr.items()
    if op == "q":
        return str(arg).removeprefix("scenario.")
    if op == "const":
        return str(arg)
    sym = {"sum": " + ", "difference": " - ", "product": " x ", "quotient": " / "}[op]
    return "(" + sym.join(expr_text(a) for a in arg) + ")"


_ROUND = {
    DerivedRounding.HALF_UP: ROUND_HALF_UP,
    DerivedRounding.DOWN: ROUND_DOWN,
    DerivedRounding.UP: ROUND_UP,
}


def _derive(
    engagement: Engagement, scenario: Scenario, months: list[Month], q: Quantities, issues: Issues
) -> None:
    units = known_units(engagement)
    count_units = {u.code for u in engagement.unit_definitions if u.kind == UnitKind.COUNT}
    defs = {}
    for i, d in enumerate(scenario.derived):
        path = pointer("scenario", "derived", i)
        if d.name in defs or q.has(d.name):
            issues.error(
                "DUPLICATE_ID",
                f"{d.name!r} is already an assumption or derived quantity",
                path + "/name",
            )
            continue
        if d.unit not in units:
            issues.error(
                "UNKNOWN_UNIT",
                f"derived quantity {d.name!r} uses unit {d.unit!r}, which is not defined",
                path + "/unit",
            )
        if d.unit in count_units and d.rounding is None:
            issues.error(
                "ROUNDING_REQUIRED",
                f"{d.name!r} is a COUNT unit: declare rounding (NONE keeps fractional expected values; HALF_UP, DOWN, or UP round each month)",
                path + "/rounding",
            )
        for sub, msg in expr_problems(d.expression, path + "/expression"):
            issues.error("BAD_EXPRESSION", msg, sub)
        defs[d.name] = (i, d)
    for _name, (i, d) in defs.items():
        for ref in expr_refs(d.expression):
            if not q.has(ref) and ref not in defs:
                issues.error(
                    "UNKNOWN_QUANTITY",
                    f"{d.name!r} refers to {ref!r}, which is neither an assumption nor a derived quantity",
                    pointer("scenario", "derived", i, "expression"),
                )
    if issues.has_errors:
        return
    order: list[str] = []
    state: dict[str, int] = {}

    def visit(n: str, stack: list[str]) -> None:
        if state.get(n) == 2:
            return
        if state.get(n) == 1:
            issues.error(
                "DEPENDENCY_CYCLE",
                f"derived quantities form a cycle: {' -> '.join(stack + [n])}",
                pointer("scenario", "derived", defs[n][0], "expression"),
            )
            return
        state[n] = 1
        for ref in expr_refs(defs[n][1].expression):
            if ref in defs:
                visit(ref, stack + [n])
        state[n] = 2
        order.append(n)

    for n in defs:
        visit(n, [])
    if issues.has_errors:
        return
    for n in order:
        i, d = defs[n]
        path = pointer("scenario", "derived", i)
        for m in months:
            try:
                v = expr_value(d.expression, m, q)
            except ZeroDivisionError:
                issues.error(
                    "DIVISION_BY_ZERO",
                    f"{d.name!r} divides by zero in {m[0]:04d}-{m[1]:02d}",
                    path + "/expression",
                )
                return
            if d.rounding in _ROUND:
                v = v.quantize(Decimal(1), rounding=_ROUND[d.rounding])
            if v < 0:
                issues.error(
                    "NEGATIVE_QUANTITY",
                    f"{d.name!r} is negative in {m[0]:04d}-{m[1]:02d} ({v})",
                    path + "/expression",
                )
                return
            q.set(d.name, m, v)
        q.units[d.name] = d.unit
