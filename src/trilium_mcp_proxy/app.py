"""The proxy app: OAuth login (mcp-login-oauth, the Trilium password), the auth gate on /mcp, /health.

With several instances, each gets the same set under /<name> with its own issuer (MCP_BASE_URL/<name>),
login and store, so a token from one instance means nothing to another. Only the metadata that RFC 8414
and RFC 9728 place at the root moves there, path-suffixed: /.well-known/oauth-authorization-server/<name>
and /.well-known/oauth-protected-resource/<name>/mcp.

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
from starlette.routing import Mount, Route

from trilium_mcp_proxy.config import Config, ConfigError, load_config
from trilium_mcp_proxy.forward import Forwarder

log = logging.getLogger("trilium_mcp_proxy")

MCP_PATH = "/mcp"
TOKEN_PREFIX = "tmpx_"


def build_provider(config: Config, trilium: httpx.AsyncClient, store_dir: Path, **overrides) -> LoginOAuthProvider:
    async def check_login(form) -> dict:
        # The password goes straight to Trilium and is never stored or logged.
        r = await trilium.post("/etapi/auth/login", json={"password": form["password"]})
        if not r.is_success:
            raise LoginRejected(f"Trilium rejected the login (HTTP {r.status_code}).")
        return {"etapi_token": r.json()["authToken"]}

    async def on_revoke(grant: dict) -> None:
        await trilium.post("/etapi/auth/logout", headers={"Authorization": grant["etapi_token"]})

    async def verify_static(token: str) -> dict:
        return {"etapi_token": token}  # a raw ETAPI token: Trilium decides whether it's valid

    args = dict(base_url=config.base_url,
                store=build_store(store_dir, secret=config.oauth_secret, salt="trilium-mcp-proxy-oauth"),
                service_name="Trilium Notes",
                fields=[LoginField("password", "Trilium password", type="password", required=True)],
                check_login=check_login, on_revoke=on_revoke, verify_static=verify_static,
                token_prefix=TOKEN_PREFIX)
    return LoginOAuthProvider(**{**args, **overrides})


def _trilium_client(url: str, transport: httpx.AsyncBaseTransport | None) -> httpx.AsyncClient:
    # No total timeout: event streams and long tool calls stay open as long as Trilium keeps them.
    return httpx.AsyncClient(base_url=url, transport=transport,
                             timeout=httpx.Timeout(connect=10, read=None, write=60, pool=10))


async def _trilium_ok(trilium: httpx.AsyncClient) -> bool:
    try:
        return (await trilium.get("/api/health-check", timeout=5)).is_success
    except httpx.HTTPError:
        return False


def _health(trilium: httpx.AsyncClient) -> Route:
    async def health(_: Request) -> JSONResponse:
        return JSONResponse({"status": "ok", "trilium": "ok" if await _trilium_ok(trilium) else "unreachable"})
    return Route("/health", health)


def _gate(config: Config, provider: LoginOAuthProvider, trilium: httpx.AsyncClient) -> Route:
    metadata_url = build_resource_metadata_url(AnyHttpUrl(config.base_url + MCP_PATH))
    gate = RequireAuthMiddleware(Forwarder(trilium, config.instructions), provider.required_scopes or [],
                                 metadata_url)
    return Route(MCP_PATH, gate, methods=["GET", "POST", "DELETE"])


def _lifespan(clients: list[httpx.AsyncClient]):
    @contextlib.asynccontextmanager
    async def lifespan(_):
        yield
        for client in clients:
            await client.aclose()
    return lifespan


def build_app(config: Config, store_dir: Path = Path("/data/oauth"),
              transport: httpx.AsyncBaseTransport | None = None, **provider_overrides):
    """`transport` and `provider_overrides` are for tests (a fake Trilium, failed_login_delay=0)."""
    if config.instances:
        return BearerPrefixMiddleware(_build_multi(config, store_dir, transport, provider_overrides))
    trilium = _trilium_client(config.trilium_url, transport)
    provider = build_provider(config, trilium, store_dir, **provider_overrides)
    app = Starlette(routes=[*provider.get_routes(mcp_path=MCP_PATH), _health(trilium),
                            _gate(config, provider, trilium)],
                    middleware=provider.get_middleware(), lifespan=_lifespan([trilium]))
    return BearerPrefixMiddleware(app)


def _build_multi(config: Config, store_dir: Path, transport, provider_overrides) -> Starlette:
    root_routes, clients = [], {}
    for instance in config.instances:
        own = Config(trilium_url=instance.trilium_url, base_url=f"{config.base_url}/{instance.name}",
                     oauth_secret=config.oauth_secret, instructions=instance.instructions)
        trilium = clients[instance.name] = _trilium_client(instance.trilium_url, transport)
        provider = build_provider(own, trilium, store_dir / instance.name, **provider_overrides)
        routes = provider.get_routes(mcp_path=MCP_PATH)
        resource_meta = [r for r in routes if r.path.startswith("/.well-known/oauth-protected-resource/")]
        server_meta = next(r for r in routes if r.path == "/.well-known/oauth-authorization-server")
        root_routes += [*resource_meta, Route(f"{server_meta.path}/{instance.name}", server_meta.endpoint,
                                              methods=server_meta.methods)]
        sub = Starlette(routes=[*(r for r in routes if r not in resource_meta), _health(trilium),
                                _gate(own, provider, trilium)],
                        middleware=provider.get_middleware())
        root_routes.append(Mount(f"/{instance.name}", app=sub))

    async def health(_: Request) -> JSONResponse:
        states = {name: "ok" if await _trilium_ok(t) else "unreachable" for name, t in clients.items()}
        return JSONResponse({"status": "ok", "instances": states})

    return Starlette(routes=[Route("/health", health), *root_routes], lifespan=_lifespan(list(clients.values())))


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
