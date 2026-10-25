"""Configuration from environment variables, named like trilium-mcp's so the compose files read alike."""

from collections.abc import Mapping
from dataclasses import dataclass

from mcp.server.auth.routes import validate_issuer_url
from pydantic import AnyHttpUrl


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class Config:
    trilium_url: str  # TRILIUM_SERVER_URL, e.g. http://trilium-marcel:8080
    base_url: str  # MCP_BASE_URL: the public URL, and the OAuth issuer
    oauth_secret: str  # MCP_OAUTH_SECRET: encrypts the OAuth store
    instructions: str | None  # MCP_INSTRUCTIONS: added to Trilium's initialize result
    port: int = 8081


def _required(env: Mapping[str, str], name: str, why: str) -> str:
    value = env.get(name, "").strip()
    if not value:
        raise ConfigError(f"{name} is not set: {why}")
    return value


def load_config(env: Mapping[str, str]) -> Config:
    trilium_url = _required(env, "TRILIUM_SERVER_URL", "the Trilium Notes server to forward to, "
                            "e.g. http://trilium:8080").rstrip("/")
    base_url = _required(env, "MCP_BASE_URL", "the proxy's public URL, which is also the OAuth issuer, "
                         "e.g. https://trilium-mcp-proxy.example").rstrip("/")
    try:
        validate_issuer_url(AnyHttpUrl(base_url))
    except ValueError as e:
        raise ConfigError(f"MCP_BASE_URL={base_url!r} is not a valid OAuth issuer "
                          f"(https, no query or fragment; plain http only for localhost): {e}") from None
    secret = _required(env, "MCP_OAUTH_SECRET", "it encrypts the stored logins; generate one with "
                       "`openssl rand -hex 32`")
    raw_port = env.get("MCP_PORT", "").strip() or "8081"
    try:
        port = int(raw_port)
    except ValueError:
        raise ConfigError(f"MCP_PORT must be an integer, got {raw_port!r}") from None
    return Config(trilium_url=trilium_url, base_url=base_url, oauth_secret=secret,
                  instructions=env.get("MCP_INSTRUCTIONS", "").strip() or None, port=port)
