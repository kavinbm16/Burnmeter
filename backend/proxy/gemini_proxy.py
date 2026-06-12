"""Gemini passthrough proxy with usage capture.

Point any Gemini SDK at http://127.0.0.1:8400/proxy/gemini and it behaves like
generativelanguage.googleapis.com — we forward verbatim and record only the
usageMetadata token counts from responses. Request/response bodies are never
persisted.

Security properties:
- Upstream host is hardcoded (UPSTREAM); the proxy cannot be used to reach
  anything else.
- If a Gemini key is stored in the KeyStore, it is injected server-side via the
  x-goog-api-key header so client apps don't need to embed it. Caller-supplied
  keys pass through untouched.

Streaming: streamGenerateContent SSE chunks each carry a cumulative
usageMetadata; the last chunk wins.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import Response, StreamingResponse

from backend.keys import KeyStore
from backend.pricing import estimate_cost_usd
from backend.providers.base import UsageRecord
from backend.store import Store

logger = logging.getLogger(__name__)

UPSTREAM = "https://generativelanguage.googleapis.com"
MODEL_RE = re.compile(r"models/([^:/?]+)")
HOP_BY_HOP = {
    "host", "content-length", "transfer-encoding", "connection", "keep-alive",
    "proxy-authenticate", "proxy-authorization", "te", "trailers", "upgrade",
    "accept-encoding",
}


def _extract_usage(payload: dict) -> dict | None:
    return payload.get("usageMetadata")


def _last_usage_from_sse(buffer: bytes) -> dict | None:
    """Parse SSE buffer; return the final (cumulative) usageMetadata seen."""
    usage = None
    for line in buffer.split(b"\n"):
        line = line.strip()
        if not line.startswith(b"data:"):
            continue
        raw = line[len(b"data:"):].strip()
        if not raw or raw == b"[DONE]":
            continue
        try:
            chunk = json.loads(raw)
        except json.JSONDecodeError:
            continue
        u = _extract_usage(chunk) if isinstance(chunk, dict) else None
        if u:
            usage = u
    return usage


def _last_usage_from_json(buffer: bytes) -> dict | None:
    """Non-SSE responses: single JSON object, or a JSON array of chunks."""
    try:
        payload = json.loads(buffer)
    except json.JSONDecodeError:
        return None
    if isinstance(payload, dict):
        return _extract_usage(payload)
    if isinstance(payload, list):
        usage = None
        for chunk in payload:
            if isinstance(chunk, dict) and _extract_usage(chunk):
                usage = _extract_usage(chunk)
        return usage
    return None


async def _record(store: Store, model: str, usage: dict) -> None:
    prompt = int(usage.get("promptTokenCount", 0))
    candidates = int(usage.get("candidatesTokenCount", 0))
    thoughts = int(usage.get("thoughtsTokenCount", 0))
    cached = int(usage.get("cachedContentTokenCount", 0))
    output = candidates + thoughts  # thinking tokens are billed as output
    cost = estimate_cost_usd(model, prompt, output, cached)
    await store.increment_usage(
        UsageRecord(
            provider="gemini",
            model=model,
            date=datetime.now(tz=timezone.utc).strftime("%Y-%m-%d"),
            input_tokens=prompt,
            output_tokens=output,
            cache_read_tokens=cached,
            requests=1,
            cost_usd=cost,
            source="proxy",
            cost_estimated=True,
        )
    )


def build_router(store: Store, keystore: KeyStore) -> APIRouter:
    router = APIRouter()

    @router.api_route(
        "/proxy/gemini/{path:path}",
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    )
    async def gemini_proxy(request: Request, path: str):
        headers = {
            k: v for k, v in request.headers.items() if k.lower() not in HOP_BY_HOP
        }
        params = dict(request.query_params)
        # inject stored key only when the caller didn't bring their own
        if "x-goog-api-key" not in {k.lower() for k in headers} and "key" not in params:
            stored = keystore.get_key("gemini")
            if stored:
                headers["x-goog-api-key"] = stored

        body = await request.body()
        model_match = MODEL_RE.search(path)
        model = model_match.group(1) if model_match else "unknown"
        is_stream = "streamGenerateContent" in path

        client = httpx.AsyncClient(base_url=UPSTREAM, timeout=httpx.Timeout(300, connect=15))
        upstream = client.build_request(
            request.method, f"/{path}", params=params, headers=headers, content=body
        )
        resp = await client.send(upstream, stream=True)
        resp_headers = {
            k: v for k, v in resp.headers.items() if k.lower() not in HOP_BY_HOP
        }

        if is_stream:
            async def relay():
                buffer = bytearray()
                try:
                    async for chunk in resp.aiter_bytes():
                        buffer.extend(chunk)
                        yield chunk
                finally:
                    await resp.aclose()
                    await client.aclose()
                    if resp.status_code < 400:
                        usage = _last_usage_from_sse(bytes(buffer)) or _last_usage_from_json(bytes(buffer))
                        if usage:
                            try:
                                await _record(store, model, usage)
                            except Exception:
                                logger.exception("failed to record proxy usage")

            return StreamingResponse(
                relay(), status_code=resp.status_code, headers=resp_headers
            )

        content = await resp.aread()
        await resp.aclose()
        await client.aclose()
        if resp.status_code < 400:
            usage = _last_usage_from_json(content)
            if usage:
                try:
                    await _record(store, model, usage)
                except Exception:
                    logger.exception("failed to record proxy usage")
        return Response(content=content, status_code=resp.status_code, headers=resp_headers)

    return router
