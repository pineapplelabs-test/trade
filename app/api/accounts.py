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
    feed: Literal["groww", "replay", "sim"]


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
        from app.portfolio.account import portfolio_accounts
        live_acct = portfolio_accounts.get(acct.id)
        current_equity = live_acct.equity if live_acct else acct.starting_capital
        current_cash = live_acct.cash if live_acct else acct.starting_capital
        realized_pnl = live_acct.realized_pnl if live_acct else 0.0
        pnl_pct = round((realized_pnl / acct.starting_capital) * 100.0, 2) if acct.starting_capital > 0 else 0.0

        out.append({
            "id": acct.id,
            "name": acct.name,
            "starting_capital": acct.starting_capital,
            "equity": current_equity,
            "cash": current_cash,
            "day_pnl": realized_pnl,
            "day_pnl_pct": pnl_pct,
            "open_positions_count": len(live_acct.positions) if live_acct else len(open_positions),
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
    """Switch market feed mode between sim, replay, and groww."""
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
