"""API list prices used for cost *estimates*.

Hubble never knows what a user actually paid: most coding-agent usage runs on
a subscription, and harness logs rarely record cost. These figures answer a
different question — what the same tokens would cost at public API list
prices — and every number derived from them is labelled an estimate.

Prices are USD per million tokens, Standard tier, read on PRICING_VERSION from:

- Anthropic: https://platform.claude.com/docs/en/about-claude/pricing ("Model pricing")
- OpenAI: https://developers.openai.com/api/docs/pricing (Standard table)
- Google: https://aistudio.google.com/docs/pricing (Paid tier, Standard)

Simplifications, all of which make the result approximate:

- Anthropic's page lists display names ("Claude Opus 5.5"); the ids below are
  the matching API aliases ("claude-opus-5-5").
- Cache writes use the 5-minute rate; Hubble stores one cache-write bucket.
- Long-context tiers (OpenAI above 272K input, Gemini above 200K) and Claude
  Haiku 5.5's over-100K tier are not applied; the base tier is used.
- Batch, fast-mode, data-residency and regional multipliers are ignored.
- OpenAI and Google have no separate cache-write price, so cache writes are
  priced as fresh input.

To update: edit the table, bump PRICING_VERSION, and re-check each source.
"""

import re
from typing import NamedTuple

PRICING_VERSION = "2026-11-19"
PRICING_SOURCES = [
    "https://platform.claude.com/docs/en/about-claude/pricing",
    "https://developers.openai.com/api/docs/pricing",
    "https://aistudio.google.com/docs/pricing",
]


class Price(NamedTuple):
    input: float
    cache_write: float
    cache_read: float
    output: float


def _openai(input_price: float, cached: float, output: float) -> Price:
    return Price(input_price, input_price, cached, output)


PRICES: dict[str, Price] = {
    # Anthropic: input, 5-minute cache write, cache hit, output
    "claude-fable-5-2": Price(8, 10, 0.20, 40),
    "claude-mythos-5-2": Price(8, 10, 0.20, 40),
    "claude-fable-5-1": Price(10, 12.50, 0.25, 50),
    "claude-mythos-5-1": Price(10, 12.50, 0.25, 50),
    "claude-fable-5": Price(10, 12.50, 1, 50),
    "claude-mythos-5": Price(10, 12.50, 1, 50),
    "claude-opus-5-5": Price(4, 5, 0.20, 20),
    "claude-opus-5": Price(5, 6.25, 0.50, 25),
    "claude-opus-4-8": Price(5, 6.25, 0.50, 25),
    "claude-opus-4-7": Price(5, 6.25, 0.50, 25),
    "claude-opus-4-6": Price(5, 6.25, 0.50, 25),
    "claude-opus-4-5": Price(5, 6.25, 0.50, 25),
    "claude-opus-4-1": Price(15, 18.75, 1.50, 75),
    "claude-opus-4": Price(15, 18.75, 1.50, 75),
    "claude-sonnet-5-5": Price(2, 2.50, 0.10, 10),
    "claude-sonnet-5": Price(2, 2.50, 0.20, 10),
    "claude-sonnet-4-6": Price(3, 3.75, 0.30, 15),
    "claude-sonnet-4-5": Price(3, 3.75, 0.30, 15),
    "claude-sonnet-4": Price(3, 3.75, 0.30, 15),
    "claude-haiku-5-5": Price(0.10, 0.125, 0.01, 0.50),
    "claude-haiku-4-5": Price(1, 1.25, 0.10, 5),
    # OpenAI: input, cached input, output
    "gpt-6.2-astra": _openai(8, 0.40, 40),
    "gpt-6.2-sol": _openai(2, 0.10, 10),
    "gpt-6.1-sol": _openai(2, 0.10, 10),
    "gpt-6.1-terra": _openai(1, 0.05, 5),
    "gpt-6-astra": _openai(10, 1, 50),
    "gpt-6-sol": _openai(2, 0.20, 10),
    "gpt-6-luna": _openai(0.10, 0.01, 0.50),
    "gpt-5.6-sol": _openai(4, 0.40, 20),
    "gpt-5.6-terra": _openai(2, 0.20, 12),
    "gpt-5.6-luna": _openai(0.20, 0.02, 1.20),
    "gpt-5.5": _openai(5, 0.50, 30),
    "gpt-5.4": _openai(2.50, 0.25, 15),
    "gpt-5.4-mini": _openai(0.75, 0.075, 4.50),
    "gpt-5.4-nano": _openai(0.20, 0.02, 1.25),
    "gpt-5.3-codex": _openai(1.75, 0.175, 14),
    "gpt-5.2": _openai(1.75, 0.175, 14),
    "gpt-5.1": _openai(1.25, 0.125, 10),
    "gpt-5": _openai(1.25, 0.125, 10),
    "gpt-5-mini": _openai(0.25, 0.025, 2),
    "gpt-5-nano": _openai(0.05, 0.005, 0.40),
    # Google: input, (no cache write), context caching, output incl. thinking
    "gemini-4-carbon": _openai(2, 0.10, 10),
    "gemini-4-argon": _openai(2, 0.10, 10),
    "gemini-4-neon": _openai(3, 0.15, 15),
    "gemini-4-hydrogen": _openai(1.50, 0.075, 7.50),
    "gemini-3.8-flash": _openai(0.75, 0.075, 3.75),
    "gemini-3.6-flash": _openai(0.75, 0.075, 3.75),
    "gemini-3.5-flash-lite": _openai(0.30, 0.03, 2.50),
    "gemini-3.1-pro-preview": _openai(2, 0.20, 12),
    "gemini-3.1-flash-lite": _openai(0.25, 0.025, 1.50),
    "gemini-3-flash-preview": _openai(0.50, 0.05, 3),
}

# What may follow a known id and still be the same priced model: a dated
# snapshot, a channel alias, or a harness suffix such as "[1m]".
_SUFFIX = re.compile(r"^(-\d{8}|-\d{4}-\d{2}-\d{2}|-latest)?(\[[^\]]*\])?$")


def price_for(model: str | None) -> Price | None:
    """Return the list price for ``model``, or ``None`` when it is not in the
    table. Unknown models are left unpriced rather than guessed."""
    if not model:
        return None
    name = model.strip().lower()
    # Harnesses sometimes prefix the vendor ("anthropic/claude-...").
    name = name.rsplit("/", 1)[-1]
    for key in sorted(PRICES, key=len, reverse=True):
        if name.startswith(key) and _SUFFIX.match(name[len(key):]):
            return PRICES[key]
    return None


def estimate_cost(
    model: str | None, input_tokens: int, cache_write_tokens: int, cache_read_tokens: int, output_tokens: int
) -> float | None:
    price = price_for(model)
    if price is None:
        return None
    return (
        input_tokens * price.input + cache_write_tokens * price.cache_write
        + cache_read_tokens * price.cache_read + output_tokens * price.output
    ) / 1_000_000
