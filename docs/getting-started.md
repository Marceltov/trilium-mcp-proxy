# Quick start

You need Trilium Notes 0.106 or later, Docker Compose, and a reverse proxy that serves HTTPS (Caddy, Traefik, nginx, Cloudflare Tunnel, …).

## 1. Turn on Trilium's MCP server

In Trilium Notes: *Options → AI / LLM*, switch on **MCP server**. Trilium now serves `/mcp`.

## 2. Add the proxy next to Trilium

In the same `docker-compose.yaml` as Trilium:

```yaml
services:
  trilium:
    image: triliumnext/trilium:v0.106.1
    # ...

  trilium-mcp-proxy:
    image: ghcr.io/marceltov/trilium-mcp-proxy:latest   # or pin a version
    restart: unless-stopped
    environment:
      TRILIUM_SERVER_URL: http://trilium:8080
      MCP_BASE_URL: https://trilium-mcp-proxy.example.org   # the public URL, behind your TLS proxy
      MCP_OAUTH_SECRET: ${MCP_OAUTH_SECRET}                 # openssl rand -hex 32
      MCP_INSTRUCTIONS: |
        Optional standing instructions every client sees at connect.
    volumes:
      - mcp-proxy-oauth:/data
    ports:
      - "8081:8081"

volumes:
  mcp-proxy-oauth:
```

Put the secret in a `.env` file next to the compose file:

```bash
echo "MCP_OAUTH_SECRET=$(openssl rand -hex 32)" >> .env
docker compose up -d trilium-mcp-proxy
```

`TRILIUM_SERVER_URL` is Trilium as the proxy reaches it: in the same compose project that's the service name, here `http://trilium:8080`.

## 3. Publish it over HTTPS

Point your reverse proxy at port 8081 under the hostname in `MCP_BASE_URL`. With Caddy:

```
trilium-mcp-proxy.example.org {
    reverse_proxy localhost:8081
}
```

`MCP_BASE_URL` must match the public URL exactly: it's the OAuth issuer, and clients compare it byte for byte. Plain `http` is only accepted for `localhost`.

Check it:

```bash
curl https://trilium-mcp-proxy.example.org/health
# {"status": "ok", "trilium": "ok"}
```

`"trilium": "unreachable"` means the proxy runs but can't reach `TRILIUM_SERVER_URL`.

## 4. Connect a client

Add `https://trilium-mcp-proxy.example.org/mcp` to your client and log in with your Trilium Notes password. See [Connect a client](connecting.md).
