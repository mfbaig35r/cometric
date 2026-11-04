"""Decimal arithmetic, rounding, and exact allocation (spec 4.7)."""

from __future__ import annotations

import decimal
from decimal import ROUND_DOWN, ROUND_HALF_EVEN, ROUND_HALF_UP, Decimal
from typing import Annotated, Any

from pydantic import BeforeValidator, PlainSerializer, WithJsonSchema

CONTEXT = decimal.Context(prec=28, rounding=ROUND_HALF_EVEN)
decimal.setcontext(CONTEXT)

ZERO = Decimal(0)
ONE = Decimal(1)

# ISO 4217 minor units for common currencies; anything else defaults to 2.
MINOR_UNITS = {"JPY": 0, "KRW": 0, "BHD": 3, "KWD": 3, "OMR": 3, "TND": 3, "JOD": 3}

_ROUNDING = {"HALF_UP": ROUND_HALF_UP, "HALF_EVEN": ROUND_HALF_EVEN}


def to_decimal(value: Any) -> Decimal:
    """Parse a decimal from str, int, or Decimal. Floats and bools are rejected (P-08)."""
    if isinstance(value, bool):
        raise ValueError("booleans are not decimal values")
    if isinstance(value, float):
        raise ValueError('floating-point numbers are not accepted; pass a string such as "120.00"')
    if isinstance(value, Decimal):
        result = value
    elif isinstance(value, int):
        result = Decimal(value)
    elif isinstance(value, str):
        try:
            result = Decimal(value.strip())
        except decimal.InvalidOperation as exc:
            raise ValueError(f"not a decimal number: {value!r}") from exc
    else:
        raise ValueError(f"expected a decimal string or integer, got {type(value).__name__}")
    if not result.is_finite():
        raise ValueError("decimal values must be finite")
    return result


def dec_str(value: Decimal) -> str:
    """Plain-notation string with trailing zeros removed ("100000.00" -> "100000")."""
    if value == 0:
        return "0"
    text = format(value.normalize(), "f")
    return text


Dec = Annotated[
    Decimal,
    BeforeValidator(to_decimal),
    PlainSerializer(lambda d: dec_str(d), return_type=str),
    WithJsonSchema(
        {"type": "string", "pattern": r"^-?\d+(\.\d+)?$", "description": "Decimal as a string"}
    ),
]


def quantize(value: Decimal, scale: int, mode: str = "HALF_UP") -> Decimal:
    return value.quantize(Decimal(1).scaleb(-scale), rounding=_ROUNDING[mode])


def allocate_exact(total: Decimal, parts: int, scale: int) -> list[Decimal]:
    """Split total into `parts` shares that sum exactly to total at `scale`.

    Each share is the truncated quotient; the residual is distributed one minor unit at a
    time to the earliest shares (spec 4.7).
    """
    if parts <= 0:
        raise ValueError("parts must be positive")
    unit = Decimal(1).scaleb(-scale)
    if total.quantize(unit) != total:
        raise ValueError(f"total {total} is not representable at scale {scale}")
    sign = -1 if total < 0 else 1
    magnitude = abs(total)
    base = (magnitude / parts).quantize(unit, rounding=ROUND_DOWN)
    residual_units = int((magnitude - base * parts) / unit)
    shares = [base + unit if i < residual_units else base for i in range(parts)]
    return [sign * s for s in shares]


def allocate_weighted(total: Decimal, weights: list[Decimal], scale: int) -> list[Decimal]:
    """Split total in proportion to weights, preserving the total exactly at `scale`."""
    weight_sum = sum(weights, ZERO)
    if weight_sum <= 0:
        raise ValueError("weights must sum to a positive value")
    unit = Decimal(1).scaleb(-scale)
    raw = [total * w / weight_sum for w in weights]
    shares = [r.quantize(unit, rounding=ROUND_DOWN) for r in raw]
    residual_units = int((total - sum(shares, ZERO)) / unit)
    order = sorted(range(len(raw)), key=lambda i: (-(raw[i] - shares[i]), i))
    for i in order[:residual_units]:
        shares[i] += unit
    return shares


def safe_ratio(numerator: Decimal, denominator: Decimal) -> Decimal | None:
    """Ratio, or None when the denominator is zero (T-008)."""
    if denominator == 0:
        return None
    return numerator / denominator


def margin_and_markup(cost: Decimal, price: Decimal) -> dict[str, Decimal | None]:
    """Margin = (P - C) / P; markup = (P - C) / C (report FM-021, FM-022; T-014)."""
    return {"margin": safe_ratio(price - cost, price), "markup": safe_ratio(price - cost, cost)}
