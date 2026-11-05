"""Cometric: Commercial Intelligence Engine.

Model commercial arrangements, simulate engagement economics, and search for structures that
balance profitability, risk, and client value. All arithmetic is deterministic decimal code.
"""

from .core.api import (
    break_even,
    calculate_periods,
    check_commercial_constraints,
    compare_arrangements,
    derive_risk_exposure,
    explain_fee,
    price_floor,
    reconcile,
    search_structures,
)
from .core.engine import ENGINE_VERSION
from .core.models import SCHEMA_VERSION
from .core.packs import describe_pack, list_packs, list_vocabulary, lookup_concept
from .core.schema import describe_schema
from .core.templates import get_template, list_templates
from .core.validation import validate_engagement

try:
    from importlib.metadata import PackageNotFoundError, version

    __version__ = version("cometric")
except PackageNotFoundError:  # running from a source tree without installation
    __version__ = "0.0.0"

__all__ = [
    "ENGINE_VERSION",
    "SCHEMA_VERSION",
    "break_even",
    "calculate_periods",
    "check_commercial_constraints",
    "compare_arrangements",
    "derive_risk_exposure",
    "describe_pack",
    "describe_schema",
    "explain_fee",
    "get_template",
    "list_packs",
    "list_templates",
    "list_vocabulary",
    "lookup_concept",
    "price_floor",
    "reconcile",
    "search_structures",
    "validate_engagement",
]
