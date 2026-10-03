"""Unit tests for BarBuilder OHLCV aggregation and Parquet persistence."""

import tempfile
from datetime import UTC, datetime
from pathlib import Path

import polars as pl

from app.feed.base import MarketTick, OrderBookDepth
from app.state.bar_builder import BarBuilder


def make_tick(token: int, symbol: str, dt: datetime, price: float, qty: int) -> MarketTick:
    return MarketTick(
        token=token,
        symbol=symbol,
        timestamp=dt,
        last_price=price,
        last_quantity=qty,
        volume=qty,
        average_traded_price=price,
        total_buy_quantity=100,
        total_sell_quantity=100,
        open=price,
        high=price,
        low=price,
        close=price,
        depth=OrderBookDepth(),
        feed_source="sim",
    )


def test_bar_builder_aggregates_1m_bars():
    """Verify ticks across minute boundaries produce accurate 1-minute OHLCV bars."""
    builder = BarBuilder()

    # Minute 0: 3 ticks (prices 100, 105, 98)
    t1 = make_tick(1, "TEST", datetime(2026, 10, 5, 9, 30, 5, tzinfo=UTC), 100.0, 10)
    t2 = make_tick(1, "TEST", datetime(2026, 10, 5, 9, 30, 25, tzinfo=UTC), 105.0, 20)
    t3 = make_tick(1, "TEST", datetime(2026, 10, 5, 9, 30, 55, tzinfo=UTC), 98.0, 30)

    assert builder.process_tick(t1) is None
    assert builder.process_tick(t2) is None
    assert builder.process_tick(t3) is None

    # Minute 1: Tick arrives -> triggers completion of Minute 0 bar
    t4 = make_tick(1, "TEST", datetime(2026, 10, 5, 9, 31, 2, tzinfo=UTC), 102.0, 15)
    bar1 = builder.process_tick(t4)

    assert bar1 is not None
    assert bar1.timeframe == "1m"
    assert bar1.open == 100.0
    assert bar1.high == 105.0
    assert bar1.low == 98.0
    assert bar1.close == 98.0
    assert bar1.volume == 60  # 10 + 20 + 30
    assert bar1.tick_count == 3
    # VWAP = (100*10 + 105*20 + 98*30) / 60 = (1000 + 2100 + 2940) / 60 = 6040 / 60 = 100.67
    assert bar1.vwap == 100.67


def test_parquet_export():
    """Verify completed bars export to valid partitioned Parquet."""
    builder = BarBuilder()

    t1 = make_tick(1, "TEST", datetime(2026, 10, 5, 9, 30, 10, tzinfo=UTC), 100.0, 10)
    t2 = make_tick(1, "TEST", datetime(2026, 10, 5, 9, 31, 10, tzinfo=UTC), 102.0, 10)
    builder.process_tick(t1)
    builder.process_tick(t2)

    with tempfile.TemporaryDirectory() as tmp_dir:
        out_path = builder.export_bars_to_parquet(Path(tmp_dir))
        assert out_path.exists()

        # Read back with Polars
        df = pl.read_parquet(out_path)
        assert df.height == 1
        assert df["symbol"][0] == "TEST"
        assert df["open"][0] == 100.0
