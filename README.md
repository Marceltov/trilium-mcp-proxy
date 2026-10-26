# trilium-mcp-proxy

<p>
  <a href="https://github.com/Marceltov/trilium-mcp-proxy/pkgs/container/trilium-mcp-proxy">
    <img alt="GHCR image" src="https://img.shields.io/github/v/release/Marceltov/trilium-mcp-proxy?logo=docker&logoColor=white&label=ghcr.io%2Fmarceltov%2Ftrilium-mcp-proxy&color=2496ED">
  </a>
  <a href="LICENSE">
    <img alt="License: AGPL v3" src="https://img.shields.io/badge/License-AGPL_v3-blue.svg">
  </a>
</p>

An OAuth front for the MCP server that [Trilium Notes](https://triliumnotes.org) 0.106+ has built in
at `/mcp`. On its own, Trilium's MCP server takes an ETAPI token in the `Authorization` header, so
every client needs a token created under *Options → ETAPI* and pasted into its configuration.

The proxy is a convenience on top: you add its URL to any MCP client (claude.ai, Claude Code, the
Claude desktop and mobile apps, …) and log in once with your Trilium password. No token to create,
paste or rotate.
- **Login:** a client logs in once in the browser with the **Trilium password**, which creates an ETAPI
  token for that client. The client then only holds opaque OAuth tokens that refresh on their own.
- **Your password stays on your server:** the proxy runs next to Trilium and the login page is its
  own. The password goes only from your browser to that page and on to your Trilium's
  `/etapi/auth/login`; the proxy never stores or logs it. The MCP client (claude.ai included) never
  sees it, only opaque OAuth tokens that work nowhere but your proxy.
- **Forwarding:** every `/mcp` request goes **unchanged** to Trilium, with only `Authorization` swapped
  for that client's ETAPI token. Responses stream back as they arrive. The tools are exactly Trilium's
  own, so new ones from a Trilium update appear without a proxy release.
- **House rules:** with `MCP_INSTRUCTIONS` set, the proxy adds your standing instructions to Trilium's
  `initialize` answer, which every client reads at connect. That's the only rewrite.
- **Header clients still work:** a client that already has an ETAPI token (Claude Code) can send it, with
  or without `Bearer`, and it's forwarded as is.
- **Revocation:** revoking a client's login logs its ETAPI token out in Trilium.

The login comes from [mcp-login-oauth](https://github.com/Marceltov/mcp-login-oauth). It replaces
[trilium-mcp](https://github.com/Marceltov/trilium-mcp), an ETAPI-based MCP server that is archived now
that Trilium has its own.

## Run it

Enable Trilium's MCP server first: *Options → AI / LLM → MCP server*. Then add the proxy next to
Trilium:

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

Put it behind a TLS reverse proxy at `MCP_BASE_URL`. `GET /health` answers
`{"status": "ok", "trilium": "ok" | "unreachable"}`.

| Variable | Default | Meaning |
|---|---|---|
| `TRILIUM_SERVER_URL` | required | Trilium Notes as the proxy reaches it, e.g. `http://trilium:8080` |
| `MCP_BASE_URL` | required | Public URL of the proxy; also the OAuth issuer (`https`, or `http` only for localhost) |
| `MCP_OAUTH_SECRET` | required | Encrypts the stored logins in `/data`; changing it logs every client out |
| `MCP_INSTRUCTIONS` | unset | Added to Trilium's `initialize` result as `instructions` |
| `MCP_PORT` | `8081` | |

## Connect a client

- **claude.ai** (and the desktop and mobile apps): *Customize → Connectors → Add custom connector* with
  `https://<your proxy>/mcp`. claude.ai opens the proxy's login page; enter your Trilium password.
- **Claude Code:** either the same URL (Claude Code does OAuth too), or with an ETAPI token from
  *Options → ETAPI*:
  `claude mcp add --transport http trilium https://<your proxy>/mcp -H "Authorization: Bearer <token>" -s user`.
  With a token, Claude Code can also talk to Trilium's `/mcp` directly. The proxy only adds the house
  rules then.

Each OAuth login creates its own ETAPI token, which shows up in Trilium under *Options → ETAPI*.
Deleting it there cuts that client off. Revoking the login from the client deletes it too.

## Development

```bash
uv sync
uv run pytest -q --ignore=tests/live   # unit tests, against a fake Trilium
./run-tests.sh -q                     # unit + live, against a disposable Trilium 0.106.1 (Docker)
```

## License

Copyright © 2026 Marcel Bruckner.

Licensed under the [GNU Affero General Public License v3.0 or later](LICENSE) (AGPL-3.0-or-later). You may use, modify, and redistribute it, but any modified version — **including one you run as a network service** — must be released under the same license with its source made available to its users, and the original copyright notice preserved. See [LICENSE](LICENSE) for the full terms.
