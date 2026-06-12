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
from typing import Callable
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import Response, StreamingResponse

from backend.keys import KeyStore
from backend.pricing import estimate_cost_usd
from backend.providers.base import UsageRecord, mask_key
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


def _modality_tokens(details: list | None, modality: str) -> int:
    """Sum tokenCount entries of one modality from {prompt,response}TokensDetails."""
    if not details:
        return 0
    return sum(
        int(d.get("tokenCount", 0))
        for d in details
        if isinstance(d, dict) and d.get("modality", "").upper() == modality
    )


def usage_to_record(model: str, usage: dict, source: str, key_id: str) -> UsageRecord:
    """Normalize a Gemini usageMetadata payload (HTTP or Live) to a UsageRecord.

    Live responses split tokens by modality in promptTokensDetails /
    responseTokensDetails; audio tokens bill at premium rates.
    """
    prompt = int(usage.get("promptTokenCount", 0))
    candidates = int(usage.get("candidatesTokenCount", 0))
    # Live uses responseTokenCount instead of candidatesTokenCount
    response = int(usage.get("responseTokenCount", 0)) or candidates
    thoughts = int(usage.get("thoughtsTokenCount", 0))
    cached = int(usage.get("cachedContentTokenCount", 0))
    output = response + thoughts  # thinking tokens are billed as output
    audio_in = _modality_tokens(usage.get("promptTokensDetails"), "AUDIO")
    audio_out = _modality_tokens(usage.get("responseTokensDetails"), "AUDIO")
    cost = estimate_cost_usd(model, prompt, output, cached, audio_in, audio_out)
    return UsageRecord(
        provider="gemini",
        model=model,
        date=datetime.now(tz=timezone.utc).strftime("%Y-%m-%d"),
        input_tokens=prompt,
        output_tokens=output,
        cache_read_tokens=cached,
        audio_input_tokens=audio_in,
        audio_output_tokens=audio_out,
        requests=1,
        cost_usd=cost,
        source=source,
        cost_estimated=True,
        key_id=key_id,
    )


async def record_usage(
    store: Store,
    model: str,
    usage: dict,
    on_capture: Callable | None = None,
    source: str = "proxy",
    key_id: str = "",
) -> None:
    rec = usage_to_record(model, usage, source, key_id)
    await store.increment_usage(rec)
    if on_capture is not None:
        try:
            await on_capture(
                {
                    "provider": "gemini",
                    "model": model,
                    "input_tokens": rec.input_tokens,
                    "output_tokens": rec.output_tokens,
                    "cache_read_tokens": rec.cache_read_tokens,
                    "audio_input_tokens": rec.audio_input_tokens,
                    "audio_output_tokens": rec.audio_output_tokens,
                    "cost_usd": rec.cost_usd,
                    "source": source,
                    "key_id": key_id,
                    "ts": datetime.now(tz=timezone.utc).isoformat(),
                }
            )
        except Exception:
            logger.exception("live capture callback failed")


def build_router(
    store: Store, keystore: KeyStore, on_capture: Callable | None = None
) -> APIRouter:
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

        used_key = (
            next((v for k, v in request.headers.items() if k.lower() == "x-goog-api-key"), None)
            or params.get("key")
            or headers.get("x-goog-api-key")
        )
        key_id = mask_key(used_key) if used_key else ""

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
                                await record_usage(store, model, usage, on_capture, source="proxy", key_id=key_id)
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
                    await record_usage(store, model, usage, on_capture, source="proxy", key_id=key_id)
                except Exception:
                    logger.exception("failed to record proxy usage")
        return Response(content=content, status_code=resp.status_code, headers=resp_headers)

    return router
