"""Unit tests for SimFeed, ReplayFeed, Kite normalization, and DataHealthMonitor."""

from datetime import UTC, datetime

import pytest

from app.feed.base import MarketTick, OrderBookDepth
from app.feed.health import DataHealthMonitor
from app.feed.instruments import InstrumentMaster
from app.feed.kite_feed import normalize_kite_tick
from app.feed.replay_feed import ReplayFeed, ReplayTickData
from app.feed.sim_feed import SimFeed


@pytest.mark.asyncio
async def test_sim_feed_generates_valid_normalized_ticks():
    """Verify SimFeed emits canonical MarketTicks with valid 5-level order book depth."""
    feed = SimFeed(tick_interval_ms=10)
    await feed.connect()

    # Collect 5 ticks
    ticks: list[MarketTick] = []
    async for tick in feed.stream_ticks():
        ticks.append(tick)
        if len(ticks) >= 5:
            break

    await feed.disconnect()

    assert len(ticks) == 5
    for t in ticks:
        assert isinstance(t, MarketTick)
        assert t.feed_source == "sim"
        assert t.last_price > 0.0
        assert len(t.depth.bids) == 5
        assert len(t.depth.asks) == 5
        # Bid must be strictly lower than ask (no crossed book)
        assert t.depth.best_bid < t.depth.best_ask
        assert t.depth.spread > 0.0


@pytest.mark.asyncio
async def test_replay_feed_is_deterministic():
    """Verify ReplayFeed replays the exact same tick stream deterministically."""
    now = datetime(2026, 10, 5, 9, 30, 0, tzinfo=UTC)
    mock_data = [
        ReplayTickData(
            token=738561,
            symbol="RELIANCE",
            timestamp=now,
            price=2950.0,
            qty=10,
            volume=50000,
            bids=[(2949.95, 100), (2949.90, 200)],
            asks=[(2950.05, 150), (2950.10, 300)],
        ),
        ReplayTickData(
            token=738561,
            symbol="RELIANCE",
            timestamp=now,
            price=2952.5,
            qty=25,
            volume=50025,
            bids=[(2952.40, 50), (2952.35, 100)],
            asks=[(2952.55, 80), (2952.60, 200)],
        ),
    ]

    feed1 = ReplayFeed(mock_data, speed_multiplier=float("inf"))
    await feed1.connect()
    run1 = [t async for t in feed1.stream_ticks()]
    await feed1.disconnect()

    feed2 = ReplayFeed(mock_data, speed_multiplier=float("inf"))
    await feed2.connect()
    run2 = [t async for t in feed2.stream_ticks()]
    await feed2.disconnect()

    assert len(run1) == 2
    assert len(run2) == 2
    for r1, r2 in zip(run1, run2, strict=False):
        assert r1.token == r2.token
        assert r1.last_price == r2.last_price
        assert r1.volume == r2.volume
        assert r1.feed_source == "replay"


def test_kite_tick_normalization():
    """Verify raw Zerodha KiteTicker payload normalizes into canonical MarketTick."""
    raw_kite_tick = {
        "instrument_token": 884737,
        "last_price": 925.50,
        "last_traded_quantity": 15,
        "average_traded_price": 924.80,
        "volume_traded": 1250000,
        "total_buy_quantity": 450000,
        "total_sell_quantity": 380000,
        "ohlc": {"open": 915.0, "high": 930.0, "low": 912.0, "close": 925.50},
        "depth": {
            "buy": [
                {"price": 925.45, "quantity": 500, "orders": 3},
                {"price": 925.40, "quantity": 800, "orders": 5},
            ],
            "sell": [
                {"price": 925.55, "quantity": 400, "orders": 2},
                {"price": 925.60, "quantity": 1200, "orders": 7},
            ],
        },
    }

    master = InstrumentMaster()
    normalized = normalize_kite_tick(raw_kite_tick, master)

    assert normalized.token == 884737
    assert normalized.symbol == "TATAMOTORS"
    assert normalized.last_price == 925.50
    assert normalized.last_quantity == 15
    assert normalized.average_traded_price == 924.80
    assert normalized.depth.best_bid == 925.45
    assert normalized.depth.best_ask == 925.55
    assert normalized.feed_source == "kite"


def test_data_health_stale_detection():
    """Verify DataHealthMonitor flags stale feeds when tick delay > 3.0 seconds."""
    monitor = DataHealthMonitor(index_token=256265)

    # Initially stale (no ticks seen)
    assert monitor.is_stale() is True

    # After tick update
    tick = MarketTick(
        token=256265,
        symbol="NIFTY 50",
        timestamp=datetime.now(UTC),
        last_price=25000.0,
        last_quantity=1,
        volume=1000,
        average_traded_price=25000.0,
        total_buy_quantity=100,
        total_sell_quantity=100,
        open=25000.0,
        high=25000.0,
        low=25000.0,
        close=25000.0,
        depth=OrderBookDepth(),
        feed_source="sim",
    )
    monitor.update_tick(tick)
    assert monitor.is_stale(256265) is False
    assert monitor.get_stale_seconds(256265) < 1.0
