"""The proxy app: OAuth login (mcp-login-oauth, the Trilium password), the auth gate on /mcp, /health.

A login mints an ETAPI token for that client through Trilium's /etapi/auth/login; revoking logs it out
again. A client that already has an ETAPI token (Claude Code) sends it as the header, with or without
"Bearer", and it's forwarded unchanged: Trilium judges it.
"""

import contextlib
import logging
import os
import sys
from pathlib import Path

import httpx
from fastmcp.server.auth.middleware import RequireAuthMiddleware
from mcp.server.auth.routes import build_resource_metadata_url
from mcp_login_oauth import BearerPrefixMiddleware, LoginField, LoginOAuthProvider, LoginRejected, build_store
from pydantic import AnyHttpUrl
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from trilium_mcp_proxy.config import Config, ConfigError, load_config
from trilium_mcp_proxy.forward import Forwarder

log = logging.getLogger("trilium_mcp_proxy")

MCP_PATH = "/mcp"
TOKEN_PREFIX = "tmpx_"


# Trilium's ETAPI error codes for a login, as the user should read them.
_LOGIN_ERRORS = {
    "WRONG_PASSWORD": "Wrong password.",
    "TOTP_REQUIRED": "Two-factor login is on: enter your TOTP code as well.",
    "WRONG_TOTP": "Wrong TOTP code.",
}


def _rejection(r: httpx.Response) -> str:
    try:
        code = r.json().get("code")
    except ValueError:
        code = None
    return _LOGIN_ERRORS.get(code) or f"Trilium rejected the login (HTTP {r.status_code})."


def build_provider(config: Config, trilium: httpx.AsyncClient, store_dir: Path, **overrides) -> LoginOAuthProvider:
    async def check_login(form) -> dict:
        # The password and TOTP code go straight to Trilium and are never stored or logged.
        body = {"password": form["password"]}
        if totp := form.get("totp", "").strip():
            body["totpToken"] = totp
        r = await trilium.post("/etapi/auth/login", json=body)
        if not r.is_success:
            raise LoginRejected(_rejection(r))
        return {"etapi_token": r.json()["authToken"]}

    async def on_revoke(grant: dict) -> None:
        await trilium.post("/etapi/auth/logout", headers={"Authorization": grant["etapi_token"]})

    async def verify_static(token: str) -> dict:
        return {"etapi_token": token}  # a raw ETAPI token: Trilium decides whether it's valid

    args = dict(base_url=config.base_url,
                store=build_store(store_dir, secret=config.oauth_secret, salt="trilium-mcp-proxy-oauth"),
                service_name="Trilium Notes",
                fields=[LoginField("password", "Trilium password", type="password", required=True),
                        LoginField("totp", "TOTP code or recovery code (if two-factor login is on)",
                                   autocomplete="one-time-code")],
                check_login=check_login, on_revoke=on_revoke, verify_static=verify_static,
                token_prefix=TOKEN_PREFIX)
    return LoginOAuthProvider(**{**args, **overrides})


def build_app(config: Config, store_dir: Path = Path("/data/oauth"),
              transport: httpx.AsyncBaseTransport | None = None, **provider_overrides):
    """`transport` and `provider_overrides` are for tests (a fake Trilium, failed_login_delay=0)."""
    # No total timeout: event streams and long tool calls stay open as long as Trilium keeps them.
    trilium = httpx.AsyncClient(base_url=config.trilium_url, transport=transport,
                                timeout=httpx.Timeout(connect=10, read=None, write=60, pool=10))
    provider = build_provider(config, trilium, store_dir, **provider_overrides)
    metadata_url = build_resource_metadata_url(AnyHttpUrl(config.base_url + MCP_PATH))
    gate = RequireAuthMiddleware(Forwarder(trilium, config.instructions), provider.required_scopes or [],
                                 metadata_url)

    async def health(_: Request) -> JSONResponse:
        try:
            ok = (await trilium.get("/api/health-check", timeout=5)).is_success
        except httpx.HTTPError:
            ok = False
        return JSONResponse({"status": "ok", "trilium": "ok" if ok else "unreachable"})

    @contextlib.asynccontextmanager
    async def lifespan(_):
        yield
        await trilium.aclose()

    app = Starlette(routes=[*provider.get_routes(mcp_path=MCP_PATH), Route("/health", health),
                            Route(MCP_PATH, gate, methods=["GET", "POST", "DELETE"])],
                    middleware=provider.get_middleware(), lifespan=lifespan)
    return BearerPrefixMiddleware(app)


def main() -> None:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        config = load_config(os.environ)
    except ConfigError as e:
        print(f"trilium-mcp-proxy: {e}", file=sys.stderr)
        sys.exit(1)
    import uvicorn
    uvicorn.run(build_app(config), host="0.0.0.0", port=config.port, log_level="warning")
