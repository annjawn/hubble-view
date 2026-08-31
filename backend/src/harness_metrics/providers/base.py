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

    def status(self) -> dict[str, Any]:
        roots = self.log_roots()
        return {
            "id": self.id,
            "name": self.name,
            "available": any(root.exists() for root in roots),
            "paths": [str(root) for root in roots],
        }

