"""Scanner API endpoint with multi-stage universe funnel & EV decision ranking."""

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Query

from app.config import get_settings
from app.feed.calendar import get_market_session_phase
from app.feed.instruments import DEFAULT_INSTRUMENTS, InstrumentMaster
from app.feed.provider import get_market_data_provider
from app.feed.recorder import global_market_recorder
from app.feed.validator import FreshnessStatus, MarketDataValidator
from app.indicators.orderbook import calculate_microprice, calculate_obi
from app.indicators.technical import calculate_rvol, calculate_vwap_deviation
from app.strategy.ev import EVParameters, calculate_expected_value
from app.universe.funnel import FunnelConfig, UniverseFunnel

router = APIRouter(prefix="/api/scanner", tags=["scanner"])
settings = get_settings()
master = InstrumentMaster()
validator = MarketDataValidator()

ACCOUNT_CAPITALS = {
    "tiny": 1000.0,
    "real5k": 5000.0,
    "shadow": 100000.0,
}

ACCOUNT_EV_HURDLES = {
    "tiny": 0.15,
    "real5k": 0.12,
    "shadow": 0.10,
}


@router.get("")
async def get_scanner_candidates(account: str = Query("tiny")) -> dict[str, Any]:
    """Scan and rank liquid NSE equities using multi-stage funnel and EV decision gate."""
    capital = ACCOUNT_CAPITALS.get(account, 1000.0)
    ev_hurdle = ACCOUNT_EV_HURDLES.get(account, 0.15)
    decision_timestamp = datetime.now(UTC)

    funnel = UniverseFunnel(FunnelConfig(max_position_pct=0.50 if account == "tiny" else 0.20))
    provider = get_market_data_provider()

    results = []
    funnel_stats = {"monitored": len(DEFAULT_INSTRUMENTS), "liquid": 0, "approved": 0, "rejected": 0}

    # Session Phase Check
    session_phase = get_market_session_phase(decision_timestamp)

    for inst in DEFAULT_INSTRUMENTS:
        tick = await provider.get_latest_tick(inst.symbol)
        if not tick:
            continue

        # 1. Freshness & Data Quality Validation
        # Enforces: market_data_timestamp <= decision_timestamp, age limits, and 5-level completeness
        freshness_status, freshness_reason = validator.validate_tick(tick, decision_timestamp=decision_timestamp)
        if freshness_status != FreshnessStatus.VALID:
            funnel_stats["rejected"] += 1
            results.append({
                "symbol": inst.symbol,
                "name": inst.name,
                "price": tick.last_price,
                "change": round(((tick.last_price - tick.close) / tick.close * 100), 2) if tick.close > 0 else 0.0,
                "status": "REJECT",
                "action": "Blocked",
                "rejection_stage": f"DATA_INTEGRITY_{freshness_status.value}",
                "rejection_reason": freshness_reason,
                "data_quality": freshness_status.value,
                "obi": 0.0,
                "rvol": 1.0,
                "ev_pct": 0.0,
                "win_chance": 0,
            })
            continue

        # 2. Universe Funnel Evaluation (liquidity, spread, circuit, affordability)
        eval_res = funnel.evaluate(inst, tick, account_capital=capital)
        if not eval_res.passed:
            funnel_stats["rejected"] += 1
            results.append({
                "symbol": inst.symbol,
                "name": inst.name,
                "price": tick.last_price,
                "change": round(((tick.last_price - tick.close) / tick.close * 100), 2) if tick.close > 0 else 0.0,
                "status": "REJECT",
                "action": "Skip",
                "rejection_stage": eval_res.stage,
                "rejection_reason": eval_res.reason,
                "data_quality": "VALID",
                "obi": 0.0,
                "rvol": 1.0,
                "ev_pct": 0.0,
                "win_chance": 0,
            })
            continue

        funnel_stats["liquid"] += 1

        # 3. Quant Indicators
        obi = calculate_obi(tick.depth)
        mp = calculate_microprice(tick.depth)
        rvol = calculate_rvol(tick.volume, baseline_volume=200000)
        vwap_dev = calculate_vwap_deviation(tick.last_price, tick.average_traded_price)

        # Baseline win probability estimate
        base_p = 0.50 + (0.10 * obi) + (0.05 * min(2.0, rvol - 1.0))
        win_prob = max(0.35, min(0.75, base_p))

        # Expected Value calculation
        expected_gain_pct = 1.20  # ~1.2% target
        expected_loss_pct = 0.70  # ~0.7% stop
        estimated_charges_pct = 0.25  # ~0.25% all-in charges & slippage

        ev_decision = calculate_expected_value(
            EVParameters(
                win_probability=win_prob,
                expected_reward=expected_gain_pct,
                expected_loss=expected_loss_pct,
                total_costs=estimated_charges_pct,
                min_hurdle=ev_hurdle,
            )
        )

        action = "Enter" if ev_decision.status.value == "ACCEPT" else "Watch"
        if action == "Enter":
            funnel_stats["approved"] += 1
            # Record market snapshot immutably on approval
            global_market_recorder.record_snapshot(tick)

        results.append({
            "symbol": inst.symbol,
            "name": inst.name,
            "price": tick.last_price,
            "change": round(((tick.last_price - tick.close) / tick.close * 100), 2) if tick.close > 0 else 0.0,
            "score": round(obi * 2.0 + (rvol - 1.0), 2),
            "win_chance": int(win_prob * 100),
            "ev_pct": round(ev_decision.net_ev, 2),
            "rvol": round(rvol, 1),
            "obi": round(obi, 2),
            "microprice": round(mp, 2),
            "vwap_deviation": round(vwap_dev, 2),
            "status": ev_decision.status.value,
            "action": action,
            "reason": ev_decision.reason,
            "data_quality": "VALID",
            "market_status": session_phase,
            "depth": {
                "bids": [{"price": b.price, "qty": b.quantity} for b in tick.depth.bids[:5]],
                "asks": [{"price": a.price, "qty": a.quantity} for a in tick.depth.asks[:5]],
            },
        })

    # Sort accepted opportunities first, highest Net EV first
    results.sort(key=lambda x: (x.get("status") == "ACCEPT", x.get("ev_pct", 0.0)), reverse=True)

    return {
        "account": account,
        "capital": capital,
        "ev_hurdle": ev_hurdle,
        "feed_source": provider.get_source_name(),
        "is_connected": provider.is_connected(),
        "session_phase": session_phase,
        "funnel_stats": funnel_stats,
        "candidates": results,
    }
