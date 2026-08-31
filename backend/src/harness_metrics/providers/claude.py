from pathlib import Path
from typing import Iterable

from .base import ProviderAdapter, UsageEvent
from .jsonl import parse_common


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
        project = path.parent.name
        yield from parse_common(path, self.id, project)

