import base64
import hashlib
import json
import secrets

import httpx
import pytest
from starlette.testclient import TestClient

from trilium_mcp_proxy import app as app_module
from trilium_mcp_proxy.app import build_app
from trilium_mcp_proxy.config import Config

BASE = "http://localhost:8081"
REDIRECT = "http://localhost:9/cb"


@pytest.fixture
def make_client(trilium, tmp_path):
    url, _ = trilium

    def make(trilium_url=url, transport=None):
        config = Config(trilium_url=trilium_url, base_url=BASE, oauth_secret="s", instructions="House rules.")
        app = build_app(config, store_dir=tmp_path / "oauth", transport=transport, failed_login_delay=0)
        return TestClient(app, base_url=BASE)
    return make


@pytest.fixture
def client(make_client):
    with make_client() as c:
        yield c


def start_login(http) -> tuple[str, str, str]:
    client_id = http.post("/register", json={"client_name": "claude.ai", "redirect_uris": [REDIRECT],
                                             "token_endpoint_auth_method": "none",
                                             "grant_types": ["authorization_code", "refresh_token"],
                                             "response_types": ["code"]}).json()["client_id"]
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    r = http.get("/authorize", params={"response_type": "code", "client_id": client_id, "redirect_uri": REDIRECT,
                                       "code_challenge": challenge, "code_challenge_method": "S256", "state": "s"},
                 follow_redirects=False)
    return client_id, httpx.URL(r.headers["location"]).params["id"], verifier


def login(http, password="pw", **extra) -> dict:
    client_id, pending, verifier = start_login(http)
    r = http.post("/login", data={"id": pending, "password": password, **extra}, follow_redirects=False)
    code = httpx.URL(r.headers["location"]).params["code"]
    tokens = http.post("/token", data={"grant_type": "authorization_code", "code": code, "redirect_uri": REDIRECT,
                                       "client_id": client_id, "code_verifier": verifier}).json()
    return {**tokens, "client_id": client_id}


def mcp(http, authorization, body=None):
    return http.post("/mcp", json=body or {"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                     headers={"Authorization": authorization, "Accept": "application/json, text/event-stream"},
                     follow_redirects=False)


def test_oauth_login_then_forward(client):
    tokens = login(client)
    assert tokens["access_token"].startswith("tmpx_")
    r = mcp(client, f"Bearer {tokens['access_token']}")
    assert r.status_code == 200 and r.json()["headers"]["authorization"] == "etapi-1"
    assert tokens["access_token"] not in r.text


def test_wrong_password_shows_trilium_rejection(client):
    _, pending, _ = start_login(client)
    r = client.post("/login", data={"id": pending, "password": "nope"}, follow_redirects=False)
    assert r.status_code == 401 and "Wrong password." in r.text


def test_login_without_totp_sends_no_totp_token(client, trilium):
    login(client, totp="")
    assert trilium[1].login_bodies == [{"password": "pw"}]


def test_totp_code_reaches_trilium(client, trilium):
    trilium[1].totp = "123456"
    tokens = login(client, totp=" 123456 ")
    assert trilium[1].login_bodies == [{"password": "pw", "totpToken": "123456"}]
    assert mcp(client, f"Bearer {tokens['access_token']}").status_code == 200


@pytest.mark.parametrize("totp, message", [("", "Two-factor login is on: enter your TOTP code as well."),
                                           ("000000", "Wrong TOTP code.")])
def test_totp_rejections_say_what_is_missing(client, trilium, totp, message):
    trilium[1].totp = "123456"
    _, pending, _ = start_login(client)
    r = client.post("/login", data={"id": pending, "password": "pw", "totp": totp}, follow_redirects=False)
    assert r.status_code == 401 and message in r.text


def test_mcp_without_token_is_401_with_resource_metadata(client):
    r = client.post("/mcp", json={})
    assert r.status_code == 401
    assert f"{BASE}/.well-known/oauth-protected-resource/mcp" in r.headers["www-authenticate"]


def test_post_mcp_without_trailing_slash_is_not_redirected(client):
    assert mcp(client, "raw-123").status_code == 200


def test_raw_etapi_token_passes_through(client):
    assert mcp(client, "raw-123").json()["headers"]["authorization"] == "raw-123"
    assert mcp(client, "Bearer raw-456").json()["headers"]["authorization"] == "raw-456"


def test_wrong_raw_token_gets_triliums_401(client):
    r = mcp(client, "bad")
    assert r.status_code == 401 and r.json() == {"error": "invalid token"}


def test_revoke_logs_out_in_trilium(client, trilium):
    _, state = trilium
    tokens = login(client)
    assert client.post("/revoke", data={"token": tokens["refresh_token"],
                                         "client_id": tokens["client_id"]}).status_code == 200
    assert state.logged_out == ["etapi-1"]
    assert mcp(client, f"Bearer {tokens['access_token']}").status_code == 401


def test_health_reports_trilium(make_client, trilium):
    with make_client() as c:
        assert c.get("/health").json() == {"status": "ok", "trilium": "ok"}
    with make_client(trilium_url="http://127.0.0.1:9") as c:
        r = c.get("/health")
        assert r.status_code == 200 and r.json() == {"status": "ok", "trilium": "unreachable"}


def test_login_page_names_trilium(client):
    _, pending, _ = start_login(client)
    page = client.get("/login", params={"id": pending}).text
    assert "Trilium Notes login" in page and "Trilium password" in page
    assert 'name="totp"' in page and 'autocomplete="one-time-code"' in page


def test_initialize_gets_instructions_through_the_app(client, trilium):
    _, state = trilium
    state.canned = b'event: message\ndata: {"result":{"protocolVersion":"2025-06-18"},"jsonrpc":"2.0","id":1}\n\n'
    r = mcp(client, "raw-123", {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    data = next(l for l in r.text.splitlines() if l.startswith("data:"))
    assert json.loads(data[5:])["result"]["instructions"] == "House rules."


def test_main_exits_on_missing_config(monkeypatch, capsys):
    for name in ("TRILIUM_SERVER_URL", "MCP_BASE_URL", "MCP_OAUTH_SECRET"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(SystemExit) as exit_:
        app_module.main()
    assert exit_.value.code == 1 and "TRILIUM_SERVER_URL" in capsys.readouterr().err
