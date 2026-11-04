"""Canonical serialization and input fingerprint (spec 8.4, T-012, T-019)."""

from __future__ import annotations

import hashlib
import json
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Any

from pydantic import BaseModel

from .money import dec_str

# Arrays whose order carries no meaning; sorted by id/code (or name+period for assumptions).
UNORDERED_KEYS = {
    "components",
    "entitlements",
    "rate_schedules",
    "commitments",
    "adjustments",
    "cost_components",
    "unit_definitions",
    "services",
    "parties",
    "weight_tables",
    "bands",
    "capacity",
    "roles",
    "arrangement_versions",
    "packs",
    "assumptions",
    "risk_allocations",
    "production_standards",
    "depends_on",
    "applies_to",
    "component_ids",
    "overflow_replaces",
    "exclusions",
    "role_rates",
    "resources",
}


def to_jsonable(obj: Any) -> Any:
    if isinstance(obj, BaseModel):
        return to_jsonable(obj.model_dump(mode="python", by_alias=True))
    if isinstance(obj, Decimal):
        return dec_str(obj)
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, date):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {str(k.value if isinstance(k, Enum) else k): to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [to_jsonable(v) for v in obj]
    return obj


def _sort_key(item: Any) -> str:
    if isinstance(item, dict):
        for k in ("id", "code", "role"):
            if k in item:
                return str(item[k])
        if "name" in item:
            return f"{item['name']}|{item.get('time_period', '')}"
        return json.dumps(item, sort_keys=True)
    return json.dumps(item, sort_keys=True)


def canonicalize(obj: Any, key: str | None = None) -> Any:
    if isinstance(obj, dict):
        return {k: canonicalize(v, k) for k, v in obj.items()}
    if isinstance(obj, list):
        items = [canonicalize(v) for v in obj]
        if key in UNORDERED_KEYS:
            items = sorted(items, key=_sort_key)
        return items
    return obj


def canonical_json(obj: Any) -> str:
    return json.dumps(
        canonicalize(to_jsonable(obj)), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )


def fingerprint(payload: dict) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
