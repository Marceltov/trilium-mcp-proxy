"""Transparent, streaming forwarding of /mcp to Trilium's built-in MCP server.

Only the Authorization header changes (to the client's ETAPI token). Bodies, methods, the query string
and the remaining headers pass through, and responses stream back chunk by chunk as they arrive. The
one exception: with instructions configured, the (small) response to `initialize` is read whole so the
instructions can be added to it (see inject.py).
"""

import asyncio
import contextlib
import json
import logging

import httpx

from trilium_mcp_proxy.inject import inject_instructions

log = logging.getLogger("trilium_mcp_proxy")

# RFC 9110 hop-by-hop headers, plus what httpx sets itself or we replace.
HOP_BY_HOP = {"connection", "keep-alive", "transfer-encoding", "te", "trailer", "upgrade",
              "proxy-authorization", "proxy-authenticate", "proxy-connection"}
REQUEST_DROP = HOP_BY_HOP | {"host", "authorization", "content-length"}


def _connection_listed(headers: list[tuple[bytes, bytes]]) -> set[str]:
    """Headers named in Connection are hop-by-hop too."""
    listed = set()
    for name, value in headers:
        if name.lower() == b"connection":
            listed |= {v.strip().lower() for v in value.decode("latin-1").split(",") if v.strip()}
    return listed


async def _read_body(receive) -> bytes:
    chunks = []
    while True:
        message = await receive()
        if message["type"] == "http.disconnect":
            raise ConnectionAbortedError
        chunks.append(message.get("body", b""))
        if not message.get("more_body"):
            return b"".join(chunks)


def _is_initialize(body: bytes) -> bool:
    """A single JSON-RPC initialize request (not a batch, not invalid JSON)."""
    try:
        message = json.loads(body)
    except ValueError:
        return False
    return isinstance(message, dict) and message.get("method") == "initialize"


async def _json(send, status: int, obj: dict) -> None:
    body = json.dumps(obj).encode()
    await send({"type": "http.response.start", "status": status,
                "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
    await send({"type": "http.response.body", "body": body})


class Forwarder:
    """Pure ASGI app for /mcp. Expects scope["user"] from the auth middleware, carrying the grant
    {"etapi_token": …} in its access token's claims (mcp-login-oauth)."""

    def __init__(self, upstream: httpx.AsyncClient, instructions: str | None = None):
        self.upstream = upstream
        self.instructions = instructions

    async def __call__(self, scope, receive, send):
        token = scope["user"].access_token.claims["grant"]["etapi_token"]
        try:
            body = await _read_body(receive)
        except ConnectionAbortedError:
            return
        drop = REQUEST_DROP | _connection_listed(scope["headers"])
        headers = [(k, v) for k, v in scope["headers"] if k.decode("latin-1").lower() not in drop]
        headers.append((b"authorization", token.encode()))
        query = scope.get("query_string", b"").decode("latin-1")
        request = self.upstream.build_request(scope["method"], "/mcp" + (f"?{query}" if query else ""),
                                              headers=headers, content=body)
        try:
            response = await self.upstream.send(request, stream=True)
        except httpx.HTTPError as e:
            log.warning("Trilium is unreachable: %s", type(e).__name__)
            await _json(send, 502, {"error": "Trilium is unreachable"})
            return
        try:
            if self.instructions and _is_initialize(body):
                await self._rewritten(response, send)
            else:
                await self._stream(response, receive, send)
        finally:
            await response.aclose()

    async def _rewritten(self, response: httpx.Response, send) -> None:
        await response.aread()  # decoded, so content-encoding goes and content-length is ours
        body = inject_instructions(response.content, response.headers.get("content-type", ""), self.instructions)
        drop = HOP_BY_HOP | _connection_listed(response.headers.raw) | {"content-length", "content-encoding"}
        headers = [(k, v) for k, v in response.headers.raw if k.decode("latin-1").lower() not in drop]
        await send({"type": "http.response.start", "status": response.status_code,
                    "headers": [*headers, (b"content-length", str(len(body)).encode())]})
        await send({"type": "http.response.body", "body": body})

    async def _stream(self, response: httpx.Response, receive, send) -> None:
        resp_drop = HOP_BY_HOP | _connection_listed(response.headers.raw)
        await send({"type": "http.response.start", "status": response.status_code,
                    "headers": [(k, v) for k, v in response.headers.raw
                                if k.decode("latin-1").lower() not in resp_drop]})

        async def pump():
            async for chunk in response.aiter_raw():
                await send({"type": "http.response.body", "body": chunk, "more_body": True})
            await send({"type": "http.response.body", "body": b"", "more_body": False})

        async def watch():  # a client that goes away mid-stream ends the upstream request too
            while (await receive())["type"] != "http.disconnect":
                pass

        tasks = [asyncio.create_task(pump()), asyncio.create_task(watch())]
        try:
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                if task is tasks[0] and (exc := task.exception()) and not isinstance(exc, OSError):
                    raise exc
        finally:
            for task in tasks:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task
