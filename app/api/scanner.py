"""Scanner API endpoint with multi-stage universe funnel & EV decision ranking."""

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Query

from app.config import get_account_spec, get_settings
from app.feed.calendar import get_market_session_phase
from app.feed.instruments import InstrumentMaster
from app.feed.provider import get_market_data_provider
from app.feed.validator import FreshnessStatus, MarketDataValidator
from app.indicators.orderbook import calculate_microprice, calculate_obi
from app.indicators.technical import calculate_rvol, calculate_vwap_deviation
from app.universe.funnel import FunnelConfig, UniverseFunnel

router = APIRouter(prefix="/api/scanner", tags=["scanner"])
settings = get_settings()
master = InstrumentMaster()
validator = MarketDataValidator(max_quote_age_ms=6000 if settings.FEED_MODE == "groww" else 3000)


@router.get("")
async def get_scanner_candidates(account: str = Query("tiny")) -> dict[str, Any]:
    """Scan and rank liquid NSE equities using multi-stage funnel and honest EV/probability status."""
    spec = get_account_spec(account)
    capital = float(spec.get("starting_capital", 1000.0))
    max_pos_pct = float(spec.get("max_position_pct", 50.0)) / 100.0
    ev_hurdle = float(spec.get("ev_min_pct", 0.15))
    decision_timestamp = datetime.now(UTC)

    funnel = UniverseFunnel(FunnelConfig(max_position_pct=max_pos_pct))
    provider = get_market_data_provider()

    results = []
    tradable_equities = master.get_tradable_equities()
    funnel_stats = {"monitored": len(tradable_equities), "liquid": 0, "approved": 0, "rejected": 0}

    # Session Phase Check
    session_phase = get_market_session_phase(decision_timestamp)

    for inst in tradable_equities:
        tick = await provider.get_latest_tick(inst.symbol)
        if not tick:
            continue

        # 1. Freshness & Data Quality Validation
        freshness_status, freshness_reason = validator.validate_tick(tick, decision_timestamp=datetime.now(UTC))
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
                "heuristic_score": None,
                "win_chance": None,
                "ev_pct": None,
                "probability_status": "UNAVAILABLE",
                "ev_status": "UNAVAILABLE",
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
                "heuristic_score": None,
                "win_chance": None,
                "ev_pct": None,
                "probability_status": "UNAVAILABLE",
                "ev_status": "UNAVAILABLE",
            })
            continue

        funnel_stats["liquid"] += 1

        # 3. Quant Indicators
        obi = calculate_obi(tick.depth)
        mp = calculate_microprice(tick.depth)
        rvol = calculate_rvol(tick.volume, baseline_volume=200000)
        vwap_dev = calculate_vwap_deviation(tick.last_price, tick.average_traded_price)
        heuristic_score = round(obi * 2.0 + (rvol - 1.0), 2)

        # Quantitative Policy: No calibrated model => No EV entry
        # Uncalibrated heuristic probability is NOT used to authorize entry.
        # win_chance and ev_pct are explicitly None (UNAVAILABLE).
        results.append({
            "symbol": inst.symbol,
            "name": inst.name,
            "price": tick.last_price,
            "change": round(((tick.last_price - tick.close) / tick.close * 100), 2) if tick.close > 0 else 0.0,
            "score": heuristic_score,
            "heuristic_score": heuristic_score,
            "win_chance": None,
            "ev_pct": None,
            "probability_status": "UNAVAILABLE",
            "ev_status": "UNAVAILABLE",
            "entry_decisions_enabled": False,
            "rvol": round(rvol, 1),
            "obi": round(obi, 2),
            "microprice": round(mp, 2),
            "vwap_deviation": round(vwap_dev, 2),
            "status": "WATCH",
            "action": "Watch",
            "reason": "NO_CALIBRATED_MODEL: EV entry decisions disabled until empirical calibration",
            "data_quality": "VALID",
            "market_status": session_phase,
            "depth": {
                "bids": [{"price": b.price, "qty": b.quantity} for b in tick.depth.bids[:5]],
                "asks": [{"price": a.price, "qty": a.quantity} for a in tick.depth.asks[:5]],
            },
        })

    # Sort surviving liquid opportunities highest heuristic score first
    results.sort(key=lambda x: (x.get("status") == "WATCH", x.get("heuristic_score") or -999.0), reverse=True)

    is_live_feed = settings.FEED_MODE == "groww" and provider.is_connected()
    return {
        "environment": "PAPER_LIVE" if is_live_feed else "DEMO",
        "data_status": "LIVE" if is_live_feed else "SIMULATED",
        "probability_status": "UNAVAILABLE",
        "ev_status": "UNAVAILABLE",
        "entry_decisions_enabled": False,
        "reason": "NO_CALIBRATED_MODEL",
        "account": account,
        "capital": capital,
        "max_position_pct": max_pos_pct * 100.0,
        "ev_hurdle": ev_hurdle,
        "feed_source": provider.get_source_name(),
        "is_connected": provider.is_connected(),
        "session_phase": session_phase,
        "funnel_stats": funnel_stats,
        "candidates": results,
    }
