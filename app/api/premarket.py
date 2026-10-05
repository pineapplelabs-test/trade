"""Pre-Market Intelligence API Endpoint."""

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.universe.premarket import PreMarketReport, global_premarket_scanner

router = APIRouter(prefix="/api/premarket", tags=["premarket"])
VALID_ACCOUNTS = {"tiny", "real5k", "shadow"}


@router.get("/report")
async def get_premarket_report(
    account: str = Query("real5k"),
    demo: bool = Query(False),
) -> dict[str, Any]:
    """Retrieve 08:30 – 09:10 AM Pre-Market Watchlist.

    Fails closed with 503 PREMARKET_UNAVAILABLE unless genuine live pre-open auction
    feed is connected, or demo=true is explicitly requested for synthetic testing.
    """
    if account not in VALID_ACCOUNTS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid account '{account}'. Must be one of: {sorted(VALID_ACCOUNTS)}",
        )

    if not demo:
        raise HTTPException(
            status_code=503,
            detail="PREMARKET_UNAVAILABLE: Genuine NSE pre-open auction market data feed is not connected. Pre-market rankings and EV entry decisions are unavailable in live mode.",
        )

    # Isolated synthetic diagnostic report for development/demo only
    report: PreMarketReport = global_premarket_scanner.generate_report(
        account_id=account,
        nifty_gap_pct=0.45,
        india_vix=13.20,
    )

    return {
        "status": "ok",
        "environment": report.environment,
        "data_status": report.data_status,
        "entry_decisions_enabled": report.entry_decisions_enabled,
        "evaluated_at": report.evaluated_at,
        "account_id": report.account_id,
        "account_capital": report.account_capital,
        "market_bias": report.market_bias,
        "nifty_indicative_change_pct": report.nifty_indicative_change_pct,
        "india_vix": report.india_vix,
        "recommended_strategy": report.recommended_strategy,
        "total_universe_scanned": report.total_universe_scanned,
        "passed_tradability": report.passed_tradability,
        "passed_affordability": report.passed_affordability,
        "focus_candidates": [
            {
                "rank": c.rank,
                "symbol": c.symbol,
                "name": c.name,
                "sector": c.sector,
                "prev_close": c.prev_close,
                "discovered_price": c.discovered_price,
                "gap_pct": c.gap_pct,
                "turnover_cr": c.turnover_cr,
                "atr_14": c.atr_14,
                "atr_pct": c.atr_pct,
                "max_affordable_shares": c.max_affordable_shares,
                "planned_entry": c.planned_entry,
                "planned_stop": c.planned_stop,
                "planned_target": c.planned_target,
                "reward_risk_ratio": c.reward_risk_ratio,
                "estimated_ev_pct": c.estimated_ev_pct,
                "selection_reason": c.selection_reason,
            }
            for c in report.focus_candidates
        ],
        "quarantined_stocks": [
            {
                "symbol": q.symbol,
                "reason": q.reason,
                "stage": q.stage,
            }
            for q in report.quarantined_stocks
        ],
    }
