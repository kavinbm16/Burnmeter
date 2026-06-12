"""Burnmeter API server. Binds 127.0.0.1 only — this app is local-first by design."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend.keys import KeyStore, install_redaction
from backend.pricing import PRICES
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


class LiveHub:
    """Fan-out of proxy capture events to connected dashboard websockets."""

    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._clients.add(ws)

    def disconnect(self, ws: WebSocket) -> None:
        self._clients.discard(ws)

    async def publish(self, event: dict) -> None:
        dead = []
        for ws in self._clients:
            try:
                await ws.send_json(event)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


live_hub = LiveHub()

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
app.include_router(build_gemini_proxy(store, keystore, on_capture=live_hub.publish))


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
async def overview(period: str = "30d", date: str | None = None):
    if date:
        start = end = date
    else:
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


class BudgetRequest(BaseModel):
    monthly_usd: float | None


@app.get("/api/budget")
async def get_budget():
    today = datetime.now(tz=timezone.utc).date()
    month_start = today.replace(day=1).isoformat()
    spent = await store.overview(month_start, today.isoformat())
    next_month = (today.replace(day=28) + timedelta(days=4)).replace(day=1)
    days_in_month = (next_month - today.replace(day=1)).days
    days_elapsed = today.day
    mtd = spent["totals"]["cost_usd"] or 0.0
    pace = (mtd / days_elapsed) * days_in_month if days_elapsed else 0.0
    return {
        "monthly_usd": await store.get_budget(),
        "spent_mtd": mtd,
        "projected_eom": pace,
        "days_elapsed": days_elapsed,
        "days_in_month": days_in_month,
    }


@app.put("/api/budget")
async def put_budget(req: BudgetRequest):
    if req.monthly_usd is not None and req.monthly_usd < 0:
        raise HTTPException(status_code=400, detail="budget must be >= 0")
    await store.set_budget(req.monthly_usd)
    return {"ok": True}


@app.get("/api/heatmap")
async def heatmap(days: int = 120):
    today = datetime.now(tz=timezone.utc).date()
    start = today - timedelta(days=min(days, 366))
    return {
        "start": start.isoformat(),
        "end": today.isoformat(),
        "days": await store.heatmap(start.isoformat(), today.isoformat()),
    }


@app.get("/api/models")
async def models(period: str = "30d", date: str | None = None):
    if date:
        start = end = date
    else:
        start, end = _period_range(period)
    return {"models": await store.models_leaderboard(start, end), "period": {"start": start, "end": end}}


@app.get("/api/pricing")
async def pricing():
    return {
        m: {"input_per_m": p.input_per_m, "output_per_m": p.output_per_m}
        for m, p in PRICES.items()
    }


@app.websocket("/ws/live")
async def ws_live(ws: WebSocket):
    await live_hub.connect(ws)
    try:
        while True:
            await ws.receive_text()  # keepalive pings from client; content ignored
    except WebSocketDisconnect:
        live_hub.disconnect(ws)


# Serve the built frontend when present (production mode).
DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if DIST.exists():
    app.mount("/", StaticFiles(directory=DIST, html=True), name="frontend")


def run() -> None:
    port = int(os.environ.get("BURNMETER_PORT", "8400"))
    uvicorn.run(app, host="127.0.0.1", port=port)


if __name__ == "__main__":
    run()
