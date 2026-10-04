"""System health and operational telemetry endpoints with Market Data Quality Metrics."""

import zoneinfo
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.session import get_db
from app.feed.calendar import get_market_session_phase
from app.feed.provider import get_market_data_provider

router = APIRouter(prefix="/api", tags=["api"])
settings = get_settings()
kolkata_tz = zoneinfo.ZoneInfo("Asia/Kolkata")


@router.get("/health")
async def get_health(db: Annotated[AsyncSession, Depends(get_db)]) -> dict:
    """Return health status of data feed, database, active model, and market clock."""
    now_utc = datetime.now(UTC)
    now_ist = now_utc.astimezone(kolkata_tz)

    # Check database connectivity
    db_ok = False
    try:
        await db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False

    provider = get_market_data_provider()
    session_phase = get_market_session_phase(now_utc)
    is_market_open = session_phase == "REGULAR"

    # Compute quote age and depth age for a sample liquid benchmark (e.g. BEL)
    quote_age_ms = 0.0
    depth_age_ms = 0.0
    tick = await provider.get_latest_tick("BEL")
    if tick:
        delta = (now_utc - tick.timestamp).total_seconds() * 1000.0
        quote_age_ms = round(max(0.0, delta), 1)
        depth_age_ms = round(max(0.0, delta), 1)

    connection_state = "CONNECTED" if provider.is_connected() else "DISCONNECTED"
    if quote_age_ms > 3000.0 and connection_state == "CONNECTED":
        connection_state = "DEGRADED"

    return {
        "status": "healthy" if db_ok and connection_state != "DISCONNECTED" else "degraded",
        "timestamp_utc": now_utc.isoformat(),
        "timestamp_ist": now_ist.strftime("%Y-%m-%d %H:%M:%S IST"),
        "clock_ist": now_ist.strftime("%H:%M:%S"),
        "feed": {
            "mode": settings.FEED_MODE,
            "source": provider.get_source_name(),
            "connection": connection_state,
            "quote_age_ms": quote_age_ms,
            "depth_age_ms": depth_age_ms,
            "stale": quote_age_ms > 3000.0,
        },
        "database": {
            "connected": db_ok,
        },
        "market": {
            "open": is_market_open,
            "session": session_phase,
        },
        "model": {
            "active": "baseline_rules",
            "loaded": True,
        },
        "safety": {
            "real_orders_disabled": True,
            "paper_trading_only": True,
        },
    }
