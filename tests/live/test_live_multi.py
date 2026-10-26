"""The multi-instance proxy (proxy-multi in docker-compose.yaml): two instances, notes and other."""

import asyncio

import httpx
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport

from tests.live.conftest import PROXY_MULTI
from tests.live.test_live import login


def session(instance: str, token: str, work):
    async def go():
        async with Client(StreamableHttpTransport(f"{PROXY_MULTI}/{instance}/mcp",
                                                  headers={"Authorization": f"Bearer {token}"})) as c:
            return await work(c)
    return asyncio.run(go())


def login_at(instance: str) -> dict:
    with httpx.Client(base_url=f"{PROXY_MULTI}/{instance}", timeout=30) as http:
        return login(http)


def test_health_lists_instances():
    assert httpx.get(f"{PROXY_MULTI}/health").json() == {"status": "ok",
                                                         "instances": {"notes": "ok", "other": "ok"}}


def test_login_at_one_instance_lists_tools_with_its_instructions():
    tokens = login_at("notes")

    async def look(c):
        return {t.name for t in await c.list_tools()}, c.initialize_result.instructions
    names, instructions = session("notes", tokens["access_token"], look)
    assert "search_notes" in names and instructions == "Notes house rules."


def test_token_of_one_instance_is_refused_by_the_other():
    tokens = login_at("notes")
    r = httpx.post(f"{PROXY_MULTI}/other/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                   headers={"Authorization": f"Bearer {tokens['access_token']}",
                            "Accept": "application/json, text/event-stream"})
    assert r.status_code == 401
    assert f"{PROXY_MULTI}/.well-known/oauth-protected-resource/other/mcp" in r.headers["www-authenticate"]


def test_metadata_per_instance():
    meta = httpx.get(f"{PROXY_MULTI}/.well-known/oauth-authorization-server/other").json()
    assert meta["authorization_endpoint"] == f"{PROXY_MULTI}/other/authorize"
