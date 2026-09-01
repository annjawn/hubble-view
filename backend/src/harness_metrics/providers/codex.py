import json
from pathlib import Path
from typing import Iterable

from .base import ProviderAdapter, UsageEvent
from .jsonl import parse_common


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
        try:
            with path.open(encoding="utf-8", errors="replace") as stream:
                for line in stream:
                    payload = json.loads(line)
                    body = payload.get("payload", payload)
                    if not isinstance(body, dict):
                        continue
                    if project is None and body.get("cwd"):
                        project = body["cwd"]
                    # Current Codex logs carry the selected model in turn_context or
                    # world-state records, separate from token_count usage records.
                    if body.get("model"):
                        model = str(body["model"])
        except (OSError, json.JSONDecodeError):
            pass
        yield from parse_common(path, self.id, project, model)
