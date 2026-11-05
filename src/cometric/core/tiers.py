"""Tiered rate evaluation and ALL_UNITS cliff detection (spec 4.2)."""

from __future__ import annotations

from decimal import Decimal
from typing import Protocol

from .enums import TierMethod
from .money import ZERO


class TierLike(Protocol):
    from_: Decimal
    to: Decimal | None
    rate: Decimal


def check_contiguous(tiers: list[TierLike]) -> list[str]:
    """Return problems with a tier list: must start at 0, be contiguous, end open-ended."""
    problems = []
    if not tiers:
        return ["schedule has no tiers"]
    if tiers[0].from_ != 0:
        problems.append("first tier must start at 0")
    for i, t in enumerate(tiers):
        if t.to is not None and t.to <= t.from_:
            problems.append(f"tier {i} has to <= from")
        if t.rate < 0:
            problems.append(f"tier {i} has a negative rate")
        if i + 1 < len(tiers):
            if t.to is None:
                problems.append(f"tier {i} is open-ended but is not the last tier")
            elif tiers[i + 1].from_ != t.to:
                problems.append(f"tier {i + 1} does not start where tier {i} ends")
    if tiers[-1].to is not None:
        problems.append("last tier must be open-ended (to = null)")
    return problems


def price(quantity: Decimal, tiers: list[TierLike], method: TierMethod) -> Decimal:
    """Total price for `quantity` units under the schedule."""
    if quantity <= 0:
        return ZERO
    if method == TierMethod.ALL_UNITS:
        for t in tiers:
            if quantity >= t.from_ and (t.to is None or quantity < t.to):
                return quantity * t.rate
        return quantity * tiers[-1].rate
    total = ZERO
    for t in tiers:
        upper = quantity if t.to is None else min(quantity, t.to)
        if upper > t.from_:
            total += (upper - t.from_) * t.rate
    return total


def incremental(
    before: Decimal, quantity: Decimal, tiers: list[TierLike], method: TierMethod
) -> Decimal:
    """Price of `quantity` more units given `before` already counted in the accumulation period."""
    return price(before + quantity, tiers, method) - price(before, tiers, method)


def all_units_cliffs(tiers: list[TierLike]) -> list[dict]:
    """Quantities that cost more than a higher threshold under ALL_UNITS (TIER_CLIFF).

    For each threshold t (start of tier j, rate r_j) and each earlier tier i with a higher rate,
    every q in tier i with q x r_i > t x r_j costs more than t units. One entry per (t, i) pair
    with a non-empty band, so jumps across several tiers are reported, not only adjacent ones.
    """
    cliffs = []
    for j, cur in enumerate(tiers):
        if j == 0:
            continue
        threshold = cur.from_
        for prev in tiers[:j]:
            if prev.rate <= cur.rate or prev.rate <= 0:
                continue
            break_even = threshold * cur.rate / prev.rate
            lower = max(prev.from_, break_even)
            upper = threshold if prev.to is None else min(prev.to, threshold)
            if lower < upper:
                cliffs.append(
                    {
                        "threshold": threshold,
                        "band_lower": lower,
                        "band_lower_inclusive": prev.from_ > break_even,
                        "band_upper_exclusive": upper,
                    }
                )
    return cliffs
