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
        try:
            with path.open(encoding="utf-8", errors="replace") as stream:
                for _ in range(5):
                    payload = json.loads(next(stream))
                    body = payload.get("payload", payload)
                    if isinstance(body, dict) and body.get("cwd"):
                        project = body["cwd"]
                        break
        except (OSError, StopIteration, json.JSONDecodeError):
            pass
        yield from parse_common(path, self.id, project)

