import json

from conftest import call
from fake_trilium import dumps
from trilium_mcp_proxy.forward import Forwarder
from trilium_mcp_proxy.relink import writes_note, written_note_id

GRANT = {"etapi_token": "etapi-1"}


def tool_call(name: str, **arguments) -> bytes:
    return dumps({"jsonrpc": "2.0", "id": 7, "method": "tools/call", "params": {"name": name, "arguments": arguments}})


def tool_result(result: dict, is_error=False) -> bytes:
    """A tool result as Trilium sends it: the tool's own result as JSON text, in one server-sent event."""
    message = {"result": {"content": [{"type": "text", "text": json.dumps(result)}]}, "jsonrpc": "2.0", "id": 7}
    if is_error:
        message["result"]["isError"] = True
    return b"event: message\ndata: " + dumps(message) + b"\n\n"


def test_writes_note_only_for_content_writing_tools():
    assert all(writes_note(tool_call(name)) for name in
               ("create_note", "set_note_content", "append_to_note", "edit_note_content"))
    assert not writes_note(tool_call("get_note"))
    assert not writes_note(tool_call("set_attribute"))
    assert not writes_note(dumps([json.loads(tool_call("set_note_content"))]))  # a batch
    assert not writes_note(b"not json")


def test_written_note_id_from_event_stream_and_json():
    sse = tool_result({"success": True, "noteId": "abc123", "title": "T"})
    assert written_note_id(sse, "text/event-stream") == "abc123"
    plain = sse.split(b"data: ")[1].strip()
    assert written_note_id(plain, "application/json") == "abc123"


def test_no_note_id_from_failed_call():
    assert written_note_id(tool_result({"error": "Note not found"}, is_error=True), "text/event-stream") is None
    assert written_note_id(tool_result({"success": False, "noteId": "abc123"}), "text/event-stream") is None
    assert written_note_id(b"event: message\ndata: {broken\n\n", "text/event-stream") is None


async def test_write_tool_resaves_note_before_responding(trilium, upstream):
    _, state = trilium
    state.contents["abc123"] = '<p><a href="#root/xyz">ü</a></p>'.encode()
    state.canned, state.canned_chunks = tool_result({"success": True, "noteId": "abc123"}), 3
    r = await call(Forwarder(upstream), body=tool_call("set_note_content", noteId="abc123", content="x"),
                   grant=GRANT)
    assert r.status == 200 and r.body == state.canned
    assert int(r.headers["content-length"]) == len(state.canned)
    assert state.content_calls == [("GET", "abc123", "etapi-1"), ("PUT", "abc123", "etapi-1")]
    assert state.contents["abc123"] == '<p><a href="#root/xyz">ü</a></p>'.encode()  # written back unchanged


async def test_failed_write_and_read_tools_leave_note_alone(trilium, upstream):
    _, state = trilium
    state.contents["abc123"] = b"<p>x</p>"
    state.canned = tool_result({"error": "Note not found"}, is_error=True)
    await call(Forwarder(upstream), body=tool_call("append_to_note", noteId="abc123", content="x"), grant=GRANT)
    state.canned = tool_result({"success": True, "noteId": "abc123"})
    await call(Forwarder(upstream), body=tool_call("get_note", noteId="abc123"), grant=GRANT)
    assert state.content_calls == []


async def test_resave_failure_still_returns_tool_result(trilium, upstream):
    _, state = trilium  # no contents: the ETAPI read is a 404
    state.canned = tool_result({"success": True, "noteId": "gone"})
    r = await call(Forwarder(upstream), body=tool_call("create_note", parentNoteId="root", title="t"), grant=GRANT)
    assert r.status == 200 and r.body == state.canned
    assert state.content_calls == [("GET", "gone", "etapi-1")]
