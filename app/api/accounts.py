"""Account management and emergency controls."""

import json
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import require_role
from app.config import get_settings
from app.db.models import Account, Position
from app.db.session import get_db
from app.execution_sim.engine import ExecutionSimulator, OrderSide, SimulatedOrder
from app.execution_sim.profiles import ExecutionProfile, ProfileMode
from app.feed.provider import get_market_data_provider
from app.fees.calculator import FeeCalculator
from app.portfolio.account import portfolio_accounts
from app.portfolio.ledger import (
    AuditEvent,
    DetailedFeeBreakdown,
    ExecutionForensics,
    LevelFillDetail,
    LossAttributionTag,
    TradeRecord,
    global_trade_ledger,
)

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


async def execute_flatten_lifecycle(exit_reason: str = "EMERGENCY_HALT_FLATTEN", decision_reason: str = "Emergency kill switch invoked") -> tuple[list[dict], list[dict]]:
    """Execute simulated SELL exits against live bid depth for all open positions.

    If bid depth is unavailable, fails safely without fabricating prices.
    Persists closed trades, forensics, statutory fees, and audit events transactionally.
    """
    flattened_positions = []
    failed_positions = []
    now = datetime.now(UTC)
    calc = FeeCalculator()
    sim = ExecutionSimulator(profile=ExecutionProfile(mode=ProfileMode.PESSIMISTIC, slippage_ticks=1, latency_ms=0, rejection_rate=0.0))
    provider = get_market_data_provider()

    for acct_id, acct in portfolio_accounts.items():
        open_syms = list(acct.positions.keys())
        for sym in open_syms:
            pos = acct.positions[sym]

            # 1. Fetch current live market state
            tick = await provider.get_latest_tick(sym)
            if not tick or not tick.depth or not tick.depth.bids:
                # Never fabricate an exit price if genuine depth is missing
                await global_trade_ledger.save_audit_event_to_db(
                    event_id=f"EVT-FLATTEN-FAIL-{sym}-{int(now.timestamp())}",
                    account_id=acct_id,
                    symbol=sym,
                    event_type="FLATTEN_FAILED_MARKET_DATA_UNAVAILABLE",
                    data={"quantity": pos.quantity, "entry_price": pos.entry_price},
                    reason=f"Flatten failed: Live market bid depth unavailable for {sym}",
                )
                failed_positions.append({
                    "account": acct_id,
                    "symbol": sym,
                    "quantity": pos.quantity,
                    "reason": "FLATTEN_FAILED_MARKET_DATA_UNAVAILABLE",
                })
                continue

            # 2. Simulate SELL order walking actual bid book
            sell_order = SimulatedOrder(
                symbol=sym,
                side=OrderSide.SELL,
                requested_quantity=pos.quantity,
                decision_timestamp=now,
            )
            fill = sim.execute_order(sell_order, tick.depth, execution_timestamp=now, execution_assumption="SIMULATED_ASSUMPTION")

            if fill.status == "REJECTED" or fill.filled_quantity == 0:
                await global_trade_ledger.save_audit_event_to_db(
                    event_id=f"EVT-FLATTEN-REJECT-{sym}-{int(now.timestamp())}",
                    account_id=acct_id,
                    symbol=sym,
                    event_type="FLATTEN_FAILED_EXECUTION_REJECTED",
                    data={"quantity": pos.quantity, "rejection_reason": fill.rejection_reason},
                    reason=f"Execution rejected during flatten: {fill.rejection_reason}",
                )
                failed_positions.append({
                    "account": acct_id,
                    "symbol": sym,
                    "quantity": pos.quantity,
                    "reason": fill.rejection_reason or "EXECUTION_REJECTED",
                })
                continue

            exit_price = fill.average_fill_price
            gross = round((exit_price - pos.entry_price) * fill.filled_quantity, 2)
            fees = calc.calculate(
                quantity=fill.filled_quantity,
                buy_price=pos.entry_price,
                sell_price=exit_price,
            )
            net_pnl = round(gross - float(fees.total_charges), 2)

            # Close in runtime portfolio account
            acct.close_position(sym, exit_price, net_pnl)

            # Build fee breakdown & forensics
            fee_breakdown = DetailedFeeBreakdown(
                schedule_id=fees.schedule_id,
                effective_date="2024-10-01",
                turnover=fees.turnover,
                buy_value=fees.buy_value,
                sell_value=fees.sell_value,
                brokerage=fees.brokerage,
                stt=fees.stt,
                exchange_txn=fees.exchange_txn,
                sebi=fees.sebi,
                gst=fees.gst,
                stamp_duty=fees.stamp_duty,
                total_charges=fees.total_charges,
            )

            forensics = ExecutionForensics(
                market_data_ts=tick.timestamp,
                decision_ts=now,
                simulated_execution_ts=fill.executed_at,
                configured_latency_ms=0,
                best_bid=tick.depth.best_bid,
                best_ask=tick.depth.best_ask,
                requested_quantity=pos.quantity,
                filled_quantity=fill.filled_quantity,
                unfilled_quantity=fill.remaining_quantity,
                vwap_fill_price=fill.average_fill_price,
                slippage_ticks=1,
                slippage_amount=fill.slippage_amount,
                levels_consumed=[
                    LevelFillDetail(level=lvl.level, price=lvl.price, quantity=lvl.quantity)
                    for lvl in fill.levels_consumed
                ],
                depth_snapshot={
                    "bids": [{"price": b.price, "qty": b.quantity} for b in tick.depth.bids[:5]],
                    "asks": [{"price": a.price, "qty": a.quantity} for a in tick.depth.asks[:5]],
                },
            )

            timeline = [
                AuditEvent(seq=1, event_name="POSITION_OPENED", timestamp=pos.opened_at, description=f"Position opened at ₹{pos.entry_price:.2f}"),
                AuditEvent(seq=2, event_name="FLATTEN_TRIGGERED", timestamp=now, description=decision_reason),
                AuditEvent(seq=3, event_name="FILL_SIMULATED", timestamp=fill.executed_at, description=f"Executed SELL {fill.filled_quantity} shares @ ₹{fill.average_fill_price:.2f}"),
                AuditEvent(seq=4, event_name="FEES_RECONCILED", timestamp=now, description=f"Statutory fees ₹{fees.total_charges:.2f}, net P&L ₹{net_pnl:.2f}"),
            ]

            trade = TradeRecord(
                trade_id=f"KILL-{sym}-{int(now.timestamp())}",
                account_id=acct_id,
                symbol=sym,
                strategy_name="EMERGENCY_FLATTEN",
                strategy_version="1.0",
                direction="BUY",
                quantity=fill.filled_quantity,
                entry_price=pos.entry_price,
                exit_price=exit_price,
                entry_timestamp=pos.opened_at,
                exit_timestamp=now,
                gross_pnl=gross,
                total_charges=float(fees.total_charges),
                slippage=fill.slippage_amount,
                net_pnl=net_pnl,
                r_multiple=0.0,
                trade_status="CLOSED",
                exit_reason=exit_reason,
                loss_tag=LossAttributionTag.NONE,
                decision_reason=decision_reason,
                fee_breakdown=fee_breakdown,
                execution_forensics=forensics,
                audit_timeline=timeline,
                environment="PAPER_LIVE" if settings.FEED_MODE == "groww" else "DEMO",
                predicted_probability=None,
            )
            global_trade_ledger.record_trade(trade)
            await global_trade_ledger.save_trade_to_db(trade)

            flattened_positions.append({
                "account": acct_id,
                "symbol": sym,
                "quantity": fill.filled_quantity,
                "entry_price": pos.entry_price,
                "exit_price": exit_price,
                "fees": float(fees.total_charges),
                "net_pnl": net_pnl,
            })

    return flattened_positions, failed_positions


@router.post("/kill")
async def emergency_kill(current_user: str = Depends(require_role(["operator", "admin"]))) -> dict:
    """Flatten all open paper positions immediately through simulated depth execution and halt all new entries."""
    global SYSTEM_HALTED
    SYSTEM_HALTED = True

    flattened, failed = await execute_flatten_lifecycle(
        exit_reason="EMERGENCY_HALT_FLATTEN",
        decision_reason=f"Emergency kill switch invoked by authorized operator '{current_user}'",
    )

    return {
        "status": "halted",
        "action": "EMERGENCY_KILL_TRIGGERED",
        "operator": current_user,
        "message": f"Emergency kill executed. Flattened {len(flattened)} positions, {len(failed)} failed due to unavailable market data. System halted.",
        "flattened_count": len(flattened),
        "failed_count": len(failed),
        "flattened_positions": flattened,
        "failed_positions": failed,
    }


@router.post("/force-flat")
async def force_flat_endpoint(current_user: str = Depends(require_role(["operator", "admin"]))) -> dict:
    """Trigger mandatory intraday 15:15 IST force-flat square off lifecycle."""
    flattened, failed = await execute_flatten_lifecycle(
        exit_reason="MANDATORY_EOD_SQUAREOFF",
        decision_reason=f"Mandatory 15:15 IST intraday force-flat executed by '{current_user}'",
    )
    return {
        "status": "ok",
        "action": "FORCE_FLAT_EXECUTED",
        "operator": current_user,
        "flattened_count": len(flattened),
        "failed_count": len(failed),
        "flattened_positions": flattened,
        "failed_positions": failed,
    }


@router.post("/resume")
async def resume_system(current_user: str = Depends(require_role(["operator", "admin"]))) -> dict:
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
async def set_feed_mode(req: FeedModeRequest, current_user: str = Depends(require_role(["operator", "admin"]))) -> dict:
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
