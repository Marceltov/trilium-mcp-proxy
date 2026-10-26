"""Several Trilium instances behind one proxy, one path each: /<name>/mcp, with its own login and issuer."""

import base64
import hashlib
import json
import secrets

import httpx
import pytest
from starlette.testclient import TestClient

from test_app import BASE, REDIRECT, mcp
from trilium_mcp_proxy.app import build_app
from trilium_mcp_proxy.config import Config, ConfigError, Instance, load_config

ENV = {"TRILIUM_INSTANCES": "marcel=http://trilium-marcel:8080/\nbille = http://trilium-bille:8080",
       "MCP_BASE_URL": "https://proxy.example/", "MCP_OAUTH_SECRET": "s"}


# -- config ---------------------------------------------------------------------------------

def test_instances_from_lines_or_commas():
    expected = (Instance("marcel", "http://trilium-marcel:8080", None),
                Instance("bille", "http://trilium-bille:8080", None))
    assert load_config(ENV).instances == expected
    commas = {**ENV, "TRILIUM_INSTANCES": "marcel=http://trilium-marcel:8080, bille=http://trilium-bille:8080"}
    assert load_config(commas).instances == expected
    assert load_config(ENV).trilium_url is None


def test_instructions_per_instance_fall_back_to_the_shared_ones():
    env = {**ENV, "MCP_INSTRUCTIONS": "Shared.", "MCP_INSTRUCTIONS_MARCEL": "Wiki rules."}
    by_name = {i.name: i.instructions for i in load_config(env).instances}
    assert by_name == {"marcel": "Wiki rules.", "bille": "Shared."}


def test_hyphenated_name_reads_underscored_instructions():
    env = {**ENV, "TRILIUM_INSTANCES": "my-notes=http://t:8080", "MCP_INSTRUCTIONS_MY_NOTES": "Mine."}
    assert load_config(env).instances[0].instructions == "Mine."


@pytest.mark.parametrize("value, needle", [
    ("Marcel=http://t:8080", "name"),
    ("health=http://t:8080", "reserved"),
    ("marcel=http://t:8080\nmarcel=http://u:8080", "twice"),
    ("marcel", "name=url"),
    ("marcel=", "name=url"),
    ("  \n ", "TRILIUM_INSTANCES"),
])
def test_bad_instances_are_rejected(value, needle):
    with pytest.raises(ConfigError, match=needle):
        load_config({**ENV, "TRILIUM_INSTANCES": value})


def test_single_and_multi_are_exclusive():
    with pytest.raises(ConfigError, match="not both"):
        load_config({**ENV, "TRILIUM_SERVER_URL": "http://t:8080"})


def test_neither_names_both():
    env = {k: v for k, v in ENV.items() if k != "TRILIUM_INSTANCES"}
    with pytest.raises(ConfigError, match="TRILIUM_SERVER_URL.*TRILIUM_INSTANCES"):
        load_config(env)


def test_single_mode_unchanged():
    env = {"TRILIUM_SERVER_URL": "http://t:8080", "MCP_BASE_URL": "https://p.example", "MCP_OAUTH_SECRET": "s"}
    config = load_config(env)
    assert config.trilium_url == "http://t:8080" and config.instances == ()


# -- app ------------------------------------------------------------------------------------

@pytest.fixture
def client(trilium, tmp_path):
    url, _ = trilium
    config = Config(trilium_url=None, base_url=BASE, oauth_secret="s", instructions=None,
                    instances=(Instance("marcel", url, "Wiki rules."),
                               Instance("bille", "http://127.0.0.1:9", None)))
    app = build_app(config, store_dir=tmp_path / "oauth", failed_login_delay=0)
    with TestClient(app, base_url=BASE) as c:
        yield c


def login_at(http, prefix: str, password="pw") -> dict:
    client_id = http.post(f"{prefix}/register", json={
        "client_name": "claude.ai", "redirect_uris": [REDIRECT], "token_endpoint_auth_method": "none",
        "grant_types": ["authorization_code", "refresh_token"], "response_types": ["code"]}).json()["client_id"]
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    r = http.get(f"{prefix}/authorize", params={
        "response_type": "code", "client_id": client_id, "redirect_uri": REDIRECT, "code_challenge": challenge,
        "code_challenge_method": "S256", "state": "s"}, follow_redirects=False)
    location = httpx.URL(r.headers["location"])
    assert location.path == f"{prefix}/login"
    r = http.post(f"{prefix}/login", data={"id": location.params["id"], "password": password},
                  follow_redirects=False)
    code = httpx.URL(r.headers["location"]).params["code"]
    return http.post(f"{prefix}/token", data={"grant_type": "authorization_code", "code": code,
                                              "redirect_uri": REDIRECT, "client_id": client_id,
                                              "code_verifier": verifier}).json()


def mcp_at(http, prefix, authorization, body=None):
    return http.post(f"{prefix}/mcp", json=body or {"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                     headers={"Authorization": authorization, "Accept": "application/json, text/event-stream"},
                     follow_redirects=False)


def test_login_at_one_instance_then_forward(client):
    tokens = login_at(client, "/marcel")
    r = mcp_at(client, "/marcel", f"Bearer {tokens['access_token']}")
    assert r.status_code == 200 and r.json()["headers"]["authorization"] == "etapi-1"


def test_token_of_one_instance_is_refused_by_another(client):
    tokens = login_at(client, "/marcel")
    r = mcp_at(client, "/bille", f"Bearer {tokens['access_token']}")
    assert r.status_code == 401


def test_raw_token_goes_to_that_instances_trilium(client):
    assert mcp_at(client, "/marcel", "raw-1").json()["headers"]["authorization"] == "raw-1"
    r = mcp_at(client, "/bille", "raw-1")  # bille's Trilium is down
    assert r.status_code == 502 and r.json() == {"error": "Trilium is unreachable"}


def test_unauthenticated_points_at_the_instances_resource_metadata(client):
    r = client.post("/bille/mcp", json={})
    assert r.status_code == 401
    assert f"{BASE}/.well-known/oauth-protected-resource/bille/mcp" in r.headers["www-authenticate"]


def test_resource_metadata_names_the_instances_issuer(client):
    meta = client.get("/.well-known/oauth-protected-resource/marcel/mcp").json()
    assert meta["resource"] == f"{BASE}/marcel/mcp"
    assert [s.rstrip("/") for s in meta["authorization_servers"]] == [f"{BASE}/marcel"]


@pytest.mark.parametrize("path", ["/.well-known/oauth-authorization-server/bille",
                                  "/bille/.well-known/oauth-authorization-server"])
def test_authorization_server_metadata_per_instance(client, path):
    meta = client.get(path).json()
    assert meta["issuer"].rstrip("/") == f"{BASE}/bille"
    assert meta["authorization_endpoint"] == f"{BASE}/bille/authorize"
    assert meta["token_endpoint"] == f"{BASE}/bille/token"


def test_instructions_per_instance(client, trilium):
    _, state = trilium
    state.canned = b'event: message\ndata: {"result":{"protocolVersion":"2025-06-18"},"jsonrpc":"2.0","id":1}\n\n'
    r = mcp_at(client, "/marcel", "raw-1", {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    data = next(l for l in r.text.splitlines() if l.startswith("data:"))
    assert json.loads(data[5:])["result"]["instructions"] == "Wiki rules."


def test_health_per_instance_and_overall(client):
    assert client.get("/health").json() == {"status": "ok",
                                            "instances": {"marcel": "ok", "bille": "unreachable"}}
    assert client.get("/marcel/health").json() == {"status": "ok", "trilium": "ok"}
    assert client.get("/bille/health").json() == {"status": "ok", "trilium": "unreachable"}


def test_unknown_instance_and_bare_mcp_are_404(client):
    assert client.post("/nope/mcp", json={}).status_code == 404
    assert mcp(client, "raw-1").status_code == 404
