"""Cometric MCP server: stateless, read-only tools, resources, and prompts (spec 8.3).

No tool writes files, calls a network service, or calls an LLM.
"""

from __future__ import annotations

import functools
import json
import os
from pathlib import Path
from typing import Any

import yaml
from mcp.server.mcpserver import MCPServer

import cometric
from cometric.core import api, packs, schema, templates
from cometric.core.engine import ENGINE_VERSION
from cometric.core.glossary import GLOSSARY
from cometric.core.models import SCHEMA_VERSION
from cometric.core.quickstart import quickstart as quickstart_payloads
from cometric.core.validation import validate_engagement

EXAMPLES = Path(cometric.__file__).resolve().parent / "examples"

INSTRUCTIONS = """Cometric computes the economics of service engagements deterministically.
Never do commercial arithmetic yourself: build inputs and let these tools compute.

Start with quickstart(): it returns the conventions, and quickstart(<tool>) returns a complete,
runnable argument object for that tool. describe_schema('paths') explains every reference syntax.

Typical flow:
0. For a new deal, propose_structures(packs, deal_profile) lists candidate structures grouped by
   who absorbs a volume shortfall (never ranked), with trade-offs and evidence strength; expand
   the ones the user wants and fill their placeholders. Ask the user for what the profile needs;
   do not invent volumes, priorities, or constraints.
1. list_templates / get_template to start from a skeleton; describe_schema for exact shapes.
2. Fill every "<required>" or "<required: what to supply>" value; validate_engagement and repair using each error's JSON Pointer `path`.
3. calculate_periods (detail: summary | periods | line_items) with a scenario and a cost policy
   (pass "reference" for the shipped reference policy, or your own).
4. compare_arrangements across low/base/high scenarios; derive_risk_exposure to see who absorbs deviations.
5. search_structures to explore a declared parameter grid. Show the search_spec to the user before running it.
6. explain_fee to trace any number; lookup_concept and list_applicable_evidence for definitions and sources.

Results report dominance, never a ranking, unless the user supplies an objective. Any recommendation
needs human review. Evidence classes C and D are inference or proposal, not observed fact."""


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


def _error(code: str, message: str, path: str = "", hint: str | None = None) -> dict[str, Any]:
    err = {"code": code, "severity": "ERROR", "message": message, "path": path}
    if hint:
        err["hint"] = hint
    return {
        "status": "invalid" if code != "INTERNAL_ERROR" else "error",
        "issues": {"errors": [err], "approvals_required": [], "warnings": [], "info": []},
    }


def _safe(name: str):
    """Every tool returns a structured result; no exception reaches the client as a blank error."""

    def deco(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except KeyError as exc:
                msg = exc.args[0] if exc.args else str(exc)
                return _error(
                    "UNKNOWN_NAME", str(msg), hint=f"quickstart('{name}') shows a valid call"
                )
            except (ValueError, TypeError) as exc:
                return _error(
                    "INVALID_INPUT",
                    str(exc),
                    hint=f"quickstart('{name}') shows a valid call; describe_schema lists every input model",
                )
            except Exception as exc:  # noqa: BLE001 - surface defects instead of a blank error
                return _error(
                    "INTERNAL_ERROR",
                    f"{type(exc).__name__}: {exc}",
                    hint="this is a defect in Cometric; report it with the call's arguments",
                )

        return wrapper

    return deco


def _load_candidate(c: Any, loader) -> Any:
    if isinstance(c, str):
        return {"engagement": loader(c)}
    if isinstance(c, dict) and "engagement" in c:
        return {**c, "engagement": loader(c["engagement"])}
    return c


def build_server(http: bool = False) -> MCPServer:
    server = MCPServer(
        name="cometric",
        title="Cometric",
        description="Commercial Intelligence Engine",
        instructions=INSTRUCTIONS,
        version=cometric.__version__,
    )
    L = lambda v: _load(v, http)  # noqa: E731

    def tool(name: str | None = None, **kw):
        def register(fn):
            tool_name = name or fn.__name__
            return server.tool(name=tool_name, **kw)(_safe(tool_name)(fn))

        return register

    @tool(
        description="Start here: conventions, and with a tool name a complete runnable argument object for that tool."
    )
    def quickstart(tool_name: str | None = None) -> dict[str, Any]:
        return quickstart_payloads(tool_name)

    # --- discovery ---------------------------------------------------------------------
    @tool(
        description="JSON Schema for an input model: engagement, scenario, cost_policy, search_spec, and parts."
    )
    def describe_schema(model: str) -> dict[str, Any]:
        return schema.describe_schema(model)

    @tool(description="Installed domain packs.")
    def list_packs() -> dict[str, Any]:
        return {"packs": packs.list_packs()}

    @tool(description="A pack's schemes, rules, evidence counts, templates, and coverage.")
    def describe_pack(pack_id: str) -> dict[str, Any]:
        return packs.describe_pack(pack_id)

    @tool(
        description="Engagement templates from the core and every installed pack, each labelled with its source. Pass pack to list one pack's; get_template(template_id, pack) fetches a pack template."
    )
    def list_templates(pack: str | None = None) -> dict[str, Any]:
        return {"templates": templates.list_templates(pack)}

    @tool(
        description="An engagement skeleton. Fill every '<required>' or '<required: label>' value; 'examples' shows the shape of each."
    )
    def get_template(template_id: str, pack: str | None = None) -> dict[str, Any]:
        return templates.get_template(template_id, pack)

    @tool(
        description="Values of a controlled vocabulary (core enum or pack scheme) with definitions."
    )
    def list_vocabulary(name: str, pack: str | None = None) -> dict[str, Any]:
        return {"name": name, "values": packs.list_vocabulary(name, pack)}

    @tool(
        description="Look up a concept, rule, or term by id (e.g. PM-023, COMPAT-004) or by text."
    )
    def lookup_concept(id_or_query: str, pack: str | None = None) -> dict[str, Any]:
        return {
            "results": json.loads(json.dumps(packs.lookup_concept(id_or_query, pack), default=str))
        }

    # --- engine ------------------------------------------------------------------------
    @tool(
        name="validate_engagement",
        description="Validate an engagement. Errors carry JSON Pointer paths for repair.",
    )
    def validate_engagement_tool(engagement: dict[str, Any] | str) -> dict[str, Any]:
        return validate_engagement(L(engagement))

    @tool(
        description="Monthly contractual fee, costs, and metrics. detail: summary | periods | line_items. cost_policy: object or 'reference'."
    )
    def calculate_periods(
        engagement: dict[str, Any] | str,
        scenario: dict[str, Any] | str,
        cost_policy: dict[str, Any] | str | None = None,
        detail: str = "summary",
        precision: str = "display",
    ) -> dict[str, Any]:
        return api.calculate_periods(L(engagement), L(scenario), L(cost_policy), detail, precision)

    @tool(
        description="Evaluate candidate arrangements on the same scenarios. Reports dominance; ranks only with a supplied objective."
    )
    def compare_arrangements(
        candidates: list[Any],
        scenarios: list[dict[str, Any]],
        cost_policy: dict[str, Any] | str,
        objective: dict[str, Any] | None = None,
        tolerance_policy: dict[str, Any] | None = None,
        detail: str = "summary",
        precision: str = "display",
    ) -> dict[str, Any]:
        return api.compare_arrangements(
            [_load_candidate(c, L) for c in candidates],
            [L(s) for s in scenarios],
            L(cost_policy),
            objective,
            tolerance_policy,
            detail,
            precision,
        )

    @tool(
        description="Who absorbs each deviation from the base scenario, from calculate_periods results."
    )
    def derive_risk_exposure(
        results: list[dict[str, Any]],
        base_scenario_id: str | None = None,
        tolerance_policy: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return api.derive_risk_exposure(results, base_scenario_id, tolerance_policy)

    @tool(
        description="Candidate commercial structures for a deal profile (service, unit of work, volume, cost shape, 1 to 3 client priorities, provider risk limit, term), grouped by who absorbs a volume shortfall and never ranked. Each carries risk allocation, fit and tension with the priorities, trade-offs, evidence strength, and the inputs to supply. options.expand returns skeleton engagements with shared scenarios for compare_arrangements. Proposes no figures."
    )
    def propose_structures(
        packs: list[str], deal_profile: dict[str, Any], options: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        from cometric.core.propose import propose_structures as run

        return run(packs, deal_profile, options)

    @tool(
        description="Deterministic grid search over declared parameters; returns the trade-off frontier. Show the spec to the user first."
    )
    def search_structures(search_spec: dict[str, Any]) -> dict[str, Any]:
        spec = dict(search_spec)
        spec["engagement"] = L(spec["engagement"])
        return api.search_structures(spec)

    @tool(
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

    @tool(
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

    @tool(description="Driver volume at which term contribution is zero.")
    def break_even(
        engagement: dict[str, Any] | str,
        scenario: dict[str, Any] | str,
        cost_policy: dict[str, Any] | str,
        driver: str,
    ) -> dict[str, Any]:
        return api.break_even(L(engagement), L(scenario), L(cost_policy), driver)

    @tool(
        description="Core checks plus pack rules; optional policy {contribution_margin_floor, scenarios, cost_policy}."
    )
    def check_commercial_constraints(
        engagement: dict[str, Any] | str, policy: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        return api.check_commercial_constraints(L(engagement), policy)

    @tool(
        description="Compare computed figures with recorded actuals by month and term. publishable_summary carries no amounts, dates, or names."
    )
    def reconcile(
        engagement: dict[str, Any] | str,
        scenario: dict[str, Any] | str,
        cost_policy: dict[str, Any] | str,
        actuals: dict[str, Any] | str,
        tolerance_absolute: str = "0.01",
        tolerance_relative: str = "0",
    ) -> dict[str, Any]:
        return api.reconcile(
            L(engagement),
            L(scenario),
            L(cost_policy),
            L(actuals),
            tolerance_absolute,
            tolerance_relative,
        )

    @tool(description="Claims and sources behind a concept or claim id, with verification status.")
    def list_applicable_evidence(claim_or_concept: str, pack: str | None = None) -> dict[str, Any]:
        return applicable_evidence(claim_or_concept, pack)

    # --- resources ---------------------------------------------------------------------
    @server.resource("cometric://quickstart", name="quickstart", mime_type="application/json")
    def quickstart_resource() -> str:
        return json.dumps(quickstart_payloads(None), indent=2)

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

    @server.resource(
        "cometric://packs/{pack}/templates/{template_id}",
        name="pack-template",
        mime_type="application/json",
    )
    def pack_template_resource(pack: str, template_id: str) -> str:
        return json.dumps(templates.get_template(template_id, pack), indent=2)

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

    @server.prompt(
        name="propose_structures",
        description="Turn a deal description into candidate structures, then compare the ones the user picks.",
    )
    def propose_structures_prompt(deal: str) -> str:
        return (
            "Build a deal_profile (describe_schema deal_profile) from the description. Ask the user only for what is "
            "missing: the unit of work and any complexity tiers, volume certainty and any expected/low/high figures, "
            "the cost shape, one to three client priorities in order, the provider's limit on volume risk, and the term. "
            "Do not invent figures. Call propose_structures and explain each candidate in plain language: who absorbs a "
            "volume shortfall, which priorities it serves and where it falls short, what its labels assume, and how strong "
            "the evidence is. Say that the order is by risk group, not preference. When the user picks candidates, expand "
            "them, ask for every input listed (requires_inputs and common_inputs), fill the skeletons, and run "
            "compare_arrangements on their shared scenarios; use derive_risk_exposure to check each volume_shortfall "
            "label. Everything is pending human review.\n"
            f"\nDeal:\n{deal}"
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
