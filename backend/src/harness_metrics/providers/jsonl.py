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


def parse_common(path: Path, provider: str, project: str | None = None) -> Iterable[UsageEvent]:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return
    for line_number, line in enumerate(lines):
        try:
            payload = json.loads(line)
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(payload, dict):
            continue
        body = payload.get("payload") if isinstance(payload.get("payload"), dict) else payload
        usage = _usage(payload)
        item = body.get("item") if isinstance(body.get("item"), dict) else {}
        event_type = str(body.get("type") or payload.get("type", ""))
        item_type = str(item.get("type", ""))
        tool_calls = 1 if event_type in {"tool", "tool_use", "function_call"} or item_type in {"tool_use", "function_call", "custom_tool_call"} else 0
        input_tokens = _number(usage, "input_tokens", "inputTokens", "prompt_tokens")
        output_tokens = _number(usage, "output_tokens", "outputTokens", "completion_tokens")
        cache_read = _number(usage, "cache_read_input_tokens", "cache_read_tokens", "cached_input_tokens")
        cache_write = _number(usage, "cache_creation_input_tokens", "cache_write_tokens")
        if not any((input_tokens, output_tokens, cache_read, cache_write, tool_calls)):
            continue
        timestamp = payload.get("timestamp") or payload.get("created_at") or payload.get("createdAt")
        if isinstance(timestamp, (int, float)):
            timestamp = datetime.fromtimestamp(timestamp / (1000 if timestamp > 1e12 else 1), timezone.utc).isoformat()
        if not isinstance(timestamp, str):
            timestamp = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()
        message = payload.get("message") if isinstance(payload.get("message"), dict) else {}
        model = payload.get("model") or body.get("model") or message.get("model")
        session_id = payload.get("session_id") or payload.get("sessionId") or body.get("session_id") or path.stem
        raw_id = f"{provider}:{path}:{line_number}:{payload.get('id', '')}"
        yield UsageEvent(
            id=hashlib.sha256(raw_id.encode()).hexdigest(),
            provider=provider,
            occurred_at=timestamp,
            session_id=str(session_id),
            project_path=project or payload.get("cwd") or body.get("cwd") or payload.get("project_path"),
            model=str(model) if model else None,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_tokens=cache_read,
            cache_write_tokens=cache_write,
            cost_usd=float(usage.get("cost_usd", 0) or 0),
            duration_ms=_number(payload, "duration_ms", "durationMs"),
            tool_calls=tool_calls,
            metadata={"type": event_type},
        )
