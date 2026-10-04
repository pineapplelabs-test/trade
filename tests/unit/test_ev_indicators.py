"""Unit tests for 5-level Order Book Imbalance, Microprice, and EV Decision Gate."""

import pytest

from app.feed.base import DepthLevel, OrderBookDepth
from app.indicators.orderbook import calculate_microprice, calculate_obi
from app.strategy.ev import DecisionStatus, EVParameters, calculate_expected_value


def test_calculate_obi_symmetric_balanced():
    depth = OrderBookDepth(
        bids=[DepthLevel(price=100.0, quantity=500)],
        asks=[DepthLevel(price=100.1, quantity=500)],
    )
    obi = calculate_obi(depth)
    assert obi == pytest.approx(0.0, abs=1e-4)


def test_calculate_obi_strong_bid_pressure():
    depth = OrderBookDepth(
        bids=[
            DepthLevel(price=100.0, quantity=300),
            DepthLevel(price=99.95, quantity=200),
            DepthLevel(price=99.90, quantity=500),
        ],
        asks=[
            DepthLevel(price=100.05, quantity=100),
            DepthLevel(price=100.10, quantity=100),
        ],
    )
    # Total bids: 1000, Total asks: 200 -> OBI = (1000 - 200) / 1200 = 800 / 1200 = +0.6667
    obi = calculate_obi(depth)
    assert obi == pytest.approx(0.6667, rel=1e-3)


def test_calculate_microprice_weights_opposite_depth():
    # If Ask has large quantity, sellers dominate -> microprice pulled towards Bid
    # If Bid has large quantity, buyers dominate -> microprice pulled towards Ask
    depth = OrderBookDepth(
        bids=[DepthLevel(price=100.0, quantity=800)],
        asks=[DepthLevel(price=100.10, quantity=200)],
    )
    # Microprice = (Ask * BidQty + Bid * AskQty) / (BidQty + AskQty)
    # = (100.10 * 800 + 100.0 * 200) / 1000 = (80080 + 20000) / 1000 = 100.08
    mp = calculate_microprice(depth)
    assert mp == pytest.approx(100.08, rel=1e-4)
    assert mp > depth.mid_price  # mid is 100.05, microprice reflects upward pressure


def test_ev_decision_gate_acceptance():
    # p = 60%, Win = ₹1.00, Loss = ₹0.50, Total Cost = ₹0.15, Hurdle = ₹0.10
    # EV = (0.60 * 1.00) - (0.40 * 0.50) - 0.15 = 0.60 - 0.20 - 0.15 = ₹0.25/share
    # 0.25 >= 0.10 hurdle -> ACCEPT
    params = EVParameters(
        win_probability=0.60,
        expected_reward=1.00,
        expected_loss=0.50,
        total_costs=0.15,
        min_hurdle=0.10,
    )
    decision = calculate_expected_value(params)
    assert decision.status == DecisionStatus.ACCEPT
    assert decision.net_ev == pytest.approx(0.25, rel=1e-4)


def test_ev_decision_gate_rejection_due_to_cost_drag():
    # Strategy would be profitable in a zero-fee fantasy: 0.55 * 1.00 - 0.45 * 0.80 = 0.55 - 0.36 = +0.19 gross
    # But after ₹0.24 Indian charges + slippage:
    # Net EV = 0.19 - 0.24 = -₹0.05/share -> REJECT
    params = EVParameters(
        win_probability=0.55,
        expected_reward=1.00,
        expected_loss=0.80,
        total_costs=0.24,
        min_hurdle=0.10,
    )
    decision = calculate_expected_value(params)
    assert decision.status == DecisionStatus.REJECT
    assert decision.net_ev == pytest.approx(-0.05, rel=1e-4)
    assert "cost" in decision.reason.lower() or "hurdle" in decision.reason.lower()
