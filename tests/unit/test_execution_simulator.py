"""Unit tests for realistic order-book walking execution simulator & share rounding."""

import pytest

from app.execution_sim.engine import ExecutionSimulator, OrderSide, SimulatedOrder
from app.execution_sim.profiles import ExecutionProfile, ProfileMode
from app.execution_sim.sizing import calculate_position_size
from app.feed.base import DepthLevel, OrderBookDepth


def test_order_book_walking_exact_vwap():
    """Verify market buy walks 5-level ask book and calculates exact VWAP fill price."""
    # Test case from prompt Section 10:
    # BUY 500 shares
    # Ask L1: 200 shares @ ₹100.00
    # Ask L2: 150 shares @ ₹100.02
    # Ask L3: 100 shares @ ₹100.05
    # Ask L4: 50 shares  @ ₹100.08
    depth = OrderBookDepth(
        bids=[DepthLevel(price=99.95, quantity=500)],
        asks=[
            DepthLevel(price=100.00, quantity=200),
            DepthLevel(price=100.02, quantity=150),
            DepthLevel(price=100.05, quantity=100),
            DepthLevel(price=100.08, quantity=50),
        ],
    )

    sim = ExecutionSimulator(profile=ExecutionProfile(mode=ProfileMode.NORMAL, slippage_ticks=0, latency_ms=0))
    order = SimulatedOrder(symbol="INFY", side=OrderSide.BUY, requested_quantity=500)

    fill = sim.execute_order(order, depth, tick_size=0.01)

    assert fill.filled_quantity == 500
    assert fill.remaining_quantity == 0
    # Expected weighted price: (20000 + 15003 + 10005 + 5004) / 500 = 50012 / 500 = 100.024
    assert fill.average_fill_price == pytest.approx(100.024, abs=1e-4)
    assert fill.is_complete is True


def test_partial_fill_when_depth_insufficient():
    """Verify simulator never assumes infinite liquidity and limits fill to displayed book depth."""
    depth = OrderBookDepth(
        bids=[],
        asks=[
            DepthLevel(price=100.00, quantity=100),
            DepthLevel(price=100.05, quantity=150),
        ],
    )
    sim = ExecutionSimulator(profile=ExecutionProfile(mode=ProfileMode.NORMAL, slippage_ticks=0, latency_ms=0))
    order = SimulatedOrder(symbol="XYZ", side=OrderSide.BUY, requested_quantity=500)

    fill = sim.execute_order(order, depth, tick_size=0.05)

    assert fill.filled_quantity == 250
    assert fill.remaining_quantity == 250
    assert fill.is_complete is False
    assert fill.status == "PARTIALLY_FILLED"


def test_pessimistic_extra_tick_slippage():
    """Verify pessimistic mode adds configured tick slippage on top of book walk."""
    depth = OrderBookDepth(
        bids=[],
        asks=[DepthLevel(price=200.00, quantity=500)],
    )
    # Pessimistic: 1 tick slippage, tick_size=0.05 -> fill price should be 200.05
    sim = ExecutionSimulator(profile=ExecutionProfile(mode=ProfileMode.PESSIMISTIC, slippage_ticks=1, latency_ms=500))
    order = SimulatedOrder(symbol="TCS", side=OrderSide.BUY, requested_quantity=100)

    fill = sim.execute_order(order, depth, tick_size=0.05)
    assert fill.average_fill_price == pytest.approx(200.05, abs=1e-4)


def test_integer_share_rounding_and_unaffordability():
    """Verify quantities are strictly integers and return 0 with 'unaffordable' when price exceeds cap."""
    # Tiny account capital: 1000 INR, max_position_pct: 50% -> max cash = 500 INR
    # Stock price: 600 INR -> unaffordable
    size_res = calculate_position_size(
        capital=1000.0,
        risk_per_trade_pct=0.01,
        max_position_pct=0.50,
        price=600.0,
        atr=5.0,
        stop_atr_multiplier=1.5,
    )
    assert size_res.shares == 0
    assert isinstance(size_res.shares, int)
    assert size_res.affordable is False
    assert "unaffordable" in size_res.reason.lower()

    # Affordable stock: price = 100 INR, max cash = 500 INR
    # Risk cash = 1000 * 0.01 = 10 INR
    # Stop distance = 1.5 * 2.0 = 3.0 INR
    # Shares by risk = floor(10 / 3.0) = floor(3.33) = 3 shares
    # Shares by cash = floor(500 / 100) = 5 shares
    # Result: 3 integer shares
    size_res_ok = calculate_position_size(
        capital=1000.0,
        risk_per_trade_pct=0.01,
        max_position_pct=0.50,
        price=100.0,
        atr=2.0,
        stop_atr_multiplier=1.5,
    )
    assert size_res_ok.shares == 3
    assert isinstance(size_res_ok.shares, int)
    assert size_res_ok.affordable is True
    assert size_res_ok.allocated_capital == 300.0
