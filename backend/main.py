"""Burnmeter API server. Binds 127.0.0.1 only — this app is local-first by design."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend.keys import KeyStore, install_redaction
from backend.providers.base import InvalidKeyError, ProviderError, mask_key
from backend.providers.openai_adapter import OpenAIAdapter
from backend.proxy.gemini_proxy import build_router as build_gemini_proxy
from backend.store import Store
from backend.sync import SyncEngine

logging.basicConfig(level=logging.INFO)
install_redaction()

store = Store()
keystore = KeyStore()
adapters = {"openai": OpenAIAdapter()}
sync_engine = SyncEngine(store, keystore, adapters)

# Providers that work purely via local capture (no usage API to poll).
PROXY_ONLY = {
    "gemini": {
        "display_name": "Google Gemini",
        "key_hint": (
            "Gemini has no usage API. Add your key here and point your apps at the "
            "local proxy URL — usage is counted from each response. Storing the key "
            "is optional; the proxy also passes through caller-supplied keys."
        ),
    }
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    await store.init()
    sync_engine.start()
    yield
    await sync_engine.stop()


app = FastAPI(title="Burnmeter", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(build_gemini_proxy(store, keystore))


def _period_range(period: str) -> tuple[str, str]:
    today = datetime.now(tz=timezone.utc).date()
    if period == "mtd":
        start = today.replace(day=1)
    elif period == "90d":
        start = today - timedelta(days=90)
    else:  # default 30d
        start = today - timedelta(days=30)
    return start.isoformat(), today.isoformat()


class AddProviderRequest(BaseModel):
    name: str  # "openai" | "gemini"
    key: str


@app.get("/api/overview")
async def overview(period: str = "30d"):
    start, end = _period_range(period)
    data = await store.overview(start, end)
    data["period"] = {"start": start, "end": end}
    return data


@app.get("/api/providers")
async def list_providers():
    rows = await store.list_providers()
    known = {
        name: {"display_name": a.display_name, "key_hint": a.key_hint, "mode": "usage_api"}
        for name, a in adapters.items()
    }
    for name, meta in PROXY_ONLY.items():
        known[name] = {**meta, "mode": "proxy"}
    return {"configured": rows, "available": known}


@app.post("/api/providers")
async def add_provider(req: AddProviderRequest):
    name = req.name.lower()
    if name in adapters:
        adapter = adapters[name]
        try:
            info = await adapter.validate_key(req.key)
        except InvalidKeyError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except ProviderError as e:
            raise HTTPException(status_code=502, detail=str(e))
        keystore.set_key(name, req.key)
        await store.add_provider(name, adapter.display_name, info.masked_key, info.label)
        # kick off the 90-day backfill in the background
        import asyncio

        asyncio.create_task(sync_engine.sync_provider(name, backfill=True))
        return {"ok": True, "masked_key": info.masked_key}
    if name in PROXY_ONLY:
        keystore.set_key(name, req.key)
        await store.add_provider(
            name, PROXY_ONLY[name]["display_name"], mask_key(req.key), "proxy capture"
        )
        await store.set_sync_state(name, "proxy")
        return {"ok": True, "masked_key": mask_key(req.key)}
    raise HTTPException(status_code=404, detail=f"unknown provider: {name}")


@app.delete("/api/providers/{name}")
async def remove_provider(name: str):
    keystore.delete_key(name)
    await store.remove_provider(name)
    return {"ok": True}


@app.post("/api/sync")
async def trigger_sync(provider: str | None = None):
    if provider:
        await sync_engine.sync_provider(provider)
    else:
        await sync_engine.sync_all()
    return {"ok": True}


@app.get("/api/providers/{name}/breakdown")
async def breakdown(name: str, period: str = "30d"):
    start, end = _period_range(period)
    data = await store.breakdown(name, start, end)
    data["period"] = {"start": start, "end": end}
    return data


# Serve the built frontend when present (production mode).
DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if DIST.exists():
    app.mount("/", StaticFiles(directory=DIST, html=True), name="frontend")


def run() -> None:
    port = int(os.environ.get("BURNMETER_PORT", "8400"))
    uvicorn.run(app, host="127.0.0.1", port=port)


if __name__ == "__main__":
    run()
