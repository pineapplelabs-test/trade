from __future__ import annotations

from datetime import UTC, datetime

from app.feed.base import DepthLevel, MarketTick, OrderBookDepth
from app.feed.instruments import (
    DEFAULT_INSTRUMENTS,
    InstrumentMaster,
    InstrumentMeta,
)
from app.universe.funnel import FunnelConfig, UniverseFunnel


def make_valid_depth(mid: float = 100.0) -> OrderBookDepth:
    return OrderBookDepth(
        bids=[DepthLevel(price=mid - 0.05 * (i + 1), quantity=1000) for i in range(5)],
        asks=[DepthLevel(price=mid + 0.05 * (i + 1), quantity=1000) for i in range(5)],
    )


def test_index_is_excluded_from_equity_master() -> None:
    """Benchmark index (e.g. NIFTY 50) is excluded from equity master and tradable equities."""
    symbols = [inst.symbol for inst in DEFAULT_INSTRUMENTS]
    assert "NIFTY 50" not in symbols
    assert "NIFTY" not in symbols

    master = InstrumentMaster()
    tradable = master.get_tradable_equities()
    for inst in tradable:
        assert inst.series == "EQ"
        assert inst.instrument_type == "EQUITY"
        assert inst.symbol != "NIFTY 50"


def test_funnel_rejects_non_eq_series() -> None:
    """Universe funnel rejects non-EQ series instruments."""
    funnel = UniverseFunnel(FunnelConfig())
    inst_bonds = InstrumentMeta(
        token=9999,
        symbol="GOVTBOND",
        name="Government Bond",
        sector="Debt",
        tick_size=0.05,
        active=True,
        surveillance_flag="NORMAL",
        series="GS",
        instrument_type="DEBT",
    )
    tick = MarketTick(
        token=9999,
        symbol="GOVTBOND",
        timestamp=datetime.now(UTC),
        last_price=100.0,
        last_quantity=10,
        volume=1000000,
        average_traded_price=100.0,
        total_buy_quantity=500000,
        total_sell_quantity=500000,
        open=99.0,
        high=101.0,
        low=99.0,
        close=100.0,
        depth=make_valid_depth(100.0),
        feed_source="groww",
    )
    res = funnel.evaluate(inst_bonds, tick, account_capital=10000.0)
    assert not res.passed
    assert res.stage == "SERIES_REJECTED"


def test_funnel_rejects_low_volume_and_low_turnover() -> None:
    """Universe funnel rejects illiquid equities failing volume or turnover thresholds."""
    funnel = UniverseFunnel(FunnelConfig(min_turnover_cr=5.0, min_volume=10000))
    inst = DEFAULT_INSTRUMENTS[0]

    # 1. Volume below minimum
    tick_low_vol = MarketTick(
        token=inst.token,
        symbol=inst.symbol,
        timestamp=datetime.now(UTC),
        last_price=300.0,
        last_quantity=10,
        volume=500,  # below 10,000
        average_traded_price=300.0,
        total_buy_quantity=200,
        total_sell_quantity=300,
        open=295.0,
        high=302.0,
        low=295.0,
        close=300.0,
        depth=make_valid_depth(300.0),
        feed_source="groww",
    )
    res_vol = funnel.evaluate(inst, tick_low_vol, account_capital=10000.0)
    assert not res_vol.passed
    assert res_vol.stage == "LIQUIDITY_REJECTED"
    assert "below minimum threshold" in res_vol.reason

    # 2. Turnover below 5 Cr (e.g. 50,000 shares * 50 Rs = 25 Lakhs = 0.25 Cr)
    tick_low_turnover = MarketTick(
        token=inst.token,
        symbol=inst.symbol,
        timestamp=datetime.now(UTC),
        last_price=50.0,
        last_quantity=10,
        volume=50000,
        average_traded_price=50.0,
        total_buy_quantity=25000,
        total_sell_quantity=25000,
        open=49.0,
        high=51.0,
        low=49.0,
        close=50.0,
        depth=make_valid_depth(50.0),
        feed_source="groww",
    )
    res_turnover = funnel.evaluate(inst, tick_low_turnover, account_capital=10000.0)
    assert not res_turnover.passed
    assert res_turnover.stage == "LIQUIDITY_REJECTED"
    assert "below minimum" in res_turnover.reason


def test_funnel_rejects_wide_spread() -> None:
    """Universe funnel rejects stocks with bid-ask spread > 0.15%."""
    funnel = UniverseFunnel(FunnelConfig(max_spread_pct=0.0015))
    inst = DEFAULT_INSTRUMENTS[0]

    # Spread: best bid 100.0, best ask 101.0 -> spread = (101-100)/100.5 = ~0.995%
    wide_depth = OrderBookDepth(
        bids=[DepthLevel(price=100.0 - 0.05 * i, quantity=1000) for i in range(5)],
        asks=[DepthLevel(price=101.0 + 0.05 * i, quantity=1000) for i in range(5)],
    )
    tick = MarketTick(
        token=inst.token,
        symbol=inst.symbol,
        timestamp=datetime.now(UTC),
        last_price=100.5,
        last_quantity=10,
        volume=1000000,
        average_traded_price=100.5,
        total_buy_quantity=500000,
        total_sell_quantity=500000,
        open=100.0,
        high=102.0,
        low=99.0,
        close=100.5,
        depth=wide_depth,
        feed_source="groww",
    )
    res = funnel.evaluate(inst, tick, account_capital=10000.0)
    assert not res.passed
    assert res.stage == "SPREAD"
    assert "exceeds max" in res.reason


def test_affordability_floors_to_zero_shares_and_never_rounds_up() -> None:
    """Small capital: Rs 1,000 capital, 50% max position = Rs 500 max position.
    Stock price Rs 800 -> 0 shares affordable -> REJECTED with AFFORDABILITY.
    Must NEVER round up to 1 share.
    """
    funnel = UniverseFunnel(FunnelConfig(max_position_pct=0.50))
    inst = DEFAULT_INSTRUMENTS[0]

    expensive_tick = MarketTick(
        token=inst.token,
        symbol=inst.symbol,
        timestamp=datetime.now(UTC),
        last_price=800.0,
        last_quantity=10,
        volume=1000000,
        average_traded_price=800.0,
        total_buy_quantity=500000,
        total_sell_quantity=500000,
        open=790.0,
        high=810.0,
        low=785.0,
        close=800.0,
        depth=make_valid_depth(800.0),
        feed_source="groww",
    )
    # Capital Rs 1,000 -> max alloc = 1000 * 0.50 = 500. 500 // 800 = 0 shares!
    res = funnel.evaluate(inst, expensive_tick, account_capital=1000.0)
    assert not res.passed
    assert res.stage == "AFFORDABILITY"
    assert "Unaffordable" in res.reason
