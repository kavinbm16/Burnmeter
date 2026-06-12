"""Gemini Live (BidiGenerateContent) usage accounting tests.

The relay itself is exercised against a fake in-process websocket server;
usage normalization and pricing are tested directly on usage_to_record.
"""

import asyncio
import json

import pytest
import websockets

from backend.keys import KeyStore
from backend.pricing import estimate_cost_usd
from backend.providers.base import UsageRecord
from backend.proxy.gemini_proxy import usage_to_record
from backend.store import Store

LIVE_USAGE = {
    "promptTokenCount": 1000,
    "responseTokenCount": 500,
    "totalTokenCount": 1500,
    "promptTokensDetails": [
        {"modality": "AUDIO", "tokenCount": 800},
        {"modality": "TEXT", "tokenCount": 200},
    ],
    "responseTokensDetails": [
        {"modality": "AUDIO", "tokenCount": 450},
        {"modality": "TEXT", "tokenCount": 50},
    ],
}


def test_live_usage_modality_split():
    rec = usage_to_record(
        "gemini-2.5-flash-native-audio", LIVE_USAGE, "live_proxy", "AIz…ab12"
    )
    assert rec.input_tokens == 1000
    assert rec.output_tokens == 500
    assert rec.audio_input_tokens == 800
    assert rec.audio_output_tokens == 450
    assert rec.source == "live_proxy"
    assert rec.key_id == "AIz…ab12"
    # text-in 200*0.50 + audio-in 800*3.00 + text-out 50*2.00 + audio-out 450*12.00 (per 1M)
    expected = (200 * 0.50 + 800 * 3.00 + 50 * 2.00 + 450 * 12.00) / 1e6
    assert rec.cost_usd == pytest.approx(expected)


def test_audio_premium_vs_text_only():
    audio_cost = estimate_cost_usd(
        "gemini-2.5-flash-native-audio", 1000, 500,
        audio_input_tokens=1000, audio_output_tokens=500,
    )
    text_cost = estimate_cost_usd("gemini-2.5-flash-native-audio", 1000, 500)
    assert audio_cost > text_cost


def test_models_without_audio_rates_bill_audio_as_text():
    a = estimate_cost_usd("gemini-2.5-flash", 1000, 500, audio_input_tokens=1000)
    b = estimate_cost_usd("gemini-2.5-flash", 1000, 500)
    assert a == b


def test_live_model_prefix_lookup():
    # versioned live ids must resolve to the live price, not base flash
    versioned = estimate_cost_usd(
        "gemini-2.5-flash-native-audio-preview-09-2025", 0, 0, audio_output_tokens=1_000_000
    )
    assert versioned == pytest.approx(12.00)


async def test_migration_v1_to_v2(tmp_path):
    import aiosqlite

    db_path = tmp_path / "old.db"
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """CREATE TABLE usage_records (
                provider TEXT NOT NULL, model TEXT NOT NULL, date TEXT NOT NULL,
                source TEXT NOT NULL,
                input_tokens INTEGER NOT NULL DEFAULT 0,
                output_tokens INTEGER NOT NULL DEFAULT 0,
                cache_read_tokens INTEGER NOT NULL DEFAULT 0,
                cache_write_tokens INTEGER NOT NULL DEFAULT 0,
                requests INTEGER NOT NULL DEFAULT 0,
                cost_usd REAL, cost_estimated INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (provider, model, date, source))"""
        )
        await db.execute(
            "INSERT INTO usage_records VALUES ('gemini','m','2026-06-01','proxy',10,5,0,0,1,0.1,1)"
        )
        await db.commit()

    store = Store(db_path)
    await store.init()
    data = await store.breakdown("gemini", "2026-06-01", "2026-06-01")
    assert data["by_model"][0]["input_tokens"] == 10
    # new columns usable after migration
    await store.increment_usage(
        UsageRecord("gemini", "m", "2026-06-01", 5, 2, source="live_proxy",
                    audio_input_tokens=4, key_id="AIz…xx")
    )
    keys = await store.keys_breakdown("gemini", "2026-06-01", "2026-06-01")
    assert keys[0]["key_id"] == "AIz…xx"
    assert keys[0]["audio_input_tokens"] == 4


async def test_keys_breakdown_separates_keys(tmp_path):
    store = Store(tmp_path / "k.db")
    await store.init()
    for key in ("AIz…aaa1", "AIz…bbb2", "AIz…aaa1"):
        await store.increment_usage(
            UsageRecord("gemini", "gemini-2.5-flash-native-audio", "2026-06-10",
                        100, 50, audio_input_tokens=80, requests=1, cost_usd=0.01,
                        source="live_proxy", cost_estimated=True, key_id=key)
        )
    keys = await store.keys_breakdown("gemini", "2026-06-01", "2026-06-30")
    assert len(keys) == 2
    top = next(k for k in keys if k["key_id"] == "AIz…aaa1")
    assert top["requests"] == 2
    assert top["audio_input_tokens"] == 160


async def test_ws_relay_captures_turn_usage(tmp_path, monkeypatch, unused_tcp_port):
    """End-to-end: client ↔ relay ↔ fake upstream; usage recorded on turnComplete."""
    import backend.proxy.gemini_live_proxy as live_mod
    import uvicorn
    from fastapi import FastAPI

    store = Store(tmp_path / "live.db")
    await store.init()
    ks = KeyStore(fallback_dir=tmp_path / "keys")
    monkeypatch.setattr(ks, "_keyring_available", lambda: False)

    # fake Gemini Live upstream
    upstream_port = unused_tcp_port

    async def upstream_handler(conn):
        setup = json.loads(await conn.recv())
        assert "setup" in setup
        await conn.send(json.dumps({"setupComplete": {}}))
        await conn.recv()  # client turn
        await conn.send(json.dumps({
            "serverContent": {"modelTurn": {"parts": [{"text": "hi"}]}},
        }))
        await conn.send(json.dumps({
            "serverContent": {"turnComplete": True},
            "usageMetadata": LIVE_USAGE,
        }))
        await conn.wait_closed()

    upstream_server = await websockets.serve(upstream_handler, "127.0.0.1", upstream_port)
    monkeypatch.setattr(live_mod, "LIVE_UPSTREAM_HOST", f"127.0.0.1:{upstream_port}")

    # patch wss → ws for the local fake
    real_connect = websockets.connect
    monkeypatch.setattr(
        live_mod.websockets, "connect",
        lambda url, **kw: real_connect(url.replace("wss://", "ws://"), **kw),
    )

    app = FastAPI()
    app.include_router(live_mod.build_live_router(store, ks))
    relay_port = upstream_port + 1
    config = uvicorn.Config(app, host="127.0.0.1", port=relay_port, log_level="error")
    server = uvicorn.Server(config)
    task = asyncio.create_task(server.serve())
    while not server.started:
        await asyncio.sleep(0.05)

    try:
        uri = (
            f"ws://127.0.0.1:{relay_port}/proxy/gemini/ws/"
            "google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent"
            "?key=AIzaFAKELIVEKEY123456789"
        )
        async with websockets.connect(uri) as client:
            await client.send(json.dumps(
                {"setup": {"model": "models/gemini-2.5-flash-native-audio"}}
            ))
            assert json.loads(await client.recv()) == {"setupComplete": {}}
            await client.send(json.dumps(
                {"clientContent": {"turns": [{"parts": [{"text": "hello"}]}]}}
            ))
            msgs = [json.loads(await client.recv()) for _ in range(2)]
            assert any(m.get("serverContent", {}).get("turnComplete") for m in msgs)
        await asyncio.sleep(0.3)  # let the relay flush
    finally:
        server.should_exit = True
        await task
        upstream_server.close()
        await upstream_server.wait_closed()

    keys = await store.keys_breakdown("gemini", "2000-01-01", "2100-01-01")
    assert len(keys) == 1
    row = keys[0]
    assert row["key_id"].startswith("AIz")
    assert row["audio_input_tokens"] == 800
    assert row["audio_output_tokens"] == 450
    data = await store.breakdown("gemini", "2000-01-01", "2100-01-01")
    assert data["by_model"][0]["model"] == "gemini-2.5-flash-native-audio"
    assert data["by_model"][0]["source"] == "live_proxy"
