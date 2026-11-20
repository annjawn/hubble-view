import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .base import UsageEvent


def _number(data: dict[str, Any], *keys: str) -> int:
    for key in keys:
        value = data.get(key)
        if isinstance(value, (int, float)):
            return int(value)
    return 0


def _usage(payload: dict[str, Any]) -> dict[str, Any]:
    body = payload.get("payload") if isinstance(payload.get("payload"), dict) else payload
    message = payload.get("message") if isinstance(payload.get("message"), dict) else {}
    response = payload.get("response") if isinstance(payload.get("response"), dict) else {}
    body_message = body.get("message") if isinstance(body.get("message"), dict) else {}
    info = body.get("info") if isinstance(body.get("info"), dict) else {}
    usage = (
        payload.get("usage") or message.get("usage") or response.get("usage")
        or body.get("usage") or body_message.get("usage") or info.get("last_token_usage") or {}
    )
    return usage if isinstance(usage, dict) else {}


def read_jsonl(path: Path) -> list[tuple[int, dict[str, Any]]]:
    """Return ``(line_number, record)`` for every JSON object line in ``path``.

    Harness transcripts are appended while Hubble reads them, so a file can end
    in a partial line or contain blank/corrupt lines. Those are skipped instead
    of discarding the whole file.
    """
    try:
        # Split on "\n" only so line numbers agree with read_jsonl_from().
        lines = path.read_text(encoding="utf-8", errors="replace").split("\n")
    except OSError:
        return []
    records: list[tuple[int, dict[str, Any]]] = []
    for line_number, line in enumerate(lines):
        try:
            payload = json.loads(line)
        except (json.JSONDecodeError, TypeError, RecursionError):
            continue
        if isinstance(payload, dict):
            records.append((line_number, payload))
    return records


def read_jsonl_from(
    path: Path, offset: int = 0, line_number: int = 0
) -> tuple[list[tuple[int, dict[str, Any]]], int, int]:
    """Read complete lines appended after ``offset``.

    Returns ``(records, next_offset, next_line_number)``. Only lines that end in
    a newline are consumed, so a line still being written is picked up whole on
    the next call. Line numbers continue from ``line_number`` and match what a
    full read with ``read_jsonl`` would assign, which keeps event ids stable.
    """
    records: list[tuple[int, dict[str, Any]]] = []
    try:
        with path.open("rb") as stream:
            stream.seek(offset)
            data = stream.read()
    except OSError:
        return records, offset, line_number
    end = data.rfind(b"\n") + 1
    if not end:
        return records, offset, line_number
    # Split on "\n" only: str.splitlines() also breaks on characters such as
    # U+2028 that are legal inside a JSON string.
    for raw in data[:end].split(b"\n")[:-1]:
        try:
            payload = json.loads(raw.decode("utf-8", errors="replace"))
        except (json.JSONDecodeError, TypeError, RecursionError):
            payload = None
        if isinstance(payload, dict):
            records.append((line_number, payload))
        line_number += 1
    return records, offset + end, line_number


def _float(value: object) -> float:
    try:
        return float(value or 0)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0


def _project_root(value: object) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    path = Path(value).expanduser()
    if path.is_absolute():
        for candidate in (path, *path.parents):
            if (candidate / ".git").exists():
                return str(candidate)
    return str(path)


def parse_common(
    path: Path, provider: str, project: str | None = None, model_hint: str | None = None,
    session_hint: str | None = None,
    records: list[tuple[int, dict[str, Any]]] | None = None,
) -> Iterable[UsageEvent]:
    """Normalize usage lines. ``records`` lets a caller supply an already-read
    slice of the file (incremental scans); otherwise the whole file is read."""
    for line_number, payload in (read_jsonl(path) if records is None else records):
        body = payload.get("payload") if isinstance(payload.get("payload"), dict) else payload
        usage = _usage(payload)
        item = body.get("item") if isinstance(body.get("item"), dict) else {}
        event_type = str(body.get("type") or payload.get("type", ""))
        item_type = str(item.get("type", ""))
        tool_types = {"tool", "tool_use", "function_call", "custom_tool_call"}
        tool_calls = 1 if event_type in tool_types or item_type in tool_types else 0
        # Claude Code records tool calls as `tool_use` blocks inside
        # message.content of an `assistant` line, not as a top-level type.
        raw_message = payload.get("message")
        # Only assistant lines count: other record types (for example
        # `api-request-blob`) replay earlier tool_use blocks as request history.
        is_assistant = payload.get("type", "assistant") == "assistant"
        content = raw_message.get("content") if isinstance(raw_message, dict) and is_assistant else None
        tool_use_ids = [
            str(block.get("id") or f"{line_number}:{index}")
            for index, block in enumerate(content if isinstance(content, list) else [])
            if isinstance(block, dict) and block.get("type") == "tool_use"
        ]
        tool_calls += len(tool_use_ids)
        input_tokens = _number(usage, "input_tokens", "inputTokens", "prompt_tokens")
        output_tokens = _number(usage, "output_tokens", "outputTokens", "completion_tokens")
        cache_read = _number(usage, "cache_read_input_tokens", "cache_read_tokens", "cached_input_tokens")
        cache_write = _number(usage, "cache_creation_input_tokens", "cache_write_tokens")
        # Codex includes cached input in input_tokens, while Claude reports it
        # separately. Normalize Codex into the same non-overlapping buckets.
        if provider == "codex" and cache_read:
            input_tokens = max(0, input_tokens - cache_read)
        if not any((input_tokens, output_tokens, cache_read, cache_write, tool_calls)):
            continue
        timestamp = payload.get("timestamp") or payload.get("created_at") or payload.get("createdAt")
        if isinstance(timestamp, (int, float)):
            timestamp = datetime.fromtimestamp(timestamp / (1000 if timestamp > 1e12 else 1), timezone.utc).isoformat()
        if not isinstance(timestamp, str):
            timestamp = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()
        message = payload.get("message") if isinstance(payload.get("message"), dict) else {}
        model = payload.get("model") or body.get("model") or message.get("model") or model_hint
        model_name = str(model) if model else None
        reported_cost = _float(usage.get("cost_usd"))
        session_id = session_hint or payload.get("session_id") or payload.get("sessionId") or body.get("session_id") or path.stem
        request_id = payload.get("requestId") or payload.get("request_id")
        if provider == "claude" and request_id:
            # Claude may persist the same API response several times while a
            # streamed message is finalized. requestId is the stable API-call
            # identity; path/line identity would count every snapshot again.
            raw_id = f"{provider}:request:{request_id}"
        else:
            raw_id = f"{provider}:{path}:{line_number}:{payload.get('id', '')}"
        project_path = _project_root(
            payload.get("cwd") or body.get("cwd") or payload.get("project_path") or project
        )
        yield UsageEvent(
            id=hashlib.sha256(raw_id.encode()).hexdigest(),
            provider=provider,
            occurred_at=timestamp,
            session_id=str(session_id),
            project_path=project_path,
            model=model_name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_tokens=cache_read,
            cache_write_tokens=cache_write,
            cost_usd=reported_cost,
            duration_ms=_number(payload, "duration_ms", "durationMs"),
            tool_calls=tool_calls,
            metadata={"type": event_type, **({"tool_use_ids": tool_use_ids} if tool_use_ids else {})},
        )
