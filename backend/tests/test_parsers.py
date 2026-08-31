import json
from pathlib import Path

from harness_metrics.providers.jsonl import parse_common


def test_parses_claude_message_usage(tmp_path: Path):
    log = tmp_path / "session.jsonl"
    log.write_text(json.dumps({
        "timestamp": "2026-08-31T00:00:00Z", "sessionId": "abc",
        "message": {"model": "claude-sonnet", "usage": {"input_tokens": 12, "output_tokens": 4}},
    }))
    event = list(parse_common(log, "claude"))[0]
    assert (event.input_tokens, event.output_tokens, event.model) == (12, 4, "claude-sonnet")


def test_parses_codex_nested_incremental_usage(tmp_path: Path):
    log = tmp_path / "session.jsonl"
    log.write_text(json.dumps({
        "timestamp": "2026-08-31T00:00:00Z", "type": "event_msg",
        "payload": {"type": "token_count", "info": {"last_token_usage": {
            "input_tokens": 20, "cached_input_tokens": 5, "output_tokens": 7,
        }}},
    }))
    event = list(parse_common(log, "codex"))[0]
    assert (event.input_tokens, event.cache_read_tokens, event.output_tokens) == (20, 5, 7)
