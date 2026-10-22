"""The two tools as an agent calls them, against a fake DeepSeek API."""
from datetime import date

import httpx
from starlette.testclient import TestClient

from tests.conftest import RESULTS, TEST_KEY, body
from tests.mcp_client import call, rpc, tools
from app import deepseek


def search_ok(request):
    return httpx.Response(200, json={"results": RESULTS})


def test_tools_and_schema(load_server):
    t = tools(load_server())
    assert set(t) == {"deepseek_search", "deepseek_fetch"}
    props = t["deepseek_search"]["inputSchema"]["properties"]
    assert t["deepseek_search"]["inputSchema"]["required"] == ["query"]
    assert props["count"]["maximum"] == 50 and props["recency"]["enum"] == ["", "day", "week", "month", "year"]
    assert t["deepseek_fetch"]["inputSchema"]["required"] == ["url"]


def test_switches_remove_tools(load_server):
    assert set(tools(load_server(ENABLE_DEEPSEEK_FETCH="false"))) == {"deepseek_search"}
    assert set(tools(load_server(ENABLE_DEEPSEEK_FETCH="true", ENABLE_DEEPSEEK_SEARCH="OFF"))) == {"deepseek_fetch"}


def test_search_sends_key_filters_and_question(load_server, fake_api):
    server = load_server()
    seen = fake_api(search_ok)
    text = call(server, "deepseek_search", query="นโยบาย AI", count=5, sites=["thaigov.go.th", "mdes.go.th"],
                exclude_sites=["pantip.com"], language="th,en", after="2026-01-01", question="ไทยมีนโยบาย AI อะไร")
    req = seen[0]
    assert req.url.path == "/v1/tools/search" and req.headers["authorization"] == f"Bearer {TEST_KEY}"
    b = body(req)
    assert b["query"] == ("นโยบาย AI site:thaigov.go.th OR site:mdes.go.th -site:pantip.com lang:th,en "
                          "after:2026-01-01")
    assert b["count"] == 5 and b["ori_question"] == "ไทยมีนโยบาย AI อะไร" and b["need_content"] is False
    assert "Found 2 search results" in text and "[1] รัฐบาลไทย | นโยบาย AI" in text   # \| unescaped
    assert "Royal Thai Government · published 2026-07-20 · authority 4/4 · relevance 2.35/3" in text
    assert "## ครม. เห็นชอบ นโยบาย AI ปี 2026" in text                                  # summary on one line
    assert "Content:" not in text


def test_title_heading_dropped_and_escapes_removed():
    assert deepseek._drop_title_heading("## รายงาน AI\nเนื้อหา", "รัฐบาลไทย | รายงาน AI") == "เนื้อหา"
    assert deepseek._drop_title_heading("## หัวข้ออื่น\nเนื้อหา", "รายงาน AI").startswith("## หัวข้ออื่น")
    assert deepseek.unescape(r'\"March\" 13°N \/ 100°E') == '"March" 13°N / 100°E'


def test_recency_becomes_after():
    q = deepseek.build_query("ข่าว", recency="week", today=date(2026, 10, 22))
    assert q == "ข่าว after:2026-10-15"
    assert deepseek.build_query("ข่าว", recency="week", after="2026-01-01") == "ข่าว after:2026-01-01"


def test_min_score_and_content(load_server, fake_api):
    server = load_server(CONTENT_CHARS="500")
    fake_api(search_ok)
    text = call(server, "deepseek_search", query="AI", min_score=1.5, with_content=True)
    assert "Found 1 search results" in text and "blog.example.com" not in text
    assert "Content: เนื้อหาเต็มของหน้า" in text and text.endswith("…")
    assert "No search results with relevance score >= 3.0" in call(server, "deepseek_search", query="AI", min_score=3)


def test_query_limits(load_server, fake_api):
    server = load_server()
    seen = fake_api(search_ok)
    assert call(server, "deepseek_search", query="  ").startswith("[query is empty")
    long = call(server, "deepseek_search", query="x" * 120, sites=["example.com"])
    assert "limit is 128" in long and not seen                                             # never sent


def test_errors_are_explained_and_retried(load_server, fake_api):
    server = load_server(RETRIES="2")
    statuses = iter([429, 503, 200])
    seen = fake_api(lambda r: httpx.Response(next(statuses), json={"results": RESULTS}))
    assert "Found 2" in call(server, "deepseek_search", query="AI") and len(seen) == 3
    seen = fake_api(lambda r: httpx.Response(402, json={"error": {"message": "Insufficient Balance"}}))
    text = call(server, "deepseek_search", query="AI")
    assert "HTTP 402" in text and "top it up" in text and "Insufficient Balance" in text and len(seen) == 1
    fake_api(lambda r: httpx.Response(401, json={}))
    assert "DEEPSEEK_API_KEY" in call(server, "deepseek_search", query="AI")


def test_network_error(load_server, fake_api):
    server = load_server(RETRIES="1")

    def down(r):
        raise httpx.ConnectError("down")
    seen = fake_api(down)
    assert "cannot reach DeepSeek (ConnectError)" in call(server, "deepseek_search", query="AI") and len(seen) == 2


def test_fetch_pages_through_long_content(load_server, fake_api):
    server = load_server()
    page = "\\# หัวข้อ\n\n" + "ก" * 2500
    seen = fake_api(lambda r: httpx.Response(200, json={"title": "หน้า \\- ทดสอบ", "content": page}))
    first = call(server, "deepseek_fetch", url="https://example.com/a", max_chars=1000)
    assert body(seen[0]) == {"url": "https://example.com/a"} and seen[0].url.path == "/v1/tools/fetch"
    assert "Title: หน้า - ทดสอบ" in first and first.split("\n\n", 1)[1].startswith("# หัวข้อ")
    assert "Showing characters 0-1000 of 2510 - call again with start=1000" in first
    last = call(server, "deepseek_fetch", url="https://example.com/a", max_chars=2000, start=1000)
    assert "Showing characters 1000-2510 of 2510" in last and "call again" not in last


def test_fetch_refusals(load_server, fake_api):
    server = load_server()
    seen = fake_api(lambda r: httpx.Response(404, json={"error": {"message": "failed to fetch URL"}}))
    assert call(server, "deepseek_fetch", url="ftp://x").startswith("[url must be")
    assert not seen
    assert "could not be fetched" in call(server, "deepseek_fetch", url="https://example.com/blocked")


def test_auth_token_protects_mcp_and_usage(load_server):
    server = load_server(MCP_AUTH_TOKEN="t0ken")
    c = TestClient(server.app)
    assert c.get("/usage").status_code == 401
    assert rpc(c, "tools/list").status_code == 401
    assert c.get("/usage", headers={"Authorization": "Bearer t0ken"}).status_code == 200
    assert c.get("/health").status_code == 200                                            # health stays open
