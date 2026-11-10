# How it works

```mermaid
flowchart LR
  client["MCP client<br>claude.ai, Claude Code, …"] -- "OAuth token" --> proxy["trilium-mcp-proxy"]
  browser["Your browser"] -- "Trilium password<br>(once, at login)" --> proxy
  proxy -- "ETAPI token for this client" --> mcp["Trilium /mcp"]
  proxy -- "password → token<br>/etapi/auth/login" --> etapi["Trilium ETAPI"]
```

The client only ever holds the proxy's OAuth tokens. The proxy swaps them for the client's ETAPI token on every request.

## Login

```mermaid
sequenceDiagram
  participant C as MCP client
  participant B as Browser
  participant P as Proxy
  participant T as Trilium
  C->>P: POST /mcp (no token)
  P-->>C: 401, resource metadata
  C->>P: register, then send the browser to /authorize
  B->>P: Trilium password
  P->>T: /etapi/auth/login
  T-->>P: new ETAPI token
  P-->>B: redirect with code
  C->>P: /token (code)
  P-->>C: OAuth access and refresh token
```

The login comes from [mcp-login-oauth](https://github.com/Marceltov/mcp-login-oauth), a small OAuth 2.1 server for MCP servers whose login is a form checked by the service behind them.

## Requests

Every request to `/mcp` with a valid OAuth token is forwarded to Trilium's `/mcp` unchanged, with only `Authorization` replaced by that client's ETAPI token. Responses stream back as they arrive, so long tool calls and event streams stay open as long as Trilium keeps them.

The one exception is the `initialize` answer: with `MCP_INSTRUCTIONS` set, the proxy adds it as `instructions`. Only that small response is read whole.

A request with a raw ETAPI token instead of an OAuth token is forwarded as is, and Trilium decides whether it's valid.

## Why a separate proxy

Trilium's built-in server is maintained upstream and gets new tools with every release; a transparent proxy picks them up for free. Adding OAuth to Trilium itself would be the cleaner end state, and the proxy can retire without anyone's tools changing. The decision is recorded in [ADR 0001](https://github.com/Marceltov/trilium-mcp-proxy/blob/main/docs/adr/0001-transparent-oauth-proxy-for-trilium-mcp.md).
