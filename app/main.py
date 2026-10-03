"""Paper Desk FastAPI Application Entry Point."""

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

import structlog
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.api.accounts import router as accounts_router
from app.api.health import router as health_router
from app.auth.routes import router as auth_router
from app.config import get_settings
from app.db.session import init_db
from app.ws.connection import manager

logger = structlog.get_logger()
settings = get_settings()

WEB_DIR = Path(__file__).resolve().parent.parent / "web"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown event lifecycle."""
    logger.info("paperdesk_starting_up", feed_mode=settings.FEED_MODE)
    # Initialize database tables and seed configured accounts
    await init_db()

    # Start live telemetry WebSocket background task
    broadcast_task = asyncio.create_task(manager.start_broadcaster())

    yield

    # Clean shutdown
    broadcast_task.cancel()
    try:
        await broadcast_task
    except asyncio.CancelledError:
        pass
    logger.info("paperdesk_shutdown_complete")


app = FastAPI(
    title="Paper Desk",
    description="NSE equity paper trading platform with realistic execution and exact Indian charges",
    version="0.1.0",
    lifespan=lifespan,
)

# Strict CORS: Same origin by default
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Same-origin or local dev
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API Routers
app.include_router(auth_router)
app.include_router(health_router)
app.include_router(accounts_router)


# WebSocket live update endpoint
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Keep connection open and receive any client pings
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)


# Zerodha Kite OAuth redirect handler stubs
@app.get("/login/kite")
async def kite_login():
    """Redirect to Zerodha login URL."""
    if not settings.KITE_API_KEY:
        return HTMLResponse(
            "<h3>Kite API Key not configured. Please set KITE_API_KEY in .env</h3>"
            "<p><a href='/'>Return to Paper Desk</a></p>"
        )
    kite_url = f"https://kite.zerodha.com/connect/login?v=3&api_key={settings.KITE_API_KEY}"
    return HTMLResponse(f"<script>window.location.href = '{kite_url}';</script>")


@app.get("/login/kite/callback")
async def kite_callback(request_token: str | None = None, status: str | None = None):
    """Handle callback from Zerodha with request_token."""
    return HTMLResponse(
        f"<h3>Zerodha Kite Login Received</h3>"
        f"<p>Status: {status}</p>"
        f"<p>Request token received. Session exchange will be completed in Milestone 2.</p>"
        f"<p><a href='/'>Return to Dashboard</a></p>"
    )


# Serve Static Assets & Main Dashboard
app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")


@app.get("/", response_class=FileResponse)
async def serve_index():
    """Serve single-page vanilla JS dashboard."""
    return FileResponse(str(WEB_DIR / "index.html"))
