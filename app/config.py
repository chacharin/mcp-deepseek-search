"""Settings from environment (.env). The API key is never returned to a caller."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

# the dummy values shipped in .env.example (sk-xxxx…, change-me) - never a real key
_PLACEHOLDER_KEY = re.compile(r"x{6,}|change-?me|your[-_ ]?(api[-_ ]?)?key", re.I)
TOOLS = ("deepseek_search", "deepseek_fetch")
_TRUE = ("true", "1", "yes", "on")
_FALSE = ("false", "0", "no", "off")


def key_state(key: str) -> str:
    """"empty", "placeholder" (still the value copied from .env.example) or "set"."""
    if not key:
        return "empty"
    return "placeholder" if _PLACEHOLDER_KEY.search(key) else "set"


def _f(name: str, default: str) -> float:
    try:
        return float(os.getenv(name, default))
    except ValueError:
        return float(default)


def _i(name: str, default: str) -> int:
    return int(_f(name, default))


def tool_switches(env=os.environ) -> tuple[dict, list[str]]:
    """ENABLE_DEEPSEEK_SEARCH / ENABLE_DEEPSEEK_FETCH: unset = on; a value that is not true/false keeps the
    tool on and is reported."""
    enabled, problems = {}, []
    for tool in TOOLS:
        name = f"ENABLE_{tool.upper()}"
        raw = (env.get(name) or "").strip().lower()
        if raw == "" or raw in _TRUE:
            enabled[tool] = True
        elif raw in _FALSE:
            enabled[tool] = False
        else:
            enabled[tool] = True
            problems.append(f"{name}={env.get(name)} is not true or false - the tool stays on")
    if not any(enabled.values()):
        problems.append("every ENABLE_DEEPSEEK_* is false - the server offers no tool")
    return enabled, problems


@dataclass(frozen=True)
class Settings:
    api_key: str = field(repr=False)
    base_url: str
    search_timeout: float
    fetch_timeout: float
    retries: int
    default_count: int
    summary_chars: int
    content_chars: int
    fetch_max_chars: int
    localization_ip: str
    price_per_request: float
    enabled: dict
    switch_problems: list
    host: str
    port: int
    auth_token: str = field(repr=False)
    usage_dir: str = "/app/usage"
    usage_log: bool = True

    @staticmethod
    def from_env() -> "Settings":
        enabled, problems = tool_switches()
        return Settings(
            api_key=os.getenv("DEEPSEEK_API_KEY", "").strip(),
            base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").strip().rstrip("/"),
            search_timeout=_f("SEARCH_TIMEOUT_SECONDS", "30"),
            fetch_timeout=_f("FETCH_TIMEOUT_SECONDS", "60"),
            retries=max(0, _i("RETRIES", "2")),
            default_count=min(50, max(1, _i("DEFAULT_COUNT", "10"))),
            summary_chars=max(100, _i("SUMMARY_CHARS", "800")),
            content_chars=max(500, _i("CONTENT_CHARS", "3000")),
            fetch_max_chars=max(1000, _i("FETCH_MAX_CHARS", "20000")),
            localization_ip=os.getenv("LOCALIZATION_IP", "").strip(),
            price_per_request=_f("PRICE_PER_REQUEST_USD", "0.00075"),
            enabled=enabled,
            switch_problems=problems,
            host=os.getenv("MCP_HOST", "0.0.0.0"),
            port=_i("MCP_PORT", "8000"),
            auth_token=os.getenv("MCP_AUTH_TOKEN", "").strip(),
            usage_dir=os.getenv("USAGE_DIR", "/app/usage").strip().rstrip("/") or "/app/usage",
            usage_log=os.getenv("USAGE_LOG", "true").strip().lower() not in _FALSE,
        )
