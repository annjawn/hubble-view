from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable


@dataclass(slots=True)
class UsageEvent:
    id: str
    provider: str
    occurred_at: str
    session_id: str | None = None
    project_path: str | None = None
    model: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    cost_usd: float = 0
    duration_ms: int = 0
    tool_calls: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


class ProviderAdapter(ABC):
    id: str
    name: str

    @abstractmethod
    def log_roots(self) -> list[Path]: ...

    @abstractmethod
    def discover(self) -> Iterable[Path]: ...

    @abstractmethod
    def parse(self, path: Path) -> Iterable[UsageEvent]: ...

    def scan_source(
        self, path: Path, state: dict[str, Any]
    ) -> tuple[Iterable[UsageEvent], Iterable[dict[str, Any]], dict[str, Any]] | None:
        """Optional incremental scan.

        ``state`` is whatever this adapter returned for ``path`` last time (empty
        on first sight). Return ``(usage_events, trace_events, new_state)`` to
        handle the source here, or ``None`` to let the scanner fall back to a
        full ``parse``. Implement it only when a source can be read from a saved
        position without losing context from earlier records.
        """
        return None

    def status(self) -> dict[str, Any]:
        roots = self.log_roots()
        return {
            "id": self.id,
            "name": self.name,
            "available": any(root.exists() for root in roots),
            "paths": [str(root) for root in roots],
        }

