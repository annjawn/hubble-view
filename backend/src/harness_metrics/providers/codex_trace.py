import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


def _number(data: object, key: str) -> int:
    return int(data.get(key, 0) or 0) if isinstance(data, dict) else 0


def _content_text(value: object) -> str | None:
    if isinstance(value, str):
        return value
    if not isinstance(value, list):
        return None
    parts: list[str] = []
    for item in value:
        if isinstance(item, str):
            parts.append(item)
        elif isinstance(item, dict):
            text = item.get("text") or item.get("content")
            if isinstance(text, str):
                parts.append(text)
            elif text is not None:
                parts.append(json.dumps(text, ensure_ascii=False))
    return "\n".join(parts) or None


def _serialized(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def parse_codex_trace(path: Path) -> Iterable[dict[str, Any]]:
    """Normalize Codex rollout records into session timeline events."""
    session_id, project, model = path.stem, None, None
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return
    for line_number, line in enumerate(lines):
        try:
            record = json.loads(line)
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(record, dict):
            continue
        payload = record.get("payload") if isinstance(record.get("payload"), dict) else {}
        outer_type, item_type = record.get("type"), payload.get("type")
        if outer_type == "session_meta":
            session_id = str(payload.get("id") or payload.get("session_id") or session_id)
            project = payload.get("cwd") or project
            continue
        if outer_type == "turn_context":
            project, model = payload.get("cwd") or project, payload.get("model") or model
            continue

        kind = role = name = content = None
        metadata: dict[str, Any] = {}
        usage: object = {}
        if outer_type == "response_item" and item_type == "message":
            kind, role = "message", str(payload.get("role") or "assistant")
            content = _content_text(payload.get("content"))
        elif outer_type == "response_item" and item_type == "reasoning":
            kind, role = "thinking", "assistant"
            content = _content_text(payload.get("summary"))
        elif outer_type == "response_item" and item_type in {"function_call", "custom_tool_call"}:
            kind, role, name = "tool_call", "assistant", str(payload.get("name") or "Tool")
            content = _serialized(payload.get("arguments") if "arguments" in payload else payload.get("input"))
            metadata["tool_use_id"] = payload.get("call_id") or payload.get("id")
        elif outer_type == "response_item" and item_type in {"function_call_output", "custom_tool_call_output"}:
            kind, name = "tool_result", "Tool result"
            content = _serialized(payload.get("output"))
            metadata["tool_use_id"] = payload.get("call_id") or payload.get("id")
            metadata["is_error"] = payload.get("status") in {"failed", "error"}
        elif outer_type == "event_msg" and item_type == "token_count":
            kind, name = "usage", "Token usage"
            info = payload.get("info") if isinstance(payload.get("info"), dict) else {}
            usage = info.get("last_token_usage") if isinstance(info.get("last_token_usage"), dict) else {}
            if not usage:
                continue
            content = "Usage updated"
        else:
            continue
        if not content and kind != "tool_result":
            continue
        timestamp = record.get("timestamp")
        if not isinstance(timestamp, str):
            timestamp = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()
        cache_read = _number(usage, "cached_input_tokens")
        input_tokens = max(0, _number(usage, "input_tokens") - cache_read)
        identity = payload.get("id") or payload.get("call_id") or record.get("ordinal") or line_number
        raw_id = f"codex:trace:{path}:{identity}:{item_type}"
        yield {
            "id": hashlib.sha256(raw_id.encode()).hexdigest(), "provider": "codex",
            "session_id": session_id, "project_path": str(project) if project else None,
            "model": str(model) if model else None, "occurred_at": timestamp,
            "kind": kind, "role": role, "name": name, "content": content,
            "input_tokens": input_tokens, "output_tokens": _number(usage, "output_tokens"),
            "cache_read_tokens": cache_read,
            "cache_write_tokens": _number(usage, "cache_write_input_tokens"),
            "metadata": metadata,
        }
