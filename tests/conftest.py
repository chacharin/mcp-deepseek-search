"""Shared fixtures. No test calls the real DeepSeek API: deepseek.transport is replaced by an httpx.MockTransport."""
from __future__ import annotations

import importlib
import json

import httpx
import pytest

TEST_KEY = "sk-test-key-not-real-0123"
ENV_KEYS = ["DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL", "SEARCH_TIMEOUT_SECONDS", "FETCH_TIMEOUT_SECONDS", "RETRIES",
            "DEFAULT_COUNT", "SUMMARY_CHARS", "CONTENT_CHARS", "FETCH_MAX_CHARS", "LOCALIZATION_IP",
            "PRICE_PER_REQUEST_USD", "ENABLE_DEEPSEEK_SEARCH", "ENABLE_DEEPSEEK_FETCH", "MCP_HOST", "MCP_PORT",
            "MCP_AUTH_TOKEN", "USAGE_DIR", "USAGE_LOG"]

RESULTS = [
    {"title": "รัฐบาลไทย \\| นโยบาย AI", "url": "https://www.thaigov.go.th/th/news/1", "site_name": "Royal Thai Government",
     "date": "2026-07-20T16:00:00+00:00", "authority": 4, "rerank_score": 2.35, "snippet": "สั้น",
     "summary": "## ครม. เห็นชอบ\nนโยบาย AI ปี 2026", "content": "เนื้อหาเต็มของหน้า " * 50},
    {"title": "บทความทั่วไป", "url": "https://blog.example.com/a", "site_name": None, "date": None,
     "authority": -1, "rerank_score": 0.8, "snippet": "ย่อ", "summary": "", "content": ""},
]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch, tmp_path):
    """Every test starts from the code defaults, with a key and a throw-away usage log, and without retry waits."""
    for k in ENV_KEYS:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("DEEPSEEK_API_KEY", TEST_KEY)
    monkeypatch.setenv("USAGE_DIR", str(tmp_path / "usage"))
    from app import deepseek

    async def no_sleep(_):
        return None
    monkeypatch.setattr(deepseek.asyncio, "sleep", no_sleep)


@pytest.fixture
def fake_api(monkeypatch):
    """fake_api(handler): handler(httpx.Request) -> httpx.Response; returns the list of requests seen."""
    from app import deepseek

    def install(handler):
        seen = []

        def record(request):
            seen.append(request)
            return handler(request)

        monkeypatch.setattr(deepseek, "transport", httpx.MockTransport(record))
        return seen

    return install


def body(request) -> dict:
    return json.loads(request.content)


@pytest.fixture
def load_server(monkeypatch):
    """load_server(**env): (re)import app.server with these environment variables."""
    def load(**env):
        for k, v in env.items():
            monkeypatch.setenv(k, v)
        import app.server
        return importlib.reload(app.server)

    return load
