"""Domain-neutral engagement templates (spec 8.3 get_template, T-029).

Unknown values are the string "<required>". Each template lists the pointers to fill and an
illustrative example for each, so an agent knows the expected shape.
"""

from __future__ import annotations

import copy

R = "<required>"


def _base(
    eid: str, unit_code: str, components: list, *, entitlements=None, schedules=None, costs=None
) -> dict:
    return {
        "schema_version": "0.2",
        "engagement_id": eid,
        "name": R,
        "currency": R,
        "start_date": R,
        "end_date": R,
        "unit_definitions": [
            {"code": unit_code, "kind": "COUNT", "counting_rule": R, "acceptance_rule": R}
        ],
        "services": [{"id": "service", "unit_definition_id": unit_code}],
        "arrangement_versions": [
            {
                "id": "v1",
                "effective_from": R,
                "components": components,
                "entitlements": entitlements or [],
                "rate_schedules": schedules or [],
            }
        ],
        "delivery_plan": {"cost_components": costs or []},
    }


def _comp(cid: str, method: str, basis: str, cadence: str, **kw) -> dict:
    c = {
        "id": cid,
        "service_id": "service",
        "calculation_method": method,
        "billing_basis": basis,
        "charge_cadence": cadence,
        "currency": R,
        "quantity_source": None,
        "unit": None,
        "effective_period": {"from": R, "to": None},
        "depends_on": [],
    }
    c.update(kw)
    return c


def _schedule(sid: str, unit: str) -> dict:
    return {
        "id": sid,
        "currency": R,
        "unit": unit,
        "tier_method": "MARGINAL",
        "tier_scope": "ALL_ELIGIBLE",
        "accumulation_period": "MONTH",
        "tiers": [{"from": "0", "to": None, "rate": R}],
    }


def _scenario(name: str, unit: str) -> dict:
    return {
        "id": "base",
        "assumptions": [{"name": name, "value": R, "unit": unit, "time_period": R, "origin": R}],
    }


COMMON_EXAMPLES = {
    "/engagement/name": "Contract review managed service",
    "/engagement/currency": "USD",
    "/engagement/start_date": "2027-01-01",
    "/engagement/end_date": "2027-12-31",
    "/engagement/unit_definitions/0/counting_rule": "One completed review of one eligible contract",
    "/engagement/unit_definitions/0/acceptance_rule": "Accepted on client sign-off",
    "/engagement/arrangement_versions/0/effective_from": "2027-01-01",
    "/scenario/assumptions/0/time_period": "TERM",
    "/scenario/assumptions/0/origin": "ESTIMATED",
}


def _template(tid: str, description: str, engagement: dict, scenario: dict, examples: dict) -> dict:
    ex = dict(COMMON_EXAMPLES)
    ex.update(examples)
    for i, _c in enumerate(engagement["arrangement_versions"][0]["components"]):
        ex[f"/engagement/arrangement_versions/0/components/{i}/currency"] = "USD"
        ex[f"/engagement/arrangement_versions/0/components/{i}/effective_period/from"] = (
            "2027-01-01"
        )
    for i, _ in enumerate(engagement["arrangement_versions"][0]["rate_schedules"]):
        ex[f"/engagement/arrangement_versions/0/rate_schedules/{i}/currency"] = "USD"
    return {
        "template_id": tid,
        "description": description,
        "engagement": engagement,
        "scenario": scenario,
        "examples": ex,
    }


def _all() -> dict[str, dict]:
    t = {}
    t["fixed_managed_service"] = _template(
        "fixed_managed_service",
        "Fixed monthly managed service with an included allowance and overage, so volume exposure is bounded.",
        _base(
            "TEMPLATE-FIXED-MANAGED",
            "unit",
            [
                _comp("base", "FIXED_RECURRING", "FIXED", "MONTHLY", fixed_amount=R),
                _comp(
                    "overage",
                    "ALLOWANCE_OVERAGE",
                    "OUTPUT",
                    "MONTHLY",
                    quantity_source="scenario.units",
                    unit="unit",
                    entitlement_id="allowance",
                    rate_schedule_id="overage_rate",
                    depends_on=["allowance"],
                ),
            ],
            entitlements=[
                {
                    "id": "allowance",
                    "granted_by": "base",
                    "unit": "unit",
                    "included_quantity": R,
                    "accumulation_period": "MONTH",
                    "overage_recognition": "PER_SEGMENT",
                    "rollover": {"policy": "NONE"},
                }
            ],
            schedules=[_schedule("overage_rate", "unit")],
        ),
        _scenario("units", "unit"),
        {
            "/engagement/arrangement_versions/0/components/0/fixed_amount": "100000",
            "/engagement/arrangement_versions/0/entitlements/0/included_quantity": "1000",
            "/engagement/arrangement_versions/0/rate_schedules/0/tiers/0/rate": "120",
            "/scenario/assumptions/0/value": "12000",
        },
    )
    t["base_plus_overage"] = _template(
        "base_plus_overage",
        "Base fee with an annual included allowance and overage recognized as consumption crosses the allowance.",
        _base(
            "TEMPLATE-BASE-OVERAGE",
            "unit",
            [
                _comp("base", "FIXED_RECURRING", "FIXED", "ANNUAL", fixed_amount=R),
                _comp(
                    "overage",
                    "ALLOWANCE_OVERAGE",
                    "OUTPUT",
                    "MONTHLY",
                    quantity_source="scenario.units",
                    unit="unit",
                    entitlement_id="allowance",
                    rate_schedule_id="overage_rate",
                    depends_on=["allowance"],
                ),
            ],
            entitlements=[
                {
                    "id": "allowance",
                    "granted_by": "base",
                    "unit": "unit",
                    "included_quantity": R,
                    "accumulation_period": "YEAR",
                    "overage_recognition": "CUMULATIVE",
                    "rollover": {"policy": "NONE"},
                }
            ],
            schedules=[_schedule("overage_rate", "unit")],
        ),
        _scenario("units", "unit"),
        {
            "/engagement/arrangement_versions/0/components/0/fixed_amount": "1200000",
            "/engagement/arrangement_versions/0/entitlements/0/included_quantity": "12000",
            "/engagement/arrangement_versions/0/rate_schedules/0/tiers/0/rate": "120",
            "/scenario/assumptions/0/value": "10000",
        },
    )
    t["dedicated_team"] = _template(
        "dedicated_team",
        "Dedicated team priced per FTE per month; client effective price depends on utilization.",
        _base(
            "TEMPLATE-DEDICATED",
            "fte_month",
            [
                _comp(
                    "team",
                    "DEDICATED_RESOURCE",
                    "RESOURCE",
                    "MONTHLY",
                    resources=[{"role": R, "fte": R, "rate_per_fte_month": R}],
                )
            ],
        ),
        {
            "id": "base",
            "assumptions": [
                {"name": "hours_used", "value": R, "unit": "hours", "time_period": R, "origin": R}
            ],
        },
        {
            "/engagement/arrangement_versions/0/components/0/resources/0/role": "analyst",
            "/engagement/arrangement_versions/0/components/0/resources/0/fte": "8",
            "/engagement/arrangement_versions/0/components/0/resources/0/rate_per_fte_month": "16000",
            "/scenario/assumptions/0/value": "10240",
        },
    )
    t["dedicated_team"]["engagement"]["unit_definitions"][0]["kind"] = "FTE_MONTHS"
    t["fixed_project"] = _template(
        "fixed_project",
        "Fixed project fee paid on a schedule; the provider bears effort and overrun risk inside the defined scope.",
        _base(
            "TEMPLATE-FIXED-PROJECT",
            "project",
            [
                _comp(
                    "project",
                    "FIXED_PROJECT",
                    "FIXED",
                    "EVENT",
                    project_fee=R,
                    payment_schedule=[{"month": R, "amount": R}],
                )
            ],
        ),
        {
            "id": "base",
            "assumptions": [
                {
                    "name": "delivery_hours",
                    "value": R,
                    "unit": "hours",
                    "time_period": R,
                    "origin": R,
                }
            ],
        },
        {
            "/engagement/arrangement_versions/0/components/0/project_fee": "900000",
            "/engagement/arrangement_versions/0/components/0/payment_schedule/0/month": "2027-06",
            "/engagement/arrangement_versions/0/components/0/payment_schedule/0/amount": "900000",
            "/scenario/assumptions/0/value": "6000",
        },
    )
    t["time_and_materials"] = _template(
        "time_and_materials",
        "Hourly rates by role; the client bears duration and productivity risk.",
        _base(
            "TEMPLATE-TM",
            "hour",
            [
                _comp(
                    "time",
                    "TIME",
                    "TIME",
                    "MONTHLY",
                    quantity_source="scenario.hours",
                    role_rates=[{"role": "consultant", "rate": R}],
                )
            ],
        ),
        {
            "id": "base",
            "assumptions": [
                {
                    "name": "hours.consultant",
                    "value": R,
                    "unit": "hours",
                    "time_period": R,
                    "origin": R,
                }
            ],
        },
        {
            "/engagement/arrangement_versions/0/components/0/role_rates/0/rate": "250",
            "/scenario/assumptions/0/value": "2000",
        },
    )
    t["time_and_materials"]["engagement"]["unit_definitions"][0]["kind"] = "HOURS"
    return t


TEMPLATES = _all()


def list_templates(pack: str | None = None) -> list[dict]:
    """Core templates and every installed pack's templates, labelled by source. With `pack`,
    only that pack's templates."""
    from .packs import available_packs, load_pack

    out = []
    if pack is None:
        out = [
            {"template_id": k, "description": v["description"], "source": "core"}
            for k, v in TEMPLATES.items()
        ]
    for pid in [pack] if pack else available_packs():
        for k, v in sorted(load_pack(pid).templates.items()):
            entry = {"template_id": k, "description": v.get("description"), "source": pid}
            if v.get("composition"):
                entry["composition"] = v["composition"]
            out.append(entry)
    return out


def get_template(template_id: str, pack: str | None = None) -> dict:
    if pack:
        from .packs import load_pack

        p = load_pack(pack)
        if template_id not in p.templates:
            raise KeyError(
                f"pack {pack} has no template {template_id!r}; templates: {sorted(p.templates)}"
            )
        return copy.deepcopy(p.templates[template_id])
    if template_id not in TEMPLATES:
        raise KeyError(f"no template {template_id!r}; templates: {sorted(TEMPLATES)}")
    return copy.deepcopy(TEMPLATES[template_id])


def fill_template(template: dict, values: dict[str, str]) -> dict:
    """Apply pointer -> value fills to a template's engagement and scenario."""
    doc = {
        "engagement": copy.deepcopy(template["engagement"]),
        "scenario": copy.deepcopy(template["scenario"]),
    }
    for ptr, value in values.items():
        parts = ptr.lstrip("/").split("/")
        cur = doc
        for p in parts[:-1]:
            cur = cur[int(p)] if isinstance(cur, list) else cur[p]
        last = parts[-1]
        if isinstance(cur, list):
            cur[int(last)] = value
        else:
            cur[last] = value
    return doc
