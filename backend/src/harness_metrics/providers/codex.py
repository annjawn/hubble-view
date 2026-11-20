from pathlib import Path
from typing import Iterable

from .base import ProviderAdapter, UsageEvent
from .jsonl import parse_common, read_jsonl


class CodexAdapter(ProviderAdapter):
    id = "codex"
    name = "Codex"

    def log_roots(self) -> list[Path]:
        return [Path.home() / ".codex" / "sessions"]

    def discover(self) -> Iterable[Path]:
        for root in self.log_roots():
            if root.exists():
                yield from root.rglob("*.jsonl")

    def parse(self, path: Path) -> Iterable[UsageEvent]:
        project = None
        model = None
        session_id = None
        for _, payload in read_jsonl(path):
            body = payload.get("payload", payload)
            if not isinstance(body, dict):
                continue
            if payload.get("type") == "session_meta" and session_id is None:
                # Same identity codex_trace uses, so usage and trace rows join.
                identity = body.get("id") or body.get("session_id")
                session_id = str(identity) if identity else None
            if project is None and body.get("cwd"):
                project = body["cwd"]
            # Current Codex logs carry the selected model in turn_context or
            # world-state records, separate from token_count usage records.
            if body.get("model"):
                model = str(body["model"])
        events = list(parse_common(path, self.id, project, model, session_id))
        # Newer rollouts write each response's usage twice: an `event_msg`
        # token_count and a `token_usage_record` with identical numbers.
        # Counting both doubles every token total, so keep one source per file.
        if any(event.metadata.get("type") == "token_usage_record" for event in events):
            events = [event for event in events if event.metadata.get("type") != "token_count"]
        yield from events
