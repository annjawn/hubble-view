from .base import ProviderAdapter
from .claude import ClaudeAdapter
from .codex import CodexAdapter
from .cursor import CursorAdapter
from .kiro import KiroAdapter


def provider_registry() -> list[ProviderAdapter]:
    return [ClaudeAdapter(), CodexAdapter(), CursorAdapter(), KiroAdapter()]


__all__ = ["ProviderAdapter", "provider_registry"]
