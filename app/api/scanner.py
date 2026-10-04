"""Scanner API endpoint with multi-stage universe funnel.

The scanner deliberately does not manufacture a win probability. Until an
independent calibration dataset exists, EV cannot be used as a live entry gate.
"""
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Query

from app.config import get_accounts_config
from app.feed.calendar import get_market_session_phase
from app.feed.instruments import DEFAULT_INSTRUMENTS, InstrumentMaster
from app.feed.provider import get_market_data_provider
from app.feed.validator import FreshnessStatus, MarketDataValidator
from app.indicators.orderbook import calculate_microprice, calculate_obi
from app.indicators.technical import calculate_rvol, calculate_vwap_deviation
from app.universe.funnel import FunnelConfig, UniverseFunnel

router = APIRouter(prefix="/api/scanner", tags=["scanner"])
master = InstrumentMaster()
validator = MarketDataValidator()

ACCOUNT_CAPITALS = {"tiny": 1000.0, "real5k": 5000.0, "shadow": 100000.0}
ACCOUNT_EV_HURDLES = {"tiny": 0.15, "real5k": 0.12, "shadow": 0.10}


@router.get("")
async def get_scanner_candidates(account: str = Query("tiny")) -> dict[str, Any]:
    """Scan tradable NSE equities without inventing a calibrated probability."""
    if account not in ACCOUNT_CAPITALS:
        account = "tiny"

    capital = ACCOUNT_CAPITALS[account]
    ev_hurdle = ACCOUNT_EV_HURDLES[account]
    decision_timestamp = datetime.now(UTC)
    funnel = UniverseFunnel(
        FunnelConfig(max_position_pct=0.50 if account == "tiny" else 0.20)
    )
    provider = get_market_data_provider()
    results: list[dict[str, Any]] = []
    funnel_stats = {"monitored": 0, "liquid": 0, "approved": 0, "rejected": 0}
    session_phase = get_market_session_phase(decision_timestamp)

    for inst in DEFAULT_INSTRUMENTS:
        # Cash-equity scanner: never treat an index as an equity candidate.
        if inst.sector == "Index" or getattr(inst, "exchange", "NSE") != "NSE" or getattr(inst, "series", "EQ") != "EQ":
            continue
        funnel_stats["monitored"] += 1

        tick = await provider.get_latest_tick(inst.symbol)
        if not tick:
            continue

        freshness_status, freshness_reason = validator.validate_tick(
            tick, decision_timestamp=decision_timestamp
        )
        if freshness_status != FreshnessStatus.VALID:
            funnel_stats["rejected"] += 1
            results.append({
                "symbol": inst.symbol,
                "name": inst.name,
                "price": tick.last_price,
                "status": "REJECT",
                "action": "Blocked",
                "rejection_stage": f"DATA_INTEGRITY_{freshness_status.value}",
                "rejection_reason": freshness_reason,
                "data_quality": freshness_status.value,
                "probability_status": "UNAVAILABLE",
                "win_chance": None,
                "ev_pct": None,
            })
            continue

        eval_res = funnel.evaluate(inst, tick, account_capital=capital)
        if not eval_res.passed:
            funnel_stats["rejected"] += 1
            results.append({
                "symbol": inst.symbol,
                "name": inst.name,
                "price": tick.last_price,
                "status": "REJECT",
                "action": "Skip",
                "rejection_stage": eval_res.stage,
                "rejection_reason": eval_res.reason,
                "data_quality": "VALID",
                "probability_status": "UNAVAILABLE",
                "win_chance": None,
                "ev_pct": None,
            })
            continue

        funnel_stats["liquid"] += 1
        obi = calculate_obi(tick.depth)
        mp = calculate_microprice(tick.depth)
        rvol = calculate_rvol(tick.volume, baseline_volume=200000)
        vwap_dev = calculate_vwap_deviation(tick.last_price, tick.average_traded_price)

        # OBI/RVOL are features, not a probability model.
        # Until p is learned and independently calibrated, no entry is allowed.
        results.append({
            "symbol": inst.symbol,
            "name": inst.name,
            "price": tick.last_price,
            "change": round(((tick.last_price - tick.close) / tick.close * 100), 2)
            if tick.close > 0 else 0.0,
            "score": round(obi * 2.0 + (rvol - 1.0), 2),
            "win_chance": None,
            "probability_status": "UNAVAILABLE",
            "ev_pct": None,
            "rvol": round(rvol, 1),
            "obi": round(obi, 2),
            "microprice": round(mp, 2),
            "vwap_deviation": round(vwap_dev, 2),
            "status": "UNCALIBRATED",
            "action": "Watch",
            "reason": (
                "Candidate observed, but entry is blocked because no independently "
                "calibrated win-probability model is available."
            ),
            "data_quality": "VALID",
            "market_status": session_phase,
            "depth": {
                "bids": [{"price": b.price, "qty": b.quantity} for b in tick.depth.bids[:5]],
                "asks": [{"price": a.price, "qty": a.quantity} for a in tick.depth.asks[:5]],
            },
        })

    results.sort(key=lambda x: x.get("score", 0.0), reverse=True)
    return {
        "account": account,
        "capital": capital,
        "ev_hurdle": ev_hurdle,
        "probability_model": "NONE",
        "probability_status": "UNCALIBRATED",
        "entry_decisions_enabled": False,
        "feed_source": provider.get_source_name(),
        "is_connected": provider.is_connected(),
        "session_phase": session_phase,
        "funnel_stats": funnel_stats,
        "candidates": results,
    }
