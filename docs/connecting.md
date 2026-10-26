# Connect a client

Every client gets the same URL, the proxy's `MCP_BASE_URL` plus `/mcp`, for example `https://trilium-mcp-proxy.example.org/mcp`. The first time, the client opens the proxy's login page in your browser; enter your Trilium Notes password. After that the client refreshes its tokens on its own.

=== "claude.ai and the Claude apps"

    1. *Customize → Connectors → Add custom connector*.
    2. A name (for example `Trilium Notes`) and the URL. Keep the detected OAuth settings.
    3. Sign in with your Trilium Notes password on the page that opens.
    4. In a chat, switch the connector on under **+ → Connectors**.

    A connector added on claude.ai is also available in the Claude desktop and mobile apps.

=== "Claude Code"

    ```bash
    claude mcp add --transport http trilium https://trilium-mcp-proxy.example.org/mcp -s user
    ```

    Restart Claude Code, run `/mcp`, pick `trilium` and choose **Authenticate**. A browser opens on the proxy's login page.

=== "Other MCP clients"

    Add the URL as a streamable HTTP server. Any client that supports MCP's OAuth flow finds the login on its own through the proxy's `/.well-known/oauth-protected-resource` and `/.well-known/oauth-authorization-server` metadata.

## With an ETAPI token instead

If a client is already set up with an ETAPI token (*Options → ETAPI*), it can keep it:

```bash
claude mcp add --transport http trilium https://trilium-mcp-proxy.example.org/mcp \
  -H "Authorization: Bearer <token>" -s user
```

The proxy forwards the token unchanged, with or without `Bearer`, and Trilium checks it. A token-based client can just as well talk to Trilium's `/mcp` directly; through the proxy it also gets `MCP_INSTRUCTIONS`.

## Disconnect a client

Each login creates its own ETAPI token, listed in Trilium under *Options → ETAPI*. Either:

- remove the connector or server in the client, which revokes the login and logs its token out in Trilium, or
- delete the token in Trilium, which cuts the client off at once.
