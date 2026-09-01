import json
import sqlite3
from pathlib import Path

from harness_metrics.providers.jsonl import parse_common
from harness_metrics.providers.cursor import CursorAdapter
from harness_metrics.providers.kiro import KiroAdapter
from harness_metrics.providers.codex import CodexAdapter


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
