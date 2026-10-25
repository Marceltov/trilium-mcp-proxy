import asyncio
import base64
import hashlib
import secrets

import httpx
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport

from tests.live.conftest import PASSWORD, PROXY

REDIRECT = "http://localhost:9/cb"


def login(http: httpx.Client) -> dict:
    client_id = http.post("/register", json={
        "client_name": "live", "redirect_uris": [REDIRECT], "token_endpoint_auth_method": "none",
        "grant_types": ["authorization_code", "refresh_token"], "response_types": ["code"]}).json()["client_id"]
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    r = http.get("/authorize", params={"response_type": "code", "client_id": client_id, "redirect_uri": REDIRECT,
                                       "code_challenge": challenge, "code_challenge_method": "S256", "state": "s"})
    pending = httpx.URL(r.headers["location"]).params["id"]
    r = http.post("/login", data={"id": pending, "password": PASSWORD})
    assert "location" in r.headers, r.text
    code = httpx.URL(r.headers["location"]).params["code"]
    tokens = http.post("/token", data={"grant_type": "authorization_code", "code": code, "redirect_uri": REDIRECT,
                                       "client_id": client_id, "code_verifier": verifier}).json()
    return {**tokens, "client_id": client_id}


def session(token: str, work):
    async def go():
        async with Client(StreamableHttpTransport(f"{PROXY}/mcp",
                                                  headers={"Authorization": f"Bearer {token}"})) as c:
            return await work(c)
    return asyncio.run(go())


def test_health_ok():
    assert httpx.get(f"{PROXY}/health").json() == {"status": "ok", "trilium": "ok"}


def test_oauth_login_lists_trilium_tools():
    with httpx.Client(base_url=PROXY, timeout=30) as http:
        tokens = login(http)

    async def tools(c):
        return {t.name for t in await c.list_tools()}
    names = session(tokens["access_token"], tools)
    assert {"search_notes", "edit_note_content", "append_to_note"} <= names


def test_initialize_has_fixture_instructions():
    with httpx.Client(base_url=PROXY, timeout=30) as http:
        tokens = login(http)

    async def instructions(c):
        return c.initialize_result.instructions
    assert session(tokens["access_token"], instructions) == "Fixture house rules."


def test_tool_call_through_proxy():
    with httpx.Client(base_url=PROXY, timeout=30) as http:
        tokens = login(http)

    async def toc(c):
        return await c.call_tool("get_help_toc", {})
    result = session(tokens["access_token"], toc)
    assert not result.is_error and result.content


def test_revoke_then_401():
    with httpx.Client(base_url=PROXY, timeout=30) as http:
        tokens = login(http)
        assert http.post("/revoke", data={"token": tokens["refresh_token"],
                                          "client_id": tokens["client_id"]}).status_code == 200
        r = http.post("/mcp", json={}, headers={"Authorization": f"Bearer {tokens['access_token']}"})
        assert r.status_code == 401
