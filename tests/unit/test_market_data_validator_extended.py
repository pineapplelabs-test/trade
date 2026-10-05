from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.feed.base import DepthLevel, MarketTick, OrderBookDepth
from app.feed.validator import FreshnessStatus, MarketDataValidator


def make_valid_depth(mid: float = 100.0) -> OrderBookDepth:
    return OrderBookDepth(
        bids=[DepthLevel(price=mid - 0.05 * (i + 1), quantity=1000) for i in range(5)],
        asks=[DepthLevel(price=mid + 0.05 * (i + 1), quantity=1000) for i in range(5)],
    )


def test_order_book_depth_zero_or_negative_quantity_rejected() -> None:
    """Depth with zero or negative quantity fails sanity check."""
    # Zero quantity in bids
    depth_zero = OrderBookDepth(
        bids=[
            DepthLevel(price=100.0, quantity=0),  # zero!
            DepthLevel(price=99.95, quantity=100),
            DepthLevel(price=99.90, quantity=100),
            DepthLevel(price=99.85, quantity=100),
            DepthLevel(price=99.80, quantity=100),
        ],
        asks=[DepthLevel(price=100.05 + 0.05 * i, quantity=100) for i in range(5)],
    )
    valid, err = depth_zero.validate_sanity()
    assert not valid
    assert "Invalid bid level" in err or "quantity" in err


def test_validator_rejects_impossible_price() -> None:
    """Ticks with last_price <= 0 are rejected as IMPOSSIBLE_PRICE."""
    validator = MarketDataValidator()
    tick_zero_price = MarketTick(
        token=1,
        symbol="TEST",
        timestamp=datetime.now(UTC),
        last_price=0.0,  # impossible
        last_quantity=10,
        volume=10000,
        average_traded_price=0.0,
        total_buy_quantity=5000,
        total_sell_quantity=5000,
        open=100.0,
        high=100.0,
        low=100.0,
        close=100.0,
        depth=make_valid_depth(),
        feed_source="groww",
    )
    st, msg = validator.validate_tick(tick_zero_price)
    assert st == FreshnessStatus.IMPOSSIBLE_PRICE
    assert "Impossible price" in msg


def test_validator_rejects_duplicate_tick() -> None:
    """Duplicate tick with identical timestamp, price, and volume is rejected."""
    validator = MarketDataValidator()
    ts = datetime.now(UTC)
    tick1 = MarketTick(
        token=1,
        symbol="TEST_DUP",
        timestamp=ts,
        last_price=100.0,
        last_quantity=10,
        volume=50000,
        average_traded_price=100.0,
        total_buy_quantity=25000,
        total_sell_quantity=25000,
        open=99.0,
        high=101.0,
        low=99.0,
        close=100.0,
        depth=make_valid_depth(),
        feed_source="groww",
    )
    # First tick passes
    st1, _ = validator.validate_tick(tick1)
    assert st1 == FreshnessStatus.VALID

    # Second identical tick fails
    tick2 = MarketTick(
        token=1,
        symbol="TEST_DUP",
        timestamp=ts,
        last_price=100.0,
        last_quantity=10,
        volume=50000,
        average_traded_price=100.0,
        total_buy_quantity=25000,
        total_sell_quantity=25000,
        open=99.0,
        high=101.0,
        low=99.0,
        close=100.0,
        depth=make_valid_depth(),
        feed_source="groww",
    )
    st2, msg2 = validator.validate_tick(tick2)
    assert st2 == FreshnessStatus.DUPLICATE_TICK
    assert "Duplicate tick detected" in msg2


def test_validator_rejects_volume_regression() -> None:
    """Tick where volume decreases from previous tick is rejected as VOLUME_REGRESSION."""
    validator = MarketDataValidator()
    ts1 = datetime.now(UTC) - timedelta(milliseconds=500)
    ts2 = datetime.now(UTC)

    tick1 = MarketTick(
        token=1,
        symbol="TEST_VOL",
        timestamp=ts1,
        last_price=100.0,
        last_quantity=10,
        volume=50000,
        average_traded_price=100.0,
        total_buy_quantity=25000,
        total_sell_quantity=25000,
        open=99.0,
        high=101.0,
        low=99.0,
        close=100.0,
        depth=make_valid_depth(),
        feed_source="groww",
    )
    assert validator.validate_tick(tick1)[0] == FreshnessStatus.VALID

    tick2 = MarketTick(
        token=1,
        symbol="TEST_VOL",
        timestamp=ts2,
        last_price=100.5,
        last_quantity=5,
        volume=40000,  # volume regressed from 50000 to 40000!
        average_traded_price=100.0,
        total_buy_quantity=25000,
        total_sell_quantity=25000,
        open=99.0,
        high=101.0,
        low=99.0,
        close=100.0,
        depth=make_valid_depth(),
        feed_source="groww",
    )
    st2, msg2 = validator.validate_tick(tick2)
    assert st2 == FreshnessStatus.VOLUME_REGRESSION
    assert "Volume regression detected" in msg2


def test_validator_rejects_clock_skew() -> None:
    """When receive timestamp differs from source timestamp by > max_clock_skew_seconds on fresh tick, reject as CLOCK_SKEW."""
    validator = MarketDataValidator(max_clock_skew_seconds=5.0)
    now = datetime.now(UTC)

    tick_skew = MarketTick(
        token=1,
        symbol="TEST_SKEW",
        timestamp=now - timedelta(seconds=1),  # fresh (< 3s)
        last_price=100.0,
        last_quantity=10,
        volume=50000,
        average_traded_price=100.0,
        total_buy_quantity=25000,
        total_sell_quantity=25000,
        open=99.0,
        high=101.0,
        low=99.0,
        close=100.0,
        depth=make_valid_depth(),
        feed_source="groww",
        received_timestamp=now + timedelta(seconds=10),  # 11s difference!
    )
    st, msg = validator.validate_tick(tick_skew)
    assert st == FreshnessStatus.CLOCK_SKEW
    assert "Clock skew detected" in msg
