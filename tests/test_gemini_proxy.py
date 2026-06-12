"""Gemini proxy tests: passthrough + usage capture, never persisting bodies."""

import json

import httpx
import pytest
import respx
from fastapi import FastAPI

from backend.keys import KeyStore
from backend.proxy.gemini_proxy import build_router
from backend.store import Store

GENERATE = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-2.5-flash:generateContent"
)

RESPONSE = {
    "candidates": [{"content": {"parts": [{"text": "hi"}]}}],
    "usageMetadata": {
        "promptTokenCount": 100,
        "candidatesTokenCount": 40,
        "thoughtsTokenCount": 10,
        "cachedContentTokenCount": 20,
        "totalTokenCount": 150,
    },
}

SSE_BODY = (
    b'data: {"candidates":[{"content":{"parts":[{"text":"h"}]}}],'
    b'"usageMetadata":{"promptTokenCount":100,"candidatesTokenCount":5}}\n\n'
    b'data: {"candidates":[{"content":{"parts":[{"text":"i"}]}}],'
    b'"usageMetadata":{"promptTokenCount":100,"candidatesTokenCount":40,'
    b'"thoughtsTokenCount":10,"cachedContentTokenCount":20}}\n\n'
)


@pytest.fixture
async def env(tmp_path, monkeypatch):
    store = Store(tmp_path / "test.db")
    await store.init()
    ks = KeyStore(fallback_dir=tmp_path / "keys")
    monkeypatch.setattr(ks, "_keyring_available", lambda: False)
    app = FastAPI()
    app.include_router(build_router(store, ks))
    transport = httpx.ASGITransport(app=app)
    client = httpx.AsyncClient(transport=transport, base_url="http://test")
    return store, ks, client


@respx.mock
async def test_non_stream_capture(env):
    store, ks, client = env
    respx.post(GENERATE).mock(return_value=httpx.Response(200, json=RESPONSE))
    resp = await client.post(
        "/proxy/gemini/v1beta/models/gemini-2.5-flash:generateContent",
        json={"contents": [{"parts": [{"text": "hello"}]}]},
        headers={"x-goog-api-key": "AIzaTESTKEY00000000000000"},
    )
    assert resp.status_code == 200
    assert resp.json()["candidates"]  # passthrough intact

    data = await store.breakdown("gemini", "2000-01-01", "2100-01-01")
    assert len(data["by_model"]) == 1
    row = data["by_model"][0]
    assert row["model"] == "gemini-2.5-flash"
    assert row["input_tokens"] == 100
    assert row["output_tokens"] == 50  # candidates + thoughts
    assert row["cache_read_tokens"] == 20
    assert row["requests"] == 1
    assert row["source"] == "proxy"
    assert row["cost_estimated"] == 1
    assert row["cost_usd"] > 0


@respx.mock
async def test_stream_capture_takes_last_chunk(env):
    store, ks, client = env
    respx.post(
        "https://generativelanguage.googleapis.com/v1beta/models/"
        "gemini-2.5-flash:streamGenerateContent"
    ).mock(
        return_value=httpx.Response(
            200, content=SSE_BODY, headers={"content-type": "text/event-stream"}
        )
    )
    resp = await client.post(
        "/proxy/gemini/v1beta/models/gemini-2.5-flash:streamGenerateContent?alt=sse",
        json={"contents": [{"parts": [{"text": "hello"}]}]},
        headers={"x-goog-api-key": "AIzaTESTKEY00000000000000"},
    )
    assert resp.status_code == 200
    data = await store.breakdown("gemini", "2000-01-01", "2100-01-01")
    row = data["by_model"][0]
    assert row["input_tokens"] == 100
    assert row["output_tokens"] == 50  # last cumulative chunk, not sum of chunks
    assert row["requests"] == 1


@respx.mock
async def test_stored_key_injected(env):
    store, ks, client = env
    ks.set_key("gemini", "AIzaSTOREDKEY9999999999999")
    route = respx.post(GENERATE).mock(return_value=httpx.Response(200, json=RESPONSE))
    await client.post(
        "/proxy/gemini/v1beta/models/gemini-2.5-flash:generateContent",
        json={"contents": []},
    )
    sent = route.calls[0].request
    assert sent.headers["x-goog-api-key"] == "AIzaSTOREDKEY9999999999999"


@respx.mock
async def test_caller_key_not_overridden(env):
    store, ks, client = env
    ks.set_key("gemini", "AIzaSTOREDKEY9999999999999")
    route = respx.post(GENERATE).mock(return_value=httpx.Response(200, json=RESPONSE))
    await client.post(
        "/proxy/gemini/v1beta/models/gemini-2.5-flash:generateContent",
        json={"contents": []},
        headers={"x-goog-api-key": "AIzaCALLERKEY8888888888888"},
    )
    assert route.calls[0].request.headers["x-goog-api-key"] == "AIzaCALLERKEY8888888888888"


@respx.mock
async def test_error_responses_not_recorded(env):
    store, ks, client = env
    respx.post(GENERATE).mock(return_value=httpx.Response(400, json={"error": "bad"}))
    resp = await client.post(
        "/proxy/gemini/v1beta/models/gemini-2.5-flash:generateContent",
        json={},
        headers={"x-goog-api-key": "AIzaTESTKEY00000000000000"},
    )
    assert resp.status_code == 400
    data = await store.breakdown("gemini", "2000-01-01", "2100-01-01")
    assert data["by_model"] == []


@respx.mock
async def test_request_bodies_never_persisted(env, tmp_path):
    store, ks, client = env
    secret_prompt = "SUPER_SECRET_PROMPT_CONTENT_XYZ"
    respx.post(GENERATE).mock(return_value=httpx.Response(200, json=RESPONSE))
    await client.post(
        "/proxy/gemini/v1beta/models/gemini-2.5-flash:generateContent",
        json={"contents": [{"parts": [{"text": secret_prompt}]}]},
        headers={"x-goog-api-key": "AIzaTESTKEY00000000000000"},
    )
    blob = (tmp_path / "test.db").read_bytes()
    assert secret_prompt.encode() not in blob
