from pathlib import Path
from typing import Any, Iterable

from .base import ProviderAdapter, UsageEvent
from .claude_trace import parse_claude_trace
from .jsonl import parse_common, read_jsonl_from


class ClaudeAdapter(ProviderAdapter):
    id = "claude"
    name = "Claude Code"

    def log_roots(self) -> list[Path]:
        return [Path.home() / ".claude" / "projects"]

    def discover(self) -> Iterable[Path]:
        for root in self.log_roots():
            if root.exists():
                yield from root.rglob("*.jsonl")

    def parse(self, path: Path) -> Iterable[UsageEvent]:
        return self._usage(path, None)

    def _project_hint(self, path: Path) -> str:
        # Transcripts live at <root>/<project>/<session>.jsonl; subagent
        # transcripts sit deeper (<project>/<session>/subagents/...). The hint
        # is always the <project> directory, used only when a line has no cwd.
        for root in self.log_roots():
            try:
                return path.relative_to(root).parts[0]
            except (ValueError, IndexError):
                continue
        return path.parent.name

    def _usage(self, path: Path, records: list[tuple[int, dict[str, Any]]] | None) -> Iterable[UsageEvent]:
        project = self._project_hint(path)
        # One API response is persisted as several lines (one per content
        # block) that share a requestId and therefore one event id. Merge them
        # so the request keeps its largest token snapshot and every tool call.
        # `tool_use_ids` stays in metadata: the scanner unions it with the
        # stored row, so a request split across two incremental reads still
        # counts each tool call once.
        merged: dict[str, UsageEvent] = {}
        for event in parse_common(path, self.id, project, records=records):
            current = merged.get(event.id)
            if current is None:
                merged[event.id] = event
                continue
            tool_ids = dict.fromkeys(
                [*current.metadata.get("tool_use_ids", []), *event.metadata.get("tool_use_ids", [])]
            )
            if tool_ids:
                current.metadata["tool_use_ids"] = list(tool_ids)
            current.occurred_at = max(current.occurred_at, event.occurred_at)
            current.model = event.model or current.model
            current.project_path = event.project_path or current.project_path
            for field in ("input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens", "duration_ms"):
                setattr(current, field, max(getattr(current, field), getattr(event, field)))
            current.cost_usd = max(current.cost_usd, event.cost_usd)
        for event in merged.values():
            event.tool_calls = len(event.metadata.get("tool_use_ids", []))
            yield event

    def scan_source(self, path: Path, state: dict[str, Any]):
        # Claude transcripts are append-only JSONL whose lines stand alone, so
        # only the bytes added since the last scan need parsing.
        offset, line = int(state.get("offset", 0) or 0), int(state.get("line", 0) or 0)
        try:
            if path.stat().st_size < offset:  # rewritten or truncated: start over
                offset, line = 0, 0
        except OSError:
            return [], [], state
        records, next_offset, next_line = read_jsonl_from(path, offset, line)
        usage = list(self._usage(path, records))
        trace = list(parse_claude_trace(path, self._project_hint(path), records))
        return usage, trace, {"offset": next_offset, "line": next_line}
