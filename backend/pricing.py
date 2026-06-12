"""Static price table — used ONLY where the provider doesn't return real cost
(Gemini proxy capture, HTTP and Live WebSocket). USD per 1M tokens; values may
drift from the provider's price page; every cost derived here is flagged
cost_estimated=True and rendered with a "≈" prefix in the UI.

Live API models bill audio tokens at premium rates, so prices are
modality-split. Verified against ai.google.dev/gemini-api/docs/pricing
on 2026-06-12. Update path for contributors: edit PRICES, run tests, PR.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelPrice:
    input_per_m: float                    # text input
    output_per_m: float                   # text output
    cache_read_per_m: float = 0.0
    audio_input_per_m: float | None = None   # None → audio billed as text
    audio_output_per_m: float | None = None


# Gemini API (generativelanguage.googleapis.com), standard tier, 2026-06.
PRICES: dict[str, ModelPrice] = {
    # standard HTTP models
    "gemini-2.5-pro": ModelPrice(1.25, 10.00, 0.31),
    "gemini-2.5-flash": ModelPrice(0.30, 2.50, 0.075),
    "gemini-2.5-flash-lite": ModelPrice(0.10, 0.40, 0.025),
    "gemini-2.0-flash": ModelPrice(0.10, 0.40, 0.025),
    "gemini-2.0-flash-lite": ModelPrice(0.075, 0.30),
    # Live API models (audio premium)
    "gemini-2.5-flash-native-audio": ModelPrice(
        0.50, 2.00, audio_input_per_m=3.00, audio_output_per_m=12.00
    ),
    "gemini-2.5-flash-preview-native-audio-dialog": ModelPrice(
        0.50, 2.00, audio_input_per_m=3.00, audio_output_per_m=12.00
    ),
    "gemini-3.1-flash-live-preview": ModelPrice(
        0.75, 4.50, audio_input_per_m=3.00, audio_output_per_m=12.00
    ),
    "gemini-2.0-flash-live": ModelPrice(
        0.35, 1.50, audio_input_per_m=2.10, audio_output_per_m=8.50
    ),
}


def _lookup(model: str) -> ModelPrice | None:
    if model in PRICES:
        return PRICES[model]
    # tolerate versioned ids like gemini-2.5-flash-preview-05-20; prefer the
    # longest (most specific) prefix so live variants beat their base model
    candidates = [name for name in PRICES if model.startswith(name)]
    if candidates:
        return PRICES[max(candidates, key=len)]
    return None


def estimate_cost_usd(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int = 0,
    audio_input_tokens: int = 0,
    audio_output_tokens: int = 0,
) -> float | None:
    """Estimated cost, or None when the model isn't in the table.

    `input_tokens`/`output_tokens` are TOTALS (all modalities); the audio
    portions are passed separately and billed at audio rates when the model
    has them, so callers can pass Live usageMetadata totals + modality details
    without pre-splitting.
    """
    p = _lookup(model)
    if p is None:
        return None
    audio_in_rate = p.audio_input_per_m if p.audio_input_per_m is not None else p.input_per_m
    audio_out_rate = p.audio_output_per_m if p.audio_output_per_m is not None else p.output_per_m
    text_in = max(0, input_tokens - cache_read_tokens - audio_input_tokens)
    text_out = max(0, output_tokens - audio_output_tokens)
    return (
        text_in * p.input_per_m
        + cache_read_tokens * p.cache_read_per_m
        + audio_input_tokens * audio_in_rate
        + text_out * p.output_per_m
        + audio_output_tokens * audio_out_rate
    ) / 1_000_000
