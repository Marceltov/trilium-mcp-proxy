# Security

## Where your password goes

Only to your own servers. The login page is served by the proxy, which you run next to Trilium:

1. The MCP client (say claude.ai) sends your browser to the proxy's `/authorize` page.
2. You type the Trilium Notes password there. The browser posts it to the proxy, over your HTTPS.
3. The proxy posts it to Trilium's `/etapi/auth/login` and gets back a new ETAPI token for this client. The password is not stored and not logged.
   With two-factor login on, the TOTP code (or a recovery code) goes along the same way. Trilium checks it on ETAPI logins from the release after 0.106.1 on; older versions accept the password alone.
4. The client receives an authorization code and trades it for opaque OAuth tokens. Those tokens mean nothing outside your proxy.

The MCP client never sees the password and never sees the ETAPI token.

## What is stored

In `/data`, encrypted with a key derived from `MCP_OAUTH_SECRET`:

- the registered clients,
- for each login, its OAuth tokens and the ETAPI token Trilium issued for it.

Anyone with the volume *and* the secret could use those ETAPI tokens, so keep `MCP_OAUTH_SECRET` out of the compose file (use `.env`) and treat the volume like Trilium's own data.

## Cutting a client off

Every login has its own ETAPI token, shown in Trilium under *Options → ETAPI*. Delete it there and the client is locked out on its next request. Revoking from the client side does the same: the proxy logs the token out in Trilium.

Changing `MCP_OAUTH_SECRET` logs every client out at once. Their ETAPI tokens stay in Trilium until you delete them.

## Failed logins

A wrong password is answered after a short delay, which slows down guessing. Every attempt is a real login against Trilium.

## What the proxy can't protect

A client that is logged in has full access to your notes, exactly as with an ETAPI token: Trilium's MCP server has no read-only mode. Only connect clients you trust, and remove the ones you no longer use.
