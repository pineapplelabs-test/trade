"""Paper Desk FastAPI Application Entry Point."""

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

import structlog
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.accounts import router as accounts_router
from app.api.analytics import router as analytics_router
from app.api.health import router as health_router
from app.api.premarket import router as premarket_router
from app.api.readiness import router as readiness_router
from app.api.scanner import router as scanner_router
from app.api.trades import router as trades_router
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

    # Load any existing persisted paper trades and open positions from SQLite
    from app.portfolio.ledger import global_trade_ledger
    await global_trade_ledger.load_trades_from_db()

    # Seed initial authentic paper trades into ledger if completely empty
    from app.portfolio.seed_trades import seed_demo_trades_if_empty
    seed_demo_trades_if_empty()

    # Start Groww live feed if configured
    if settings.FEED_MODE == "groww":
        from app.feed.groww_feed import groww_feed
        await groww_feed.connect()

    # Start live telemetry WebSocket background task
    broadcast_task = asyncio.create_task(manager.start_broadcaster())

    yield

    # Clean shutdown
    if settings.FEED_MODE == "groww":
        from app.feed.groww_feed import groww_feed
        await groww_feed.disconnect()

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

# Strict CORS: Explicit configurable allowlist (wildcards forbidden with credentials)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Register API Routers
app.include_router(auth_router)
app.include_router(health_router)
app.include_router(accounts_router)
app.include_router(scanner_router)
app.include_router(trades_router)
app.include_router(analytics_router)
app.include_router(readiness_router)
app.include_router(premarket_router)


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


# Serve Static Assets & Main Dashboard
app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")


@app.get("/", response_class=FileResponse)
async def serve_index():
    """Serve single-page vanilla JS dashboard."""
    return FileResponse(str(WEB_DIR / "index.html"))
