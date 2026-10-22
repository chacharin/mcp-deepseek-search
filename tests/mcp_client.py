"""Talk to the app the way an MCP agent does (in-process, through Starlette's TestClient).

The MCP session manager may start only once per app, so each loaded server keeps one running client."""
import json

from starlette.testclient import TestClient

HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
_clients: dict[int, TestClient] = {}


def client(server) -> TestClient:
    c = _clients.get(id(server.app))
    if c is None:
        c = TestClient(server.app)
        c.__enter__()                  # runs the lifespan (MCP session manager) once for this app
        _clients[id(server.app)] = c
    return c


def rpc(c, method, params=None, headers=None):
    r = c.post("/mcp", headers={**HEADERS, **(headers or {})},
               json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}})
    if r.status_code != 200:
        return r
    if r.headers["content-type"].startswith("text/event-stream"):
        data = [line[6:] for line in r.text.splitlines() if line.startswith("data: ")]
        return json.loads(data[-1])
    return r.json()


def tools(server):
    return {t["name"]: t for t in rpc(client(server), "tools/list")["result"]["tools"]}


def call(server, name, **arguments):
    res = rpc(client(server), "tools/call", {"name": name, "arguments": arguments})["result"]
    return res["content"][0]["text"]
