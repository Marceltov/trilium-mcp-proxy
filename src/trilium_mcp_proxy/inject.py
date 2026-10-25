"""Add the house rules (MCP_INSTRUCTIONS) to the result of Trilium's initialize response.

This is the proxy's one rewrite. Trilium answers initialize as a server-sent event; a plain JSON answer is
handled the same way. Anything that doesn't parse as expected is returned unchanged.
"""

import json


def _with_instructions(message, instructions: str):
    """The JSON-RPC message with instructions added, or None when it isn't an initialize result."""
    result = message.get("result") if isinstance(message, dict) else None
    if not isinstance(result, dict) or "protocolVersion" not in result:
        return None
    own = result.get("instructions")
    merged = f"{own}\n\n{instructions}" if isinstance(own, str) and own.strip() else instructions
    return {**message, "result": {**result, "instructions": merged}}


def inject_instructions(body: bytes, content_type: str, instructions: str) -> bytes:
    if content_type.split(";")[0].strip().lower() == "text/event-stream":
        lines = body.splitlines(keepends=True)
        for i, line in enumerate(lines):
            if not line.startswith(b"data:"):
                continue
            payload = line[5:]
            ending = payload[len(payload.rstrip(b"\r\n")):]
            try:
                message = json.loads(payload)
            except ValueError:
                continue
            if (changed := _with_instructions(message, instructions)) is not None:
                lines[i] = b"data: " + json.dumps(changed, ensure_ascii=False).encode() + ending
        return b"".join(lines)
    try:
        changed = _with_instructions(json.loads(body), instructions)
    except ValueError:
        return body
    return body if changed is None else json.dumps(changed, ensure_ascii=False).encode()
