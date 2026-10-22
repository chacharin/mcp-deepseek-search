"""mcp-deepseek-search: MCP server over streamable HTTP (http://<host>:<port>/mcp) + GET /health + GET /usage.

Tools (each switched on or off with ENABLE_DEEPSEEK_SEARCH / ENABLE_DEEPSEEK_FETCH, default on)
  deepseek_search(query, count, sites, exclude_sites, language, recency, after, before, min_score,
                  with_content, question)   web search: titles, URLs, dates, authority, relevance, summaries
  deepseek_fetch(url, max_chars, start)     a web page as Markdown, read in parts when it is long

GET /usage?since=&until=&limit=  one record per DeepSeek call and per tool call (no query text or content),
                                 in the harness-usage/1 schema; needs MCP_AUTH_TOKEN like /mcp when one is set
The DeepSeek key stays in this process: agents call this server, never DeepSeek itself.
"""
import contextlib
import hmac
import sys
import time
import uuid
from typing import Annotated, Literal

import uvicorn
from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from pydantic import Field
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

from app import deepseek
from app.config import Settings, key_state
from app.usage import SCHEMA, UsageLog

S = Settings.from_env()
VERSION = "0.1.0"
USAGE = UsageLog("mcp-deepseek-search", VERSION, S.usage_dir, S.usage_log)
for _p in S.switch_problems:
    print(f"WARNING: {_p}", file=sys.stderr, flush=True)
if key_state(S.api_key) != "set":
    print("WARNING: DEEPSEEK_API_KEY is not set (or is still the example value) - every call will fail",
          file=sys.stderr, flush=True)

mcp = MCPServer(
    name="deepseek-search",
    version=VERSION,
    instructions=("ค้นหาเว็บและอ่านหน้าเว็บผ่าน DeepSeek Search & Fetch API "
                  "ผลค้นหามีชื่อ URL วันที่เผยแพร่ ระดับความน่าเชื่อถือ คะแนนความเกี่ยวข้อง และสรุปเนื้อหา"),
)


# ------------------------------------------------------------------ usage log
def log_calls(tool: str, t0: float, calls: list, status: str, error: str | None, detail: dict) -> None:
    """One record per DeepSeek call (search_call / fetch_call, priced per successful request), then one for
    the tool call as a whole, sharing a request_id."""
    rid = uuid.uuid4().hex[:16]
    for c in calls:
        USAGE.write({"kind": f"{c.endpoint}_call", "tool": tool, "request_id": rid, "provider": "deepseek",
                     "endpoint_host": S.base_url.split("://", 1)[-1], "started_at": round(c.started_at, 3),
                     "ended_at": round(c.ended_at, 3), "duration_s": round(c.ended_at - c.started_at, 3),
                     "cost_usd": S.price_per_request if c.billable else 0.0, "tokens_estimated": None,
                     "status": "ok" if not c.error else "error", "error": c.error,
                     "detail": {"http_status": c.status, "attempts": c.attempts, "billable": c.billable,
                                "response_chars": c.response_chars, **c.extra}})
    t1 = time.time()
    cost = round(sum(S.price_per_request for c in calls if c.billable), 6)
    USAGE.write({"kind": "mcp_tool", "tool": tool, "request_id": rid, "provider": "deepseek",
                 "started_at": round(t0, 3), "ended_at": round(t1, 3), "duration_s": round(t1 - t0, 3),
                 "cost_usd": cost, "status": status, "error": error, "detail": {"api_calls": len(calls), **detail}})


# ------------------------------------------------------------------ tools
SEARCH_DESCRIPTION = (
    "Search the web (DeepSeek Search). ค้นหาเว็บ แล้วส่งรายการผลลัพธ์กลับมา แต่ละรายการมีชื่อ URL วันที่เผยแพร่ "
    "ระดับความน่าเชื่อถือของแหล่ง (authority 0–4, ตั้งแต่ 3 คือแหล่งน่าเชื่อถือสูง) คะแนนความเกี่ยวข้อง "
    "(relevance 0–3, ตั้งแต่ 1.5 คือผลที่ดี) และสรุปเนื้อหา ไม่มี AI สรุปคำตอบให้ ให้อ่านผลแล้วสรุปเอง "
    "หากต้องการเนื้อหาเต็มของหน้าใด ให้ใช้ deepseek_fetch กับ URL นั้น"
)
FETCH_DESCRIPTION = (
    "Read a web page (DeepSeek Fetch). อ่านเนื้อหาหน้าเว็บเป็น Markdown เพื่อยืนยันข้อเท็จจริงหรืออ่านรายละเอียดจากแหล่งที่ค้นเจอ "
    "หน้าที่ยาวจะแสดงทีละช่วง และบอกค่า start สำหรับอ่านช่วงถัดไป บางไซต์ไม่อนุญาตให้ดึงเนื้อหา"
)


async def deepseek_search(
    query: Annotated[str, Field(description=(
        "คำค้น ใช้ภาษาของแหล่งที่ต้องการ ใส่ operator ได้ เช่น \"วลีตรงตัว\" หรือ -คำที่ไม่ต้องการ "
        "รวมตัวกรองด้านล่างแล้วต้องยาวไม่เกิน 128 ตัวอักษร"))],
    count: Annotated[int, Field(description="จำนวนผลลัพธ์ 1–50", ge=1, le=50)] = S.default_count,
    sites: Annotated[list[str], Field(description="ค้นเฉพาะเว็บไซต์เหล่านี้ เช่น [\"thaigov.go.th\"]")] = [],
    exclude_sites: Annotated[list[str], Field(description="ตัดเว็บไซต์เหล่านี้ออกจากผลลัพธ์")] = [],
    language: Annotated[str, Field(description="จำกัดภาษาของผลลัพธ์ เช่น \"th\" หรือ \"th,en\"")] = "",
    recency: Annotated[Literal["", "day", "week", "month", "year"], Field(
        description="จำกัดเฉพาะที่เผยแพร่ภายในช่วงล่าสุด: day, week, month, year")] = "",
    after: Annotated[str, Field(description="เผยแพร่หลังวันที่ (YYYY หรือ YYYY-MM-DD)")] = "",
    before: Annotated[str, Field(description="เผยแพร่ก่อนวันที่ (YYYY หรือ YYYY-MM-DD)")] = "",
    min_score: Annotated[float, Field(description="ตัดผลที่คะแนนความเกี่ยวข้องต่ำกว่านี้ (0–3)", ge=0, le=3)] = 0,
    with_content: Annotated[bool, Field(description=(
        "true = แนบเนื้อหาของแต่ละหน้า (ตัดตามความยาวที่กำหนด) ใช้ token มากขึ้น"))] = False,
    question: Annotated[str, Field(description="คำถามเดิมของผู้ใช้ ช่วยให้ค้นได้ตรงขึ้น (ไม่บังคับ)")] = "",
) -> str:
    t0 = time.time()
    q = (query or "").strip()
    full = deepseek.build_query(q, sites, exclude_sites, language, after, before, recency) if q else ""
    detail = {"count": count, "query_chars": len(q), "filters": {
        "sites": len(sites), "exclude_sites": len(exclude_sites), "language": language or None,
        "recency": recency or None, "after": bool(after), "before": bool(before), "min_score": min_score},
        "with_content": with_content}
    if not q:
        log_calls("deepseek_search", t0, [], "error", "empty_query", detail)
        return "[query is empty - say what to search for]"
    if len(full) > deepseek.MAX_QUERY_CHARS:
        log_calls("deepseek_search", t0, [], "error", "query_too_long", detail)
        return (f"[the query with its filters is {len(full)} characters - the limit is {deepseek.MAX_QUERY_CHARS}; "
                f"shorten the query or use fewer sites]: {full}")
    results, call = await deepseek.search(S, full, count, question, with_content)
    if results is None:
        log_calls("deepseek_search", t0, [call], "error", call.error, detail)
        return f"[DeepSeek search failed: {call.error}]"
    text, stats = deepseek.format_results(results, full, min_score, S, with_content)
    call.extra.update(stats)
    log_calls("deepseek_search", t0, [call], "ok", None, {**detail, **stats, "result_chars": len(text)})
    return text


async def deepseek_fetch(
    url: Annotated[str, Field(description="URL ของหน้าเว็บ (http หรือ https)")],
    max_chars: Annotated[int, Field(description="จำนวนตัวอักษรสูงสุดที่ส่งกลับในครั้งนี้", ge=1000, le=100000)]
    = S.fetch_max_chars,
    start: Annotated[int, Field(description="อ่านต่อจากตัวอักษรที่เท่าไร (ใช้เมื่อหน้ายาว)", ge=0)] = 0,
) -> str:
    t0 = time.time()
    url = (url or "").strip()
    detail = {"max_chars": max_chars, "start": start}
    if not url.lower().startswith(("http://", "https://")) or len(url) > 8192:
        log_calls("deepseek_fetch", t0, [], "error", "bad_url", detail)
        return "[url must be an http:// or https:// address of at most 8192 characters]"
    data, call = await deepseek.fetch(S, url)
    if data is None:
        log_calls("deepseek_fetch", t0, [call], "error", call.error, detail)
        return f"[DeepSeek fetch failed: {call.error}]"
    text, stats = deepseek.format_page(data, url, start, max_chars)
    call.extra.update(stats)
    log_calls("deepseek_fetch", t0, [call], "ok", None, {**detail, **stats})
    return text


# every tool returns text; structured_output=False stops the SDK sending it a second time as structuredContent
if S.enabled["deepseek_search"]:
    mcp.add_tool(deepseek_search, description=SEARCH_DESCRIPTION, structured_output=False,
                 annotations=ToolAnnotations(read_only_hint=True, open_world_hint=True))
if S.enabled["deepseek_fetch"]:
    mcp.add_tool(deepseek_fetch, description=FETCH_DESCRIPTION, structured_output=False,
                 annotations=ToolAnnotations(read_only_hint=True, open_world_hint=True))


# ------------------------------------------------------------------ http app
def health_report() -> dict:
    """ok = the key is set and every switch was read. Never calls DeepSeek (that would cost money)."""
    state = key_state(S.api_key)
    problems = list(S.switch_problems)
    if state == "empty":
        problems.append("DEEPSEEK_API_KEY is empty - put your key from platform.deepseek.com in .env")
    elif state == "placeholder":
        problems.append("DEEPSEEK_API_KEY is still the example value from .env.example - put your real key in .env")
    if S.usage_log and not USAGE.writable():
        problems.append(f"the usage log folder {S.usage_dir} is not writable - usage records are not kept")
    return {"ok": not problems, "version": VERSION, "base_url": S.base_url, "key_configured": state == "set",
            "tools": S.enabled, "localization_ip": bool(S.localization_ip),
            "usage_log": {"enabled": S.usage_log, "dir": S.usage_dir, "writable": USAGE.writable(),
                          "last_error": USAGE.error},
            "auth": bool(S.auth_token), "problems": problems}


async def health(_: Request) -> JSONResponse:
    return JSONResponse(health_report())


def _qf(request: Request, name: str) -> float | None:
    v = request.query_params.get(name)
    try:
        return float(v) if v not in (None, "") else None
    except ValueError:
        return None


async def usage(request: Request) -> JSONResponse:
    """The usage log: ?since=<epoch s>&until=<epoch s>&limit=<n> (default: everything kept, newest 50000)."""
    limit = int(_qf(request, "limit") or 50000)
    return JSONResponse({"schema": SCHEMA, "environment": USAGE.env,
                         "records": USAGE.read(_qf(request, "since"), _qf(request, "until"), max(1, limit))})


class BearerAuth:
    def __init__(self, app, token: str):
        self.app, self.token = app, token

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and self.token and scope["path"].startswith(("/mcp", "/usage")):
            got = dict(scope.get("headers") or []).get(b"authorization", b"").decode()
            if not hmac.compare_digest(got, f"Bearer {self.token}"):
                await JSONResponse({"error": "unauthorized"}, status_code=401)(scope, receive, send)
                return
        await self.app(scope, receive, send)


mcp_app = mcp.streamable_http_app(
    streamable_http_path="/mcp", stateless_http=True, host=S.host,
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)


@contextlib.asynccontextmanager
async def lifespan(app):
    async with mcp_app.router.lifespan_context(app):
        yield


app = BearerAuth(Starlette(routes=[Route("/health", health), Route("/usage", usage), Mount("/", app=mcp_app)],
                           lifespan=lifespan), S.auth_token)

if __name__ == "__main__":
    uvicorn.run(app, host=S.host, port=S.port, log_level="info")
