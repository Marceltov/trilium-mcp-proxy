---
status: accepted
date: 2026-10-25
decision-makers: Marcel Bruckner
---

# A transparent OAuth proxy in front of Trilium's built-in MCP server

## Context and Problem Statement

Trilium Notes 0.106 has its own MCP server at `/mcp`, maintained upstream, with partial edits
(`edit_note_content`, `append_to_note`) that trilium-mcp's generated ETAPI tools lack. It
authenticates only with an ETAPI token in the `Authorization` header. claude.ai's connector can't send
one; it only does OAuth. How do OAuth-only clients get Trilium's official tools?

## Considered Options

* **Extend trilium-mcp** with a proxy mode next to its generated tools.
* **Contribute OAuth to Trilium upstream.** It's parked for now; it would also need a maintainer
  decision.
* **A separate, transparent proxy:** OAuth in front, every request forwarded unchanged, only
  `Authorization` swapped.

## Decision Outcome

Chosen: **a separate, transparent proxy**. It does one job, so trilium-mcp stays as it is, and it can
be retired later without touching the proxy. Transparency means Trilium's tool list is exactly what
clients see: new tools arrive with a Trilium update, not with a proxy release.

The one rewrite is adding `MCP_INSTRUCTIONS` to the `initialize` result. Clients read standing
instructions only from there, and the LLM wiki's house rules depend on them. Only that small response is
read whole; everything else streams.

The login is [mcp-login-oauth](https://github.com/Marceltov/mcp-login-oauth) with the Trilium password.
Each login mints its own ETAPI token, so a client can be cut off in Trilium's *Options → ETAPI*.

### Consequences

* Good, because claude.ai, the desktop and mobile apps get Trilium's official tools with a one-time
  login, and Claude Code can keep using a plain ETAPI token.
* Good, because the proxy holds no Trilium tool knowledge that could go stale.
* Bad, because a proxy-side change to tool behaviour (renaming, filtering) is deliberately impossible.
  That would be a different project.
* Bad, because each login leaves an ETAPI token in Trilium until it's revoked or deleted by hand.
