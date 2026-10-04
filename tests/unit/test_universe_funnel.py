"""Tests for multi-stage Universe Funnel with explicit rejection logging."""

from datetime import UTC, datetime

from app.feed.base import DepthLevel, MarketTick, OrderBookDepth
from app.feed.instruments import InstrumentMeta


def create_sample_tick(
    symbol: str = "TEST",
    price: float = 100.0,
    volume: int = 500000,
    spread_pct: float = 0.001,
    close: float = 100.0,
    upper_circuit: float = 120.0,
    lower_circuit: float = 80.0,
) -> MarketTick:
    spread = price * spread_pct
    best_bid = price - (spread / 2.0)
    best_ask = price + (spread / 2.0)
    return MarketTick(
        token=1001,
        symbol=symbol,
        timestamp=datetime.now(UTC),
        last_price=price,
        last_quantity=50,
        volume=volume,
        average_traded_price=price,
        total_buy_quantity=10000,
        total_sell_quantity=8000,
        open=close,
        high=max(price, close),
        low=min(price, close),
        close=close,
        depth=OrderBookDepth(
            bids=[DepthLevel(price=best_bid, quantity=200)],
            asks=[DepthLevel(price=best_ask, quantity=200)],
        ),
        feed_source="sim",
    )


def test_funnel_rejects_asm_gsm():
    from app.universe.funnel import FunnelConfig, UniverseFunnel

    config = FunnelConfig(min_price=20.0, max_price=5000.0)
    funnel = UniverseFunnel(config)

    inst_normal = InstrumentMeta(token=1, symbol="GOOD", name="Good Corp", sector="Tech", tick_size=0.05, active=True, surveillance_flag="NORMAL")
    inst_asm = InstrumentMeta(token=2, symbol="BAD", name="Risky Corp", sector="Tech", tick_size=0.05, active=True, surveillance_flag="ASM")

    tick = create_sample_tick("GOOD", price=100.0)
    res_normal = funnel.evaluate(inst_normal, tick, account_capital=1000.0)
    assert res_normal.passed is True

    res_asm = funnel.evaluate(inst_asm, tick, account_capital=1000.0)
    assert res_asm.passed is False
    assert "ASM" in res_asm.reason


def test_funnel_rejects_unaffordable_for_tiny_account():
    from app.universe.funnel import FunnelConfig, UniverseFunnel

    # Tiny account capital: 1000 INR, max position pct: 50% -> max affordable price: 500 INR
    config = FunnelConfig(max_position_pct=0.50)
    funnel = UniverseFunnel(config)

    inst = InstrumentMeta(token=1, symbol="EXPENSIVE", name="High Stock", sector="Tech", tick_size=0.05, active=True, surveillance_flag="NORMAL")
    tick_expensive = create_sample_tick("EXPENSIVE", price=650.0)

    res = funnel.evaluate(inst, tick_expensive, account_capital=1000.0)
    assert res.passed is False
    assert "unaffordable" in res.reason.lower()


def test_funnel_rejects_wide_spread():
    from app.universe.funnel import FunnelConfig, UniverseFunnel

    # Max spread: 0.15% (0.0015)
    config = FunnelConfig(max_spread_pct=0.0015)
    funnel = UniverseFunnel(config)

    inst = InstrumentMeta(token=1, symbol="WIDESPREAD", name="Illiquid Corp", sector="Tech", tick_size=0.05, active=True, surveillance_flag="NORMAL")
    tick_wide = create_sample_tick("WIDESPREAD", price=100.0, spread_pct=0.005)  # 0.50% spread

    res = funnel.evaluate(inst, tick_wide, account_capital=100000.0)
    assert res.passed is False
    assert "spread" in res.reason.lower()


def test_funnel_rejects_circuit_limit():
    from app.universe.funnel import FunnelConfig, UniverseFunnel

    funnel = UniverseFunnel(FunnelConfig())
    inst = InstrumentMeta(token=1, symbol="CIRCUIT", name="Locked Corp", sector="Tech", tick_size=0.05, active=True, surveillance_flag="NORMAL")

    tick_circuit = create_sample_tick("CIRCUIT", price=120.0, upper_circuit=120.0)
    res = funnel.evaluate(inst, tick_circuit, account_capital=100000.0, upper_circuit=120.0)
    assert res.passed is False
    assert "circuit" in res.reason.lower()


def test_funnel_enforces_volume_and_turnover() -> None:
    from app.universe.funnel import FunnelConfig, UniverseFunnel

    inst = InstrumentMeta(token=1, symbol="ILLIQ", name="Illiquid", sector="Tech", tick_size=0.05, active=True, surveillance_flag="NORMAL")
    funnel = UniverseFunnel(FunnelConfig(min_volume=25000, min_turnover_cr=5.0))

    low_volume = create_sample_tick("ILLIQ", price=100.0, volume=1000)
    result = funnel.evaluate(inst, low_volume, account_capital=100000.0)
    assert result.passed is False
    assert result.stage == "MIN_VOLUME"

    low_turnover = create_sample_tick("ILLIQ", price=100.0, volume=25000)
    result = funnel.evaluate(inst, low_turnover, account_capital=100000.0)
    assert result.passed is False
    assert result.stage == "MIN_TURNOVER"
