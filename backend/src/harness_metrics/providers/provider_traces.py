import hashlib
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from .antigravity import _fields, _message, _string, _timestamp, _workspace
from .jsonl import _project_root


def _id(provider: str, source: Path, *parts: object) -> str:
    return hashlib.sha256(":".join([provider, "trace", str(source), *(str(p) for p in parts)]).encode()).hexdigest()


def _event(provider: str, source: Path, identity: object, session_id: str, occurred_at: str,
           kind: str, role: str | None, content: str | None, *, project: str | None = None,
           model: str | None = None, name: str | None = None,
           metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"id": _id(provider, source, identity), "provider": provider, "session_id": session_id,
            "project_path": project, "model": model, "occurred_at": occurred_at, "kind": kind,
            "role": role, "name": name, "content": content, "input_tokens": 0,
            "output_tokens": 0, "cache_read_tokens": 0, "cache_write_tokens": 0,
            "metadata": metadata or {}}


def parse_cursor_trace(path: Path, snapshot: dict[str, Any]) -> Iterable[dict[str, Any]]:
    try:
        records = [json.loads(line) for line in path.read_text(encoding="utf-8", errors="replace").splitlines()]
        base = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
    except (OSError, json.JSONDecodeError):
        return
    workspace = snapshot.get("workspaceIdentifier")
    uri = workspace.get("uri") if isinstance(workspace, dict) else None
    project = _project_root(uri.get("fsPath")) if isinstance(uri, dict) else path.parents[2].name
    config = snapshot.get("modelConfig") if isinstance(snapshot.get("modelConfig"), dict) else {}
    model = config.get("modelName")
    session_id = path.stem
    for line_no, record in enumerate(records):
        if not isinstance(record, dict):
            continue
        role = str(record.get("role") or "assistant")
        message = record.get("message") if isinstance(record.get("message"), dict) else {}
        blocks = message.get("content") if isinstance(message.get("content"), list) else [message.get("content")]
        timestamp = (base + timedelta(microseconds=line_no)).isoformat()
        for block_no, block in enumerate(blocks):
            kind, name, content, metadata = "message", None, None, {}
            if isinstance(block, str):
                content = block
            elif isinstance(block, dict):
                block_type = block.get("type")
                if block_type in {"tool_use", "function_call"}:
                    kind, name = "tool_call", str(block.get("name") or "Tool")
                    content = json.dumps(block.get("input", {}), ensure_ascii=False)
                    metadata["tool_use_id"] = block.get("id")
                elif block_type in {"tool_result", "function_result"}:
                    kind, name = "tool_result", str(block.get("name") or "Tool result")
                    content = json.dumps(block.get("content"), ensure_ascii=False) if not isinstance(block.get("content"), str) else block.get("content")
                    metadata.update({"tool_use_id": block.get("tool_use_id"), "is_error": bool(block.get("is_error"))})
                elif block_type in {"thinking", "reasoning"}:
                    kind, content = "thinking", str(block.get("thinking") or block.get("text") or "")
                else:
                    content = str(block.get("text")) if block.get("text") is not None else None
            if content is not None:
                yield _event("cursor", path, f"{line_no}:{block_no}", session_id, timestamp,
                             kind, role, content, project=project, model=str(model) if model else None,
                             name=name, metadata=metadata)


def parse_kiro_trace(path: Path) -> Iterable[dict[str, Any]]:
    if path.suffix != ".jsonl":
        return
    try:
        records = [json.loads(line) for line in path.read_text(encoding="utf-8", errors="replace").splitlines()]
        metadata = json.loads((path.parent / "session.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    session_id = str(metadata.get("id") or path.parent.name)
    roots = metadata.get("workspacePaths") or metadata.get("rootPaths") or []
    project = _project_root(roots[0]) if roots else None
    model = str(metadata.get("modelId")) if metadata.get("modelId") else None
    for index, record in enumerate(records):
        payload = record.get("payload") if isinstance(record, dict) and isinstance(record.get("payload"), dict) else {}
        kind_type = payload.get("type")
        occurred_at = str(record.get("timestamp") or metadata.get("lastModifiedAt") or metadata.get("createdAt"))
        kind = role = name = content = None
        extra: dict[str, Any] = {}
        if kind_type in {"user", "assistant"}:
            kind, role, content = "message", str(kind_type), str(payload.get("content") or "")
        elif kind_type == "tool_call":
            kind, role, name = "tool_call", "assistant", str(payload.get("name") or payload.get("toolName") or "Tool")
            content = json.dumps(payload.get("input") or payload.get("arguments") or {}, ensure_ascii=False)
            extra["tool_use_id"] = payload.get("toolCallId") or payload.get("id")
        elif kind_type == "tool_result":
            kind, name = "tool_result", str(payload.get("name") or payload.get("toolName") or "Tool result")
            value = payload.get("content") if "content" in payload else payload.get("result")
            content = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
            extra.update({"tool_use_id": payload.get("toolCallId"), "is_error": bool(payload.get("isError") or payload.get("error"))})
        elif kind_type in {"thinking", "reasoning"}:
            kind, role, content = "thinking", "assistant", str(payload.get("content") or "")
        if kind and (content or kind == "tool_result"):
            yield _event("kiro", path, record.get("id") or index, session_id, occurred_at,
                         kind, role, content, project=project, model=model, name=name, metadata=extra)


def parse_opencode_trace(path: Path, database: Path) -> Iterable[dict[str, Any]]:
    if not database.exists():
        return
    try:
        connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True, timeout=5)
        connection.row_factory = sqlite3.Row
        rows = connection.execute("""SELECT p.id,p.session_id,p.time_created,p.data,m.data message_data,s.directory
            FROM part p JOIN message m ON m.id=p.message_id JOIN session s ON s.id=p.session_id
            ORDER BY p.time_created,p.id""").fetchall()
        connection.close()
    except sqlite3.Error:
        return
    for row in rows:
        try:
            part, message = json.loads(row["data"]), json.loads(row["message_data"])
        except (json.JSONDecodeError, TypeError):
            continue
        part_type, role = part.get("type"), str(message.get("role") or "assistant")
        kind = name = content = None
        metadata: dict[str, Any] = {}
        if part_type == "text":
            kind, content = "message", part.get("text")
        elif part_type == "reasoning":
            kind, content = "thinking", part.get("text")
        elif part_type == "tool":
            state = part.get("state") if isinstance(part.get("state"), dict) else {}
            status = state.get("status")
            name = str(part.get("tool") or "Tool")
            call_id = part.get("callID")
            call = state.get("input", {})
            occurred_at = datetime.fromtimestamp(float(row["time_created"]) / 1000, timezone.utc).isoformat()
            yield _event("opencode", path, f"{row['id']}:call", str(row["session_id"]), occurred_at,
                         "tool_call", role, call if isinstance(call, str) else json.dumps(call, ensure_ascii=False),
                         project=_project_root(row["directory"]), model=message.get("modelID"), name=name,
                         metadata={"tool_use_id": call_id})
            if status not in {"completed", "error"}:
                continue
            kind = "tool_result"
            value = state.get("output") if "output" in state else state.get("error")
            content = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
            metadata = {"tool_use_id": call_id, "is_error": status == "error"}
        if not kind or content is None:
            continue
        occurred_at = datetime.fromtimestamp(float(row["time_created"]) / 1000, timezone.utc).isoformat()
        yield _event("opencode", path, row["id"], str(row["session_id"]), occurred_at,
                     kind, role if kind != "tool_result" else None, content,
                     project=_project_root(row["directory"]), model=message.get("modelID"),
                     name=name, metadata=metadata)


def _protobuf_texts(blob: bytes, depth: int = 0) -> list[str]:
    if depth > 5:
        return []
    texts: list[str] = []
    for _, wire, value in _fields(blob):
        if wire != 2 or not isinstance(value, bytes):
            continue
        try:
            text = value.decode("utf-8")
            if text.strip() and all(char.isprintable() or char in "\n\r\t" for char in text):
                texts.append(text)
                continue
        except UnicodeDecodeError:
            pass
        texts.extend(_protobuf_texts(value, depth + 1))
    return texts


def parse_antigravity_trace(path: Path) -> Iterable[dict[str, Any]]:
    try:
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5)
        steps = connection.execute("SELECT idx,step_type,metadata FROM steps ORDER BY idx").fetchall()
        trajectory = connection.execute("SELECT data FROM trajectory_metadata_blob ORDER BY id LIMIT 1").fetchone()
        connection.close()
    except sqlite3.Error:
        return
    trajectory_blob = trajectory[0] if trajectory else None
    project, session_id = _workspace(trajectory_blob), path.stem
    fallback = _timestamp(_message(trajectory_blob, 2) if trajectory_blob else None) or datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
    for ordinal, (index, step_type, blob) in enumerate(steps):
        texts = _protobuf_texts(blob or b"")
        # Keep human-readable payloads; discard short enum labels and opaque identifiers.
        content = max((text for text in texts if len(text.strip()) >= 2), key=len, default=None)
        if not content:
            continue
        kind, role, name = "message", "assistant", None
        if step_type == 132:
            kind, name = "tool_call", next((text for text in texts if 1 < len(text) < 80), "Tool")
        occurred = (fallback + timedelta(microseconds=ordinal)).isoformat()
        yield _event("antigravity", path, index, session_id, occurred, kind, role, content,
                     project=project, name=name, metadata={"step_type": step_type})
