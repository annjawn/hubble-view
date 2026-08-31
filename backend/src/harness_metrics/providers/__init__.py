from .base import ProviderAdapter
from .claude import ClaudeAdapter
from .codex import CodexAdapter


def provider_registry() -> list[ProviderAdapter]:
    return [ClaudeAdapter(), CodexAdapter()]


__all__ = ["ProviderAdapter", "provider_registry"]
