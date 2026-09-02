import json
import sqlite3
from pathlib import Path

from harness_metrics.providers.jsonl import parse_common
from harness_metrics.providers.cursor import CursorAdapter
from harness_metrics.providers.kiro import KiroAdapter
from harness_metrics.providers.codex import CodexAdapter
from harness_metrics.providers.opencode import OpenCodeAdapter
from harness_metrics.providers.antigravity import AntigravityAdapter


def test_parses_claude_message_usage(tmp_path: Path):
    log = tmp_path / "session.jsonl"
    log.write_text(json.dumps({
        "timestamp": "2026-08-31T00:00:00Z", "sessionId": "abc",
        "message": {"model": "claude-sonnet", "usage": {"input_tokens": 12, "output_tokens": 4}},
    }))
    event = list(parse_common(log, "claude"))[0]
    assert (event.input_tokens, event.output_tokens, event.model) == (12, 4, "claude-sonnet")


def test_claude_repeated_request_records_share_one_event_id(tmp_path: Path):
    log = tmp_path / "session.jsonl"
    records = [
        {"timestamp": f"2026-08-31T00:00:0{index}Z", "requestId": "request-1",
         "message": {"model": "claude-fable", "usage": {
             "input_tokens": 2, "output_tokens": 10,
             "cache_read_input_tokens": 1000,
         }}}
        for index in range(3)
    ]
    log.write_text("\n".join(json.dumps(record) for record in records))
    events = list(parse_common(log, "claude"))
    assert len(events) == 3
    assert len({event.id for event in events}) == 1


def test_parses_codex_nested_incremental_usage(tmp_path: Path):
    log = tmp_path / "session.jsonl"
    log.write_text(json.dumps({
        "timestamp": "2026-08-31T00:00:00Z", "type": "event_msg",
        "payload": {"type": "token_count", "info": {"last_token_usage": {
            "input_tokens": 20, "cached_input_tokens": 5, "output_tokens": 7,
        }}},
    }))
    event = list(parse_common(log, "codex"))[0]
    assert (event.input_tokens, event.cache_read_tokens, event.output_tokens) == (15, 5, 7)


def test_codex_propagates_turn_context_model_to_usage(tmp_path: Path):
    log = tmp_path / "session.jsonl"
    log.write_text("\n".join([
        json.dumps({"type": "turn_context", "payload": {"model": "gpt-5.6-codex", "cwd": str(tmp_path)}}),
        json.dumps({"type": "event_msg", "payload": {"type": "token_count", "info": {
            "last_token_usage": {"input_tokens": 20, "output_tokens": 7},
        }}}),
    ]))
    event = list(CodexAdapter().parse(log))[0]
    assert event.model == "gpt-5.6-codex"


def test_event_cwd_takes_precedence_over_encoded_project_hint(tmp_path: Path):
    log = tmp_path / "session.jsonl"
    log.write_text(json.dumps({
        "timestamp": "2026-08-31T00:00:00Z", "cwd": "/Users/example/My-Project",
        "usage": {"input_tokens": 12, "output_tokens": 4},
    }))
    event = list(parse_common(log, "claude", "-Users-example-My-Project"))[0]
    assert event.project_path == "/Users/example/My-Project"


def test_nested_working_directory_resolves_to_repository_root(tmp_path: Path):
    repository = tmp_path / "project"
    nested = repository / "src" / "feature"
    nested.mkdir(parents=True)
    (repository / ".git").mkdir()
    log = tmp_path / "nested.jsonl"
    log.write_text(json.dumps({
        "timestamp": "2026-08-31T00:00:00Z", "cwd": str(nested),
        "usage": {"input_tokens": 12},
    }))
    event = list(parse_common(log, "claude"))[0]
    assert event.project_path == str(repository)


def test_cursor_counts_tool_calls_and_marks_local_token_estimates(tmp_path: Path):
    log = tmp_path / "cursor-session.jsonl"
    log.write_text(json.dumps({"role": "assistant", "message": {"content": [
        {"type": "text", "text": "done"}, {"type": "tool_use", "name": "Read"},
        {"type": "tool_use", "name": "Edit"},
    ]}}))
    event = list(CursorAdapter().parse(log))[0]
    assert event.tool_calls == 2
    assert event.output_tokens > 0
    assert event.metadata["estimated"] is True


def test_cursor_uses_local_composer_model_workspace_and_context(tmp_path: Path):
    workspace = tmp_path / "project"
    workspace.mkdir()
    (workspace / ".git").mkdir()
    database = tmp_path / "state.vscdb"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE cursorDiskKV (key TEXT UNIQUE, value BLOB)")
        connection.execute("INSERT INTO cursorDiskKV VALUES (?, ?)", ("composerData:session", json.dumps({
            "modelConfig": {"modelName": "grok-test"},
            "workspaceIdentifier": {"uri": {"fsPath": str(workspace)}},
            "promptTokenBreakdown": {"totalUsedTokens": 120, "categories": [
                {"label": "System prompt", "estimatedTokens": 20},
                {"label": "Conversation", "estimatedTokens": 100},
            ]},
        })))
    log = tmp_path / "session.jsonl"
    log.write_text("\n".join([
        json.dumps({"role": "user", "message": {"content": [{"type": "text", "text": "x" * 40}]}}),
        json.dumps({"role": "assistant", "message": {"content": [{"type": "text", "text": "y" * 20}]}}),
    ]))
    adapter = CursorAdapter()
    adapter._state_db = lambda: database  # type: ignore[method-assign]
    event = list(adapter.parse(log))[0]
    assert (event.model, event.project_path) == ("grok-test", str(workspace))
    assert (event.cache_read_tokens, event.cache_write_tokens, event.output_tokens) == (20, 65, 6)


def test_kiro_reads_session_metadata_and_usage_units(tmp_path: Path):
    session = tmp_path / "workspace" / "session"
    session.mkdir(parents=True)
    (session / "session.json").write_text(json.dumps({
        "id": "sess-1", "modelId": "test-model", "workspacePaths": [str(tmp_path)],
        "createdAt": "2026-08-31T00:00:00Z",
    }))
    log = session / "messages.jsonl"
    log.write_text("\n".join([
        json.dumps({"id": "user-1", "timestamp": "2026-08-31T00:00:00Z",
                    "payload": {"type": "user", "content": "x" * 40}}),
        json.dumps({"id": "assistant-1", "timestamp": "2026-08-31T00:00:30Z",
                    "payload": {"type": "assistant", "content": "y" * 20}}),
        json.dumps({"id": "record-1", "timestamp": "2026-08-31T00:01:00Z",
                    "payload": {"type": "usage_summary", "elapsedTime": 1200,
                                "promptTurnSummaries": [{"usage": 3.5, "unit": "credit"}]}}),
    ]))
    event = list(KiroAdapter().parse(log))[0]
    assert (event.session_id, event.model, event.duration_ms) == ("sess-1", "test-model", 1200)
    assert event.metadata["kiro_usage_units"] == 3.5
    assert (event.cache_write_tokens, event.output_tokens) == (10, 5)
    assert event.metadata["estimator"] == "kiro-usage"


def test_opencode_reads_per_turn_usage_and_tool_calls(tmp_path: Path):
    database = tmp_path / "opencode.db"
    with sqlite3.connect(database) as connection:
        connection.executescript("""
            CREATE TABLE session (id TEXT PRIMARY KEY, directory TEXT NOT NULL);
            CREATE TABLE message (
                id TEXT PRIMARY KEY, session_id TEXT NOT NULL,
                time_created INTEGER NOT NULL, time_updated INTEGER NOT NULL, data TEXT NOT NULL
            );
            CREATE TABLE part (id TEXT PRIMARY KEY, message_id TEXT NOT NULL, data TEXT NOT NULL);
        """)
        connection.execute("INSERT INTO session VALUES ('ses-1', ?)", (str(tmp_path),))
        connection.execute("INSERT INTO message VALUES ('msg-1', 'ses-1', 1000, 2500, ?)", (json.dumps({
            "role": "assistant", "providerID": "opencode", "modelID": "big-pickle", "cost": 0,
            "time": {"created": 1000, "completed": 2500},
            "tokens": {"input": 10, "output": 20, "reasoning": 5,
                       "cache": {"read": 100, "write": 30}},
        }),))
        connection.executemany("INSERT INTO part VALUES (?, 'msg-1', ?)", [
            ("part-1", json.dumps({"type": "tool"})),
            ("part-2", json.dumps({"type": "text"})),
        ])
    adapter = OpenCodeAdapter()
    adapter._database = lambda: database  # type: ignore[method-assign]
    event = list(adapter.parse(database))[0]
    assert (event.provider, event.model, event.session_id) == ("opencode", "big-pickle", "ses-1")
    assert (event.input_tokens, event.output_tokens) == (10, 25)
    assert (event.cache_read_tokens, event.cache_write_tokens) == (100, 30)
    assert (event.tool_calls, event.duration_ms) == (1, 1500)
    assert event.metadata["reasoning_tokens"] == 5


def test_antigravity_decodes_generation_usage_and_project(tmp_path: Path):
    def varint(value: int) -> bytes:
        result = bytearray()
        while value > 0x7f:
            result.append((value & 0x7f) | 0x80)
            value >>= 7
        result.append(value)
        return bytes(result)

    def integer(field: int, value: int) -> bytes:
        return varint(field << 3) + varint(value)

    def message(field: int, value: bytes) -> bytes:
        return varint((field << 3) | 2) + varint(len(value)) + value

    usage = b"".join([
        integer(1, 100), integer(2, 200), integer(5, 500),
        integer(9, 50), integer(10, 25), message(11, b"response-1"),
    ])
    chat = message(4, usage) + message(19, b"gemini-test")
    generation = message(1, chat)
    started = integer(1, 1_788_306_421) + integer(2, 0)
    ended = integer(1, 1_788_306_423) + integer(2, 0)
    step_metadata = message(1, started) + message(8, ended)
    workspace = message(1, f"file://{tmp_path}".encode())
    trajectory = message(1, workspace) + message(2, started)

    database = tmp_path / "conversation.db"
    with sqlite3.connect(database) as connection:
        connection.executescript("""
            CREATE TABLE gen_metadata (idx INTEGER PRIMARY KEY, data BLOB);
            CREATE TABLE steps (idx INTEGER PRIMARY KEY, step_type INTEGER, metadata BLOB);
            CREATE TABLE trajectory_metadata_blob (id TEXT PRIMARY KEY, data BLOB);
        """)
        connection.execute("INSERT INTO gen_metadata VALUES (0, ?)", (generation,))
        connection.execute("INSERT INTO steps VALUES (0, 15, ?)", (step_metadata,))
        connection.execute("INSERT INTO steps VALUES (1, 132, NULL)")
        connection.execute("INSERT INTO trajectory_metadata_blob VALUES ('main', ?)", (trajectory,))

    event = list(AntigravityAdapter().parse(database))[0]
    assert (event.provider, event.model, event.project_path) == ("antigravity", "gemini-test", str(tmp_path))
    assert (event.input_tokens, event.output_tokens, event.cache_read_tokens) == (300, 75, 500)
    assert (event.tool_calls, event.duration_ms) == (1, 2000)
    assert event.metadata["reasoning_tokens"] == 25
