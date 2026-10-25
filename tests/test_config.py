import pytest

from trilium_mcp_proxy.config import Config, ConfigError, load_config

ENV = {"TRILIUM_SERVER_URL": "http://trilium:8080/", "MCP_BASE_URL": "https://proxy.example/",
       "MCP_OAUTH_SECRET": "s"}


def test_minimal_config():
    assert load_config(ENV) == Config(trilium_url="http://trilium:8080", base_url="https://proxy.example",
                                      oauth_secret="s", instructions=None, port=8081)


@pytest.mark.parametrize("name", ["TRILIUM_SERVER_URL", "MCP_BASE_URL", "MCP_OAUTH_SECRET"])
def test_missing_required_names_it(name):
    with pytest.raises(ConfigError, match=name):
        load_config({k: v for k, v in ENV.items() if k != name})


def test_base_url_must_be_valid_issuer():
    with pytest.raises(ConfigError, match="MCP_BASE_URL"):
        load_config({**ENV, "MCP_BASE_URL": "http://x.example"})
    assert load_config({**ENV, "MCP_BASE_URL": "http://localhost:8081"}).base_url == "http://localhost:8081"


def test_port_must_be_int():
    with pytest.raises(ConfigError, match="MCP_PORT"):
        load_config({**ENV, "MCP_PORT": "eighty"})
    assert load_config({**ENV, "MCP_PORT": "9000"}).port == 9000


def test_blank_instructions_are_none():
    assert load_config({**ENV, "MCP_INSTRUCTIONS": "  \n"}).instructions is None
    assert load_config({**ENV, "MCP_INSTRUCTIONS": "Rules.\n"}).instructions == "Rules."
