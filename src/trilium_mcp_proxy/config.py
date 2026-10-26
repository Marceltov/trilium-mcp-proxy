"""Configuration from environment variables, named like trilium-mcp's so the compose files read alike.

One Trilium (TRILIUM_SERVER_URL, served at /mcp) or several (TRILIUM_INSTANCES, each at /<name>/mcp).
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass

from mcp.server.auth.routes import validate_issuer_url
from pydantic import AnyHttpUrl

INSTANCE_NAME = re.compile(r"[a-z0-9][a-z0-9-]*")
RESERVED_NAMES = {"health", "mcp", "authorize", "token", "register", "revoke", "login"}


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class Instance:
    name: str  # the path segment: /<name>/mcp
    trilium_url: str
    instructions: str | None


@dataclass(frozen=True)
class Config:
    trilium_url: str | None  # TRILIUM_SERVER_URL, e.g. http://trilium-marcel:8080; None with instances
    base_url: str  # MCP_BASE_URL: the public URL, and the OAuth issuer (per instance: plus /<name>)
    oauth_secret: str  # MCP_OAUTH_SECRET: encrypts the OAuth store
    instructions: str | None  # MCP_INSTRUCTIONS: added to Trilium's initialize result
    port: int = 8081
    instances: tuple[Instance, ...] = ()  # TRILIUM_INSTANCES; empty in single mode


def _required(env: Mapping[str, str], name: str, why: str) -> str:
    value = env.get(name, "").strip()
    if not value:
        raise ConfigError(f"{name} is not set: {why}")
    return value


def _optional(env: Mapping[str, str], name: str) -> str | None:
    return env.get(name, "").strip() or None


def _instances(raw: str, env: Mapping[str, str], shared_instructions: str | None) -> tuple[Instance, ...]:
    entries = [e.strip() for e in re.split(r"[\n,]", raw) if e.strip()]
    if not entries:
        raise ConfigError("TRILIUM_INSTANCES is empty: list one name=url per line or comma")
    instances, seen = [], set()
    for entry in entries:
        name, sep, url = (part.strip() for part in entry.partition("="))
        if not sep or not name or not url:
            raise ConfigError(f"TRILIUM_INSTANCES entry {entry!r} is not name=url")
        if not INSTANCE_NAME.fullmatch(name):
            raise ConfigError(f"TRILIUM_INSTANCES: instance name {name!r} must be lowercase letters, "
                              "digits and hyphens")
        if name in RESERVED_NAMES:
            raise ConfigError(f"TRILIUM_INSTANCES: instance name {name!r} is reserved")
        if name in seen:
            raise ConfigError(f"TRILIUM_INSTANCES: instance {name!r} is listed twice")
        seen.add(name)
        own = _optional(env, "MCP_INSTRUCTIONS_" + name.upper().replace("-", "_"))
        instances.append(Instance(name, url.rstrip("/"), own or shared_instructions))
    return tuple(instances)


def load_config(env: Mapping[str, str]) -> Config:
    single, multi = _optional(env, "TRILIUM_SERVER_URL"), _optional(env, "TRILIUM_INSTANCES")
    if single and multi:
        raise ConfigError("set TRILIUM_SERVER_URL (one Trilium) or TRILIUM_INSTANCES (several), not both")
    if not single and not multi:
        raw = env.get("TRILIUM_INSTANCES")
        if raw is not None and raw.strip() == "":
            raise ConfigError("TRILIUM_INSTANCES is empty: list one name=url per line or comma")
        raise ConfigError("TRILIUM_SERVER_URL is not set: the Trilium Notes server to forward to, "
                          "e.g. http://trilium:8080 (or TRILIUM_INSTANCES for several)")
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
    instructions = _optional(env, "MCP_INSTRUCTIONS")
    instances = _instances(multi, env, instructions) if multi else ()
    return Config(trilium_url=single.rstrip("/") if single else None, base_url=base_url, oauth_secret=secret,
                  instructions=instructions, port=port, instances=instances)
