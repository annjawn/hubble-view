import hashlib
import json
import os
import platform
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .base import ProviderAdapter, UsageEvent
from .jsonl import _project_root


def _text_tokens(value: object) -> int:
    if isinstance(value, str):
        return len(value) // 4
    if isinstance(value, list):
        return sum(_text_tokens(item) for item in value)
    if isinstance(value, dict):
        return sum(_text_tokens(item) for key, item in value.items() if key != "images")
    return 0


class CursorAdapter(ProviderAdapter):
    id = "cursor"
    name = "Cursor"

    @staticmethod
    def _state_db() -> Path:
        if platform.system() == "Darwin":
            base = Path.home() / "Library" / "Application Support" / "Cursor"
        elif platform.system() == "Windows":
            base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "Cursor"
        else:
            base = Path.home() / ".config" / "Cursor"
        return base / "User" / "globalStorage" / "state.vscdb"

    def log_roots(self) -> list[Path]:
        return [Path.home() / ".cursor" / "projects", self._state_db()]

    def discover(self) -> Iterable[Path]:
        root = Path.home() / ".cursor" / "projects"
        if root.exists():
            yield from root.glob("*/agent-transcripts/*/*.jsonl")

    def _composer_snapshot(self, composer_id: str) -> dict[str, Any]:
        database = self._state_db()
        if not database.exists():
            return {}
        try:
            connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True, timeout=2)
            row = connection.execute(
                "SELECT value FROM cursorDiskKV WHERE key = ?", (f"composerData:{composer_id}",)
            ).fetchone()
            connection.close()
            if not row:
                return {}
            value = json.loads(row[0])
            return value if isinstance(value, dict) else {}
        except (OSError, sqlite3.Error, json.JSONDecodeError, TypeError):
            return {}

    @staticmethod
    def _snapshot_project(snapshot: dict[str, Any]) -> str | None:
        workspace = snapshot.get("workspaceIdentifier")
        uri = workspace.get("uri") if isinstance(workspace, dict) else None
        path = uri.get("fsPath") if isinstance(uri, dict) else None
        return _project_root(path)

    @staticmethod
    def _snapshot_model(snapshot: dict[str, Any]) -> str | None:
        config = snapshot.get("modelConfig")
        if not isinstance(config, dict):
            return None
        model = config.get("modelName")
        if not model:
            selected = config.get("selectedModels")
            if isinstance(selected, list) and selected and isinstance(selected[0], dict):
                model = selected[0].get("modelId")
        return str(model) if model else None

    @staticmethod
    def _snapshot_prompt(snapshot: dict[str, Any]) -> tuple[int, int]:
        breakdown = snapshot.get("promptTokenBreakdown")
        if not isinstance(breakdown, dict):
            return 0, 0
        total = int(breakdown.get("totalUsedTokens", 0) or 0)
        conversation = 0
        for category in breakdown.get("categories", []):
            if isinstance(category, dict) and category.get("label") == "Conversation":
                conversation = int(category.get("estimatedTokens", 0) or 0)
                break
        return max(0, total - conversation), conversation

    def parse(self, path: Path) -> Iterable[UsageEvent]:
        try:
            records = [json.loads(line) for line in path.read_text(encoding="utf-8", errors="replace").splitlines()]
            occurred_at = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()
        except (OSError, json.JSONDecodeError):
            return
        snapshot = self._composer_snapshot(path.stem)
        project = self._snapshot_project(snapshot) or path.parents[2].name
        model = self._snapshot_model(snapshot)
        fixed_prompt, snapshot_conversation = self._snapshot_prompt(snapshot)
        raw_conversation = sum(
            _text_tokens(record.get("message", {}).get("content", []))
            for record in records if isinstance(record, dict) and isinstance(record.get("message"), dict)
        )
        scale = snapshot_conversation / raw_conversation if snapshot_conversation and raw_conversation else 1.0

        cumulative = 0
        previous_request = 0
        for line_number, payload in enumerate(records):
            if not isinstance(payload, dict):
                continue
            message = payload.get("message")
            content = message.get("content", []) if isinstance(message, dict) else []
            content_tokens = _text_tokens(content)
            if payload.get("role") != "assistant":
                cumulative += content_tokens
                continue
            prompt_conversation = round(cumulative * scale)
            new_context = round(max(0, cumulative - previous_request) * scale)
            cache_write = new_context
            cache_read = fixed_prompt + max(0, prompt_conversation - new_context)
            output_tokens = content_tokens
            tool_calls = sum(
                1 for item in content
                if isinstance(item, dict) and item.get("type") in {"tool_use", "function_call"}
            )
            raw_id = f"cursor:{path}:{line_number}"
            yield UsageEvent(
                id=hashlib.sha256(raw_id.encode()).hexdigest(), provider=self.id,
                occurred_at=occurred_at, session_id=path.stem, project_path=project,
                model=model, output_tokens=output_tokens, cache_read_tokens=cache_read,
                cache_write_tokens=cache_write, tool_calls=tool_calls,
                metadata={"type": "assistant", "usage_source": "local-estimate",
                          "estimated": True, "estimator": "cursor-context-v1"},
            )
            previous_request = cumulative
            cumulative += content_tokens
