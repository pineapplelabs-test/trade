"""Account management and emergency controls."""

import json
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import get_current_user
from app.config import get_settings
from app.db.models import Account, Position
from app.db.session import get_db
from app.fees.calculator import FeeCalculator
from app.portfolio.account import portfolio_accounts
from app.portfolio.ledger import LossAttributionTag, TradeRecord, global_trade_ledger

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
async def emergency_kill(current_user: str = Depends(get_current_user)) -> dict:
    """Flatten all open paper positions immediately and halt all new entries."""
    global SYSTEM_HALTED
    SYSTEM_HALTED = True

    flattened_positions = []
    now = datetime.now(UTC)

    calc = FeeCalculator()
    for acct_id, acct in portfolio_accounts.items():
        open_syms = list(acct.positions.keys())
        for sym in open_syms:
            pos = acct.positions[sym]
            exit_price = pos.current_price
            gross = round((exit_price - pos.entry_price) * pos.quantity, 2)
            fees = calc.calculate(
                quantity=pos.quantity,
                buy_price=pos.entry_price,
                sell_price=exit_price,
            )
            net_pnl = round(gross - float(fees.total_charges), 2)
            acct.close_position(sym, exit_price, net_pnl)

            trade = TradeRecord(
                trade_id=f"KILL-{sym}-{int(now.timestamp())}",
                account_id=acct_id,
                symbol=sym,
                strategy_name="EMERGENCY_KILL",
                strategy_version="1.0",
                direction="BUY",
                quantity=pos.quantity,
                entry_price=pos.entry_price,
                exit_price=exit_price,
                entry_timestamp=pos.opened_at,
                exit_timestamp=now,
                gross_pnl=gross,
                total_charges=float(fees.total_charges),
                slippage=0.0,
                net_pnl=net_pnl,
                r_multiple=0.0,
                trade_status="CLOSED",
                exit_reason="EMERGENCY_HALT_FLATTEN",
                loss_tag=LossAttributionTag.NONE,
                decision_reason="Emergency kill switch invoked by authorized operator",
                environment="PAPER_LIVE" if settings.FEED_MODE == "groww" else "DEMO",
            )
            global_trade_ledger.record_trade(trade)

            flattened_positions.append(
                {
                    "account": acct_id,
                    "symbol": sym,
                    "quantity": pos.quantity,
                    "entry_price": pos.entry_price,
                    "exit_price": exit_price,
                    "net_pnl": net_pnl,
                }
            )

    return {
        "status": "halted",
        "action": "EMERGENCY_KILL_TRIGGERED",
        "operator": current_user,
        "message": f"All open positions flattened ({len(flattened_positions)} executed). Trading halted.",
        "flattened_count": len(flattened_positions),
        "flattened_positions": flattened_positions,
    }


@router.post("/resume")
async def resume_system(current_user: str = Depends(get_current_user)) -> dict:
    """Manual restart after an emergency halt."""
    global SYSTEM_HALTED
    SYSTEM_HALTED = False
    return {
        "status": "active",
        "action": "SYSTEM_RESUMED",
        "operator": current_user,
        "message": "Paper Desk engine resumed by authorized operator.",
    }


@router.post("/mode")
async def set_feed_mode(req: FeedModeRequest, current_user: str = Depends(get_current_user)) -> dict:
    """Switch market feed mode between sim, replay, and groww."""
    settings.FEED_MODE = req.feed
    return {
        "status": "ok",
        "feed_mode": settings.FEED_MODE,
        "operator": current_user,
    }


@router.get("/system-status")
async def get_system_status() -> dict:
    """Get kill switch status and operational flags."""
    return {
        "system_halted": SYSTEM_HALTED,
        "feed_mode": settings.FEED_MODE,
        "pessimistic_fills": settings.PESSIMISTIC_FILLS,
    }
