import asyncio
import json

import httpx

from conftest import call
from trilium_mcp_proxy.forward import Forwarder

GRANT = {"etapi_token": "etapi-1"}


async def test_body_and_method_pass_through(trilium, upstream):
    fwd = Forwarder(upstream)
    for method in ("POST", "GET", "DELETE"):
        r = await call(fwd, method=method, body=b'{"x": 1}' if method == "POST" else b"", grant=GRANT)
        echo = json.loads(r.body)
        assert r.status == 200 and echo["method"] == method
        assert echo["body"] == ('{"x": 1}' if method == "POST" else "")


async def test_authorization_is_replaced_with_grant_token(trilium, upstream):
    r = await call(Forwarder(upstream), headers=[("Authorization", "Bearer tmpx_client")], grant=GRANT)
    assert json.loads(r.body)["headers"]["authorization"] == "etapi-1"


async def test_host_and_hop_by_hop_headers_dropped(trilium, upstream):
    r = await call(Forwarder(upstream), grant=GRANT,
                   headers=[("Host", "proxy.example"), ("Connection", "keep-alive, x-secret"),
                            ("Keep-Alive", "timeout=5"), ("Proxy-Authorization", "x"), ("X-Kept", "1"),
                            ("Mcp-Session-Id", "s1"), ("Accept", "application/json, text/event-stream")])
    seen = json.loads(r.body)["headers"]
    assert seen["host"].startswith("127.0.0.1")
    assert "keep-alive" not in seen and "proxy-authorization" not in seen
    assert seen["x-kept"] == "1" and seen["mcp-session-id"] == "s1" and "event-stream" in seen["accept"]


async def test_query_string_kept(trilium, upstream):
    r = await call(Forwarder(upstream), query=b"a=1&b=2", grant=GRANT)
    assert json.loads(r.body)["query"] == "a=1&b=2"


async def test_stream_arrives_in_chunks(trilium, upstream):
    _, state = trilium
    r = await call(Forwarder(upstream), method="GET", query=b"stream=3", grant=GRANT)
    data = [(t, c) for t, c in r.chunks if c]
    assert r.status == 200 and r.headers["content-type"].startswith("text/event-stream")
    assert b"".join(c for _, c in data).count(b"event: message") == 3
    assert data[0][0] < state.stream_times[-1]  # the first chunk was here before upstream sent the last


async def test_client_disconnect_closes_upstream(trilium, upstream):
    _, state = trilium
    await asyncio.wait_for(call(Forwarder(upstream), method="GET", query=b"stream=50", grant=GRANT,
                                disconnect_after=1), timeout=5)
    for _ in range(50):
        if state.stream_closed:
            break
        await asyncio.sleep(0.05)
    assert state.stream_closed and len(state.stream_times) < 50


async def test_upstream_down_is_502_json():
    dead = httpx.AsyncClient(base_url="http://127.0.0.1:9")
    r = await call(Forwarder(dead), grant=GRANT)
    assert r.status == 502 and json.loads(r.body) == {"error": "Trilium is unreachable"}
