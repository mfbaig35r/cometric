"""propose_structures end to end: the reviewed golden proposal for the spec A4 profile, and the
partner flow through the MCP server (propose, expand, fill, compare, check labels)."""

import asyncio
import json
import os
from pathlib import Path

import pytest
from test_propose import fixture_fill

from cometric.core.propose import propose_structures
from cometric.core.quickstart import payloads

GOLDEN = Path(__file__).parent / "golden" / "propose_a4.json"


def test_golden_proposal_for_the_spec_profile():
    req = payloads()["propose_structures"]
    out = propose_structures(req["packs"], req["deal_profile"], req["options"])
    text = json.dumps(out, indent=1, sort_keys=True) + "\n"
    if os.environ.get("UPDATE_GOLDEN"):
        GOLDEN.write_text(text)
    assert text == GOLDEN.read_text(), "proposal changed; review it, then UPDATE_GOLDEN=1"


def test_partner_flow_through_mcp():
    pytest.importorskip("mcp")
    from cometric.mcp.server import build_server

    srv = build_server()

    def call(name, args):
        async def go():
            res = await srv.call_tool(name, args)
            return res.structured_content or json.loads(res.content[0].text)

        return asyncio.run(go())

    req = payloads()["propose_structures"]
    proposal = call("propose_structures", req)
    assert proposal["status"] == "ok"
    picked = [c["id"] for c in proposal["candidates"]][-2:]
    expanded = call("propose_structures", {**req, "options": {**req["options"], "expand": picked}})
    skeletons = [c["skeleton"] for c in expanded["candidates"] if c["id"] in picked]
    filled = [fixture_fill(s) for s in skeletons]
    compared = call(
        "compare_arrangements",
        {
            "candidates": [f["engagement"] for f in filled],
            "scenarios": filled[0]["scenarios"],
            "cost_policy": "reference",
        },
    )
    assert compared["status"] == "ok"
    assert all(c["valid"] and c["feasible"] for c in compared["candidates"])
    chosen = [c for c in expanded["candidates"] if c["id"] in picked]
    for f, c in zip(filled, chosen, strict=True):
        results = []
        for sid in ("expected", "low"):
            sc = next(s for s in f["scenarios"] if s["id"] == sid)
            r = call(
                "calculate_periods",
                {"engagement": f["engagement"], "scenario": sc, "cost_policy": "reference"},
            )
            results.append({"scenario_id": sid, **r})
        exposure = call(
            "derive_risk_exposure",
            {
                "results": results,
                "base_scenario_id": "expected",
                "tolerance_policy": {"provider_relative": "0.05", "client_relative": "0.05"},
            },
        )
        assert (
            exposure["deviations"][0]["derived_bearer"] == c["risk_allocation"]["volume_shortfall"]
        )
