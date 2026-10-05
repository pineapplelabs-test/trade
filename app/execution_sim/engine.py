"""Realistic Order-Book Walking Execution Simulator with Latency and Depth Validation.

Simulates marketable orders walking the 5-level order book depth.
Calculates volume-weighted average fill price across consumed levels.
Supports partial fills when displayed liquidity is insufficient.
Injects latency and pessimistic tick slippage.
Blocks execution if 5-level depth is missing or insufficient.
"""

import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from app.execution_sim.profiles import ExecutionProfile
from app.feed.base import OrderBookDepth


class OrderSide(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


@dataclass(frozen=True)
class SimulatedOrder:
    symbol: str
    side: OrderSide
    requested_quantity: int
    decision_timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    limit_price: float | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class ConsumedLevel:
    level: int
    price: float
    quantity: int


@dataclass(frozen=True)
class SimulatedFill:
    symbol: str
    side: OrderSide
    requested_quantity: int
    filled_quantity: int
    remaining_quantity: int
    average_fill_price: float
    slippage_amount: float
    is_complete: bool
    status: str                        # "FILLED" | "PARTIALLY_FILLED" | "REJECTED"
    levels_consumed: list[ConsumedLevel]
    decision_timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    executed_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    rejection_reason: str | None = None
    execution_assumption: str = "SIMULATED_ASSUMPTION"


class ExecutionSimulator:
    """Simulates realistic trade fills against discrete 5-level book depth."""

    def __init__(self, profile: ExecutionProfile | None = None) -> None:
        self.profile = profile or ExecutionProfile()

    def execute_order(
        self,
        order: SimulatedOrder,
        depth: OrderBookDepth,
        tick_size: float = 0.05,
        execution_timestamp: datetime | None = None,
        require_full_depth: bool = False,
        execution_assumption: str = "SIMULATED_ASSUMPTION",
    ) -> SimulatedFill:
        """Walk the 5-level order book and compute weighted fill price with latency and limit enforcement."""
        exec_ts = execution_timestamp or (order.decision_timestamp + timedelta(milliseconds=self.profile.latency_ms))

        # Check: Insufficient Depth Guard on the side being filled
        target_levels = depth.asks if order.side == OrderSide.BUY else depth.bids
        if not target_levels:
            return SimulatedFill(
                symbol=order.symbol,
                side=order.side,
                requested_quantity=order.requested_quantity,
                filled_quantity=0,
                remaining_quantity=order.requested_quantity,
                average_fill_price=0.0,
                slippage_amount=0.0,
                is_complete=False,
                status="REJECTED",
                levels_consumed=[],
                decision_timestamp=order.decision_timestamp,
                executed_at=exec_ts,
                rejection_reason=f"EXECUTION BLOCKED: Insufficient market-depth data ({'ask' if order.side == OrderSide.BUY else 'bid'} book is empty)",
                execution_assumption=execution_assumption,
            )

        # Check: Rejection Rate (deterministic, reproducible stochastic rejection)
        if self.profile.rejection_rate > 0.0:
            seed_key = f"{order.symbol}:{order.decision_timestamp.isoformat()}:{order.requested_quantity}:{order.side}:{order.limit_price}"
            h_int = int(hashlib.sha256(seed_key.encode("utf-8")).hexdigest()[:8], 16)
            prob_draw = (h_int % 10000) / 10000.0
            if prob_draw < self.profile.rejection_rate:
                return SimulatedFill(
                    symbol=order.symbol,
                    side=order.side,
                    requested_quantity=order.requested_quantity,
                    filled_quantity=0,
                    remaining_quantity=order.requested_quantity,
                    average_fill_price=0.0,
                    slippage_amount=0.0,
                    is_complete=False,
                    status="REJECTED",
                    levels_consumed=[],
                    decision_timestamp=order.decision_timestamp,
                    executed_at=exec_ts,
                    rejection_reason=f"EXECUTION BLOCKED: Stochastic rejection (profile rejection_rate={self.profile.rejection_rate})",
                    execution_assumption=execution_assumption,
                )

        if require_full_depth and not depth.is_complete_5_level:
            return SimulatedFill(
                symbol=order.symbol,
                side=order.side,
                requested_quantity=order.requested_quantity,
                filled_quantity=0,
                remaining_quantity=order.requested_quantity,
                average_fill_price=0.0,
                slippage_amount=0.0,
                is_complete=False,
                status="REJECTED",
                levels_consumed=[],
                decision_timestamp=order.decision_timestamp,
                executed_at=exec_ts,
                rejection_reason=f"EXECUTION BLOCKED: Insufficient market-depth data (bids={len(depth.bids)}, asks={len(depth.asks)} < 5)",
                execution_assumption=execution_assumption,
            )

        levels = depth.asks[:5] if order.side == OrderSide.BUY else depth.bids[:5]

        # Filter levels by limit price if specified
        marketable_levels = []
        for lvl in levels:
            if order.side == OrderSide.BUY:
                if order.limit_price is not None and lvl.price > order.limit_price:
                    continue
            else:
                if order.limit_price is not None and lvl.price < order.limit_price:
                    continue
            marketable_levels.append(lvl)

        if not marketable_levels:
            best_avail = levels[0].price if levels else 0.0
            return SimulatedFill(
                symbol=order.symbol,
                side=order.side,
                requested_quantity=order.requested_quantity,
                filled_quantity=0,
                remaining_quantity=order.requested_quantity,
                average_fill_price=0.0,
                slippage_amount=0.0,
                is_complete=False,
                status="REJECTED",
                levels_consumed=[],
                decision_timestamp=order.decision_timestamp,
                executed_at=exec_ts,
                rejection_reason=f"EXECUTION BLOCKED: Limit price ₹{order.limit_price} not marketable (best available ₹{best_avail})",
                execution_assumption=execution_assumption,
            )

        needed_qty = order.requested_quantity
        consumed_levels: list[ConsumedLevel] = []
        total_cost = 0.0
        total_filled = 0

        for i, lvl in enumerate(marketable_levels, start=1):
            if needed_qty <= 0:
                break
            available = lvl.quantity
            fill_from_lvl = min(needed_qty, available)
            if fill_from_lvl > 0:
                total_cost += fill_from_lvl * lvl.price
                total_filled += fill_from_lvl
                needed_qty -= fill_from_lvl
                consumed_levels.append(ConsumedLevel(level=i, price=lvl.price, quantity=fill_from_lvl))

        if total_filled == 0:
            return SimulatedFill(
                symbol=order.symbol,
                side=order.side,
                requested_quantity=order.requested_quantity,
                filled_quantity=0,
                remaining_quantity=order.requested_quantity,
                average_fill_price=0.0,
                slippage_amount=0.0,
                is_complete=False,
                status="REJECTED",
                levels_consumed=[],
                decision_timestamp=order.decision_timestamp,
                executed_at=exec_ts,
                rejection_reason="EXECUTION BLOCKED: Zero liquidity available at depth levels",
                execution_assumption=execution_assumption,
            )

        remaining = order.requested_quantity - total_filled
        if not self.profile.allow_partial_fills and remaining > 0:
            return SimulatedFill(
                symbol=order.symbol,
                side=order.side,
                requested_quantity=order.requested_quantity,
                filled_quantity=0,
                remaining_quantity=order.requested_quantity,
                average_fill_price=0.0,
                slippage_amount=0.0,
                is_complete=False,
                status="REJECTED",
                levels_consumed=[],
                decision_timestamp=order.decision_timestamp,
                executed_at=exec_ts,
                rejection_reason=f"EXECUTION BLOCKED: Partial fill disallowed by profile (available {total_filled}/{order.requested_quantity})",
                execution_assumption=execution_assumption,
            )

        base_avg_price = total_cost / float(total_filled)

        # Apply profile tick slippage (pessimistic execution)
        slippage_ticks = self.profile.slippage_ticks
        tick_slippage = slippage_ticks * tick_size
        if order.side == OrderSide.BUY:
            final_fill_price = base_avg_price + tick_slippage
            if order.limit_price is not None:
                final_fill_price = min(final_fill_price, order.limit_price)
        else:
            final_fill_price = base_avg_price - tick_slippage
            if order.limit_price is not None:
                final_fill_price = max(final_fill_price, order.limit_price)

        final_fill_price = max(0.01, round(final_fill_price, 4))
        is_complete = remaining == 0
        status = "FILLED" if is_complete else "PARTIALLY_FILLED"

        return SimulatedFill(
            symbol=order.symbol,
            side=order.side,
            requested_quantity=order.requested_quantity,
            filled_quantity=total_filled,
            remaining_quantity=remaining,
            average_fill_price=final_fill_price,
            slippage_amount=round(tick_slippage, 4),
            is_complete=is_complete,
            status=status,
            levels_consumed=consumed_levels,
            decision_timestamp=order.decision_timestamp,
            executed_at=exec_ts,
            execution_assumption=execution_assumption,
        )
