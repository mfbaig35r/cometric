"""JSON Schema export for every input model (spec 8.3 describe_schema)."""

from __future__ import annotations

from pydantic import BaseModel

from . import models

MODELS: dict[str, type[BaseModel]] = {
    "engagement": models.Engagement,
    "scenario": models.Scenario,
    "cost_policy": models.CostPolicy,
    "tolerance_policy": models.TolerancePolicy,
    "arrangement_version": models.ArrangementVersion,
    "fee_component": models.FeeComponent,
    "rate_schedule": models.RateSchedule,
    "entitlement": models.Entitlement,
    "commitment": models.Commitment,
    "adjustment": models.Adjustment,
    "delivery_plan": models.DeliveryPlan,
    "cost_component": models.CostComponent,
    "assumption": models.Assumption,
}

SEARCH_SPEC_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "SearchSpec",
    "type": "object",
    "required": ["engagement", "scenarios", "parameters"],
    "properties": {
        "engagement": {
            "type": "object",
            "description": "Base engagement; parameters overwrite values at JSON Pointers.",
        },
        "scenarios": {"type": "array", "items": {"type": "object"}},
        "cost_policy": {
            "description": "Cost policy object or the name of a built-in policy such as 'reference'."
        },
        "parameters": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["name", "pointer"],
                "properties": {
                    "name": {"type": "string"},
                    "pointer": {
                        "type": "string",
                        "description": "JSON Pointer into the engagement, e.g. /arrangement_versions/0/components/0/fixed_amount",
                    },
                    "values": {"type": "array", "items": {"type": "string"}},
                    "range": {
                        "type": "object",
                        "properties": {
                            "from": {"type": "string"},
                            "to": {"type": "string"},
                            "step": {"type": "string"},
                        },
                    },
                },
            },
        },
        "constraints": {
            "type": "object",
            "description": "Predicate over {scenarios: {id: metrics}, parameters: {...}}",
        },
        "objective": {
            "type": "object",
            "properties": {
                "metric": {"type": "string"},
                "sense": {"enum": ["max", "min"]},
                "aggregation": {"enum": ["BASE", "WORST", "MEAN"]},
                "base_scenario": {"type": "string"},
            },
        },
        "frontier_metrics": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"path": {"type": "string"}, "sense": {"enum": ["max", "min"]}},
            },
        },
        "max_candidates": {"type": "integer", "maximum": 10000},
        "max_returned": {"type": "integer"},
    },
}


def describe_schema(model: str) -> dict:
    if model == "search_spec":
        return SEARCH_SPEC_SCHEMA
    if model not in MODELS:
        raise KeyError(f"no model {model!r}; models: {sorted([*MODELS, 'search_spec'])}")
    return MODELS[model].model_json_schema(by_alias=True)


def model_names() -> list[str]:
    return sorted([*MODELS, "search_spec"])
