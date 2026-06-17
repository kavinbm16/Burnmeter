"""Tests for estimate_cost_usd — including cache_write_tokens path."""

import pytest

from backend.pricing import estimate_cost_usd


def test_claude_opus_cost_basic():
    cost = estimate_cost_usd("claude-opus-4-8", 1000, 500)
    assert cost == pytest.approx((1000 * 5.00 + 500 * 25.00) / 1_000_000)


def test_claude_cache_write_billed_separately():
    # 800 text input + 200 cache_write (6.25/M), 500 output
    cost = estimate_cost_usd("claude-opus-4-8", 1000, 500, cache_write_tokens=200)
    text_in = 800
    expected = (text_in * 5.00 + 200 * 6.25 + 500 * 25.00) / 1_000_000
    assert cost == pytest.approx(expected)


def test_claude_cache_read_billed_at_read_rate():
    # 700 text input + 300 cache_read (0.50/M), 500 output
    cost = estimate_cost_usd("claude-opus-4-8", 1000, 500, cache_read_tokens=300)
    text_in = 700
    expected = (text_in * 5.00 + 300 * 0.50 + 500 * 25.00) / 1_000_000
    assert cost == pytest.approx(expected)


def test_claude_all_cache_types():
    # 500 text + 300 cache_write + 200 cache_read, 500 output
    cost = estimate_cost_usd(
        "claude-opus-4-8", 1000, 500,
        cache_read_tokens=200, cache_write_tokens=300,
    )
    text_in = 500
    expected = (text_in * 5.00 + 300 * 6.25 + 200 * 0.50 + 500 * 25.00) / 1_000_000
    assert cost == pytest.approx(expected)


def test_claude_sonnet_prices():
    cost = estimate_cost_usd("claude-sonnet-4-6", 1_000_000, 1_000_000)
    assert cost == pytest.approx(3.00 + 15.00)


def test_claude_haiku_prices():
    cost = estimate_cost_usd("claude-haiku-4-5", 1_000_000, 1_000_000)
    assert cost == pytest.approx(1.00 + 5.00)


def test_claude_versioned_model_id_matches():
    cost = estimate_cost_usd("claude-opus-4-8-20260101", 1_000_000, 0)
    assert cost == pytest.approx(5.00)


def test_gemini_cache_write_zero_no_effect():
    cost_before = estimate_cost_usd("gemini-2.5-flash", 1000, 500)
    cost_after = estimate_cost_usd("gemini-2.5-flash", 1000, 500, cache_write_tokens=200)
    assert cost_before is not None
    assert cost_after is not None


def test_unknown_model_returns_none():
    assert estimate_cost_usd("gpt-9000-turbo", 1000, 500) is None
