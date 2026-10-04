"""Trade retrieval, execution forensics, and fee audit API endpoints."""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.portfolio.ledger import TradeRecord, global_trade_ledger

router = APIRouter(prefix="/api/trades", tags=["trades"])

VALID_ACCOUNTS = {"tiny", "shadow", "real5k"}


def serialize_trade_summary(t: TradeRecord) -> dict[str, Any]:
    """Serialize trade for high-level ledger table view."""
    return {
        "trade_id": t.trade_id,
        "account_id": t.account_id,
        "symbol": t.symbol,
        "direction": t.direction,
        "strategy": t.strategy_name,
        "strategy_version": t.strategy_version,
        "quantity": t.quantity,
        "entry_price": t.entry_price,
        "exit_price": t.exit_price,
        "entry_timestamp": t.entry_timestamp.isoformat() if isinstance(t.entry_timestamp, datetime) else str(t.entry_timestamp),
        "exit_timestamp": t.exit_timestamp.isoformat() if isinstance(t.exit_timestamp, datetime) else str(t.exit_timestamp),
        "gross_pnl": round(t.gross_pnl, 2),
        "total_charges": round(t.total_charges, 2),
        "slippage": round(t.slippage, 2),
        "net_pnl": round(t.net_pnl, 2),
        "r_multiple": round(t.r_multiple, 2),
        "trade_status": t.trade_status,
        "exit_reason": t.exit_reason,
        "loss_tag": t.loss_tag.value if hasattr(t.loss_tag, "value") else str(t.loss_tag),
        "decision_reason": t.decision_reason,
    }


def serialize_forensic_trade_detail(t: TradeRecord) -> dict[str, Any]:
    """Serialize complete forensic audit package for the Forensic Modal."""
    summary = serialize_trade_summary(t)

    # 1. Decision Snapshot (Original values recorded; never recalculate or invent)
    decision_data: dict[str, Any] = {
        "recorded": t.decision_snapshot is not None,
    }
    if t.decision_snapshot:
        ds = t.decision_snapshot
        decision_data.update({
            "rvol": ds.rvol if ds.rvol is not None else "Unavailable",
            "obi": ds.obi if ds.obi is not None else "Unavailable",
            "microprice": ds.microprice if ds.microprice is not None else "Unavailable",
            "vwap_deviation": ds.vwap_deviation if ds.vwap_deviation is not None else "Unavailable",
            "atr": ds.atr if ds.atr is not None else "Unavailable",
            "spread": ds.spread if ds.spread is not None else "Unavailable",
            "win_probability": ds.win_probability if ds.win_probability is not None else "Unavailable",
            "expected_reward": ds.expected_reward if ds.expected_reward is not None else "Unavailable",
            "expected_loss": ds.expected_loss if ds.expected_loss is not None else "Unavailable",
            "expected_costs": ds.expected_costs if ds.expected_costs is not None else "Unavailable",
            "net_ev": ds.net_ev if ds.net_ev is not None else "Unavailable",
            "ev_hurdle": ds.ev_hurdle if ds.ev_hurdle is not None else "Unavailable",
            "decision": ds.decision,
            "decision_reason": ds.decision_reason,
            "eval_timestamp": ds.eval_timestamp.isoformat() if isinstance(ds.eval_timestamp, datetime) else str(ds.eval_timestamp),
        })
    else:
        for field_name in [
            "rvol", "obi", "microprice", "vwap_deviation", "atr", "spread",
            "win_probability", "expected_reward", "expected_loss", "expected_costs",
            "net_ev", "ev_hurdle", "decision", "decision_reason", "eval_timestamp",
        ]:
            decision_data[field_name] = "Unavailable"

    # 2. Execution Forensics (Depth walking, latency, slippage)
    execution_data: dict[str, Any] = {
        "recorded": t.execution_forensics is not None,
    }
    if t.execution_forensics:
        ef = t.execution_forensics
        execution_data.update({
            "market_data_ts": ef.market_data_ts.isoformat() if ef.market_data_ts else "Unavailable",
            "decision_ts": ef.decision_ts.isoformat() if ef.decision_ts else "Unavailable",
            "simulated_execution_ts": ef.simulated_execution_ts.isoformat() if isinstance(ef.simulated_execution_ts, datetime) else str(ef.simulated_execution_ts),
            "configured_latency_ms": ef.configured_latency_ms,
            "best_bid": ef.best_bid if ef.best_bid is not None else "Unavailable",
            "best_ask": ef.best_ask if ef.best_ask is not None else "Unavailable",
            "requested_quantity": ef.requested_quantity,
            "filled_quantity": ef.filled_quantity,
            "unfilled_quantity": ef.unfilled_quantity,
            "vwap_fill_price": ef.vwap_fill_price,
            "slippage_ticks": ef.slippage_ticks,
            "slippage_amount": round(ef.slippage_amount, 4),
            "levels_consumed": [
                {"level": lvl.level, "price": lvl.price, "quantity": lvl.quantity}
                for lvl in ef.levels_consumed
            ],
            "depth_snapshot": ef.depth_snapshot or {},
        })
    else:
        execution_data.update({
            "market_data_ts": "Unavailable",
            "decision_ts": "Unavailable",
            "simulated_execution_ts": t.entry_timestamp.isoformat() if isinstance(t.entry_timestamp, datetime) else str(t.entry_timestamp),
            "configured_latency_ms": "Unavailable",
            "best_bid": "Unavailable",
            "best_ask": "Unavailable",
            "requested_quantity": t.quantity,
            "filled_quantity": t.quantity,
            "unfilled_quantity": 0,
            "vwap_fill_price": t.entry_price,
            "slippage_ticks": 1,
            "slippage_amount": t.slippage,
            "levels_consumed": [],
            "depth_snapshot": {},
        })

    # 3. Detailed Fee Breakdown (Exact statutory taxes down to paisa)
    fee_data: dict[str, Any] = {
        "recorded": t.fee_breakdown is not None,
    }
    if t.fee_breakdown:
        fb = t.fee_breakdown
        fee_data.update({
            "schedule_id": fb.schedule_id,
            "effective_date": fb.effective_date,
            "turnover": round(fb.turnover, 2),
            "buy_value": round(fb.buy_value, 2),
            "sell_value": round(fb.sell_value, 2),
            "brokerage": round(fb.brokerage, 2),
            "stt": round(fb.stt, 2),
            "exchange_txn": round(fb.exchange_txn, 2),
            "sebi": round(fb.sebi, 4),
            "gst": round(fb.gst, 2),
            "stamp_duty": round(fb.stamp_duty, 2),
            "total_charges": round(fb.total_charges, 2),
        })
    else:
        # Fallback to recorded aggregate charges
        fee_data.update({
            "schedule_id": "DEFAULT_NSE_2024",
            "effective_date": "2024-10-01",
            "turnover": round((t.entry_price + t.exit_price) * t.quantity, 2),
            "buy_value": round(t.entry_price * t.quantity, 2),
            "sell_value": round(t.exit_price * t.quantity, 2),
            "brokerage": "Unavailable",
            "stt": "Unavailable",
            "exchange_txn": "Unavailable",
            "sebi": "Unavailable",
            "gst": "Unavailable",
            "stamp_duty": "Unavailable",
            "total_charges": round(t.total_charges, 2),
        })

    # 4. Final Accounting Reconciliation
    # Note: Slippage is already embedded into the simulated fill price.
    # We report slippage as an execution-cost attribution metric without subtracting it twice.
    accounting = {
        "entry_value": round(t.entry_price * t.quantity, 2),
        "exit_value": round(t.exit_price * t.quantity, 2),
        "gross_pnl": round(t.gross_pnl, 2),
        "applicable_charges": round(t.total_charges, 2),
        "execution_slippage_attribution": round(t.slippage, 2),
        "slippage_already_in_fill": True,
        "net_pnl": round(t.net_pnl, 2),
        "reconciled": round(t.gross_pnl - t.total_charges, 2) == round(t.net_pnl, 2),
    }

    # 5. Chronological Audit Timeline
    timeline_events = []
    if t.audit_timeline:
        for ev in t.audit_timeline:
            timeline_events.append({
                "seq": ev.seq,
                "event_name": ev.event_name,
                "timestamp": ev.timestamp.isoformat() if isinstance(ev.timestamp, datetime) else str(ev.timestamp),
                "description": ev.description,
                "metadata": ev.metadata,
            })

    return {
        "trade_summary": summary,
        "decision_snapshot": decision_data,
        "execution_forensics": execution_data,
        "fee_breakdown": fee_data,
        "accounting": accounting,
        "audit_timeline": timeline_events,
    }


@router.get("")
async def list_trades(
    account: str = Query("tiny"),
    limit: int = Query(100, ge=1, le=500),
) -> list[dict[str, Any]]:
    """List historical closed trades for specified account."""
    if account not in VALID_ACCOUNTS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid account '{account}'. Must be one of: {sorted(VALID_ACCOUNTS)}",
        )

    trades = global_trade_ledger.list_trades_for_account(account, limit=limit)
    return [serialize_trade_summary(t) for t in reversed(trades)]


@router.get("/{trade_id}")
async def get_trade_detail(trade_id: str) -> dict[str, Any]:
    """Retrieve complete forensic trade record with decision snapshot, fills, and fee breakdown."""
    trade = global_trade_ledger.get_trade_by_id(trade_id)
    if not trade:
        raise HTTPException(
            status_code=404,
            detail=f"Trade '{trade_id}' not found in ledger.",
        )
    return serialize_forensic_trade_detail(trade)
