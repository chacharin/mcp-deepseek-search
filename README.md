# mcp-deepseek-search

**English** | [ภาษาไทย](README.th.md)

An [MCP](https://modelcontextprotocol.io) server that gives AI agents and assistants two tools: **web search** and **web page
reading**, powered by the [DeepSeek Search & Fetch API](https://api-docs.deepseek.com/guides/search/).

Any MCP client that supports streamable HTTP can use it, for example Claude Code, Claude Desktop, VS Code, Cursor or your own
agent. The server keeps your DeepSeek API key to itself and logs the time and cost of every call, so you always know what your
agent spent.

- [What you get](#what-you-get)
- [Tools](#tools)
- [How it works](#how-it-works)
- [Quick start (Docker)](#quick-start-docker)
- [Running without Docker](#running-without-docker)
- [Connecting an MCP client](#connecting-an-mcp-client)
- [Turning tools on and off](#turning-tools-on-and-off)
- [Usage and cost data](#usage-and-cost-data)
- [Configuration reference](#configuration-reference)
- [Security](#security)
- [Troubleshooting](#troubleshooting)
- [Development](#development)

## What you get

- **Search results an agent can judge.** Every result has a publish date, a source authority score (0–4) and a relevance score
  (0–3), so the agent can prefer recent, trustworthy sources and skip weak matches.
- **Search filters as parameters.** Sites to include or exclude, language, recency or a date range. The server turns them into
  DeepSeek search operators for you.
- **Pages read in parts.** Long pages come back in chunks with the offset for the next chunk, so the agent's context does not fill
  up with one page.
- **No AI-written answer.** The server returns sources, not a summary from another model. Your agent reads them and writes its
  own answer with its own citations.
- **Token savings.** Markdown escapes and summary headings that repeat the title are removed before the text reaches the agent.
- **Cost and time log.** One JSON line per call, available at `GET /usage`. It contains numbers only, never the query or the page.
- **Per-tool switches.** Turn either tool off in `.env` and it disappears from the client's tool list.

## Tools

| Tool | What it does | Switch in .env |
|---|---|---|
| `deepseek_search` | Searches the web. Each result has a title, URL, site name, publish date, authority, relevance and a summary | `ENABLE_DEEPSEEK_SEARCH` |
| `deepseek_fetch` | Reads one web page as Markdown. Long pages come back in parts | `ENABLE_DEEPSEEK_FETCH` |

### `deepseek_search`

| Parameter | Type | Default | Meaning |
|---|---|---|---|
| `query` | text | (required) | The search terms. Operators work, e.g. `"exact phrase"` or `-unwanted` |
| `count` | 1–50 | `DEFAULT_COUNT` (10) | Number of results. The price is the same for any count; more results use more agent tokens |
| `sites` | list | `[]` | Search only these sites, e.g. `["who.int", "cdc.gov"]` (becomes `site:who.int OR site:cdc.gov`) |
| `exclude_sites` | list | `[]` | Leave these sites out (becomes `-site:example.com`) |
| `language` | text | `""` (any language) | Limit the result language, e.g. `en` or `en,th`. Leave it out or empty for no limit |
| `recency` | `day` `week` `month` `year` | `""` (any time) | Only pages published within that period (turned into `after:`) |
| `after` / `before` | `YYYY` or `YYYY-MM-DD` | `""` | Publish date range. `after` wins over `recency` when both are given |
| `min_score` | 0–3 | `0` | Drop results with a relevance score below this. 1.5 and above is a good match |
| `with_content` | true / false | `false` | Include each page's content (cut to `CONTENT_CHARS`). Uses many more tokens |
| `question` | text | `""` | The user's original question. Helps DeepSeek rank results |

The query plus all its filters must fit in **128 characters** (an API limit). If it does not, the server does not call DeepSeek
(so nothing is billed) and tells the agent to shorten the query or use fewer sites.

Example of what the agent receives:

```
Found 2 search results for: renewable energy policy site:iea.org after:2026-01-01

[1] Renewables 2026 – Analysis
URL: https://www.iea.org/reports/renewables-2026
IEA · published 2026-03-14 · authority 4/4 · relevance 2.41/3
Global renewable capacity additions are set to ...

[2] ...
```

### `deepseek_fetch`

| Parameter | Type | Default | Meaning |
|---|---|---|---|
| `url` | text | (required) | An `http://` or `https://` address |
| `max_chars` | 1,000–100,000 | `FETCH_MAX_CHARS` (20,000) | The most characters returned in this call |
| `start` | number | `0` | Character offset to continue from |

When a page is longer than `max_chars`, the reply starts with
`Showing characters 0-20000 of 54210 - call again with start=20000 for the rest`. The agent calls again with that `start` to read
on. Each call is a new (billed) fetch.

Some sites refuse automated reading. The agent then gets a short explanation (HTTP 403 or 404) instead of an error.

## How it works

```
MCP client / agent ──MCP (HTTP)──▶ mcp-deepseek-search ──HTTPS──▶ api.deepseek.com/v1/tools/search
                                        │                         api.deepseek.com/v1/tools/fetch
                                        └── usage/*.jsonl ──GET /usage──▶ your spreadsheet, dashboard or research
```

1. The client calls a tool over MCP.
2. The server checks the input and builds the DeepSeek request. Filters become search operators.
3. HTTP 408, 429, 5xx and network errors are retried with a short back-off (`RETRIES`, default 2). Other errors come back to the
   agent as a short explanation, e.g. *"HTTP 402 - the DeepSeek account has no balance left"*. The server never crashes the
   client's call.
4. The answer is cleaned (Markdown escapes removed, long summaries cut) and returned as text.
5. One usage record per DeepSeek call and one per tool call are written to the log.

**Pricing** (set by DeepSeek): USD 0.00075 per *successful* request, i.e. USD 0.75 per 1,000 searches or fetches. A search with
no results or a fetch that fails is not billed. Check the current price on the DeepSeek site and update `PRICE_PER_REQUEST_USD` if it
changes. The value is only used for the cost figures in the usage log.

## Quick start (Docker)

You need [Docker](https://docs.docker.com/get-docker/) with Docker Compose, and a DeepSeek API key from
[platform.deepseek.com](https://platform.deepseek.com). The account needs a balance.

**1. Get the code**

```bash
git clone https://github.com/chacharin/mcp-deepseek-search.git
```

```bash
cd mcp-deepseek-search
```

**2. Create the docker network** (once per machine). Containers on this network, such as an agent running in Docker, reach the
server by name. Skip this step if the network already exists.

```bash
docker network create agent_network
```

**3. Create `.env` and put your key in it**

```bash
cp .env.example .env
```

Open `.env` and replace the example value of `DEEPSEEK_API_KEY` with your key. Leave the rest as it is for now.

**4. Start the server**

```bash
docker compose up -d --build
```

**5. Check it**

```bash
curl http://localhost:8807/health
```

You should see `"ok": true`. If not, `problems` says what to fix. The health check never calls DeepSeek, so it costs nothing.

The MCP endpoint is now `http://localhost:8807/mcp` on this machine, and `http://mcp-deepseek-search:8000/mcp` from other
containers on `agent_network`.

To stop the server, run `docker compose down`. The usage log is kept in the `usage` volume.

## Running without Docker

You need Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
```

Add these lines to `.env` so the server listens on port 8807 and keeps its log in the project folder:

```
MCP_PORT=8807
USAGE_DIR=./usage
```

```bash
uv run --env-file .env python -m app.server
```

## Connecting an MCP client

The server speaks **streamable HTTP**. Use the URL that your client can reach:

| Where the client runs | URL |
|---|---|
| The same machine | `http://localhost:8807/mcp` |
| Another container on `agent_network` | `http://mcp-deepseek-search:8000/mcp` |
| Another machine on your network | `http://<server-ip>:8807/mcp` (set `MCP_AUTH_TOKEN`, see [Security](#security)) |

If you set `MCP_AUTH_TOKEN`, the client must send the header `Authorization: Bearer <token>`.

**Claude Code**

```bash
claude mcp add --transport http deepseek-search http://localhost:8807/mcp
```

With a token, add `--header "Authorization: Bearer <token>"`.

**Claude Desktop** (`claude_desktop_config.json`, through the [mcp-remote](https://www.npmjs.com/package/mcp-remote) bridge;
needs Node.js)

```json
{
  "mcpServers": {
    "deepseek-search": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "http://localhost:8807/mcp"]
    }
  }
}
```

**VS Code** (`.vscode/mcp.json`)

```json
{
  "servers": {
    "deepseek-search": { "type": "http", "url": "http://localhost:8807/mcp" }
  }
}
```

**Cursor** (`~/.cursor/mcp.json`)

```json
{
  "mcpServers": {
    "deepseek-search": { "url": "http://localhost:8807/mcp" }
  }
}
```

**Hermes Agent** (`config.yaml`)

```yaml
mcp_servers:
  deepseek_search:
    url: http://mcp-deepseek-search:8000/mcp
    timeout: 120
    # headers: {Authorization: "Bearer <token>"}
```

**Other clients:** use the URL above with the streamable HTTP transport. Set the tool timeout to at least 60 seconds, since a slow
site can take that long to fetch.

**Try it without an agent** using [MCP Inspector](https://github.com/modelcontextprotocol/inspector) (needs Node.js):

```bash
npx @modelcontextprotocol/inspector
```

In the page that opens, choose Transport = *Streamable HTTP*, URL = `http://localhost:8807/mcp`, press *Connect*, then open *Tools*
and run `deepseek_search`.

**A tip for your agent's instructions.** Agents get better results when told how to use the scores, for example:
*"Search with deepseek_search. Prefer results with authority 3–4 and relevance 1.5 or more. Before quoting a fact, read the page with
deepseek_fetch. Cite every URL you use."*

## Turning tools on and off

Set either switch in `.env` to `true` or `false` (`1/0`, `yes/no` and `on/off` also work):

```
ENABLE_DEEPSEEK_SEARCH=true
ENABLE_DEEPSEEK_FETCH=false
```

A tool that is off is not in the tool list at all, so its description costs no tokens and it cannot be called. Any other value
keeps the tool on and is reported in `/health`.

Apply a change with `docker compose up -d`, then reconnect or restart the client. Clients read the tool list when they connect.

## Usage and cost data

```bash
curl http://localhost:8807/usage
```

The log is JSON Lines in the `usage` volume, one file per day, in the `harness-usage/1` schema. It holds **numbers only**: no
query text, URLs or page content.

| `kind` | One record per | Main fields |
|---|---|---|
| `search_call` / `fetch_call` | DeepSeek API call | `duration_s`, `cost_usd`, `status`, `detail.http_status`, `detail.attempts`, `detail.billable`, `detail.results`, `detail.kept`, `detail.content_chars` |
| `mcp_tool` | tool call | total time, total cost, the filters used (as counts and flags, not values) |

The records of one tool call share a `request_id`. Query parameters:

| Parameter | Meaning |
|---|---|
| `since`, `until` | Time range in Unix seconds |
| `limit` | Most records returned, default 50,000 (the newest are kept; they are listed oldest first) |

Example: today's total cost (needs Python):

```bash
curl -s "http://localhost:8807/usage?since=$(date -d today +%s)" | python -c "import json,sys; r=json.load(sys.stdin)['records']; print(sum(x['cost_usd'] for x in r if x['kind']!='mcp_tool'))"
```

Turn logging off with `USAGE_LOG=false`.

## Configuration reference

All settings live in `.env`. Each one is also explained in [.env.example](.env.example). After a change, run `docker compose up -d`.

| Variable | Default | Meaning |
|---|---|---|
| `DEEPSEEK_API_KEY` | (required) | Your DeepSeek API key |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com` | Change it to go through a company proxy |
| `SEARCH_TIMEOUT_SECONDS` | `30` | Longest wait for a search |
| `FETCH_TIMEOUT_SECONDS` | `60` | Longest wait for a page |
| `RETRIES` | `2` | Retries after HTTP 408, 429, 5xx or a network error |
| `PRICE_PER_REQUEST_USD` | `0.00075` | Price used for the cost figures |
| `ENABLE_DEEPSEEK_SEARCH` | `true` | Offer `deepseek_search` |
| `ENABLE_DEEPSEEK_FETCH` | `true` | Offer `deepseek_fetch` |
| `DEFAULT_COUNT` | `10` | Results per search when the agent gives no `count` |
| `SUMMARY_CHARS` | `800` | Longest summary per result |
| `CONTENT_CHARS` | `3000` | Longest content per result with `with_content` |
| `FETCH_MAX_CHARS` | `20000` | Characters per `deepseek_fetch` call when the agent gives no `max_chars` |
| `LOCALIZATION_IP` | (empty) | An IP address in the region you want results for. Empty = no region |
| `MCP_AUTH_TOKEN` | (empty) | When set, `/mcp` and `/usage` require `Authorization: Bearer <token>` |
| `USAGE_LOG` | `true` | Keep the usage log |
| `USAGE_DIR` | `/app/usage` | Folder of the usage log |
| `MCP_HOST` / `MCP_PORT` | `0.0.0.0` / `8000` | Address and port inside the container (or on your machine without Docker) |
| `DOCKER_NETWORK` | `agent_network` | Docker network shared with your agents |
| `PUBLISH_ADDR` | `0.0.0.0` | `0.0.0.0` = other machines can connect, `127.0.0.1` = this machine only |
| `PUBLISH_PORT` | `8807` | Port on your machine |

## Security

- **Never commit `.env`.** It is already in `.gitignore`.
- **Anyone who can reach the server can spend your DeepSeek balance.** If other machines can reach the port
  (`PUBLISH_ADDR=0.0.0.0`, the default), set `MCP_AUTH_TOKEN` to a long random value, or use `PUBLISH_ADDR=127.0.0.1`.
- The key never leaves the server. `/health` only says whether a key is set, and it is always open so that monitoring works.
- The usage log never contains queries, URLs or page content.
- The container runs as a non-root user.
- Search results and pages come from the open web. Tell your agent to treat them as information, not as instructions.

## Troubleshooting

| What you see | Cause and fix |
|---|---|
| `network agent_network declared as external, but could not be found` | Run `docker network create agent_network`, or set `DOCKER_NETWORK` to an existing network |
| `port is already allocated` | Another program uses 8807. Set `PUBLISH_PORT` to a free port |
| `/health` says the key is empty or still the example value | Put your real key in `.env`, then `docker compose up -d` |
| `HTTP 401` | The key is wrong or was revoked. Create a new one at platform.deepseek.com |
| `HTTP 402` | The DeepSeek account has no balance. Top it up |
| `HTTP 429` | Too many requests per second. The server already retried; slow the agent down |
| `HTTP 403` or `404` on a fetch | The site refuses automated reading, or the page has no readable content. Try another source |
| `the query with its filters is … characters` | Shorten the query or use fewer `sites` (128-character limit) |
| The client gets `401 unauthorized` | `MCP_AUTH_TOKEN` is set; send `Authorization: Bearer <token>` |
| A tool is missing in the client | Check its `ENABLE_…` switch and `/health`, then reconnect the client |
| Cost figures look wrong | Update `PRICE_PER_REQUEST_USD` to the current DeepSeek price |

See the server's own log with `docker compose logs -f`.

## Development

```bash
uv sync
```

```bash
uv run pytest -q
```

The tests use a fake DeepSeek API, so they need no key and cost nothing.

| File | Contents |
|---|---|
| `app/config.py` | Settings from the environment, tool switches |
| `app/deepseek.py` | DeepSeek API calls, retries, query operators, text formatting |
| `app/server.py` | The MCP tools, `/health`, `/usage`, token check |
| `app/usage.py` | The usage log (JSON Lines) |
| `tests/` | Tests against a fake API |

To change what the agent reads, edit `format_results` and `format_page` in `app/deepseek.py`. To change the tool descriptions the
agent sees, edit `SEARCH_DESCRIPTION`, `FETCH_DESCRIPTION` and the parameter descriptions in `app/server.py`.

## License

MIT. DeepSeek is a trademark of its owner. This project is not affiliated with DeepSeek.
