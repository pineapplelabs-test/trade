"""Unit tests verifying every hard boundary in RiskGate."""

from datetime import time

from app.risk.risk_gate import RiskGate


def test_risk_gate_daily_loss_limit_halt():
    """Verify that a 2.0% daily loss (-₹100 on ₹5,000) halts new entries."""
    gate = RiskGate()
    decision = gate.evaluate_entry(
        account_id="real5k",
        starting_capital=5000.0,
        current_equity=4890.0,
        day_pnl=-110.0,  # >2.0% loss
        current_time_ist=time(10, 30),
    )
    assert decision.allowed is False
    assert decision.action == "HALT"
    assert "DAILY_LOSS_LIMIT" in str(decision.reason)


def test_risk_gate_market_clock_boundaries():
    """Verify entry reject before 09:20, reject after 15:00, and force-flat at 15:15."""
    gate = RiskGate()

    # 1. 09:18 IST (opening 5 mins noise window)
    dec_early = gate.evaluate_entry(
        account_id="real5k",
        starting_capital=5000.0,
        current_equity=5000.0,
        day_pnl=0.0,
        current_time_ist=time(9, 18),
    )
    assert dec_early.allowed is False
    assert dec_early.reason == "MARKET_OPENING_NOISE_WINDOW"

    # 2. 15:05 IST (after 15:00 entry cutoff)
    dec_late = gate.evaluate_entry(
        account_id="real5k",
        starting_capital=5000.0,
        current_equity=5000.0,
        day_pnl=0.0,
        current_time_ist=time(15, 5),
    )
    assert dec_late.allowed is False
    assert dec_late.reason == "AFTER_HOURS_ENTRY_CUTOFF"

    # 3. 15:16 IST (force-flat square off)
    dec_flat = gate.evaluate_entry(
        account_id="real5k",
        starting_capital=5000.0,
        current_equity=5000.0,
        day_pnl=0.0,
        current_time_ist=time(15, 16),
    )
    assert dec_flat.allowed is False
    assert dec_flat.action == "FORCE_FLAT"


def test_risk_gate_stale_feed_and_kill_switch():
    """Verify stale feed (>3s) and kill switch veto orders."""
    gate = RiskGate()

    # Stale feed
    dec_stale = gate.evaluate_entry(
        account_id="real5k",
        starting_capital=5000.0,
        current_equity=5000.0,
        day_pnl=0.0,
        current_time_ist=time(11, 0),
        stale_tick_seconds=4.5,
    )
    assert dec_stale.allowed is False
    assert dec_stale.reason == "DATA_FEED_STALE"

    # Kill switch
    dec_kill = gate.evaluate_entry(
        account_id="real5k",
        starting_capital=5000.0,
        current_equity=5000.0,
        day_pnl=0.0,
        current_time_ist=time(11, 0),
        kill_switch_active=True,
    )
    assert dec_kill.allowed is False
    assert dec_kill.reason == "KILL_SWITCH_ACTIVE"


def test_risk_gate_position_limit_reached():
    """Verify order rejected when account is already at max concurrent positions."""
    gate = RiskGate()
    decision = gate.evaluate_entry(
        account_id="real5k",
        starting_capital=5000.0,
        current_equity=5000.0,
        day_pnl=0.0,
        current_time_ist=time(11, 0),
        current_open_positions=2,
        max_open_positions=2,
    )
    assert decision.allowed is False
    assert decision.reason == "MAX_OPEN_POSITIONS_REACHED"


def test_risk_gate_allows_valid_order():
    """Verify order allowed when within all bounds."""
    gate = RiskGate()
    decision = gate.evaluate_entry(
        account_id="real5k",
        starting_capital=5000.0,
        current_equity=5000.0,
        day_pnl=20.0,
        current_time_ist=time(10, 15),
        current_open_positions=0,
        max_open_positions=2,
    )
    assert decision.allowed is True
    assert decision.action == "ALLOW"
