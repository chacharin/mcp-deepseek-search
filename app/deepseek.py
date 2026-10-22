"""Calls to the DeepSeek Search and Fetch APIs (https://api-docs.deepseek.com/guides/search/) and the text
returned to the agent.

  POST /v1/tools/search  {query, count, ori_question, localization, need_content} -> {"results": [...]}
  POST /v1/tools/fetch   {url}                                                   -> {"title", "content"}

Both are billed per successful request (a non-empty search, a fetch with content), not by tokens.
HTTP 408, 429 and 5xx are retried with a short back-off, as the API documentation asks; every other error
comes back as a short explanation for the agent. Nothing here raises to the MCP layer.
"""
from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

import httpx

from app.config import Settings

# tests replace this with an httpx.MockTransport; None = real network
transport: httpx.AsyncBaseTransport | None = None

RETRY_STATUS = {408, 429, 500, 502, 503, 504}
MAX_QUERY_CHARS = 128      # the Search API limit, operators included
HINTS = {
    400: "the request was refused as invalid",
    401: "the DeepSeek API key is missing or wrong - check DEEPSEEK_API_KEY in .env",
    402: "the DeepSeek account has no balance left - top it up at platform.deepseek.com",
    403: "DeepSeek's security policy refused to fetch this URL",
    404: "the page could not be fetched (blocked by the site, unavailable, or no readable content)",
    408: "the request timed out at DeepSeek",
    413: "the request is too large",
    429: "too many requests per second (rate limit) - try again shortly",
    504: "a site behind DeepSeek timed out",
}
_ESCAPED = re.compile(r"\\([\\`*_{}\[\]()#+\-.!:,|>~=\"'/])")   # Markdown escapes the APIs add everywhere
RECENCY_DAYS = {"day": 1, "week": 7, "month": 31, "year": 366}


@dataclass
class Call:
    """One HTTP call to DeepSeek, for the usage log."""
    endpoint: str
    started_at: float
    ended_at: float = 0.0
    status: int = 0
    attempts: int = 0
    error: str | None = None
    billable: bool = False
    response_chars: int = 0
    extra: dict = field(default_factory=dict)


def unescape(text: str) -> str:
    return _ESCAPED.sub(r"\1", text or "")


def build_query(query: str, sites=(), exclude_sites=(), language: str = "", after: str = "", before: str = "",
                recency: str = "", today: date | None = None) -> str:
    """The query with the Search API operators (site:, -site:, lang:, after:, before:) appended."""
    parts = [query.strip()]
    sites = [s.strip() for s in sites or [] if s and s.strip()]
    if sites:
        parts.append(" OR ".join(f"site:{s}" for s in sites))
    parts += [f"-site:{s.strip()}" for s in exclude_sites or [] if s and s.strip()]
    if language.strip():
        parts.append("lang:" + ",".join(x.strip() for x in language.split(",") if x.strip()))
    if recency and not after:
        after = ((today or date.today()) - timedelta(days=RECENCY_DAYS[recency])).isoformat()
    if after.strip():
        parts.append(f"after:{after.strip()}")
    if before.strip():
        parts.append(f"before:{before.strip()}")
    return " ".join(p for p in parts if p)


def _error_text(status: int, body: Any) -> str:
    msg = ""
    if isinstance(body, dict):
        msg = str((body.get("error") or {}).get("message") or "")[:200]
    hint = HINTS.get(status) or ("a DeepSeek server error" if status >= 500 else "")
    return f"HTTP {status}" + (f" - {hint}" if hint else "") + (f" ({msg})" if msg else "")


async def _post(s: Settings, path: str, body: dict, timeout: float, call: Call) -> Any:
    """POST with retries on 408/429/5xx and network errors. Returns the JSON body, or None (call.error set)."""
    headers = {"Authorization": f"Bearer {s.api_key}", "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=timeout, transport=transport) as c:
        for attempt in range(1, s.retries + 2):
            call.attempts = attempt
            try:
                r = await c.post(f"{s.base_url}{path}", json=body, headers=headers)
            except httpx.HTTPError as e:
                call.status, call.error = 0, f"cannot reach DeepSeek ({type(e).__name__})"
                if attempt <= s.retries:
                    await asyncio.sleep(1.5 * attempt)
                    continue
                return None
            call.status = r.status_code
            call.response_chars = len(r.content)
            try:
                data = r.json()
            except ValueError:
                data = None
            if r.status_code == 200:
                call.error = None
                return data
            call.error = _error_text(r.status_code, data)
            if r.status_code in RETRY_STATUS and attempt <= s.retries:
                await asyncio.sleep(1.5 * attempt)
                continue
            return None
    return None


async def search(s: Settings, query: str, count: int, question: str, with_content: bool) -> tuple[list | None, Call]:
    call = Call("search", time.time())
    body: dict = {"query": query, "count": count, "need_content": with_content}
    if question.strip():
        body["ori_question"] = question.strip()[:128]
    if s.localization_ip:
        body["localization"] = s.localization_ip
    data = await _post(s, "/v1/tools/search", body, s.search_timeout, call)
    call.ended_at = time.time()
    results = data.get("results") if isinstance(data, dict) else None
    if results is not None and not isinstance(results, list):
        results, call.error = None, "unexpected answer from the Search API"
    call.billable = bool(results)
    return results, call


async def fetch(s: Settings, url: str) -> tuple[dict | None, Call]:
    call = Call("fetch", time.time())
    data = await _post(s, "/v1/tools/fetch", {"url": url}, s.fetch_timeout, call)
    call.ended_at = time.time()
    if data is not None and not isinstance(data, dict):
        data, call.error = None, "unexpected answer from the Fetch API"
    call.billable = bool(data and data.get("content"))
    return data, call


def _drop_title_heading(summary: str, title: str) -> str:
    """Search summaries often open with the title again as a Markdown heading - drop it to save tokens."""
    first, _, rest = summary.lstrip().partition("\n")
    head = first.lstrip("#").strip()
    if first.startswith("#") and head and (head in title or title in head):
        return rest.lstrip()
    return summary


def _clip(text: str, limit: int) -> str:
    text = " ".join(unescape(text).split()) if limit < 2000 else unescape(text).strip()
    return text if len(text) <= limit else text[:limit].rstrip() + " …"


def format_results(results: list, query: str, min_score: float, s: Settings, with_content: bool) -> tuple[str, dict]:
    """The text the agent reads, and counts for the usage log."""
    kept = [r for r in results if isinstance(r, dict) and float(r.get("rerank_score") or 0) >= min_score]
    stats = {"results": len(results), "kept": len(kept)}
    if not kept:
        why = f" with relevance score >= {min_score}" if results and min_score > 0 else ""
        return f"No search results{why} for: {query}", stats
    lines = [f"Found {len(kept)} search results for: {query}", ""]
    for i, r in enumerate(kept, 1):
        meta = []
        if r.get("site_name"):
            meta.append(str(r["site_name"]))
        if r.get("date"):
            meta.append("published " + str(r["date"])[:10])
        if isinstance(r.get("authority"), int) and r["authority"] >= 0:
            meta.append(f"authority {r['authority']}/4")
        if r.get("rerank_score") is not None:
            meta.append(f"relevance {float(r['rerank_score']):.2f}/3")
        lines.append(f"[{i}] {unescape(str(r.get('title') or '(no title)'))}")
        lines.append(f"URL: {r.get('url', '')}")
        if meta:
            lines.append(" · ".join(meta))
        summary = _drop_title_heading(unescape(r.get("summary") or r.get("snippet") or ""),
                                      unescape(str(r.get("title") or "")))
        if summary:
            lines.append(_clip(summary, s.summary_chars))
        if with_content and r.get("content"):
            lines.append("Content: " + _clip(r["content"], s.content_chars))
        lines.append("")
    return "\n".join(lines).rstrip(), stats


def format_page(data: dict, url: str, start: int, max_chars: int) -> tuple[str, dict]:
    content = unescape(data.get("content") or "")
    total = len(content)
    start = max(0, min(start, total))
    end = min(total, start + max_chars)
    head = [f"Title: {unescape(data.get('title') or '') or '(no title)'}", f"URL: {url}"]
    if total > max_chars or start:
        more = f" - call again with start={end} for the rest" if end < total else ""
        head.append(f"Showing characters {start}-{end} of {total}{more}")
    return "\n".join(head) + "\n\n" + content[start:end], {"content_chars": total, "returned_chars": end - start}
