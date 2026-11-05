"""Cometric MCP server: stateless, read-only tools, resources, and prompts (spec 8.3).

No tool writes files, calls a network service, or calls an LLM.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import yaml
from mcp.server.mcpserver import MCPServer

import cometric
from cometric.core import api, packs, schema, templates
from cometric.core.engine import ENGINE_VERSION
from cometric.core.models import SCHEMA_VERSION
from cometric.core.validation import validate_engagement

EXAMPLES = Path(cometric.__file__).resolve().parent / "examples"

INSTRUCTIONS = """Cometric computes the economics of service engagements deterministically.
Never do commercial arithmetic yourself: build inputs and let these tools compute.

Typical flow:
1. list_templates / get_template to start from a skeleton; describe_schema for exact shapes.
2. Fill every "<required>" value; validate_engagement and repair using each error's JSON Pointer `path`.
3. calculate_periods (detail: summary | periods | line_items) with a scenario and a cost policy
   (pass "reference" for the shipped reference policy, or your own).
4. compare_arrangements across low/base/high scenarios; derive_risk_exposure to see who absorbs deviations.
5. search_structures to explore a declared parameter grid. Show the search_spec to the user before running it.
6. explain_fee to trace any number; lookup_concept and list_applicable_evidence for definitions and sources.

Results report dominance, never a ranking, unless the user supplies an objective. Any recommendation
needs human review. Evidence classes C and D are inference or proposal, not observed fact."""

GLOSSARY = {
    "contractual_fee": "Contractual consideration computed under the arrangement for a period. Not recognized revenue.",
    "gross_profit": "contractual_fee minus DIRECT_DELIVERY costs.",
    "contribution_profit": "gross_profit minus ENGAGEMENT_AVOIDABLE costs. Layers partition costs, so nothing is subtracted twice.",
    "margin": "(price - cost) / price. Not the same as markup, (price - cost) / cost.",
    "accumulation_period": "The period over which an allowance, minimum, tier counter, or capacity limit accumulates: MONTH, QUARTER, YEAR, CONTRACT_YEAR, TERM.",
    "recognition": "When an accumulated effect is charged: CUMULATIVE (the month the threshold is crossed), PERIOD_END (true-up in the final month), PER_SEGMENT (monthly only).",
    "margin_layer": "DIRECT_DELIVERY, ENGAGEMENT_AVOIDABLE, PORTFOLIO_SHARED, CORPORATE_OVERHEAD. A cost policy maps every cost category to exactly one layer.",
    "cost_policy": "Mapping from cost category to margin layer plus the transition-cost view. 'reference' is shipped and must be named explicitly.",
    "dominance": "Candidate X dominates Y when X is at least as good on every comparison metric and strictly better on one.",
    "derived_bearer": "Who absorbs a deviation from the base scenario: PROVIDER (contribution falls), CLIENT (unit price rises), SHARED, or NONE_ADVERSE.",
    "realization": "contractual_fee / standard_value, where standard_value is hours worked at the delivery plan's standard rate card. Below 1 is a write-down.",
    "outcome_fee": "Fee from an OUTCOME_ADJUSTMENT component, measured over its accumulation period and charged at period end: SHARE of improvement against a baseline, SUCCESS amount at a target, or PERCENT_OF_OUTCOME. Needs attribution, a cap, and recorded approval.",
    "price_floor": "(DIRECT_DELIVERY + ENGAGEMENT_AVOIDABLE costs + risk premium) / (1 - target margin). A decision formula, not a benchmark.",
    "evidence_class": "A_DIRECT, B_CORROBORATED, C_INFERENCE, D_PROPOSED. Independent of prevalence.",
    "origin": "Every assumption is OBSERVED, CONTRACTED, ESTIMATED, ILLUSTRATIVE, or INTERNAL_POLICY.",
}


def _allowed_root() -> Path | None:
    root = os.environ.get("COMETRIC_ALLOWED_ROOT")
    return Path(root).resolve() if root else None


def _load(value: Any, transport_http: bool = False) -> Any:
    """Inputs are inline JSON objects, or file paths under COMETRIC_ALLOWED_ROOT (stdio only)."""
    if not isinstance(value, str):
        return value
    if value in ("reference",):
        return value
    root = _allowed_root()
    if transport_http or root is None:
        raise ValueError(
            "pass inputs inline; file paths need the stdio server started with COMETRIC_ALLOWED_ROOT"
        )
    path = (root / value).resolve() if not Path(value).is_absolute() else Path(value).resolve()
    if root not in path.parents and path != root:
        raise ValueError(f"path {value!r} is outside the allowed root")
    text = path.read_text()
    doc = yaml.safe_load(text) if path.suffix in (".yaml", ".yml") else json.loads(text)
    if isinstance(doc, dict) and "engagement" in doc and "schema_version" not in doc:
        return doc["engagement"]
    return doc


def build_server(http: bool = False) -> MCPServer:
    server = MCPServer(
        name="cometric",
        title="Cometric",
        description="Commercial Intelligence Engine",
        instructions=INSTRUCTIONS,
        version=cometric.__version__,
    )
    L = lambda v: _load(v, http)  # noqa: E731

    # --- discovery ---------------------------------------------------------------------
    @server.tool(
        description="JSON Schema for an input model: engagement, scenario, cost_policy, search_spec, and parts."
    )
    def describe_schema(model: str) -> dict[str, Any]:
        return schema.describe_schema(model)

    @server.tool(description="Installed domain packs.")
    def list_packs() -> dict[str, Any]:
        return {"packs": packs.list_packs()}

    @server.tool(description="A pack's schemes, rules, evidence counts, templates, and coverage.")
    def describe_pack(pack_id: str) -> dict[str, Any]:
        return packs.describe_pack(pack_id)

    @server.tool(description="Engagement templates (core and pack).")
    def list_templates() -> dict[str, Any]:
        return {"templates": templates.list_templates()}

    @server.tool(
        description="An engagement skeleton. Fill every '<required>' value; 'examples' shows the shape of each."
    )
    def get_template(template_id: str, pack: str | None = None) -> dict[str, Any]:
        return templates.get_template(template_id, pack)

    @server.tool(
        description="Values of a controlled vocabulary (core enum or pack scheme) with definitions."
    )
    def list_vocabulary(name: str, pack: str | None = None) -> dict[str, Any]:
        return {"name": name, "values": packs.list_vocabulary(name, pack)}

    @server.tool(
        description="Look up a concept, rule, or term by id (e.g. PM-023, COMPAT-004) or by text."
    )
    def lookup_concept(id_or_query: str, pack: str | None = None) -> dict[str, Any]:
        return {
            "results": json.loads(json.dumps(packs.lookup_concept(id_or_query, pack), default=str))
        }

    # --- engine ------------------------------------------------------------------------
    @server.tool(
        name="validate_engagement",
        description="Validate an engagement. Errors carry JSON Pointer paths for repair.",
    )
    def validate_engagement_tool(engagement: dict[str, Any] | str) -> dict[str, Any]:
        return validate_engagement(L(engagement))

    @server.tool(
        description="Monthly contractual fee, costs, and metrics. detail: summary | periods | line_items. cost_policy: object or 'reference'."
    )
    def calculate_periods(
        engagement: dict[str, Any] | str,
        scenario: dict[str, Any] | str,
        cost_policy: dict[str, Any] | str | None = None,
        detail: str = "summary",
    ) -> dict[str, Any]:
        return api.calculate_periods(L(engagement), L(scenario), L(cost_policy), detail)

    @server.tool(
        description="Evaluate candidate arrangements on the same scenarios. Reports dominance; ranks only with a supplied objective."
    )
    def compare_arrangements(
        candidates: list[dict[str, Any]],
        scenarios: list[dict[str, Any]],
        cost_policy: dict[str, Any] | str,
        objective: dict[str, Any] | None = None,
        tolerance_policy: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return api.compare_arrangements(
            [{**c, "engagement": L(c["engagement"])} for c in candidates],
            [L(s) for s in scenarios],
            L(cost_policy),
            objective,
            tolerance_policy,
        )

    @server.tool(
        description="Who absorbs each deviation from the base scenario, from calculate_periods results."
    )
    def derive_risk_exposure(
        results: list[dict[str, Any]],
        base_scenario_id: str | None = None,
        tolerance_policy: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return api.derive_risk_exposure(results, base_scenario_id, tolerance_policy)

    @server.tool(
        description="Deterministic grid search over declared parameters; returns the trade-off frontier. Show the spec to the user first."
    )
    def search_structures(search_spec: dict[str, Any]) -> dict[str, Any]:
        spec = dict(search_spec)
        spec["engagement"] = L(spec["engagement"])
        return api.search_structures(spec)

    @server.tool(
        description="Line-item trace for a period (and optional component), recomputed from inputs."
    )
    def explain_fee(
        engagement: dict[str, Any] | str,
        scenario: dict[str, Any] | str,
        period: str,
        cost_policy: dict[str, Any] | str | None = None,
        component: str | None = None,
    ) -> dict[str, Any]:
        return api.explain_fee(L(engagement), L(scenario), L(cost_policy), period, component)

    @server.tool(
        description="Fee at which contribution margin equals the target, at each scenario volume."
    )
    def price_floor(
        engagement: dict[str, Any] | str,
        scenarios: list[dict[str, Any]],
        cost_policy: dict[str, Any] | str,
        target_margin: str,
        risk_premium: str = "0",
    ) -> dict[str, Any]:
        return api.price_floor(
            L(engagement), [L(s) for s in scenarios], L(cost_policy), target_margin, risk_premium
        )

    @server.tool(description="Driver volume at which term contribution is zero.")
    def break_even(
        engagement: dict[str, Any] | str,
        scenario: dict[str, Any] | str,
        cost_policy: dict[str, Any] | str,
        driver: str,
    ) -> dict[str, Any]:
        return api.break_even(L(engagement), L(scenario), L(cost_policy), driver)

    @server.tool(
        description="Core checks plus pack rules; optional policy {contribution_margin_floor, scenarios, cost_policy}."
    )
    def check_commercial_constraints(
        engagement: dict[str, Any] | str, policy: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        return api.check_commercial_constraints(L(engagement), policy)

    @server.tool(
        description="Claims and sources behind a concept or claim id, with verification status."
    )
    def list_applicable_evidence(claim_or_concept: str, pack: str | None = None) -> dict[str, Any]:
        return applicable_evidence(claim_or_concept, pack)

    # --- resources ---------------------------------------------------------------------
    @server.resource("cometric://glossary", name="glossary", mime_type="application/json")
    def glossary() -> str:
        return json.dumps(
            {"engine_version": ENGINE_VERSION, "schema_version": SCHEMA_VERSION, "terms": GLOSSARY},
            indent=2,
        )

    @server.resource("cometric://schema/{model}", name="schema", mime_type="application/json")
    def schema_resource(model: str) -> str:
        return json.dumps(schema.describe_schema(model), indent=2)

    @server.resource(
        "cometric://packs/{pack}/concepts/{scheme_name}",
        name="concept-scheme",
        mime_type="application/json",
    )
    def concept_scheme(pack: str, scheme_name: str) -> str:
        return json.dumps(packs.scheme(pack, scheme_name), indent=2, default=str)

    @server.resource("cometric://packs/{pack}/rules", name="rules", mime_type="application/json")
    def rules(pack: str) -> str:
        return json.dumps(
            {"pack": pack, "rules": packs.load_pack(pack).rules}, indent=2, default=str
        )

    @server.resource(
        "cometric://packs/{pack}/coverage", name="coverage", mime_type="application/json"
    )
    def coverage(pack: str) -> str:
        return json.dumps(
            {"pack": pack, "areas": packs.load_pack(pack).coverage}, indent=2, default=str
        )

    @server.resource(
        "cometric://templates/{template_id}", name="template", mime_type="application/json"
    )
    def template_resource(template_id: str) -> str:
        return json.dumps(templates.get_template(template_id), indent=2)

    @server.resource("cometric://examples/{case}", name="example", mime_type="application/json")
    def example(case: str) -> str:
        path = EXAMPLES / f"{case}.json"
        if not path.exists() or path.parent != EXAMPLES:
            raise ValueError(
                f"no example {case!r}; examples: {sorted(p.stem for p in EXAMPLES.glob('*.json'))}"
            )
        return path.read_text()

    # --- prompts -----------------------------------------------------------------------
    @server.prompt(
        description="Turn a term sheet, SOW, or contract summary into a validated engagement."
    )
    def model_from_terms(terms: str) -> str:
        return (
            "Model these commercial terms with Cometric. Do not compute any amounts yourself.\n"
            "1. Call list_templates and pick the closest template; call get_template.\n"
            "2. Fill every '<required>' value from the terms. Where the terms are silent, ask the user; do not invent rates, volumes, or policies.\n"
            "3. Call validate_engagement. For each error, fix the field at its `path` and validate again until valid.\n"
            "4. Show the user each assumption with its origin (CONTRACTED from the terms, ESTIMATED, ILLUSTRATIVE) and confirm them.\n"
            f"\nTerms:\n{terms}"
        )

    @server.prompt(
        description="Design a commercial arrangement with the twelve-step selection sequence."
    )
    def design_arrangement(service_description: str) -> str:
        return (
            "Design candidate commercial arrangements for this service with Cometric, following these steps:\n"
            "1 characterize the service; 2 identify economic drivers; 3 quantify uncertainty (low/base/high); "
            "4 capture client preferences; 5 shortlist feasible billing bases (list_vocabulary billing_basis); "
            "6 select compatible levers (lookup_concept on levers and compatibility rules); 7 screen constraints "
            "(check_commercial_constraints with the relevant pack); 8 model low/base/high (calculate_periods); "
            "9 assess client value (effective unit price, unused allowance); 10 compare candidates "
            "(compare_arrangements); 11 identify negotiation exchanges (lookup_concept NEG-); "
            "12 present alternatives with explicit assumptions and the items needing human approval.\n"
            "Selection heuristics (SEL-*) are inference, not rules: cite them as such. Never call one structure optimal "
            "unless the user gave an objective.\n"
            f"\nService:\n{service_description}"
        )

    @server.prompt(description="Compare three structures across low, base, and high demand.")
    def compare_structures(context: str) -> str:
        return (
            "Build three candidate engagements (by default: fixed managed service, dedicated capacity, base plus overage, "
            "or the user's choice) that price the same service. Build low, base, and high scenarios with the user. "
            "Run compare_arrangements with a cost policy the user confirms. Present, per candidate: fee, contribution, "
            "client effective unit price, capacity use, derived risk exposure, and which candidates are dominated. "
            "Do not rank non-dominated candidates.\n"
            f"\nContext:\n{context}"
        )

    @server.prompt(
        name="search_structures", description="Draft and run a structure search with the user."
    )
    def search_structures_prompt(goal: str) -> str:
        return (
            "Draft a search_spec (describe_schema search_spec): the base engagement, the parameters to vary with JSON Pointers "
            "and value lists, the scenarios, the cost policy, any constraints, and an objective only if the user states one. "
            "Show the spec to the user and get confirmation before calling search_structures. Present the frontier, the binding "
            "constraints, and the counts. The result is pending human review.\n"
            f"\nGoal:\n{goal}"
        )

    @server.prompt(description="Find and quantify negotiation exchanges for a proposed concession.")
    def negotiation_options(concession: str) -> str:
        return (
            "Use lookup_concept to find negotiation exchanges (NEG-*) that match this concession. For each, build the "
            "modified engagement and quantify it against the current one with compare_arrangements. Present the trade, "
            "not a recommendation.\n"
            f"\nProposed concession:\n{concession}"
        )

    @server.prompt(
        description="Walk through a calculation separating facts, assumptions, and computed results."
    )
    def explain_result(question: str) -> str:
        return (
            "Answer with explain_fee for the relevant period and component. Separate: contract facts (rates, allowances, "
            "minimums from the engagement), assumptions (scenario quantities with their origin), and calculated results "
            "(engine amounts). Quote amounts exactly as returned.\n"
            f"\nQuestion:\n{question}"
        )

    return server


def applicable_evidence(claim_or_concept: str, pack: str | None = None) -> dict[str, Any]:
    all_claims: dict[str, dict] = {}
    all_sources: dict[str, dict] = {}
    for pid in packs.available_packs():
        p = packs.load_pack(pid)
        for c in p.claims:
            all_claims[c["id"]] = {"pack": pid, **c}
        for s in p.sources:
            all_sources[s["id"]] = {"pack": pid, **s}
    claim_ids: list[str] = []
    concept = None
    if claim_or_concept in all_claims:
        claim_ids = [claim_or_concept]
    else:
        hits = packs.lookup_concept(claim_or_concept, pack)
        if hits:
            concept = hits[0]
            claim_ids = list(concept.get("claims") or [])
            for o in concept.get("overlays", []):
                claim_ids += list(o.get("claims") or [])
    records = []
    for cid in dict.fromkeys(claim_ids):
        c = all_claims.get(cid)
        if not c:
            continue
        records.append(
            {
                **c,
                "source_records": [
                    all_sources[s] for s in c.get("sources") or [] if s in all_sources
                ],
            }
        )
    return json.loads(
        json.dumps(
            {
                "query": claim_or_concept,
                "concept": {k: concept[k] for k in ("id", "label", "evidence_class", "prevalence")}
                if concept
                else None,
                "claims": records,
            },
            default=str,
        )
    )


def http_app(token: str | None = None, allowed_hosts: list[str] | None = None):
    """Stateless streamable-HTTP app: POST /mcp only, GET /mcp -> 405, optional bearer token.

    DNS-rebinding protection stays on. Allowed Host headers default to localhost; deployments
    set COMETRIC_ALLOWED_HOSTS (comma-separated, e.g. "mcp.example.com,mcp.example.com:443").
    """
    from mcp.server.transport_security import TransportSecuritySettings

    server = build_server(http=True)
    hosts = allowed_hosts
    if hosts is None:
        env = os.environ.get("COMETRIC_ALLOWED_HOSTS")
        hosts = (
            [h.strip() for h in env.split(",")]
            if env
            else ["localhost", "localhost:*", "127.0.0.1", "127.0.0.1:*"]
        )
    security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=hosts,
        allowed_origins=[f"https://{h}" for h in hosts] + [f"http://{h}" for h in hosts],
    )
    app = server.streamable_http_app(
        stateless_http=True, json_response=True, transport_security=security
    )
    token = token if token is not None else os.environ.get("COMETRIC_MCP_TOKEN")

    async def guarded(scope, receive, send):
        if scope["type"] == "http" and scope["path"].rstrip("/") == "/mcp":
            if scope["method"] in ("GET", "DELETE"):
                await _respond(send, 405, b"Method Not Allowed", [(b"allow", b"POST")])
                return
            if token:
                headers = dict(scope.get("headers") or [])
                if headers.get(b"authorization", b"") != f"Bearer {token}".encode():
                    await _respond(send, 401, b"Unauthorized", [])
                    return
        await app(scope, receive, send)

    return guarded


async def _respond(send, status: int, body: bytes, headers: list) -> None:
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [(b"content-type", b"text/plain"), *headers],
        }
    )
    await send({"type": "http.response.body", "body": body})


def main(transport: str = "stdio", host: str = "127.0.0.1", port: int = 8765) -> None:
    if transport == "stdio":
        build_server().run("stdio")
        return
    import uvicorn

    uvicorn.run(http_app(), host=host, port=port)
