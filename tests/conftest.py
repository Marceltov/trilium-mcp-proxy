"""Serve the fake Trilium over real HTTP (in-process ASGI transports buffer, which would hide streaming
bugs) and drive ASGI apps directly with recorded send/receive."""

import asyncio
import socket
import threading
import time

import httpx
import pytest
import uvicorn

from fake_trilium import State, build_fake


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def fake_server():
    state_box = {"state": State()}

    async def app(scope, receive, send):  # indirection so each test gets a fresh State
        await build_fake(state_box["state"])(scope, receive, send)

    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        time.sleep(0.01)
    yield f"http://127.0.0.1:{port}", state_box
    server.should_exit = True
    thread.join(timeout=5)


@pytest.fixture
def trilium(fake_server):
    url, box = fake_server
    box["state"] = State()
    return url, box["state"]


class Recorded:
    """The result of one ASGI request: status, headers, body chunks with arrival times."""

    def __init__(self):
        self.status = None
        self.headers: dict[str, str] = {}
        self.chunks: list[tuple[float, bytes]] = []

    @property
    def body(self) -> bytes:
        return b"".join(c for _, c in self.chunks)


async def call(app, method="POST", path="/mcp", body=b"", headers=(), query=b"", grant=None,
               disconnect_after=None) -> Recorded:
    """Run one request through an ASGI app. `grant` sets scope["user"] like the auth middleware does;
    `disconnect_after` sends http.disconnect after that many response body chunks."""
    out = Recorded()
    got_chunk = asyncio.Event()
    sent_body = False

    async def receive():
        nonlocal sent_body
        if not sent_body:
            sent_body = True
            return {"type": "http.request", "body": body, "more_body": False}
        while disconnect_after is None or len([c for _, c in out.chunks if c]) < disconnect_after:
            got_chunk.clear()
            await got_chunk.wait()
        return {"type": "http.disconnect"}

    async def send(message):
        if message["type"] == "http.response.start":
            out.status = message["status"]
            out.headers = {k.decode().lower(): v.decode() for k, v in message["headers"]}
        elif message["type"] == "http.response.body":
            out.chunks.append((time.monotonic(), message.get("body", b"")))
            got_chunk.set()

    scope = {"type": "http", "method": method, "path": path, "raw_path": path.encode(), "query_string": query,
             "headers": [(k.lower().encode(), v.encode()) for k, v in headers], "scheme": "http",
             "server": ("proxy", 80), "client": ("127.0.0.1", 1), "root_path": "", "http_version": "1.1",
             "asgi": {"version": "3.0"}}
    if grant is not None:
        from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser
        from fastmcp.server.auth import AccessToken
        scope["user"] = AuthenticatedUser(AccessToken(token="tmpx_client", client_id="c", scopes=[],
                                                      claims={"grant": grant}))
    await app(scope, receive, send)
    return out


@pytest.fixture
def upstream(trilium):
    url, _ = trilium
    return httpx.AsyncClient(base_url=url, timeout=httpx.Timeout(connect=10, read=None, write=60, pool=10))
