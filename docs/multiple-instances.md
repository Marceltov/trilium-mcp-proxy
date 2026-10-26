# Several instances

One proxy can serve several Trilium Notes instances, for example one per person plus a shared one. Each gets its own path under the same hostname:

```
https://trilium-mcp-proxy.example.org/marcel/mcp
https://trilium-mcp-proxy.example.org/bille/mcp
https://trilium-mcp-proxy.example.org/shared/mcp
```

Each path is a separate login: its own login page (checked against that instance's password), its own OAuth issuer and its own stored logins. A token from one instance is refused by every other, so logging in to one never opens another.

## Configure it

Replace `TRILIUM_SERVER_URL` with `TRILIUM_INSTANCES`, one `name=url` per line (or separated by commas):

```yaml
  trilium-mcp-proxy:
    image: ghcr.io/marceltov/trilium-mcp-proxy:latest
    restart: unless-stopped
    environment:
      TRILIUM_INSTANCES: |
        marcel=http://trilium-marcel:8080
        bille=http://trilium-bille:8080
        shared=http://trilium-shared:8080
      MCP_BASE_URL: https://trilium-mcp-proxy.example.org
      MCP_OAUTH_SECRET: ${MCP_OAUTH_SECRET}
      MCP_INSTRUCTIONS: Shared house rules for every instance.
      MCP_INSTRUCTIONS_MARCEL: |
        This Trilium contains an LLM-maintained wiki. Search for #llmWikiSchema first.
    volumes:
      - mcp-proxy-oauth:/data
    ports:
      - "8081:8081"
```

- **Names** are the path segment: lowercase letters, digits and hyphens. `health`, `mcp`, `authorize`, `token`, `register`, `revoke` and `login` are reserved.
- **URLs** are each Trilium as the proxy reaches it. When the instances live in other compose projects, put the proxy on their networks (or use addresses it can reach).
- **Instructions:** `MCP_INSTRUCTIONS_<NAME>` (name uppercased, hyphens as underscores) sets one instance's house rules; instances without one get `MCP_INSTRUCTIONS`.
- Turn on the MCP server in every instance (*Options → AI / LLM → MCP server*).

`TRILIUM_SERVER_URL` and `TRILIUM_INSTANCES` can't both be set. With `TRILIUM_SERVER_URL` the proxy keeps serving one Trilium at `/mcp`, exactly as before.

## Connect

Add each instance as its own connector or server, with its path:

```bash
claude mcp add --transport http trilium https://trilium-mcp-proxy.example.org/marcel/mcp -s user
claude mcp add --transport http trilium-shared https://trilium-mcp-proxy.example.org/shared/mcp -s user
```

Each one opens that instance's login page; sign in with that instance's password.

## Health

`/health` lists every instance:

```json
{"status": "ok", "instances": {"marcel": "ok", "bille": "ok", "shared": "unreachable"}}
```

`/<name>/health` reports one, in the single-instance shape (`{"status": "ok", "trilium": "ok"}`), which suits one uptime monitor per instance.

## Under the hood

Instance `marcel`'s issuer is `MCP_BASE_URL/marcel`. Its OAuth endpoints live under `/marcel/` (`/marcel/authorize`, `/marcel/token`, `/marcel/login`, …), and its metadata sits where RFC 8414 and RFC 9728 put it for an issuer with a path: `/.well-known/oauth-authorization-server/marcel` and `/.well-known/oauth-protected-resource/marcel/mcp`. MCP clients find all of it on their own from the `401` they get at `/marcel/mcp`.

Logins are stored per instance in `/data/oauth/<name>`. Switching an existing single-instance proxy to `TRILIUM_INSTANCES` changes its URLs, so clients connect and log in again.
