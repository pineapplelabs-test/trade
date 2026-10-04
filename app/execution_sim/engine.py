"""Realistic Order-Book Walking Execution Simulator with Latency and Depth Validation.

Simulates marketable orders walking the 5-level order book depth.
Calculates volume-weighted average fill price across consumed levels.
Supports partial fills when displayed liquidity is insufficient.
Injects latency and pessimistic tick slippage.
Blocks execution if 5-level depth is missing or insufficient.
"""

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
    ) -> SimulatedFill:
        """Walk the 5-level order book and compute weighted fill price with latency."""
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
            )

        levels = depth.asks[:5] if order.side == OrderSide.BUY else depth.bids[:5]

        needed_qty = order.requested_quantity
        consumed_levels: list[ConsumedLevel] = []
        total_cost = 0.0
        total_filled = 0

        for i, lvl in enumerate(levels, start=1):
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
            )

        base_avg_price = total_cost / float(total_filled)

        # Apply profile tick slippage (pessimistic execution)
        slippage_ticks = self.profile.slippage_ticks
        tick_slippage = slippage_ticks * tick_size
        if order.side == OrderSide.BUY:
            final_fill_price = base_avg_price + tick_slippage
        else:
            final_fill_price = base_avg_price - tick_slippage

        final_fill_price = max(0.01, round(final_fill_price, 4))
        remaining = order.requested_quantity - total_filled
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
        )
