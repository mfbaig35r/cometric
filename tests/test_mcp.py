"""T-035: MCP tools, resources, prompts, and the stateless HTTP transport."""

import asyncio
import json

import pytest

pytest.importorskip("mcp")

from starlette.testclient import TestClient  # noqa: E402

from cometric.mcp.server import build_server, http_app  # noqa: E402


def run(coro):
    return asyncio.run(coro)


def _structured(result):
    if getattr(result, "structured_content", None):
        return result.structured_content
    return json.loads(result.content[0].text)


def test_tools_compute_through_the_server(spec_example):
    s = build_server()
    out = _structured(
        run(
            s.call_tool(
                "calculate_periods",
                {
                    "engagement": spec_example["engagement"],
                    "scenario": spec_example["scenarios"][0],
                },
            )
        )
    )
    assert out["term"]["contractual_fee"] == "124000"
    v = _structured(
        run(s.call_tool("validate_engagement", {"engagement": {"schema_version": "0.2"}}))
    )
    assert not v["valid"] and all(e["path"].startswith("/engagement") for e in v["errors"])
    tpl = _structured(run(s.call_tool("get_template", {"template_id": "base_plus_overage"})))
    assert "examples" in tpl
    ev = _structured(run(s.call_tool("list_applicable_evidence", {"claim_or_concept": "PM-011"})))
    assert ev["concept"]["id"] == "PM-011"


def test_every_resource_resolves():
    s = build_server()
    uris = [
        "cometric://glossary",
        "cometric://schema/engagement",
        "cometric://schema/search_spec",
        "cometric://templates/dedicated_team",
        "cometric://examples/case_a",
        "cometric://examples/spec_example",
    ]
    for pack in ("base", "alsp"):
        uris += [f"cometric://packs/{pack}/rules", f"cometric://packs/{pack}/coverage"]
    uris += [
        "cometric://packs/base/concepts/pricing_models",
        "cometric://packs/alsp/concepts/service_categories",
    ]
    for uri in uris:
        contents = list(run(s.read_resource(uri)))
        assert contents and json.loads(contents[0].content), uri


def test_every_prompt_renders():
    s = build_server()
    for p in run(s.list_prompts()):
        args = {a.name: "example" for a in (p.arguments or [])}
        r = run(s.get_prompt(p.name, args))
        text = r.messages[0].content.text
        assert "example" in text
        assert "$" not in text  # prompts carry no numbers or benchmarks


def test_http_transport_is_stateless_and_rejects_get():
    with TestClient(http_app(token=""), base_url="http://localhost:8765") as client:
        assert client.get("/mcp").status_code == 405
        body = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "t", "version": "0"},
            },
        }
        headers = {
            "accept": "application/json, text/event-stream",
            "content-type": "application/json",
        }
        r = client.post("/mcp", json=body, headers=headers)
        assert r.status_code == 200, r.text
        assert "mcp-session-id" not in {k.lower() for k in r.headers}
        call = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
        r2 = client.post(
            "/mcp", json=call, headers={**headers, "mcp-protocol-version": "2025-06-18"}
        )
        assert r2.status_code == 200, r2.text
        assert "calculate_periods" in r2.text


def test_http_bearer_token():
    with TestClient(http_app(token="secret"), base_url="http://localhost:8765") as client:
        body = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
        assert client.post("/mcp", json=body).status_code == 401


def test_file_paths_confined_to_allowed_root(monkeypatch, tmp_path):
    from cometric.mcp.server import _load

    (tmp_path / "e.json").write_text('{"engagement": {"schema_version": "0.2"}}')
    monkeypatch.setenv("COMETRIC_ALLOWED_ROOT", str(tmp_path))
    assert _load("e.json") == {"schema_version": "0.2"}
    with pytest.raises(ValueError):
        _load("../outside.json")
    with pytest.raises(ValueError):
        _load("e.json", transport_http=True)
    monkeypatch.delenv("COMETRIC_ALLOWED_ROOT")
    with pytest.raises(ValueError):
        _load("e.json")
