# Configuration

All configuration is environment variables.

| Variable | Default | Meaning |
|---|---|---|
| `TRILIUM_SERVER_URL` | required¹ | Trilium Notes as the proxy reaches it, e.g. `http://trilium:8080`; served at `/mcp` |
| `TRILIUM_INSTANCES` | required¹ | Several instances, one `name=url` per line or comma; each served at `/<name>/mcp`. See [Several instances](multiple-instances.md) |
| `MCP_BASE_URL` | required | Public URL of the proxy; also the OAuth issuer (`https`, or `http` only for localhost) |
| `MCP_OAUTH_SECRET` | required | Encrypts the stored logins in `/data`; changing it logs every client out |
| `MCP_INSTRUCTIONS` | unset | Added to Trilium's `initialize` result as `instructions` |
| `MCP_INSTRUCTIONS_<NAME>` | unset | With `TRILIUM_INSTANCES`: one instance's instructions instead of `MCP_INSTRUCTIONS` (name uppercased, `-` as `_`) |
| `MCP_PORT` | `8081` | Port the proxy listens on inside the container |
| `LOG_LEVEL` | `INFO` | Python log level |

¹ Exactly one of `TRILIUM_SERVER_URL` and `TRILIUM_INSTANCES`.

A missing or invalid required variable stops the container at startup with a message naming it.

## Data volume

Mount a volume at `/data`. It holds the OAuth store (registered clients, refresh tokens and each login's ETAPI token), encrypted with a key derived from `MCP_OAUTH_SECRET`. Without the volume, every container restart logs all clients out.

## House rules

`MCP_INSTRUCTIONS` is the one thing the proxy adds to Trilium's answers: it becomes the `instructions` field of the `initialize` result, which MCP clients read when they connect. Use it for standing rules, for example:

```yaml
      MCP_INSTRUCTIONS: |
        This Trilium contains an LLM-maintained wiki. Search for #llmWikiSchema,
        read that note and follow it. Never write under "Sources".
```

## Endpoints

| Path | What |
|---|---|
| `/mcp` | Trilium's MCP server, behind the login (with several instances: `/<name>/mcp`) |
| `/health` | `{"status": "ok", "trilium": "ok" \| "unreachable"}`, no login needed |
| `/.well-known/…`, `/authorize`, `/token`, `/register`, `/revoke` and the login page | The OAuth endpoints MCP clients find and use on their own |
