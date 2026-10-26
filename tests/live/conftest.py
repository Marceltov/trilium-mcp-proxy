"""Live tests drive the dev stack from docker-compose.yaml (run-tests.sh starts it).

The targets are pinned to the in-repo fixture and never read from the environment, so they can't
point at a real Trilium.
"""

import httpx
import pytest

PROXY = "http://localhost:9291"
PROXY_MULTI = "http://localhost:9292"  # the same image with TRILIUM_INSTANCES (notes, other)
PASSWORD = "trilium-mcp"  # the fixture's throwaway password (see fixture/README.md)


def _up() -> bool:
    try:
        return httpx.get(f"{PROXY}/health", timeout=2).status_code == 200
    except httpx.HTTPError:
        return False


def pytest_collection_modifyitems(items):
    if not _up():
        skip = pytest.mark.skip(reason=f"dev stack not running at {PROXY} (use run-tests.sh)")
        for item in items:
            if "/live/" in str(item.fspath):
                item.add_marker(skip)
