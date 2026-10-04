"""Position Sizing and Whole-Share Integer Allocation Engine.

Enforces:
1. Pure integer shares: floor(min(risk_shares, max_position_shares, cash_shares)).
2. Small account rule: price <= capital * max_position_pct. If shares < 1, skip with 'unaffordable'.
3. Unused cash calculation.
"""

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class PositionSizeResult:
    shares: int
    affordable: bool
    allocated_capital: float
    unused_cash: float
    stop_price: float
    target_price: float
    reason: str


def calculate_position_size(
    capital: float,
    risk_per_trade_pct: float,
    max_position_pct: float,
    price: float,
    atr: float,
    stop_atr_multiplier: float = 1.5,
    target_atr_multiplier: float = 2.5,
) -> PositionSizeResult:
    """Calculate integer position size adhering to risk budget and capital cap."""
    if price <= 0:
        return PositionSizeResult(0, False, 0.0, capital, 0.0, 0.0, "Invalid share price")

    max_position_cash = capital * max_position_pct
    # Check if even 1 single share is affordable
    if price > max_position_cash:
        return PositionSizeResult(
            shares=0,
            affordable=False,
            allocated_capital=0.0,
            unused_cash=capital,
            stop_price=0.0,
            target_price=0.0,
            reason=f"Unaffordable: share price ₹{price:.2f} exceeds position cap ₹{max_position_cash:.2f}",
        )

    # Risk budgeting: cash to risk = capital * risk_per_trade_pct
    risk_budget = capital * risk_per_trade_pct
    stop_distance = max(price * 0.005, atr * stop_atr_multiplier)
    shares_by_risk = math.floor(risk_budget / stop_distance) if stop_distance > 0 else 0

    # Max cash constraint
    shares_by_cash = math.floor(max_position_cash / price)

    # Final integer shares
    raw_shares = min(shares_by_risk, shares_by_cash)
    final_shares = max(0, int(raw_shares))

    if final_shares < 1:
        return PositionSizeResult(
            shares=0,
            affordable=False,
            allocated_capital=0.0,
            unused_cash=capital,
            stop_price=0.0,
            target_price=0.0,
            reason=f"Unaffordable: computed size {raw_shares:.2f} is under 1 share for risk budget ₹{risk_budget:.2f}",
        )

    allocated_capital = round(final_shares * price, 2)
    unused_cash = round(capital - allocated_capital, 2)
    stop_price = round(price - stop_distance, 2)
    target_price = round(price + (atr * target_atr_multiplier), 2)

    return PositionSizeResult(
        shares=final_shares,
        affordable=True,
        allocated_capital=allocated_capital,
        unused_cash=unused_cash,
        stop_price=stop_price,
        target_price=target_price,
        reason=f"Allocated {final_shares} shares (₹{allocated_capital:.2f})",
    )
