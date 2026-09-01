import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from kiro_usage import CHARS_PER_TOKEN, CLI_DB, IDE_DB, calc_cost
from kiro_usage.viewer import load_all_sessions, load_ide_usage

from .base import ProviderAdapter, UsageEvent
from .jsonl import _project_root


class KiroAdapter(ProviderAdapter):
    id = "kiro"
    name = "Kiro"

    def log_roots(self) -> list[Path]:
        return [Path.home() / ".kiro" / "sessions", CLI_DB, IDE_DB]

    def discover(self) -> Iterable[Path]:
        sessions = Path.home() / ".kiro" / "sessions"
        if sessions.exists() and not IDE_DB.exists():
            yield from sessions.glob("*/*/messages.jsonl")
        if CLI_DB.exists():
            yield CLI_DB
        if IDE_DB.exists():
            yield IDE_DB

    @staticmethod
    def _session_metadata(path: Path) -> dict[str, Any]:
        try:
            value = json.loads((path.parent / "session.json").read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    @staticmethod
    def _event_id(source: Path, *parts: object) -> str:
        raw = ":".join(["kiro", str(source), *(str(part) for part in parts)])
        return hashlib.sha256(raw.encode()).hexdigest()

    def _parse_current_ide_session(self, path: Path) -> Iterable[UsageEvent]:
        metadata = self._session_metadata(path)
        workspace_paths = metadata.get("workspacePaths") or metadata.get("rootPaths") or []
        project = _project_root(workspace_paths[0]) if workspace_paths else None
        session_id = str(metadata.get("id") or path.parent.name)
        model = str(metadata.get("modelId")) if metadata.get("modelId") else None
        try:
            records = [json.loads(line) for line in path.read_text(encoding="utf-8", errors="replace").splitlines()]
        except (OSError, json.JSONDecodeError):
            return

        turns: list[dict[str, Any]] = []
        current: dict[str, Any] | None = None
        usage_units = 0.0
        duration_ms = 0
        for record in records:
            payload = record.get("payload") if isinstance(record, dict) else None
            if not isinstance(payload, dict):
                continue
            kind = payload.get("type")
            content = payload.get("content")
            content_chars = len(content) if isinstance(content, str) else len(str(content)) if content else 0
            if kind == "user":
                current = {"timestamp": record.get("timestamp"), "user": content_chars,
                           "assistant": 0, "context": 0, "tools": 0}
                turns.append(current)
            elif current is not None and kind == "assistant":
                current["assistant"] += content_chars
                current["context"] += content_chars
            elif current is not None and kind == "tool_result":
                current["context"] += content_chars
            elif current is not None and kind == "tool_call":
                current["tools"] += 1
            elif kind == "usage_summary":
                duration_ms = int(payload.get("elapsedTime", 0) or 0)
                usage_units += sum(float(item.get("usage", 0) or 0) for item in payload.get("promptTurnSummaries", []) if isinstance(item, dict))

        cumulative = 0
        previous_context = 0
        for index, turn in enumerate(turns):
            user_tokens = turn["user"] // CHARS_PER_TOKEN
            context_tokens = turn["context"] // CHARS_PER_TOKEN
            output_tokens = turn["assistant"] // CHARS_PER_TOKEN
            cache_read = cumulative if index else 0
            cache_write = user_tokens + (previous_context if index else 0)
            cumulative += user_tokens + context_tokens
            previous_context = context_tokens
            occurred_at = turn["timestamp"] or metadata.get("lastModifiedAt") or metadata.get("createdAt")
            if not occurred_at:
                occurred_at = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()
            yield UsageEvent(
                id=self._event_id(path, session_id, index), provider=self.id,
                occurred_at=str(occurred_at), session_id=session_id, project_path=project,
                model=model, output_tokens=output_tokens, cache_read_tokens=cache_read,
                cache_write_tokens=cache_write,
                cost_usd=calc_cost(cache_write, cache_read, output_tokens, model),
                duration_ms=duration_ms if index == len(turns) - 1 else 0,
                tool_calls=int(turn["tools"]),
                metadata={"type": "estimated_turn", "estimator": "kiro-usage",
                          "kiro_usage_units": usage_units if index == len(turns) - 1 else 0},
            )

    def _parse_cli(self, path: Path) -> Iterable[UsageEvent]:
        for conversation in load_all_sessions():
            for day, usage in conversation["daily"].items():
                yield UsageEvent(
                    id=self._event_id(path, conversation["full_id"], day), provider=self.id,
                    occurred_at=f"{day}T12:00:00+00:00", session_id=conversation["full_id"],
                    project_path=_project_root(conversation["cwd"]),
                    model=next(iter(conversation["models"]), None),
                    output_tokens=int(usage["out"]), cache_read_tokens=int(usage["cr"]),
                    cache_write_tokens=int(usage["cw"]), cost_usd=float(usage["cost"]),
                    metadata={"type": "kiro_cli_daily", "estimator": "kiro-usage"},
                )

    def _parse_ide_database(self, path: Path) -> Iterable[UsageEvent]:
        usage = load_ide_usage()
        if not usage:
            return
        for day, values in usage["daily"].items():
            yield UsageEvent(
                id=self._event_id(path, day), provider=self.id,
                occurred_at=f"{day}T12:00:00+00:00", session_id=f"kiro-ide:{day}",
                input_tokens=int(values["input"]), output_tokens=int(values["out"]),
                cost_usd=float(values["cost"]),
                metadata={"type": "kiro_ide_daily", "estimator": "kiro-usage",
                          "calls": int(values["calls"])},
            )

    def parse(self, path: Path) -> Iterable[UsageEvent]:
        if path == CLI_DB:
            yield from self._parse_cli(path)
        elif path == IDE_DB:
            yield from self._parse_ide_database(path)
        else:
            yield from self._parse_current_ide_session(path)
