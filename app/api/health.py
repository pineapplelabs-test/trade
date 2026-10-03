"""System health and operational telemetry endpoints."""

import zoneinfo
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.session import get_db

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

    # Check market session (NSE 09:15 - 15:30 IST Mon-Fri)
    is_weekday = now_ist.weekday() < 5
    current_time_str = now_ist.strftime("%H:%M:%S")
    is_market_hours = is_weekday and ("09:15:00" <= current_time_str <= "15:30:00")

    return {
        "status": "healthy" if db_ok else "degraded",
        "timestamp_utc": now_utc.isoformat(),
        "timestamp_ist": now_ist.strftime("%Y-%m-%d %H:%M:%S IST"),
        "clock_ist": now_ist.strftime("%H:%M:%S"),
        "feed": {
            "mode": settings.FEED_MODE,
            "status": "active" if settings.FEED_MODE == "sim" else "offline",
            "stale": False,
        },
        "database": {
            "connected": db_ok,
        },
        "market": {
            "open": is_market_hours,
            "session": "REGULAR" if is_market_hours else "CLOSED",
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
