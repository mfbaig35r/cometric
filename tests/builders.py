"""Small builders for hand-made test engagements."""

from __future__ import annotations

import copy

PERIOD = {"from": "2027-01-01", "to": None}


def unit(code="unit", rule="One accepted unit", kind="COUNT"):
    return {
        "code": code,
        "kind": kind,
        "counting_rule": rule,
        "acceptance_rule": "Accepted on sign-off",
    }


def comp(cid, method, basis, cadence="MONTHLY", **kw):
    c = {
        "id": cid,
        "service_id": "svc",
        "calculation_method": method,
        "billing_basis": basis,
        "charge_cadence": cadence,
        "currency": "USD",
        "quantity_source": None,
        "unit": None,
        "effective_period": copy.deepcopy(PERIOD),
        "depends_on": [],
    }
    c.update(kw)
    return c


def schedule(
    sid, unit_code="unit", tiers=None, method="MARGINAL", scope="ALL_ELIGIBLE", period="MONTH"
):
    return {
        "id": sid,
        "currency": "USD",
        "unit": unit_code,
        "tier_method": method,
        "tier_scope": scope,
        "accumulation_period": period,
        "tiers": tiers or [{"from": "0", "to": None, "rate": "10"}],
    }


def engagement(
    components,
    *,
    units=None,
    entitlements=None,
    schedules=None,
    commitments=None,
    adjustments=None,
    versions=None,
    costs=None,
    capacity=None,
    breach=None,
    start="2027-01-01",
    end="2027-12-31",
    **extra,
):
    e = {
        "schema_version": "0.2",
        "engagement_id": "TEST",
        "currency": "USD",
        "start_date": start,
        "end_date": end,
        "unit_definitions": units or [unit()],
        "services": [{"id": "svc", "unit_definition_id": (units or [unit()])[0]["code"]}],
        "arrangement_versions": versions
        or [
            {
                "id": "v1",
                "effective_from": start,
                "components": components,
                "entitlements": entitlements or [],
                "rate_schedules": schedules or [],
                "commitments": commitments or [],
                "adjustments": adjustments or [],
            }
        ],
    }
    if costs is not None or capacity is not None:
        e["delivery_plan"] = {
            "cost_components": costs or [],
            "capacity": capacity or [],
            "breach_mode": breach,
        }
    e.update(extra)
    return e


def scen(sid="s", assumptions=(), horizon=None):
    s = {
        "id": sid,
        "assumptions": [
            {"name": n, "value": v, "unit": u, "time_period": p, "origin": "ILLUSTRATIVE"}
            for n, v, u, p in assumptions
        ],
    }
    if horizon:
        s["horizon"] = {"from": horizon[0], "to": horizon[1]}
    return s


def codes(result_or_report, bucket=None):
    issues = result_or_report.get("issues", result_or_report)
    buckets = [bucket] if bucket else ["errors", "approvals_required", "warnings", "info"]
    return [i["code"] for b in buckets for i in issues.get(b, [])]
