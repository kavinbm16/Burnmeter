"""Gemini Live API (BidiGenerateContent) WebSocket proxy with usage capture.

The Live API speaks WebSocket, not HTTP:
  wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.
  v1beta.GenerativeService.BidiGenerateContent?key=API_KEY

Point the SDK at ws://127.0.0.1:8400/proxy/gemini and sessions relay through
here. We forward frames verbatim both ways and only parse server frames for
usageMetadata. Audio payloads are never persisted.

Usage accounting: Live server messages carry per-turn usageMetadata with
modality splits (promptTokensDetails / responseTokensDetails). The same turn's
usageMetadata can appear on several messages (generationComplete, then
turnComplete), so we hold the latest one as pending and flush it on
turnComplete — or on session close if a turn never completed. Audio tokens are
priced at the model's premium audio rates (see pricing.py).

Key attribution: the key arrives as a `key=` query param or `x-goog-api-key`
header (or is injected from the KeyStore). Its masked hint (`AIz…ab12`) is
stored as key_id so usage breaks down per key — full keys never touch the DB.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Callable
from urllib.parse import urlencode

import websockets
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.keys import KeyStore
from backend.providers.base import mask_key
from backend.proxy.gemini_proxy import record_usage
from backend.store import Store

logger = logging.getLogger(__name__)

LIVE_UPSTREAM_HOST = "generativelanguage.googleapis.com"
FORWARD_HEADERS = {"x-goog-api-key", "authorization", "content-type"}


def _parse_frame(raw: str | bytes) -> dict | None:
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


def _extract_model(frame: dict) -> str | None:
    setup = frame.get("setup")
    if isinstance(setup, dict) and isinstance(setup.get("model"), str):
        return setup["model"].split("/")[-1]
    return None


def _is_turn_complete(frame: dict) -> bool:
    sc = frame.get("serverContent")
    return bool(isinstance(sc, dict) and sc.get("turnComplete"))


def build_live_router(
    store: Store, keystore: KeyStore, on_capture: Callable | None = None
) -> APIRouter:
    router = APIRouter()

    @router.websocket("/proxy/gemini/{path:path}")
    async def gemini_live_proxy(ws: WebSocket, path: str):
        await ws.accept()

        params = dict(ws.query_params)
        header_key = next(
            (v for k, v in ws.headers.items() if k.lower() == "x-goog-api-key"), None
        )
        used_key = header_key or params.get("key")
        if not used_key:
            used_key = keystore.get_key("gemini")
            if used_key:
                params["key"] = used_key
        key_id = mask_key(used_key) if used_key else ""

        upstream_url = f"wss://{LIVE_UPSTREAM_HOST}/{path}"
        if params:
            upstream_url += "?" + urlencode(params)
        extra_headers = {
            k: v for k, v in ws.headers.items() if k.lower() in FORWARD_HEADERS
        }

        model = "unknown"
        pending_usage: dict | None = None

        async def flush(usage: dict | None) -> None:
            if usage:
                try:
                    await record_usage(
                        store, model, usage, on_capture, source="live_proxy", key_id=key_id
                    )
                except Exception:
                    logger.exception("failed to record live usage")

        try:
            async with websockets.connect(
                upstream_url, additional_headers=extra_headers, max_size=None
            ) as upstream:

                async def client_to_upstream():
                    nonlocal model
                    while True:
                        msg = await ws.receive()
                        if msg.get("type") == "websocket.disconnect":
                            await upstream.close()
                            return
                        data = msg.get("text") or msg.get("bytes")
                        if data is None:
                            continue
                        frame = _parse_frame(data)
                        if frame:
                            found = _extract_model(frame)
                            if found:
                                model = found
                        await upstream.send(data)

                async def upstream_to_client():
                    nonlocal pending_usage
                    async for data in upstream:
                        frame = _parse_frame(data)
                        if frame:
                            usage = frame.get("usageMetadata")
                            if usage:
                                pending_usage = usage
                            if _is_turn_complete(frame) and pending_usage:
                                await flush(pending_usage)
                                pending_usage = None
                        if isinstance(data, bytes):
                            await ws.send_bytes(data)
                        else:
                            await ws.send_text(data)

                done, pend = await asyncio.wait(
                    [
                        asyncio.create_task(client_to_upstream()),
                        asyncio.create_task(upstream_to_client()),
                    ],
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for t in pend:
                    t.cancel()
        except (WebSocketDisconnect, websockets.ConnectionClosed):
            pass
        except Exception:
            logger.exception("live proxy session failed")
        finally:
            # a turn that produced usage but never sent turnComplete (client hung
            # up mid-response) still gets counted
            await flush(pending_usage)
            try:
                await ws.close()
            except Exception:
                pass

    return router
