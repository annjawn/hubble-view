from .base import ProviderAdapter
from .antigravity import AntigravityAdapter
from .claude import ClaudeAdapter
from .codex import CodexAdapter
from .cursor import CursorAdapter
from .kiro import KiroAdapter
from .opencode import OpenCodeAdapter


def provider_registry() -> list[ProviderAdapter]:
    return [ClaudeAdapter(), CodexAdapter(), CursorAdapter(), KiroAdapter(), OpenCodeAdapter(), AntigravityAdapter()]


__all__ = ["ProviderAdapter", "provider_registry"]
