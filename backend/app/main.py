"""MedOrchestra API — FastAPI application entry point."""
from __future__ import annotations

import asyncio
import logging
import threading
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import jwt
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from . import __version__
from .config import settings
from .database import Base, engine
from .events import bus
from .routers import (agents, ambulance, appointments, auth, billing, clinical, copilot, dashboard, docs, governance, insights, monitor,
                      patients, public, resources, staff, surgery, twin, users, ward)
from .security import decode_token

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("medorchestra")

FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"


def _warm_models() -> None:
    """Train the ML models in the background so the first request is fast."""
    from .agents.nlp import model_card
    from .services.los_model import warm
    from .services.readmission import model_card as readmission_card

    warm()
    readmission_card()
    model_card()


@asynccontextmanager
async def lifespan(app: FastAPI):
    from .seed import is_stale, needs_seed, reset_and_seed, schema_outdated
    from .services.dispatch import tracker
    from .services.telemetry import hub

    if schema_outdated():
        log.info("Database schema changed — rebuilding demo hospital data …")
        reset_and_seed()
    Base.metadata.create_all(bind=engine)
    if needs_seed() or is_stale():
        log.info("Seeding demo hospital data …")
        reset_and_seed()
    loop = asyncio.get_running_loop()
    bus.bind_loop(loop)
    default_handler = loop.get_exception_handler()

    def quiet_disconnects(lp, context):
        # Windows' Proactor loop logs a traceback whenever a browser drops a socket abruptly
        # (tab closed mid-WebSocket). It is harmless noise, so keep the console readable.
        if isinstance(context.get("exception"), (ConnectionResetError, ConnectionAbortedError)):
            return
        if default_handler is None:
            lp.default_exception_handler(context)
        else:
            default_handler(lp, context)

    loop.set_exception_handler(quiet_disconnects)
    threading.Thread(target=_warm_models, daemon=True, name="model-warmup").start()
    if settings.fleet_tracker:
        tracker.start()
    if settings.telemetry_enabled:
        hub.start()
    log.info("LLM understanding: %s", f"Claude ({settings.llm_model})" if settings.llm_available else "local NLP pipeline (no API key)")
    yield
    from .simulation import simulator
    simulator.stop()
    tracker.stop()
    hub.stop()


app = FastAPI(
    title="MedOrchestra — Multi-Agent AI Hospital Management API",
    description="Hospital resource optimisation, clinical workflow automation and patient-care coordination "
                "through specialised AI agents with human-in-the-loop control.",
    version=__version__,
    lifespan=lifespan,
)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), geolocation=(self), microphone=(self)",
    "Cross-Origin-Opener-Policy": "same-origin",
}


@app.middleware("http")
async def request_context(request: Request, call_next):
    """Request id + timing for tracing, and baseline security headers on every response."""
    rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
    t0 = time.perf_counter()
    response = await call_next(request)
    response.headers["X-Request-ID"] = rid
    response.headers["X-Process-Time-ms"] = f"{(time.perf_counter() - t0) * 1000:.1f}"
    for k, v in SECURITY_HEADERS.items():
        response.headers.setdefault(k, v)
    return response


for r in (auth, users, dashboard, patients, ward, resources, surgery, appointments, staff, clinical, agents, insights,
          billing, ambulance, twin, copilot, governance, public, docs, monitor):
    app.include_router(r.router)


@app.get("/api/health", tags=["system"])
def health():
    try:
        with engine.connect() as conn:
            conn.execute(text("select 1"))
        db_ok = True
    except Exception:  # pragma: no cover
        db_ok = False
    return {"status": "ok" if db_ok else "degraded", "version": __version__, "database": db_ok}


@app.websocket("/ws")
async def websocket(ws: WebSocket, token: str | None = None):
    try:
        payload = decode_token(token or "")
    except jwt.PyJWTError:
        await ws.close(code=4401)
        return
    await bus.connect(ws, {"id": payload.get("sub"), "role": payload.get("role")})
    try:
        while True:
            msg = await ws.receive_text()
            if msg == "ping":
                await ws.send_text('{"type":"pong"}')
    except WebSocketDisconnect:
        bus.disconnect(ws)
    except Exception:
        bus.disconnect(ws)


# Serve the built React app (single-server deployment) when frontend/dist exists.
if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        if full_path.startswith(("api/", "ws")):  # unknown API path → real 404, never the SPA shell
            return JSONResponse({"detail": "Not Found"}, status_code=404)
        candidate = FRONTEND_DIST / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(FRONTEND_DIST / "index.html", headers={"Cache-Control": "no-cache"})
