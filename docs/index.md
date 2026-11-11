---
hide:
  - toc
---

<div class="tm-hero" markdown>

# Sign in to Trilium Notes' MCP server with your password

<p class="tm-hero__lead">Trilium Notes 0.106+ has its own MCP server. trilium-mcp-proxy puts an OAuth login in front of it: add one URL to claude.ai, Claude Code, the Claude apps or any other MCP client, log in once with your Trilium Notes password, and you're done. No ETAPI token to create, paste or rotate.</p>

[Set it up](getting-started.md){ .md-button .md-button--primary } [Connect a client](connecting.md){ .md-button }

</div>

## Why a proxy

On its own, Trilium's MCP server (`/mcp`) takes an ETAPI token in the `Authorization` header. That works, but every client needs a token created under *Options → ETAPI* and pasted into its configuration, and you have to keep track of which token went where.

The proxy is a convenience on top. It adds the login every MCP client already knows (OAuth), and gets out of the way otherwise:

- **Your password stays on your server.** The proxy runs next to Trilium and the login page is its own. The password goes from your browser to the proxy and on to your Trilium, which trades it for an ETAPI token. The proxy never stores or logs it, and the MCP client (claude.ai included) never sees it. See [Security](security.md).
- **Trilium's own tools, unchanged.** Every `/mcp` request goes to Trilium as it is, with only `Authorization` swapped for that client's ETAPI token. New tools from a Trilium update appear without a proxy release.
- **One token per client.** Each login creates its own ETAPI token, listed in Trilium under *Options → ETAPI*. Delete it there and that client is cut off.
- **House rules.** With `MCP_INSTRUCTIONS` set, every client gets your standing instructions when it connects.
- **Tokens still work.** A client configured with an ETAPI token can send it through the proxy as before.

## What it isn't

The proxy doesn't add, rename or filter tools: what you see is exactly Trilium's MCP server. It replaces [trilium-mcp](https://github.com/Marceltov/trilium-mcp), an earlier ETAPI-based MCP server that is archived now that Trilium has its own.
