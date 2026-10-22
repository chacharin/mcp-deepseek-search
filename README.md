# mcp-deepseek-search

**English** | [ภาษาไทย](README.th.md)

An MCP server that lets AI agents search the web and read web pages through the
[DeepSeek Search & Fetch API](https://api-docs.deepseek.com/guides/search/).
It speaks streamable HTTP (`http://<host>:8807/mcp`) and logs the time and cost of every call, so usage can be exported for research.

## Tools

| Tool | What it does | Switch in .env |
|---|---|---|
| `deepseek_search` | Web search. Each result has a title, URL, publish date, source authority (0–4), relevance score (0–3) and a summary | `ENABLE_DEEPSEEK_SEARCH` |
| `deepseek_fetch` | Reads a web page as Markdown. Long pages come back in parts, with the `start` value for the next part | `ENABLE_DEEPSEEK_FETCH` |

There is no AI-written answer: the agent reads the results and writes its own, so it stays in full control of its citations.

### `deepseek_search` parameters

| Parameter | Meaning |
|---|---|
| `query` (required) | The search terms. Operators work, e.g. `"exact phrase"` or `-unwanted` |
| `count` | Number of results, 1–50 (default `DEFAULT_COUNT`) |
| `sites` / `exclude_sites` | Search only these sites, or leave them out (becomes `site:a OR site:b` and `-site:c`) |
| `language` | Limit the result language, e.g. `th` or `th,en`. Omitted or empty (`""`) = any language, the default |
| `recency` | `day`, `week`, `month` or `year` (turned into `after:` automatically) |
| `after` / `before` | Publish date range (`YYYY` or `YYYY-MM-DD`) |
| `min_score` | Drop results with a relevance score below this (0–3) |
| `with_content` | Include each page's content (uses more tokens) |
| `question` | The user's original question; helps DeepSeek rank results |

The query with all its filters must be at most 128 characters (an API limit). A longer one is not sent to DeepSeek; the server asks the agent to shorten it.

### `deepseek_fetch` parameters

`url` (required), `max_chars` (1,000–100,000, default `FETCH_MAX_CHARS`), `start` (character offset to continue from)

## How it works

```
agent (Hermes, ...) ──MCP──▶ mcp-deepseek-search ──HTTPS──▶ api.deepseek.com/v1/tools/{search,fetch}
                                  │
                                  └── usage/*.jsonl ──GET /usage──▶ collector / research
```

- The API key stays in this server; agents never see it.
- HTTP 408, 429, 5xx and network errors are retried (`RETRIES`). Other errors come back as a short explanation, e.g. 402 = no balance left.
- Markdown escapes (`\|`, `\-`, ...) and summary headings that repeat the title are removed to save agent tokens.
- Billing is per successful request: USD 0.00075 (a search with no results or a failed fetch is free).

## Setup

You need Docker and a docker network shared with the agent.

```bash
docker network create agent_network
```

```bash
cp .env.example .env
```

Set `DEEPSEEK_API_KEY` in `.env` to a key from https://platform.deepseek.com (the account needs a balance), then run

```bash
docker compose up -d --build
```

```bash
curl http://localhost:8807/health
```

`"ok": true` means the key is set and every switch was read (health never calls DeepSeek, so it costs nothing).

## Connecting an agent

Hermes (the profile's `config.yaml`)

```yaml
mcp_servers:
  deepseek_search:
    url: http://mcp-deepseek-search:8000/mcp      # from inside agent_network
    timeout: 120
    # headers: {Authorization: "Bearer <MCP_AUTH_TOKEN>"}   # when MCP_AUTH_TOKEN is set
```

Clients outside docker use `http://localhost:8807/mcp`. To try it with MCP Inspector:

```bash
npx @modelcontextprotocol/inspector
```

Choose Transport = Streamable HTTP, URL = `http://localhost:8807/mcp`.

## Turning tools on and off

Set `ENABLE_DEEPSEEK_SEARCH` and `ENABLE_DEEPSEEK_FETCH` in `.env` to `true` or `false`
(`1/0`, `yes/no`, `on/off` also work; any other value keeps the tool on and is reported in `/health`).
A tool that is off is not listed at all, so its description costs no tokens. After a change, run `docker compose up -d` and restart the agent (or `/reload-mcp`).

## Usage data (`GET /usage`)

Every call is logged as JSONL in the `usage` volume, in the `harness-usage/1` schema (numbers only, no query text or content).

| kind | One record per | Main fields |
|---|---|---|
| `search_call` / `fetch_call` | DeepSeek API call | `duration_s`, `cost_usd`, `detail.http_status`, `attempts`, `billable`, `results`, `kept`, `content_chars` |
| `mcp_tool` | tool call | total time, total cost, filters used (counts, not values) |

Records of the same tool call share a `request_id`. Filter by time with `?since=<epoch>&until=<epoch>&limit=<n>`.
Turn logging off with `USAGE_LOG=false`.

## Configuration

Every setting is described in [.env.example](.env.example), e.g. `DEFAULT_COUNT`, `SUMMARY_CHARS`, `CONTENT_CHARS`, `FETCH_MAX_CHARS`,
`LOCALIZATION_IP` (region-aware results), `SEARCH_TIMEOUT_SECONDS`, `FETCH_TIMEOUT_SECONDS`, `RETRIES`, `PRICE_PER_REQUEST_USD`
and the port `PUBLISH_PORT` (default 8807).

## Security

- Never commit `.env` (it is in `.gitignore`).
- When the port is open to other machines (`PUBLISH_ADDR=0.0.0.0`), anyone on the network can spend your DeepSeek balance.
  Set `MCP_AUTH_TOKEN`, or use `PUBLISH_ADDR=127.0.0.1`.
- `/health` is always open and never reveals the key.

## Development

```bash
uv sync
```

```bash
uv run pytest -q
```

The tests use a fake DeepSeek API, so they cost nothing. Code layout: `app/config.py` (settings), `app/deepseek.py` (API calls and text formatting),
`app/server.py` (MCP tools, `/health`, `/usage`), `app/usage.py` (usage log).

Works with [osint-harness-profile](https://github.com/chacharin/osint-harness-profile).

## License

MIT
