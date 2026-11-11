"""A fake Trilium Notes for the tests: /mcp echoes or streams, /etapi/auth/* mint and record tokens."""

import asyncio
import json
import time
from dataclasses import dataclass, field

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse
from starlette.routing import Route


@dataclass
class State:
    minted: int = 0
    logged_out: list[str] = field(default_factory=list)
    stream_times: list[float] = field(default_factory=list)
    stream_closed: bool = False
    healthy: bool = True
    # Raw bytes /mcp answers with instead of echoing, and how many chunks to split them into.
    canned: bytes | None = None
    canned_type: str = "text/event-stream"
    canned_chunks: int = 1
    reject_tokens: set[str] = field(default_factory=lambda: {"bad"})
    totp: str | None = None  # the code two-factor login expects; None: two-factor login is off
    login_bodies: list[dict] = field(default_factory=list)


def build_fake(state: State) -> Starlette:
    async def mcp(request: Request) -> Response:
        auth = request.headers.get("authorization", "")
        if auth in state.reject_tokens:
            return JSONResponse({"error": "invalid token"}, status_code=401)
        body = await request.body()
        if n := int(request.query_params.get("stream", "0")):
            async def chunks():
                try:
                    for i in range(n):
                        state.stream_times.append(time.monotonic())
                        yield f"event: message\ndata: {i}\n\n".encode()
                        await asyncio.sleep(0.2)
                finally:
                    state.stream_closed = True
            return StreamingResponse(chunks(), media_type="text/event-stream")
        if state.canned is not None:
            canned, k = state.canned, state.canned_chunks
            size = -(-len(canned) // k)

            async def pieces():
                for i in range(0, len(canned), size):
                    yield canned[i:i + size]
                    await asyncio.sleep(0.01)
            return StreamingResponse(pieces(), media_type=state.canned_type)
        return JSONResponse({"method": request.method, "query": request.url.query,
                             "headers": dict(request.headers), "body": body.decode()})

    async def login(request: Request) -> Response:
        # Error bodies and order as Trilium's etapi/auth.ts: TOTP presence first, then password, then code.
        body = await request.json()
        state.login_bodies.append(body)
        if state.totp and not body.get("totpToken"):
            return JSONResponse({"status": 401, "code": "TOTP_REQUIRED", "message": "TOTP token is required."},
                                status_code=401)
        if body.get("password") != "pw":
            return JSONResponse({"status": 401, "code": "WRONG_PASSWORD", "message": "Wrong password."},
                                status_code=401)
        if state.totp and body["totpToken"] != state.totp:
            return JSONResponse({"status": 401, "code": "WRONG_TOTP", "message": "Wrong TOTP token."},
                                status_code=401)
        state.minted += 1
        return JSONResponse({"authToken": f"etapi-{state.minted}"}, status_code=201)

    async def logout(request: Request) -> Response:
        state.logged_out.append(request.headers.get("authorization", ""))
        return Response(status_code=204)

    async def health(_: Request) -> Response:
        return JSONResponse({"status": "ok"}) if state.healthy else Response(status_code=503)

    return Starlette(routes=[Route("/mcp", mcp, methods=["GET", "POST", "DELETE"]),
                             Route("/etapi/auth/login", login, methods=["POST"]),
                             Route("/etapi/auth/logout", logout, methods=["POST"]),
                             Route("/api/health-check", health)])


def dumps(obj) -> bytes:
    return json.dumps(obj).encode()
