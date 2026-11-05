"""Command-line interface. Every command prints JSON; inputs are JSON or YAML files.

A file may hold a bare object, or a casebook fixture with `engagement` and `scenarios` keys.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

from . import __version__
from .core import api, packs, schema, templates
from .core.validation import validate_engagement


def _read(path: str) -> Any:
    text = Path(path).read_text()
    return yaml.safe_load(text) if path.endswith((".yaml", ".yml")) else json.loads(text)


def _engagement(path: str) -> Any:
    doc = _read(path)
    return doc["engagement"] if isinstance(doc, dict) and "engagement" in doc else doc


def _scenarios(path: str | None, fallback: str, ids: list[str] | None = None) -> list[Any]:
    doc = _read(path or fallback)
    if isinstance(doc, dict) and "scenarios" in doc:
        found = doc["scenarios"]
    elif isinstance(doc, list):
        found = doc
    else:
        found = [doc]
    if ids:
        found = [s for s in found if s.get("id") in ids]
    return found


def _policy(value: str | None, engagement_file: str) -> Any:
    if value is None:
        return None
    if Path(value).exists():
        return _read(value)
    doc = _read(engagement_file)
    if isinstance(doc, dict) and value in (doc.get("cost_policies") or {}):
        return doc["cost_policies"][value]
    return value


def _print(obj: Any) -> None:
    json.dump(obj, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="cometric", description="Commercial Intelligence Engine")
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="cmd", required=True)

    v = sub.add_parser("validate", help="validate an engagement")
    v.add_argument("engagement")

    c = sub.add_parser("calculate", help="monthly fees, costs, and metrics")
    c.add_argument("engagement")
    c.add_argument("--scenarios", help="file with scenario(s); defaults to the engagement file")
    c.add_argument("--scenario", action="append", help="scenario id to run (repeatable)")
    c.add_argument("--cost-policy", help="file, a policy name inside a fixture, or 'reference'")
    c.add_argument("--detail", default="summary", choices=["summary", "periods", "line_items"])

    e = sub.add_parser("explain", help="line-item trace for one period")
    e.add_argument("engagement")
    e.add_argument("--period", required=True)
    e.add_argument("--scenarios")
    e.add_argument("--scenario")
    e.add_argument("--component")
    e.add_argument("--cost-policy")

    cmp_ = sub.add_parser("compare", help="compare engagements across the same scenarios")
    cmp_.add_argument("engagements", nargs="+")
    cmp_.add_argument("--scenarios", required=True)
    cmp_.add_argument("--cost-policy", required=True)

    s = sub.add_parser("search", help="structure search from a search_spec file")
    s.add_argument("spec")

    f = sub.add_parser("floor", help="price floor at each scenario volume")
    f.add_argument("engagement")
    f.add_argument("--scenarios")
    f.add_argument("--cost-policy", required=True)
    f.add_argument("--target-margin", required=True)
    f.add_argument("--risk-premium", default="0")

    b = sub.add_parser("break-even", help="driver volume at zero contribution")
    b.add_argument("engagement")
    b.add_argument("--driver", required=True)
    b.add_argument("--scenarios")
    b.add_argument("--scenario")
    b.add_argument("--cost-policy", required=True)

    rc = sub.add_parser("reconcile", help="compare computed figures with recorded actuals")
    rc.add_argument("engagement")
    rc.add_argument(
        "--actuals",
        required=True,
        help="file with {periods: {YYYY-MM: {metric: amount}}, term: {...}}",
    )
    rc.add_argument("--scenarios")
    rc.add_argument("--scenario")
    rc.add_argument("--cost-policy", required=True)
    rc.add_argument("--tolerance-absolute", default="0.01")
    rc.add_argument("--tolerance-relative", default="0")
    rc.add_argument(
        "--summary-only", action="store_true", help="print only the publishable summary"
    )

    sch = sub.add_parser("schema", help="JSON Schema for a model")
    sch.add_argument("model", choices=schema.model_names())

    sub.add_parser("packs", help="list installed packs")
    pv = sub.add_parser("validate-pack", help="validate a pack's data files")
    pv.add_argument("pack")
    lk = sub.add_parser("lookup", help="look up a concept by id or text")
    lk.add_argument("query")
    lk.add_argument("--pack")

    tl = sub.add_parser("templates", help="list templates")
    tl.add_argument("--pack", help="list a pack's templates instead of the core ones")
    t = sub.add_parser("template", help="print a template")
    t.add_argument("template_id")
    t.add_argument("--pack", help="pack that ships the template, e.g. consulting")

    m = sub.add_parser("mcp", help="run the MCP server")
    m.add_argument("--transport", default="stdio", choices=["stdio", "http"])
    m.add_argument("--host", default="127.0.0.1")
    m.add_argument("--port", type=int, default=8765)

    a = p.parse_args(argv)

    if a.cmd == "validate":
        out = validate_engagement(_engagement(a.engagement))
        _print(out)
        return 0 if out["valid"] else 1
    if a.cmd == "calculate":
        eng = _engagement(a.engagement)
        results = [
            api.calculate_periods(eng, sc, _policy(a.cost_policy, a.engagement), a.detail)
            for sc in _scenarios(a.scenarios, a.engagement, a.scenario)
        ]
        _print(results[0] if len(results) == 1 else results)
        return 0 if all(r["status"] in ("ok", "infeasible") for r in results) else 1
    if a.cmd == "explain":
        sc = _scenarios(a.scenarios, a.engagement, [a.scenario] if a.scenario else None)[0]
        _print(
            api.explain_fee(
                _engagement(a.engagement),
                sc,
                _policy(a.cost_policy, a.engagement),
                a.period,
                a.component,
            )
        )
        return 0
    if a.cmd == "compare":
        cands = [{"id": Path(x).stem, "engagement": _engagement(x)} for x in a.engagements]
        _print(
            api.compare_arrangements(
                cands,
                _scenarios(a.scenarios, a.scenarios),
                _policy(a.cost_policy, a.engagements[0]),
            )
        )
        return 0
    if a.cmd == "search":
        _print(api.search_structures(_read(a.spec)))
        return 0
    if a.cmd == "floor":
        _print(
            api.price_floor(
                _engagement(a.engagement),
                _scenarios(a.scenarios, a.engagement),
                _policy(a.cost_policy, a.engagement),
                a.target_margin,
                a.risk_premium,
            )
        )
        return 0
    if a.cmd == "break-even":
        sc = _scenarios(a.scenarios, a.engagement, [a.scenario] if a.scenario else None)[0]
        _print(
            api.break_even(
                _engagement(a.engagement), sc, _policy(a.cost_policy, a.engagement), a.driver
            )
        )
        return 0
    if a.cmd == "reconcile":
        sc = _scenarios(a.scenarios, a.engagement, [a.scenario] if a.scenario else None)[0]
        out = api.reconcile(
            _engagement(a.engagement),
            sc,
            _policy(a.cost_policy, a.engagement),
            _read(a.actuals),
            a.tolerance_absolute,
            a.tolerance_relative,
        )
        _print(
            {
                k: out.get(k)
                for k in ("status", "feasible", "compared", "discrepancies", "publishable_summary")
            }
            | {
                "errors": out.get("issues", {}).get("errors", []),
                "warnings": out.get("issues", {}).get("warnings", []),
            }
            if a.summary_only
            else out
        )
        return 0 if out.get("status") in ("reconciled", "discrepancies", "nothing_compared") else 1
    if a.cmd == "schema":
        _print(schema.describe_schema(a.model))
        return 0
    if a.cmd == "packs":
        _print(packs.list_packs())
        return 0
    if a.cmd == "validate-pack":
        problems = packs.validate_pack(a.pack)
        _print({"pack": a.pack, "valid": not problems, "problems": problems})
        return 0 if not problems else 1
    if a.cmd == "lookup":
        _print(packs.lookup_concept(a.query, a.pack))
        return 0
    if a.cmd == "templates":
        if a.pack:
            from .core.packs import load_pack

            p = load_pack(a.pack)
            _print(
                [
                    {"template_id": k, "description": v.get("description"), "source": a.pack}
                    for k, v in sorted(p.templates.items())
                ]
            )
        else:
            _print(templates.list_templates())
        return 0
    if a.cmd == "template":
        _print(templates.get_template(a.template_id, a.pack))
        return 0
    if a.cmd == "mcp":
        from .mcp.server import main as mcp_main

        mcp_main("stdio" if a.transport == "stdio" else "http", a.host, a.port)
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
