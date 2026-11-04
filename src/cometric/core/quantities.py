"""Turn scenario assumptions into exact monthly quantities (spec 4.7, 6.1)."""

from __future__ import annotations

import re
from decimal import Decimal

from .enums import Distribution, Origin, UnitKind
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
            if len(targets) == 1:
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
        except ValueError as exc:
            issues.error("NOT_ALLOCATABLE", str(exc), path + "/value")
            continue
        for m, s in zip(targets, shares, strict=True):
            q.set(a.name, m, s)
        q.units[a.name] = a.unit
        q.origins.setdefault(a.name, set()).add(a.origin)
    return q
