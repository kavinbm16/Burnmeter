"""Provider adapter contracts.

Every data source (usage API, proxy capture, billing export) normalizes into
UsageRecord / CostRecord. The dashboard only ever reads these shapes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True)
class UsageRecord:
    provider: str  # "openai" | "gemini"
    model: str
    date: str  # YYYY-MM-DD (UTC)
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    requests: int = 0
    cost_usd: float | None = None
    # "usage_api" | "proxy" | "billing_export" — surfaced in the UI so users
    # know whether a number is provider-reported or locally estimated.
    source: str = "usage_api"
    cost_estimated: bool = False


@dataclass(frozen=True)
class CostRecord:
    provider: str
    date: str  # YYYY-MM-DD (UTC)
    cost_usd: float
    line_item: str | None = None
    source: str = "usage_api"


@dataclass(frozen=True)
class KeyInfo:
    """Result of a successful key validation."""

    provider: str
    label: str  # e.g. org name or "valid admin key"
    masked_key: str  # e.g. "sk-…ab12" — the only form ever shown


class ProviderError(Exception):
    """Base for adapter failures. Message must never contain the key."""


class InvalidKeyError(ProviderError):
    """Key rejected by provider, or wrong key type (e.g. non-admin)."""


class RateLimitedError(ProviderError):
    def __init__(self, retry_after: float | None = None):
        super().__init__("provider rate limited")
        self.retry_after = retry_after


def mask_key(key: str) -> str:
    """Mask a key for display: keep prefix hint + last 4 chars."""
    if len(key) <= 8:
        return "…" + key[-2:]
    return f"{key[:3]}…{key[-4:]}"


class ProviderAdapter(ABC):
    """A provider that can be polled for historical usage with an API key."""

    name: str
    display_name: str
    key_hint: str  # shown in Settings, e.g. "Requires org Admin key"

    @abstractmethod
    async def validate_key(self, key: str) -> KeyInfo:
        """Check the key works for usage endpoints. Raises InvalidKeyError."""

    @abstractmethod
    async def fetch_usage(self, key: str, start: date, end: date) -> list[UsageRecord]:
        """Per-model, per-day token usage in [start, end]."""

    @abstractmethod
    async def fetch_costs(self, key: str, start: date, end: date) -> list[CostRecord]:
        """Per-day billed cost in [start, end]."""
