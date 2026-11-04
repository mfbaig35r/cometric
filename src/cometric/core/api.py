"""Public operations (spec 8.3). Every operation is a pure function of its inputs (P-10)."""

from __future__ import annotations

import copy
import itertools
from decimal import Decimal
from typing import Any

from .engine import ENGINE_VERSION, CalculationResult, Calculator, effective_money_policy
from .enums import RiskBearer
from .fingerprint import fingerprint, to_jsonable
from .issues import CometricError, Issues
from .models import SCHEMA_VERSION, CostPolicy, Engagement, Scenario, TolerancePolicy
from .money import ZERO, safe_ratio, to_decimal
from .predicates import PredicateError, evaluate, leaves, resolve
from .validation import (
    parse_cost_policy,
    parse_engagement,
    parse_scenario,
    report,
    status_for,
    validate_engagement_model,
    validate_scenario_model,
)

DETAILS = ("summary", "periods", "line_items")
COST_FIELDS = (
    "direct_delivery_cost",
    "engagement_avoidable_cost",
    "portfolio_shared_cost",
    "corporate_overhead_cost",
    "unavoidable_direct_cost",
    "gross_profit",
    "contribution_profit",
    "full_cost_profit",
    "gross_margin",
    "contribution_margin",
    "cost_per_unit",
    "unit_contribution",
    "cumulative_contribution",
    "cumulative_contribution_incurred",
    "transition_payback_month",
)


def _prepare(
    engagement: Any, scenario: Any, cost_policy: Any, issues: Issues
) -> tuple[Engagement | None, Scenario | None, CostPolicy | None]:
    e = parse_engagement(engagement, issues)
    s = parse_scenario(scenario, issues)
    cp = parse_cost_policy(cost_policy, issues)
    if e is not None:
        validate_engagement_model(e, issues)
        if e.packs:
            from .packs import check_engagement_vocabulary

            check_engagement_vocabulary(e, issues)
        if s is not None:
            validate_scenario_model(e, s, issues)
    return e, s, cp


def input_fingerprint(
    operation: str,
    e: Engagement,
    s: Scenario | None,
    cp: CostPolicy | None,
    extra: dict | None = None,
) -> str:
    payload = {
        "operation": operation,
        "schema_version": SCHEMA_VERSION,
        "engine_version": ENGINE_VERSION,
        "engagement": e,
        "scenario": s,
        "cost_policy": cp,
        "money_policy": effective_money_policy(e),
        "packs": e.packs,
    }
    if extra:
        payload.update(extra)
    return fingerprint(payload)


def run_calculation(
    engagement: Any, scenario: Any, cost_policy: Any = None
) -> tuple[CalculationResult | None, Issues, Engagement | None, Scenario | None, CostPolicy | None]:
    """Internal: validated calculation returning engine objects."""
    issues = Issues()
    e, s, cp = _prepare(engagement, scenario, cost_policy, issues)
    if issues.has_errors or e is None or s is None:
        return None, issues, e, s, cp
    try:
        result = Calculator(e, s, cp, issues).run()
    except CometricError as exc:
        return None, exc.issues, e, s, cp
    return result, issues, e, s, cp


def _blank_costs(block: dict) -> None:
    for k in COST_FIELDS:
        if k in block:
            block[k] = None
    if "costs_by_category" in block:
        block["costs_by_category"] = None


def calculate_periods(
    engagement: Any, scenario: Any, cost_policy: Any = None, detail: str = "summary"
) -> dict:
    if detail not in DETAILS:
        detail = "summary"
    result, issues, e, s, cp = run_calculation(engagement, scenario, cost_policy)
    if result is None:
        out = {
            "status": status_for(issues),
            "feasible": None,
            "engine_version": ENGINE_VERSION,
            "schema_version": SCHEMA_VERSION,
        }
        out["issues"] = report(issues)
        return to_jsonable(out)
    assert e is not None and s is not None
    data = copy.deepcopy(result.data)
    costs_evaluated = (
        cp is not None and e.delivery_plan is not None and bool(e.delivery_plan.cost_components)
    )
    if not costs_evaluated:
        reason = (
            "no cost_policy supplied"
            if cp is None
            else "the engagement has no delivery_plan cost section"
        )
        issues.info(
            "COSTS_NOT_EVALUATED", f"margin and contribution metrics are unavailable: {reason}"
        )
        for block in [data["term"], *data["years"].values(), *data["periods"]]:
            _blank_costs(block)
    out: dict[str, Any] = {
        "status": "ok" if result.feasible else "infeasible",
        "feasible": result.feasible,
        "engine_version": ENGINE_VERSION,
        "schema_version": SCHEMA_VERSION,
        "input_fingerprint": input_fingerprint("calculate_periods", e, s, cp),
        "engagement_id": e.engagement_id,
        "scenario_id": s.id,
        "cost_policy": cp.id if cp else None,
        "currency": e.currency,
        "money_policy": effective_money_policy(e),
        "packs": e.packs,
        "costs_evaluated": costs_evaluated,
        "horizon": {
            "from": data["periods"][0]["period"] if data["periods"] else None,
            "to": data["periods"][-1]["period"] if data["periods"] else None,
        },
        "term": data["term"],
        "years": data["years"],
    }
    if detail in ("periods", "line_items"):
        out["periods"] = data["periods"]
    if detail == "line_items":
        out["line_items"] = {
            "fees": [ln.as_dict() for ln in result.fee_lines],
            "costs": [ln.as_dict() for ln in result.cost_lines],
        }
        out["ledger"] = result.ledger
    out["issues"] = report(issues)
    return to_jsonable(out)


def explain_fee(
    engagement: Any,
    scenario: Any,
    cost_policy: Any = None,
    period: str | None = None,
    component: str | None = None,
) -> dict:
    result, issues, e, s, cp = run_calculation(engagement, scenario, cost_policy)
    if result is None:
        return to_jsonable({"status": status_for(issues), "issues": report(issues)})
    lines = [
        ln
        for ln in result.fee_lines
        if (period is None or ln.period == period)
        and (component is None or ln.component == component or ln.ref == component)
    ]
    total = sum((ln.rounded for ln in lines), ZERO)
    ledger = [x for x in result.ledger if period is None or x["period"] == period]
    explanation = [
        f"step {ln.step} ({ln.as_dict()['stage']}): {ln.ref} {ln.kind} = {ln.rounded} [{ln.formula}]"
        for ln in lines
    ]
    return to_jsonable(
        {
            "status": "ok",
            "input_fingerprint": input_fingerprint("calculate_periods", e, s, cp),
            "period": period,
            "component": component,
            "fee_total": total,
            "line_items": [ln.as_dict() for ln in lines],
            "ledger": ledger,
            "explanation": explanation,
            "labels": {
                "contract_facts": "rates, allowances, minimums, and adjustment terms come from the engagement",
                "assumptions": "quantities come from the scenario, each with its origin",
                "calculated": "every amount above is computed by the engine",
            },
        }
    )


# --- break-even and price floor ---------------------------------------------------------


def _with_driver(s: Scenario, driver: str, value: Decimal) -> Scenario:
    base = next((a for a in s.assumptions if a.name == driver), None)
    if base is None:
        raise KeyError(driver)
    others = [a for a in s.assumptions if a.name != driver]
    new = base.model_copy(
        update={
            "value": value,
            "time_period": "TERM",
            "profile": [],
            "distribution": base.distribution.FLAT,
        }
    )
    return s.model_copy(update={"assumptions": [*others, new]})


def break_even(
    engagement: Any, scenario: Any, cost_policy: Any, driver: str, max_value: int = 10**9
) -> dict:
    """Driver volume at which term contribution is zero; piecewise, by bracketing (spec 5.4)."""
    issues = Issues()
    e, s, cp = _prepare(engagement, scenario, cost_policy, issues)
    if issues.has_errors or e is None or s is None or cp is None:
        if cp is None:
            issues.error("COST_POLICY_REQUIRED", "break-even needs a cost policy", "/cost_policy")
        return to_jsonable({"status": status_for(issues), "issues": report(issues)})

    def f(x: int) -> Decimal:
        r = Calculator(e, _with_driver(s, driver, Decimal(x)), cp).run()
        return r.data["term"]["contribution_profit"]

    try:
        f0 = f(0)
    except KeyError:
        issues.error("UNKNOWN_DRIVER", f"scenario has no assumption named {driver!r}", "/driver")
        return to_jsonable({"status": "invalid", "issues": report(issues)})
    if f0 == 0:
        return to_jsonable(
            {"status": "ok", "driver": driver, "exact": ZERO, "whole": 0, "direction": "flat"}
        )
    hi = 1
    fhi = f(hi)
    while (fhi > 0) == (f0 > 0) and fhi != 0 and hi < max_value:
        hi *= 2
        fhi = f(hi)
    if (fhi > 0) == (f0 > 0) and fhi != 0:
        return to_jsonable(
            {
                "status": "ok",
                "driver": driver,
                "exact": None,
                "whole": None,
                "reason": "contribution does not change sign within the searched range",
            }
        )
    lo, flo = 0, f0
    while hi - lo > 1:
        mid = (lo + hi) // 2
        fm = f(mid)
        if (fm > 0) == (flo > 0) and fm != 0:
            lo, flo = mid, fm
        else:
            hi, fhi = mid, fm
    slope = fhi - flo
    exact = Decimal(lo) + (-flo) / slope if slope != 0 else Decimal(hi)
    increasing = f0 < 0
    whole = hi if increasing else (hi if fhi >= 0 else lo)
    return to_jsonable(
        {
            "status": "ok",
            "driver": driver,
            "exact": exact,
            "whole": whole,
            "direction": "increasing" if increasing else "decreasing",
            "note": "Exact value assumes contribution is linear between the bracketing whole units.",
        }
    )


def price_floor(
    engagement: Any,
    scenarios: list[Any],
    cost_policy: Any,
    target_margin: Any,
    risk_premium: Any = "0",
) -> dict:
    """P_min(q) = (C(q) + RiskPremium) / (1 - m_t), per scenario volume (spec 5.6)."""
    issues = Issues()
    try:
        m_t = to_decimal(target_margin)
        rp = to_decimal(risk_premium)
    except ValueError as exc:
        issues.error("SCHEMA", str(exc), "/target_margin")
        return to_jsonable({"status": "invalid", "issues": report(issues)})
    if m_t >= 1:
        issues.error("TARGET_MARGIN_RANGE", "target_margin must be less than 1", "/target_margin")
    if rp < 0:
        issues.error("RISK_PREMIUM_RANGE", "risk_premium cannot be negative", "/risk_premium")
    if cost_policy is None:
        issues.error("COST_POLICY_REQUIRED", "price floor needs a cost policy", "/cost_policy")
    if issues.has_errors:
        return to_jsonable({"status": "invalid", "issues": report(issues)})
    rows = []
    for sc in scenarios:
        r = calculate_periods(engagement, sc, cost_policy)
        if r["status"] not in ("ok", "infeasible"):
            return r
        t = r["term"]
        cost = Decimal(t["direct_delivery_cost"]) + Decimal(t["engagement_avoidable_cost"])
        floor = (cost + rp) / (1 - m_t)
        q = Decimal(t["client_consumed_quantity"]) if t.get("client_consumed_quantity") else None
        fee = Decimal(t["contractual_fee"])
        rows.append(
            {
                "scenario_id": r["scenario_id"],
                "volume": q,
                "volume_quantity": t.get("client_value_quantity"),
                "costs_in_floor": cost,
                "price_floor": floor,
                "unit_floor": safe_ratio(floor, q) if q else None,
                "current_fee": fee,
                "headroom": fee - floor,
            }
        )
    return to_jsonable(
        {
            "status": "ok",
            "target_margin": m_t,
            "risk_premium": rp,
            "origin": "INTERNAL_POLICY",
            "formula": "(DIRECT_DELIVERY + ENGAGEMENT_AVOIDABLE costs + risk premium) / (1 - target margin)",
            "note": "A decision formula under the caller's targets, not a market benchmark.",
            "floors": rows,
        }
    )


# --- risk exposure, comparison, search --------------------------------------------------


def _d(v: Any) -> Decimal | None:
    if v is None:
        return None
    return v if isinstance(v, Decimal) else Decimal(str(v))


def _client_price(term: dict) -> Decimal | None:
    v = term.get("effective_client_unit_price")
    if v is None:
        v = term.get("effective_client_price_per_used_hour")
    return _d(v)


def derive_risk_exposure(
    results: list[dict],
    base_scenario_id: str | None = None,
    tolerance_policy: Any = None,
    declared: list[dict] | None = None,
) -> dict:
    """Who absorbs each deviation from the base case (spec 5.5)."""
    tol = (
        TolerancePolicy.model_validate(tolerance_policy)
        if tolerance_policy is not None and not isinstance(tolerance_policy, TolerancePolicy)
        else tolerance_policy
    )
    by_id = {r["scenario_id"]: r for r in results if r.get("status") in ("ok", "infeasible")}
    if not by_id:
        return {
            "status": "invalid",
            "issues": {
                "errors": [
                    {
                        "code": "NO_RESULTS",
                        "message": "no successful calculation results supplied",
                        "path": "/results",
                    }
                ]
            },
        }
    base_id = base_scenario_id or ("base" if "base" in by_id else next(iter(by_id)))
    base = by_id[base_id]["term"]
    base_cp = _d(base["contribution_profit"])
    base_price = _client_price(base)
    rows = []
    warnings = []
    declared = declared or []
    for sid, r in by_id.items():
        if sid == base_id:
            continue
        t = r["term"]
        cp = _d(t["contribution_profit"])
        price = _client_price(t)
        pdown = (base_cp - cp) if base_cp is not None and cp is not None else None
        cdown = (price - base_price) if price is not None and base_price is not None else None
        label = None
        if tol is not None and pdown is not None and cdown is not None:
            p_adv = pdown > tol.provider_relative * abs(base_cp)
            c_adv = cdown > tol.client_relative * abs(base_price)
            label = (
                RiskBearer.SHARED
                if p_adv and c_adv
                else RiskBearer.PROVIDER
                if p_adv
                else RiskBearer.CLIENT
                if c_adv
                else RiskBearer.NONE_ADVERSE
            ).value
        row = {
            "scenario_id": sid,
            "provider_downside": pdown,
            "client_downside": cdown,
            "client_price": price,
            "fee_change": _d(t["contractual_fee"]) - _d(base["contractual_fee"]),
            "derived_bearer": label,
        }
        rows.append(row)
        for d in declared:
            if (
                label
                and label != RiskBearer.NONE_ADVERSE.value
                and d.get("declared_bearer") not in (label, RiskBearer.SHARED.value)
            ):
                warnings.append(
                    {
                        "code": "RISK_MISMATCH",
                        "message": f"{d.get('risk_type')} risk is declared as borne by {d.get('declared_bearer')} but scenario {sid} shows {label}",
                        "path": "",
                    }
                )
    return to_jsonable(
        {
            "status": "ok",
            "base_scenario_id": base_id,
            "base_contribution": base_cp,
            "base_client_price": base_price,
            "tolerance": tol,
            "deviations": rows,
            "warnings": warnings,
        }
    )


def _term_summary(r: dict) -> dict:
    t = r["term"]
    return {
        k: t.get(k)
        for k in (
            "contractual_fee",
            "direct_delivery_cost",
            "engagement_avoidable_cost",
            "gross_profit",
            "contribution_profit",
            "gross_margin",
            "contribution_margin",
            "effective_client_unit_price",
            "effective_client_price_per_used_hour",
            "commitment_utilization",
            "overage_fee",
            "commitment_shortfall",
            "capacity",
        )
    }


def _dominates(a: list[tuple[Decimal | None, str]], b: list[tuple[Decimal | None, str]]) -> bool:
    better = False
    for (va, sense), (vb, _) in zip(a, b, strict=True):
        if va is None:
            return False
        if vb is None:
            better = True
            continue
        if sense == "max":
            if va < vb:
                return False
            if va > vb:
                better = True
        else:
            if va > vb:
                return False
            if va < vb:
                better = True
    return better


def dominance(vectors: dict[str, list[tuple[Decimal | None, str]]]) -> dict[str, list[str]]:
    return {
        i: [j for j in vectors if j != i and _dominates(vectors[j], vectors[i])] for i in vectors
    }


def _evaluate_candidate(engagement: Any, scenarios: list[Any], cost_policy: Any) -> dict:
    results = [calculate_periods(engagement, sc, cost_policy) for sc in scenarios]
    ok = all(r["status"] in ("ok", "infeasible") for r in results)
    feasible = ok and all(r.get("feasible") for r in results)
    return {"results": results, "valid": ok, "feasible": feasible}


def _objective_value(per_scenario: dict[str, dict], objective: dict) -> Decimal | None:
    metric = objective["metric"]
    agg = objective.get("aggregation", "BASE")
    values = {sid: _d(m.get(metric)) for sid, m in per_scenario.items()}
    if agg == "BASE":
        return values.get(objective.get("base_scenario", "base"), next(iter(values.values()), None))
    vals = [v for v in values.values() if v is not None]
    if not vals or len(vals) != len(values):
        return None
    if agg == "WORST":
        return min(vals) if objective.get("sense", "max") == "max" else max(vals)
    return sum(vals, ZERO) / len(vals)


def compare_arrangements(
    candidates: list[dict],
    scenario_set: list[Any],
    cost_policy: Any,
    objective: dict | None = None,
    tolerance_policy: Any = None,
) -> dict:
    """Evaluate candidates on the same scenarios; report dominance, never a ranking (spec 6.2)."""
    rows = {}
    for cand in candidates:
        ev = _evaluate_candidate(cand["engagement"], scenario_set, cost_policy)
        per = {r["scenario_id"]: _term_summary(r) for r in ev["results"] if r.get("scenario_id")}
        exposure = (
            derive_risk_exposure(ev["results"], tolerance_policy=tolerance_policy)
            if ev["valid"]
            else None
        )
        rows[cand["id"]] = {
            "id": cand["id"],
            "valid": ev["valid"],
            "feasible": ev["feasible"],
            "scenarios": per,
            "risk_exposure": exposure,
            "issues": [r["issues"] for r in ev["results"] if r["status"] not in ("ok",)],
        }
    feasible_ids = [i for i, r in rows.items() if r["feasible"]]
    vectors = {}
    for i in feasible_ids:
        vec = []
        for sid in rows[i]["scenarios"]:
            m = rows[i]["scenarios"][sid]
            vec.append((_d(m["contribution_profit"]), "max"))
            vec.append((_client_price(m), "min"))
        vectors[i] = vec
    dom = dominance(vectors)
    for i in rows:
        rows[i]["dominated_by"] = dom.get(i, []) if i in feasible_ids else None
    out = {
        "status": "ok",
        "metrics": [
            "contribution_profit (max) in every scenario",
            "effective client unit price (min) in every scenario",
        ],
        "candidates": list(rows.values()),
        "non_dominated": [i for i in feasible_ids if not dom[i]],
        "infeasible": [i for i, r in rows.items() if r["valid"] and not r["feasible"]],
        "ranking": None,
    }
    if objective:
        scored = {i: _objective_value(rows[i]["scenarios"], objective) for i in feasible_ids}
        scored = {i: v for i, v in scored.items() if v is not None}
        if scored:
            best_v = (
                max(scored.values())
                if objective.get("sense", "max") == "max"
                else min(scored.values())
            )
            out["objective"] = objective
            out["best_under_objective"] = [i for i, v in scored.items() if v == best_v]
    return to_jsonable(out)


def _set_pointer(doc: Any, ptr: str, value: Any) -> None:
    parts = [p.replace("~1", "/").replace("~0", "~") for p in ptr.lstrip("/").split("/")]
    cur = doc
    for p in parts[:-1]:
        cur = cur[int(p)] if isinstance(cur, list) else cur[p]
    last = parts[-1]
    if isinstance(cur, list):
        cur[int(last)] = value
    else:
        cur[last] = value


def _param_values(p: dict) -> list[str]:
    if "values" in p:
        return [str(v) for v in p["values"]]
    r = p["range"]
    start, stop, step = to_decimal(r["from"]), to_decimal(r["to"]), to_decimal(r["step"])
    if step <= 0:
        raise ValueError("range step must be positive")
    out = []
    v = start
    while v <= stop:
        out.append(str(v))
        v += step
    return out


def search_structures(search_spec: dict) -> dict:
    """Deterministic grid search returning the trade-off frontier (spec 6.4)."""
    spec = search_spec
    base_engagement = spec["engagement"]
    scenarios = spec["scenarios"]
    cost_policy = spec.get("cost_policy")
    params = spec.get("parameters", [])
    max_candidates = int(spec.get("max_candidates", 10000))
    max_candidates = min(max_candidates, 10000)
    max_returned = int(spec.get("max_returned", 50))
    try:
        grids = [_param_values(p) for p in params]
    except (KeyError, ValueError) as exc:
        return {
            "status": "invalid",
            "issues": {
                "errors": [{"code": "PARAMETER_SPEC", "message": str(exc), "path": "/parameters"}]
            },
        }
    size = 1
    for g in grids:
        size *= len(g)
    if size > max_candidates:
        return {
            "status": "rejected",
            "reason": f"grid has {size} candidates, above max_candidates {max_candidates}",
            "grid_size": size,
        }
    constraints = spec.get("constraints")
    objective = spec.get("objective")
    frontier_metrics = spec.get("frontier_metrics")
    counts = {
        "enumerated": 0,
        "invalid": 0,
        "infeasible": 0,
        "failing_constraints": 0,
        "evaluated": 0,
    }
    invalid_reasons: dict[str, int] = {}
    evaluated = []
    for combo in itertools.product(*grids):
        counts["enumerated"] += 1
        eng = copy.deepcopy(base_engagement)
        values = {}
        for p, v in zip(params, combo, strict=True):
            try:
                _set_pointer(eng, p["pointer"], v)
            except (KeyError, IndexError, ValueError, TypeError):
                return {
                    "status": "invalid",
                    "issues": {
                        "errors": [
                            {
                                "code": "BAD_POINTER",
                                "message": f"pointer {p['pointer']} does not resolve",
                                "path": "/parameters",
                            }
                        ]
                    },
                }
            values[p["name"]] = v
        ev = _evaluate_candidate(eng, scenarios, cost_policy)
        if not ev["valid"]:
            counts["invalid"] += 1
            for r in ev["results"]:
                for err in r.get("issues", {}).get("errors", []):
                    invalid_reasons[err["code"]] = invalid_reasons.get(err["code"], 0) + 1
            continue
        if not ev["feasible"]:
            counts["infeasible"] += 1
            continue
        per = {r["scenario_id"]: _term_summary(r) for r in ev["results"]}
        exposure = derive_risk_exposure(ev["results"])
        doc = {"scenarios": per, "parameters": values}
        if constraints is not None:
            try:
                if not evaluate(constraints, doc):
                    counts["failing_constraints"] += 1
                    continue
            except PredicateError as exc:
                return {
                    "status": "invalid",
                    "issues": {
                        "errors": [
                            {"code": "BAD_CONSTRAINT", "message": str(exc), "path": "/constraints"}
                        ]
                    },
                }
        counts["evaluated"] += 1
        evaluated.append(
            {
                "parameters": values,
                "scenarios": per,
                "risk_exposure": exposure,
                "fingerprints": [r["input_fingerprint"] for r in ev["results"]],
                "_doc": doc,
            }
        )
    vectors = {}
    for i, c in enumerate(evaluated):
        vectors[str(i)] = _frontier_vector(c, frontier_metrics)
    dom = dominance(vectors)
    frontier = [evaluated[int(i)] for i in vectors if not dom[i]]
    for c in frontier:
        c["binding_constraints"] = _binding(constraints, c["_doc"]) if constraints else []
    best = None
    if objective:
        scored = [(c, _objective_value(c["scenarios"], objective)) for c in evaluated]
        scored = [(c, v) for c, v in scored if v is not None]
        if scored:
            bv = (
                max(v for _, v in scored)
                if objective.get("sense", "max") == "max"
                else min(v for _, v in scored)
            )
            best = [c["parameters"] for c, v in scored if v == bv]
    truncated = len(frontier) > max_returned
    for c in evaluated:
        c.pop("_doc", None)
    out = {
        "status": "ok",
        "approval_state": "PENDING_HUMAN_REVIEW",
        "record_type": "PricingRecommendation",
        "counts": {**counts, "on_frontier": len(frontier)},
        "invalid_reasons": invalid_reasons,
        "frontier_metrics": frontier_metrics
        or [
            "contribution_profit in base (max)",
            "effective client unit price in base (min)",
            "largest provider downside (min)",
            "largest client downside (min)",
        ],
        "frontier": frontier[:max_returned],
        "frontier_truncated": truncated,
        "objective": objective,
        "best_under_objective": best,
        "note": "Frontier candidates are not ranked. A recommendation needs human review before adoption.",
    }
    return to_jsonable(out)


def _frontier_vector(c: dict, metrics: list[dict] | None) -> list[tuple[Decimal | None, str]]:
    per = c["scenarios"]
    base_id = "base" if "base" in per else next(iter(per))
    if metrics:
        vec = []
        for m in metrics:
            vals = resolve(c["_doc"], m["path"])
            v = _d(vals[0]) if vals else None
            vec.append((v, m.get("sense", "max")))
        return vec
    devs = (
        c["risk_exposure"].get("deviations", []) if c["risk_exposure"].get("status") == "ok" else []
    )
    pd = [_d(d["provider_downside"]) for d in devs if d["provider_downside"] is not None]
    cd = [_d(d["client_downside"]) for d in devs if d["client_downside"] is not None]
    return [
        (_d(per[base_id]["contribution_profit"]), "max"),
        (_client_price(per[base_id]), "min"),
        (max(pd) if pd else ZERO, "min"),
        (max(cd) if cd else ZERO, "min"),
    ]


def _binding(constraints: dict, doc: dict) -> list[dict]:
    out = []
    for leaf in leaves(constraints):
        op = next(k for k in leaf if k != "path")
        if op not in ("gt", "lt", "gte", "lte"):
            continue
        vals = [_d(v) for v in resolve(doc, leaf["path"]) if v is not None]
        if not vals:
            continue
        target = _d(leaf[op])
        slack = min(abs(v - target) for v in vals)
        out.append(
            {"path": leaf["path"], "op": op, "threshold": target, "closest_value_slack": slack}
        )
    out.sort(key=lambda x: x["closest_value_slack"])
    return out


def check_commercial_constraints(engagement: Any, policy: dict | None = None) -> dict:
    """Core checks plus rules from declared packs; policy thresholds are caller-supplied (spec 7.3)."""
    issues = Issues()
    e = parse_engagement(engagement, issues)
    if e is None:
        return to_jsonable({"status": status_for(issues), **report(issues)})
    validate_engagement_model(e, issues)
    rules_fired: list[dict] = []
    if e.packs:
        from .packs import check_engagement_vocabulary, evaluate_rules

        check_engagement_vocabulary(e, issues)
        rules_fired = evaluate_rules(e, issues)
    measured = {}
    if policy and policy.get("contribution_margin_floor") is not None and policy.get("scenarios"):
        floor = to_decimal(policy["contribution_margin_floor"])
        for sc in policy["scenarios"]:
            r = calculate_periods(e, sc, policy.get("cost_policy"))
            cm = (
                r.get("term", {}).get("contribution_margin")
                if r.get("status") in ("ok", "infeasible")
                else None
            )
            measured[r.get("scenario_id", "?")] = cm
            if cm is not None and Decimal(cm) < floor:
                issues.approval(
                    "CONTRIBUTION_BELOW_FLOOR",
                    f"contribution margin {cm} in scenario {r['scenario_id']} is below the policy floor {floor}",
                )
    return to_jsonable(
        {
            "status": status_for(issues),
            "rules_fired": rules_fired,
            "measured": measured,
            **report(issues),
        }
    )
