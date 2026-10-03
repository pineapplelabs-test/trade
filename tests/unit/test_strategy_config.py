"""Unit tests verifying all strategy configuration requirements and boundaries."""

from app.config import get_strategy_config


def test_spread_penalty_is_negative():
    """Verify spread penalty cannot accidentally reward wider spreads."""
    cfg = get_strategy_config()
    spread_weight = cfg.get("composite_weights", {}).get("spread_penalty", 0.0)
    assert spread_weight < 0.0, "Spread penalty must be negative to penalize wide spreads!"
    assert spread_weight == -0.10


def test_orb_parameters():
    """Verify ORB strategy parameters: 1.5 ATR stop, 2.5 ATR target."""
    cfg = get_strategy_config()
    orb = cfg.get("strategies", {}).get("orb", {})
    assert orb.get("atr_stop_multiple") == 1.5
    assert orb.get("atr_target_multiple") == 2.5
    assert orb.get("min_rvol") == 1.5
    assert orb.get("require_above_vwap") is True


def test_vwap_reversion_parameters():
    """Verify VWAP mean reversion parameters: 60-bar window, z < -2.0, microprice check."""
    cfg = get_strategy_config()
    vwap = cfg.get("strategies", {}).get("vwap_reversion", {})
    assert vwap.get("zscore_window_bars") == 60
    assert vwap.get("min_zscore") == -2.0  # Must be negative for oversold mean-reversion long
    assert vwap.get("require_microprice_above_mid") is True
    assert vwap.get("vix_percentile_max") == 50.0
    assert vwap.get("nifty_absolute_return_max_pct") == 0.5


def test_trade_limits_and_timings():
    """Verify cooldown, max trades per day, and market timings."""
    cfg = get_strategy_config()
    limits = cfg.get("trade_limits", {})
    assert limits.get("cooldown_minutes") == 30
    assert limits.get("max_trades_per_symbol_day") == 2

    timings = cfg.get("market_timing", {})
    assert timings.get("entry_start_time") == "09:20:00"
    assert timings.get("entry_cutoff_time") == "15:00:00"
    assert timings.get("force_flat_time") == "15:15:00"


def test_ev_hurdles_for_all_accounts():
    """Verify EV hurdles for tiny, real5k, and shadow accounts."""
    cfg = get_strategy_config()
    ev = cfg.get("ev_thresholds", {})
    assert ev.get("tiny_ev_min_pct") == 0.15
    assert ev.get("real5k_ev_min_pct") == 0.12
    assert ev.get("shadow_ev_min_pct") == 0.10
