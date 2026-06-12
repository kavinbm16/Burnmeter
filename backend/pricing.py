"""Static price table — used ONLY where the provider doesn't return real cost
(Gemini proxy capture). Values are USD per 1M tokens and may drift from the
provider's price page; every cost derived here is flagged cost_estimated=True
and rendered with a "≈" prefix in the UI.

Update path for contributors: edit PRICES, run tests, PR.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelPrice:
    input_per_m: float
    output_per_m: float
    cache_read_per_m: float = 0.0


# Gemini API (generativelanguage.googleapis.com), standard tier, prices as of 2026-06.
PRICES: dict[str, ModelPrice] = {
    "gemini-2.5-pro": ModelPrice(1.25, 10.00, 0.31),
    "gemini-2.5-flash": ModelPrice(0.30, 2.50, 0.075),
    "gemini-2.5-flash-lite": ModelPrice(0.10, 0.40, 0.025),
    "gemini-2.0-flash": ModelPrice(0.10, 0.40, 0.025),
    "gemini-2.0-flash-lite": ModelPrice(0.075, 0.30),
}


def _lookup(model: str) -> ModelPrice | None:
    if model in PRICES:
        return PRICES[model]
    # tolerate versioned ids like gemini-2.5-flash-preview-05-20
    candidates = [name for name in PRICES if model.startswith(name)]
    if candidates:
        return PRICES[max(candidates, key=len)]
    return None


def estimate_cost_usd(
    model: str, input_tokens: int, output_tokens: int, cache_read_tokens: int = 0
) -> float | None:
    """Estimated cost, or None when the model isn't in the table (UI shows 'unpriced')."""
    p = _lookup(model)
    if p is None:
        return None
    return (
        (input_tokens - cache_read_tokens) * p.input_per_m
        + cache_read_tokens * p.cache_read_per_m
        + output_tokens * p.output_per_m
    ) / 1_000_000
