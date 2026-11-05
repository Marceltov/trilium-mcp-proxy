"""Re-save notes written through Trilium's MCP tools over ETAPI, so that Trilium records their links.

Trilium's MCP write tools store a note's content without scanning it for links, so the notes they write
get no internalLink relations: the note map, backlinks and searches on ~internalLink miss them. ETAPI's
content PUT does scan. So after such a tool call succeeds, the proxy reads the note's content and writes
it back unchanged through ETAPI, with the client's own token, before the client sees the result. Not
needed any more once Trilium's tools scan links themselves.
"""

import json
import logging

import httpx

log = logging.getLogger("trilium_mcp_proxy")

WRITE_TOOLS = {"create_note", "set_note_content", "append_to_note", "edit_note_content"}


def writes_note(body: bytes) -> bool:
    """A single JSON-RPC call of one of the tools that write a note's content."""
    try:
        message = json.loads(body)
    except ValueError:
        return False
    if not isinstance(message, dict) or message.get("method") != "tools/call":
        return False
    params = message.get("params")
    return isinstance(params, dict) and params.get("name") in WRITE_TOOLS


def _messages(body: bytes, content_type: str):
    if content_type.split(";")[0].strip().lower() == "text/event-stream":
        payloads = [line[5:] for line in body.splitlines() if line.startswith(b"data:")]
    else:
        payloads = [body]
    for payload in payloads:
        try:
            yield json.loads(payload)
        except ValueError:
            continue


def written_note_id(body: bytes, content_type: str) -> str | None:
    """The noteId in a successful tool result. Trilium returns the tool's result as JSON text."""
    for message in _messages(body, content_type):
        result = message.get("result") if isinstance(message, dict) else None
        if not isinstance(result, dict) or result.get("isError"):
            continue
        for item in result.get("content") or []:
            try:
                data = json.loads(item.get("text", ""))
            except (AttributeError, TypeError, ValueError):
                continue
            if isinstance(data, dict) and data.get("success") and isinstance(data.get("noteId"), str):
                return data["noteId"]
    return None


async def relink(trilium: httpx.AsyncClient, token: str, note_id: str) -> None:
    """Write the note's content back unchanged, which makes Trilium scan it for links. A failure is
    logged and otherwise ignored: the tool call itself succeeded."""
    url = f"/etapi/notes/{note_id}/content"
    headers = {"Authorization": token}
    try:
        r = await trilium.get(url, headers=headers, timeout=30)
        if r.is_success:
            r = await trilium.put(url, headers={**headers, "Content-Type": "text/plain; charset=utf-8"},
                                  content=r.content, timeout=30)
    except httpx.HTTPError as e:
        log.warning("Could not re-save note %s for its links: %s", note_id, type(e).__name__)
        return
    if not r.is_success:
        log.warning("Could not re-save note %s for its links: HTTP %s", note_id, r.status_code)
