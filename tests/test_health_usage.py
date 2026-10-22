"""/health (never calls DeepSeek) and the usage log (cost per successful request, no query text)."""
import json

import httpx
from starlette.testclient import TestClient

from tests.conftest import RESULTS
from tests.mcp_client import call


def test_health_reports_key_and_switches(load_server):
    h = TestClient(load_server().app).get("/health").json()
    assert h["ok"] and h["key_configured"] and h["tools"] == {"deepseek_search": True, "deepseek_fetch": True}
    h = TestClient(load_server(DEEPSEEK_API_KEY="sk-xxxxxxxxxxxxxxxx", ENABLE_DEEPSEEK_FETCH="maybe").app).get("/health").json()
    assert not h["ok"] and h["tools"]["deepseek_fetch"] is True
    assert any("example value" in p for p in h["problems"]) and any("maybe" in p for p in h["problems"])


def records(server):
    return TestClient(server.app).get("/usage").json()["records"]


def test_search_is_logged_and_priced(load_server, fake_api):
    server = load_server()
    fake_api(lambda r: httpx.Response(200, json={"results": RESULTS}))
    call(server, "deepseek_search", query="นโยบายลับ", count=7)
    api, tool = records(server)
    assert api["kind"] == "search_call" and api["tool"] == "deepseek_search" and api["cost_usd"] == 0.00075
    assert api["detail"]["billable"] and api["detail"]["results"] == 2 and api["detail"]["http_status"] == 200
    assert tool["kind"] == "mcp_tool" and tool["request_id"] == api["request_id"] and tool["cost_usd"] == 0.00075
    assert tool["detail"]["count"] == 7 and tool["detail"]["query_chars"] == len("นโยบายลับ")
    assert "นโยบายลับ" not in json.dumps([api, tool], ensure_ascii=False)               # no query text


def test_empty_results_and_failures_cost_nothing(load_server, fake_api):
    server = load_server(RETRIES="0")
    fake_api(lambda r: httpx.Response(200, json={"results": []}))
    call(server, "deepseek_search", query="ไม่มีผล")
    fake_api(lambda r: httpx.Response(404, json={}))
    call(server, "deepseek_fetch", url="https://example.com/x")
    recs = records(server)
    assert [r["cost_usd"] for r in recs] == [0.0, 0.0, 0.0, 0.0]
    assert recs[2]["kind"] == "fetch_call" and recs[2]["status"] == "error" and recs[3]["status"] == "error"


def test_rejected_input_logs_only_the_tool_call(load_server, fake_api):
    server = load_server()
    seen = fake_api(lambda r: httpx.Response(200, json={"results": RESULTS}))
    call(server, "deepseek_search", query="")
    (rec,) = records(server)
    assert rec["kind"] == "mcp_tool" and rec["error"] == "empty_query" and not seen


def test_usage_log_can_be_switched_off(load_server, fake_api):
    server = load_server(USAGE_LOG="false")
    fake_api(lambda r: httpx.Response(200, json={"results": RESULTS}))
    call(server, "deepseek_search", query="AI")
    assert records(server) == []
