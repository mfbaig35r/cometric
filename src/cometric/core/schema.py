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


def _propose_models() -> dict[str, type[BaseModel]]:
    from .propose import DealProfile, ProposeOptions

    return {"deal_profile": DealProfile, "propose_options": ProposeOptions}


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
                "required": ["name"],
                "properties": {
                    "name": {"type": "string"},
                    "pointers": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Write the same value to several places (e.g. the same uplift on every tier)",
                    },
                    "transform": {
                        "enum": ["set", "scale", "add"],
                        "description": "set writes the value; scale writes base x (1 + value); add writes base + value, where base is the engagement's current value at each pointer",
                    },
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
                "tie_breakers": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "Further {metric, sense, aggregation} keys applied in order when the objective ties",
                },
            },
        },
        "include_baseline": {
            "type": "boolean",
            "description": "Default true: evaluate the engagement as given and report each best result's difference from it",
        },
        "dry_run": {
            "type": "boolean",
            "description": "Return grid size, calculation count, and an estimated time without running",
        },
        "detail": {"enum": ["summary", "standard", "full"], "description": "Default summary"},
        "precision": {"enum": ["display", "exact"], "description": "Default display"},
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


RESULT_METRICS = [
    "contractual_fee",
    "overage_fee",
    "outcome_fee",
    "commitment_shortfall",
    "direct_delivery_cost",
    "engagement_avoidable_cost",
    "gross_profit",
    "contribution_profit",
    "gross_margin",
    "contribution_margin",
    "effective_client_unit_price",
    "effective_client_price_per_used_hour",
    "commitment_utilization",
]

EXTRA_SCHEMAS = {
    "candidate": {
        "title": "Candidate (compare_arrangements)",
        "description": "Either a wrapper {id, engagement} or a bare engagement object (its engagement_id becomes the id).",
        "oneOf": [
            {
                "type": "object",
                "required": ["engagement"],
                "properties": {
                    "id": {"type": "string"},
                    "engagement": {
                        "type": ["object", "string"],
                        "description": "Engagement object, or a file path when the stdio server has COMETRIC_ALLOWED_ROOT",
                    },
                },
            },
            {"type": "object", "required": ["schema_version"], "description": "A bare engagement"},
        ],
    },
    "constraint": {
        "title": "Constraint / rule predicate",
        "description": (
            'Combinators: {"all": [P, ...]}, {"any": [P, ...]}, {"not": P}. Leaf: {"path": PATH, "<op>": VALUE} '
            'with op one of equals, in, contains, exists, gt, lt, gte, lte; or {"path": PATH, "op": "<=", "value": VALUE}. '
            'A leaf is true when ANY value at PATH satisfies it, so \'every scenario >= x\' is written {"not": {"path": "scenarios.*.m", "lt": x}}.'
        ),
        "examples": [
            {"not": {"path": "scenarios.*.contribution_margin", "lt": "0.15"}},
            {
                "all": [
                    {"path": "scenarios.base.effective_client_unit_price", "lte": "110"},
                    {"path": "scenarios.low.contribution_profit", "gt": "0"},
                ]
            },
        ],
    },
    "paths": {
        "title": "Reference conventions",
        "description": "How each kind of reference is written.",
        "properties": {
            "quantity_source": 'Scenario assumption name, optionally prefixed: "scenario.units" or "units". Time and band quantities append .<role> or .<band>.',
            "constraint_paths": "Dotted paths into {scenarios: {<scenario_id>: metrics}, parameters: {<name>: value}}; * matches any scenario id. Metrics: "
            + ", ".join(RESULT_METRICS)
            + ".",
            "rule_paths": "Dotted paths into the engagement; [*] expands lists, e.g. arrangement_versions[*].components[*].billing_basis.",
            "search_parameters": 'JSON Pointers into the engagement, e.g. /arrangement_versions/0/components/0/fixed_amount; or "assumption": <name> to set a scenario assumption in every scenario.',
            "derived_quantities": "Scenario derived quantities are referenced by name like assumptions; expressions use {q}, {const}, {sum}, {difference}, {product}, {quotient}.",
            "error_paths": "JSON Pointers into the call's arguments, e.g. /engagement/arrangement_versions/0/components/1/unit.",
            "by_reference": "On the stdio server started with COMETRIC_ALLOWED_ROOT, any engagement, scenario, or actuals argument may be a file path under that root instead of an object; a casebook fixture file is unwrapped to its engagement.",
        },
    },
    "actuals": {
        "title": "Actuals (reconcile)",
        "type": "object",
        "properties": {
            "periods": {"type": "object", "description": '{"YYYY-MM": {metric: "amount"}}'},
            "term": {"type": "object", "description": '{metric: "amount"}'},
        },
        "description": "Amounts are decimal strings or integers. Metrics: contractual_fee, outcome_fee, overage_fee, commitment_shortfall, direct_delivery_cost, engagement_avoidable_cost, gross_profit, contribution_profit, worked_hours, standard_value.",
    },
}


def describe_schema(model: str) -> dict:
    if model == "search_spec":
        return SEARCH_SPEC_SCHEMA
    if model in EXTRA_SCHEMAS:
        return EXTRA_SCHEMAS[model]
    models_ = {**MODELS, **_propose_models()}
    if model not in models_:
        raise KeyError(f"no model {model!r}; models: {model_names()}")
    return models_[model].model_json_schema(by_alias=True)


def model_names() -> list[str]:
    return sorted([*MODELS, *_propose_models(), *EXTRA_SCHEMAS, "search_spec"])
