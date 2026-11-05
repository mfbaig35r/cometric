"""Output shaping for LLM consumers: display precision and compact results (spec 8.3).

Exact decimals are always available with precision="exact"; "display" rounds ratios to 4 places
and prices to 2, and leaves money (already at the currency's minor unit) unchanged.
"""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Any

RATIO_KEYS = {
    "gross_margin",
    "contribution_margin",
    "commitment_utilization",
    "capacity_utilization",
    "productive_hours_utilization",
    "relative_difference",
    "realization",
    "target_margin",
}
PRICE_KEYS = {
    "effective_client_unit_price",
    "effective_client_price_per_used_hour",
    "cost_per_unit",
    "unit_contribution",
    "client_price",
    "client_downside",
    "base_client_price",
    "effective_billing_rate",
    "unit_floor",
}
KEY_METRICS = (
    "contractual_fee",
    "contribution_profit",
    "contribution_margin",
    "effective_client_unit_price",
    "overage_fee",
    "commitment_shortfall",
)
_DEC = re.compile(r"^-?\d+\.\d+$")


def _round(value: str, places: int) -> str:
    q = Decimal(value).quantize(Decimal(1).scaleb(-places))
    text = format(q.normalize(), "f") if q != 0 else "0"
    return text


def present(
    obj: Any,
    precision: str = "display",
    drop_nulls: bool = False,
    key: str | None = None,
    depth: int = 0,
) -> Any:
    """Round for display and, when asked, drop empty fields below the top level (top-level
    nulls such as "ranking": null carry meaning and are kept)."""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if drop_nulls and depth > 0 and v is None:
                continue
            out[k] = present(v, precision, drop_nulls, k, depth + 1)
        return out
    if isinstance(obj, list):
        return [present(v, precision, drop_nulls, key, depth + 1) for v in obj]
    if precision == "display" and isinstance(obj, str) and _DEC.match(obj):
        decimals = len(obj.split(".")[1])
        if key in RATIO_KEYS and decimals > 4:
            return _round(obj, 4)
        if key in PRICE_KEYS and decimals > 2:
            return _round(obj, 2)
        if decimals > 6:
            return _round(obj, 4)
    return obj


def key_metrics(metrics: dict) -> dict:
    return {k: metrics.get(k) for k in KEY_METRICS}
