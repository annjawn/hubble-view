import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


def _tokens(usage: object, key: str) -> int:
    return int(usage.get(key, 0) or 0) if isinstance(usage, dict) else 0


def _text(value: object) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = [item.get("text") for item in value if isinstance(item, dict) and item.get("type") == "text"]
        return "\n".join(str(part) for part in parts if part) or None
    return None


def parse_claude_trace(path: Path, project_hint: str | None = None) -> Iterable[dict[str, Any]]:
    """Normalize human-visible Claude transcript and tool events.

    IDs use the persisted message/block identity where available so rescanning a
    growing transcript is idempotent.
    """
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
        message = payload.get("message") if isinstance(payload.get("message"), dict) else {}
        role = message.get("role") or (payload.get("type") if payload.get("type") in {"user", "assistant"} else None)
        content = message.get("content")
        blocks = content if isinstance(content, list) else [content]
        usage = message.get("usage") if isinstance(message.get("usage"), dict) else payload.get("usage", {})
        timestamp = payload.get("timestamp")
        if not isinstance(timestamp, str):
            timestamp = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()
        session_id = str(payload.get("sessionId") or payload.get("session_id") or path.stem)
        project = payload.get("cwd") or project_hint
        model = message.get("model") or payload.get("model")
        parent_id = str(payload.get("uuid") or message.get("id") or f"{path}:{line_number}")
        for block_index, block in enumerate(blocks):
            kind, name, body, metadata = "message", None, None, {}
            if isinstance(block, str):
                body = block
            elif isinstance(block, dict):
                block_type = str(block.get("type") or "message")
                if block_type == "tool_use":
                    kind, name = "tool_call", str(block.get("name") or "Tool")
                    body = json.dumps(block.get("input", {}), ensure_ascii=False)
                    metadata["tool_use_id"] = block.get("id")
                elif block_type == "tool_result":
                    kind, name = "tool_result", "Tool result"
                    body = _text(block.get("content")) or json.dumps(block.get("content"), ensure_ascii=False)
                    metadata.update({"tool_use_id": block.get("tool_use_id"), "is_error": bool(block.get("is_error"))})
                elif block_type == "thinking":
                    kind, body = "thinking", str(block.get("thinking") or "")
                else:
                    body = str(block.get("text")) if block.get("text") is not None else _text(block.get("content"))
            if not body and not any((_tokens(usage, "input_tokens"), _tokens(usage, "output_tokens"))):
                continue
            raw_id = f"claude:trace:{parent_id}:{block_index}"
            yield {
                "id": hashlib.sha256(raw_id.encode()).hexdigest(), "provider": "claude",
                "session_id": session_id, "project_path": str(project) if project else None,
                "model": str(model) if model else None, "occurred_at": timestamp,
                "kind": kind, "role": str(role) if role else None, "name": name,
                "content": body, "input_tokens": _tokens(usage, "input_tokens") if block_index == 0 else 0,
                "output_tokens": _tokens(usage, "output_tokens") if block_index == 0 else 0,
                "cache_read_tokens": _tokens(usage, "cache_read_input_tokens") if block_index == 0 else 0,
                "cache_write_tokens": _tokens(usage, "cache_creation_input_tokens") if block_index == 0 else 0,
                "metadata": metadata,
            }
