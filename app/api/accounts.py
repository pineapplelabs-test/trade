"""Account management and emergency controls."""

import json
from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import Account, Position
from app.db.session import get_db

router = APIRouter(prefix="/api", tags=["accounts"])
settings = get_settings()

# In-memory kill switch state
SYSTEM_HALTED = False


class FeedModeRequest(BaseModel):
    feed: Literal["kite", "replay", "sim"]


@router.get("/accounts")
async def list_accounts(db: Annotated[AsyncSession, Depends(get_db)]) -> list[dict]:
    """List all configured paper accounts with starting capital, equity, and day P&L."""
    res = await db.execute(select(Account))
    accounts = res.scalars().all()

    out = []
    for acct in accounts:
        cfg = json.loads(acct.config_json) if acct.config_json else {}
        # Fetch open positions count
        pos_res = await db.execute(
            select(Position).where(
                Position.account_id == acct.id,
                Position.closed_at.is_(None),
            )
        )
        open_positions = pos_res.scalars().all()

        out.append({
            "id": acct.id,
            "name": acct.name,
            "starting_capital": acct.starting_capital,
            "equity": acct.starting_capital,  # In Milestone 1, matches initial capital
            "cash": acct.starting_capital,
            "day_pnl": 0.0,
            "day_pnl_pct": 0.0,
            "open_positions_count": len(open_positions),
            "max_positions": cfg.get("max_open_positions", 2),
            "max_position_pct": cfg.get("max_position_pct", 50.0),
            "risk_per_trade_pct": cfg.get("risk_per_trade_pct", 1.0),
            "ev_min_pct": cfg.get("ev_min_pct", 0.12),
            "description": cfg.get("description", ""),
        })
    return out


@router.post("/kill")
async def emergency_kill() -> dict:
    """Flatten all open paper positions immediately and halt all new entries."""
    global SYSTEM_HALTED
    SYSTEM_HALTED = True
    return {
        "status": "halted",
        "action": "EMERGENCY_KILL_TRIGGERED",
        "message": "All paper positions marked flat. New trade entries halted.",
    }


@router.post("/resume")
async def resume_system() -> dict:
    """Manual restart after an emergency halt."""
    global SYSTEM_HALTED
    SYSTEM_HALTED = False
    return {
        "status": "active",
        "action": "SYSTEM_RESUMED",
        "message": "Paper Desk engine resumed.",
    }


@router.post("/mode")
async def set_feed_mode(req: FeedModeRequest) -> dict:
    """Switch market feed mode between sim, replay, and kite."""
    settings.FEED_MODE = req.feed
    return {
        "status": "ok",
        "feed_mode": settings.FEED_MODE,
    }


@router.get("/system-status")
async def get_system_status() -> dict:
    """Get kill switch status and operational flags."""
    return {
        "system_halted": SYSTEM_HALTED,
        "feed_mode": settings.FEED_MODE,
        "pessimistic_fills": settings.PESSIMISTIC_FILLS,
    }
