import json

from conftest import call
from fake_trilium import dumps
from trilium_mcp_proxy.forward import Forwarder
from trilium_mcp_proxy.inject import inject_instructions

GRANT = {"etapi_token": "etapi-1"}
RESULT = {"protocolVersion": "2025-06-18", "capabilities": {"tools": {"listChanged": True}},
          "serverInfo": {"name": "trilium-notes", "version": "0.106.1"}}
TRILIUM_INIT = b"event: message\ndata: " + dumps({"result": RESULT, "jsonrpc": "2.0", "id": 1}) + b"\n\n"
INIT_REQ = dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})


def sse_result(body: bytes) -> dict:
    line = next(l for l in body.replace(b"\r\n", b"\n").split(b"\n") if l.startswith(b"data:"))
    return json.loads(line[5:])["result"]


def test_sse_initialize_gets_instructions():
    out = inject_instructions(TRILIUM_INIT, "text/event-stream", "House rules.")
    assert sse_result(out)["instructions"] == "House rules."
    assert out.startswith(b"event: message\n") and out.endswith(b"\n\n")


def test_existing_instructions_are_kept_first():
    body = b"data: " + dumps({"result": {**RESULT, "instructions": "Trilium's own."}, "jsonrpc": "2.0",
                               "id": 1}) + b"\n\n"
    assert sse_result(inject_instructions(body, "text/event-stream", "Ours."))["instructions"] == \
        "Trilium's own.\n\nOurs."


def test_json_initialize_gets_instructions():
    body = dumps({"result": RESULT, "jsonrpc": "2.0", "id": 1})
    out = json.loads(inject_instructions(body, "application/json; charset=utf-8", "Ours."))
    assert out["result"]["instructions"] == "Ours."


def test_unparseable_body_returned_unchanged():
    for body in (b"data: {not json\n\n", b"", b"\xff\xfe"):
        assert inject_instructions(body, "text/event-stream", "Ours.") == body
    assert inject_instructions(b"{nope", "application/json", "Ours.") == b"{nope"


async def test_crlf_and_split_chunks(trilium, upstream):
    _, state = trilium
    state.canned, state.canned_chunks = TRILIUM_INIT.replace(b"\n", b"\r\n"), 3
    r = await call(Forwarder(upstream, instructions="House rules."), body=INIT_REQ, grant=GRANT)
    assert r.status == 200 and sse_result(r.body)["instructions"] == "House rules."
    assert int(r.headers["content-length"]) == len(r.body)


async def test_non_initialize_is_byte_identical(trilium, upstream):
    _, state = trilium
    note = b"event: message\ndata: " + dumps({"result": {"content": [{"type": "text", "text":
            '{"protocolVersion": "2025-06-18"} lives in this note'}]}, "jsonrpc": "2.0", "id": 2}) + b"\n\n"
    state.canned, state.canned_chunks = note, 2
    req = dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "get_note"}})
    r = await call(Forwarder(upstream, instructions="House rules."), body=req, grant=GRANT)
    assert r.body == note


async def test_no_instructions_configured_streams_initialize_untouched(trilium, upstream):
    _, state = trilium
    state.canned = TRILIUM_INIT
    r = await call(Forwarder(upstream), body=INIT_REQ, grant=GRANT)
    assert r.body == TRILIUM_INIT


async def test_batch_or_invalid_request_is_not_injected(trilium, upstream):
    _, state = trilium
    state.canned = TRILIUM_INIT
    for req in (b"[" + INIT_REQ + b"]", b"{broken"):
        r = await call(Forwarder(upstream, instructions="House rules."), body=req, grant=GRANT)
        assert r.body == TRILIUM_INIT
