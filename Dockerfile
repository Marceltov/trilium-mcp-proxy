# trilium-mcp-proxy: OAuth front for Trilium Notes' built-in MCP server.
#
# Multi-stage: resolve the venv with uv (git only here: mcp-login-oauth is pinned by git tag),
# then ship just the venv on python-slim, as a non-root user.

FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder
ENV UV_PYTHON_PREFERENCE=only-system \
    UV_PYTHON_DOWNLOADS=never \
    UV_COMPILE_BYTECODE=1
RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml uv.lock README.md LICENSE ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
RUN uv sync --frozen --no-dev --no-editable

FROM python:3.12-slim
ARG APP_VERSION=dev
RUN useradd --system --uid 10001 --home-dir /app mcp \
    && mkdir -p /data && chown mcp /data
COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    APP_VERSION=${APP_VERSION}
USER mcp
VOLUME /data
EXPOSE 8081
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/health' % os.environ.get('MCP_PORT', '8081'), timeout=4)"
CMD ["trilium-mcp-proxy"]
