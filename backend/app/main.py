"""MedOrchestra API — FastAPI application entry point."""
from __future__ import annotations

import asyncio
import logging
import threading
from contextlib import asynccontextmanager
from pathlib import Path

import jwt
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .config import settings
from .database import Base, engine
from .events import bus
from .routers import agents, appointments, auth, clinical, dashboard, insights, patients, resources, staff, surgery, users, ward
from .security import decode_token

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("medorchestra")

FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    from .seed import is_stale, needs_seed, reset_and_seed

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
    from .services.los_model import warm
    threading.Thread(target=warm, daemon=True, name="los-model-warmup").start()
    log.info("LLM understanding: %s", f"Claude ({settings.llm_model})" if settings.llm_available else "local NLP pipeline (no API key)")
    yield
    from .simulation import simulator
    simulator.stop()


app = FastAPI(
    title="MedOrchestra — Multi-Agent AI Hospital Management API",
    description="Hospital resource optimisation, clinical workflow automation and patient-care coordination "
                "through specialised AI agents with human-in-the-loop control.",
    version=__version__,
    lifespan=lifespan,
)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])

for r in (auth, users, dashboard, patients, ward, resources, surgery, appointments, staff, clinical, agents, insights):
    app.include_router(r.router)


@app.get("/api/health", tags=["system"])
def health():
    return {"status": "ok", "version": __version__}


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
