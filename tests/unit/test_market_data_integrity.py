"""Comprehensive Unit Tests for Read-Only Market Data & Data Integrity (Phase 6)."""

from datetime import UTC, datetime, timedelta

import pytest

from app.execution_sim.engine import ExecutionSimulator, OrderSide, SimulatedOrder
from app.execution_sim.profiles import ExecutionProfile, ProfileMode
from app.feed.base import DepthLevel, MarketTick, OrderBookDepth
from app.feed.calendar import get_market_session_phase, is_trading_day
from app.feed.provider import DemoMarketDataProvider
from app.feed.recorder import MarketDataRecorder
from app.feed.validator import FreshnessStatus, MarketDataValidator


def make_valid_depth(mid: float = 380.0, tick_size: float = 0.05) -> OrderBookDepth:
    """Helper to generate structurally valid 5-level order book depth."""
    bids = [
        DepthLevel(price=round(mid - (i * tick_size), 2), quantity=1000 - (i * 100))
        for i in range(1, 6)
    ]
    asks = [
        DepthLevel(price=round(mid + (i * tick_size), 2), quantity=1000 - (i * 100))
        for i in range(1, 6)
    ]
    return OrderBookDepth(bids=bids, asks=asks)


def test_normalized_quote_and_depth_sanity():
    """Verify order book depth ordering and sanity rules."""
    depth = make_valid_depth(380.0)
    assert depth.is_complete_5_level is True
    valid, err = depth.validate_sanity()
    assert valid is True
    assert err is None
    assert depth.best_bid == 379.95
    assert depth.best_ask == 380.05
    assert depth.spread == 0.10


def test_crossed_or_inverted_depth_fails_sanity():
    """Fail if bid >= ask (crossed book) or prices are not monotonic."""
    # Crossed book (bid > ask)
    crossed_depth = OrderBookDepth(
        bids=[DepthLevel(price=381.0, quantity=100)],
        asks=[DepthLevel(price=380.0, quantity=100)],
    )
    valid, err = crossed_depth.validate_sanity()
    assert valid is False
    assert "Crossed or locked book" in err

    # Non-monotonic bids (bid[1] > bid[0])
    non_monotonic_depth = OrderBookDepth(
        bids=[
            DepthLevel(price=379.0, quantity=100),
            DepthLevel(price=380.0, quantity=100),  # Higher than previous!
        ],
        asks=[DepthLevel(price=381.0, quantity=100)],
    )
    valid2, err2 = non_monotonic_depth.validate_sanity()
    assert valid2 is False
    assert "Bids not descending" in err2


def test_validator_rejects_future_market_data():
    """Rule 7: Temporal causality test. Reject if market_timestamp > decision_timestamp."""
    validator = MarketDataValidator()
    now = datetime.now(UTC)

    decision_ts = now
    future_market_ts = now + timedelta(milliseconds=250)

    tick = MarketTick(
        token=3861249,
        symbol="BEL",
        timestamp=future_market_ts,  # Future leak!
        last_price=380.0,
        last_quantity=10,
        volume=100000,
        average_traded_price=380.0,
        total_buy_quantity=5000,
        total_sell_quantity=5000,
        open=375.0,
        high=382.0,
        low=374.0,
        close=380.0,
        depth=make_valid_depth(380.0),
        feed_source="sim",
    )

    status, reason = validator.validate_tick(tick, decision_timestamp=decision_ts, now=now)
    assert status == FreshnessStatus.FUTURE_LEAK
    assert "Future market data detected" in reason


def test_validator_rejects_stale_market_data():
    """Rule 5: Freshness validation. Reject if quote age exceeds threshold."""
    validator = MarketDataValidator(max_quote_age_ms=3000)
    now = datetime.now(UTC)
    old_market_ts = now - timedelta(milliseconds=5500)  # 5.5s old

    tick = MarketTick(
        token=3861249,
        symbol="BEL",
        timestamp=old_market_ts,
        last_price=380.0,
        last_quantity=10,
        volume=100000,
        average_traded_price=380.0,
        total_buy_quantity=5000,
        total_sell_quantity=5000,
        open=375.0,
        high=382.0,
        low=374.0,
        close=380.0,
        depth=make_valid_depth(380.0),
        feed_source="sim",
    )

    status, reason = validator.validate_tick(tick, decision_timestamp=now, now=now)
    assert status == FreshnessStatus.STALE
    assert "Market quote too old" in reason


def test_validator_rejects_insufficient_depth():
    """Rule 6: Never fabricate missing depth. Require full 5 levels."""
    validator = MarketDataValidator(require_full_5_level=True)
    now = datetime.now(UTC)

    # Incomplete 2-level depth
    shallow_depth = OrderBookDepth(
        bids=[DepthLevel(price=379.95, quantity=100), DepthLevel(price=379.90, quantity=100)],
        asks=[DepthLevel(price=380.05, quantity=100), DepthLevel(price=380.10, quantity=100)],
    )

    tick = MarketTick(
        token=3861249,
        symbol="BEL",
        timestamp=now,
        last_price=380.0,
        last_quantity=10,
        volume=100000,
        average_traded_price=380.0,
        total_buy_quantity=200,
        total_sell_quantity=200,
        open=375.0,
        high=382.0,
        low=374.0,
        close=380.0,
        depth=shallow_depth,
        feed_source="sim",
    )

    status, reason = validator.validate_tick(tick, decision_timestamp=now, now=now)
    assert status == FreshnessStatus.INSUFFICIENT_DEPTH
    assert "require 5 full levels" in reason


def test_execution_simulator_blocks_on_empty_or_shallow_depth():
    """Simulator must block execution when depth is missing instead of synthesizing liquidity."""
    sim = ExecutionSimulator()
    order = SimulatedOrder(symbol="BEL", side=OrderSide.BUY, requested_quantity=10)

    # 1. Empty depth
    empty_depth = OrderBookDepth(bids=[], asks=[])
    fill_empty = sim.execute_order(order, empty_depth)
    assert fill_empty.status == "REJECTED"
    assert "Insufficient market-depth" in fill_empty.rejection_reason

    # 2. Shallow depth (3 levels instead of 5)
    shallow_depth = OrderBookDepth(
        bids=[DepthLevel(price=379.0, quantity=100)] * 3,
        asks=[DepthLevel(price=381.0, quantity=100)] * 3,
    )
    fill_shallow = sim.execute_order(order, shallow_depth, require_full_depth=True)
    assert fill_shallow.status == "REJECTED"
    assert "Insufficient market-depth" in fill_shallow.rejection_reason


def test_execution_simulator_respects_simulated_latency():
    """Rule 8: Verify execution timestamp is decision timestamp + latency."""
    sim = ExecutionSimulator(profile=ExecutionProfile(mode=ProfileMode.NORMAL, latency_ms=500, rejection_rate=0.0))
    now = datetime.now(UTC)

    order = SimulatedOrder(
        symbol="BEL",
        side=OrderSide.BUY,
        requested_quantity=2,
        decision_timestamp=now,
    )

    depth = make_valid_depth(380.0)
    fill = sim.execute_order(order, depth)

    assert fill.status == "FILLED"
    expected_exec_ts = now + timedelta(milliseconds=sim.profile.latency_ms)
    assert fill.executed_at == expected_exec_ts
    assert fill.executed_at > fill.decision_timestamp


@pytest.mark.asyncio
async def test_demo_provider_returns_deterministic_ticks():
    """Rule 17: Demo mode must remain fully functional and deterministic."""
    provider = DemoMarketDataProvider()
    tick = await provider.get_latest_tick("BEL")
    assert tick is not None
    assert tick.symbol == "BEL"
    assert tick.feed_source == "sim"
    assert provider.get_source_name() == "DEMO"
    assert tick.depth.is_complete_5_level is True


def test_market_recorder_persists_snapshots():
    """Rule 9 & 10: Snapshot immutability & audit recording."""
    recorder = MarketDataRecorder(capacity=10)
    now = datetime.now(UTC)

    tick = MarketTick(
        token=3861249,
        symbol="BEL",
        timestamp=now,
        last_price=380.0,
        last_quantity=10,
        volume=100000,
        average_traded_price=380.0,
        total_buy_quantity=5000,
        total_sell_quantity=5000,
        open=375.0,
        high=382.0,
        low=374.0,
        close=380.0,
        depth=make_valid_depth(380.0),
        feed_source="groww",
    )

    snap_id = recorder.record_snapshot(tick)
    assert snap_id.startswith("SNAP-BEL-")

    snap = recorder.get_snapshot(snap_id)
    assert snap is not None
    assert snap.symbol == "BEL"
    assert snap.last_price == 380.0
    assert len(snap.bids) == 5
    assert len(snap.asks) == 5


def test_market_calendar_session_boundaries():
    """Rule 12: Validate official NSE trading session checks."""
    # Weekend
    sunday = datetime(2026, 10, 4, 10, 0, tzinfo=UTC)
    assert is_trading_day(sunday.date()) is False
    assert get_market_session_phase(sunday) == "CLOSED"
