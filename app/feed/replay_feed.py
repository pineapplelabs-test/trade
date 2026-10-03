"""Deterministic Historical Replay Feed (ReplayFeed).

Replays recorded ticks or simulated history at configurable speed multipliers.
Enables running backtests and live paper engine on identical code paths.
"""

import asyncio
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from datetime import datetime

from app.feed.base import DepthLevel, FeedBase, MarketTick, OrderBookDepth


@dataclass
class ReplayTickData:
    token: int
    symbol: str
    timestamp: datetime
    price: float
    qty: int
    volume: int
    bids: list[tuple[float, int]]
    asks: list[tuple[float, int]]


class ReplayFeed(FeedBase):
    """Replays recorded market ticks deterministically with speed control."""

    def __init__(
        self,
        ticks: list[ReplayTickData] | None = None,
        speed_multiplier: float = 1.0,  # 1.0 = real-time, 10.0 = 10x, float('inf') = max throughput
    ) -> None:
        self.ticks = ticks or []
        self.speed_multiplier = speed_multiplier
        self.subscribed_tokens: set[int] = set()
        self.is_running = False

    async def connect(self) -> None:
        self.is_running = True
        if not self.subscribed_tokens and self.ticks:
            self.subscribed_tokens = {t.token for t in self.ticks}

    async def disconnect(self) -> None:
        self.is_running = False

    async def subscribe(self, tokens: list[int]) -> None:
        for t in tokens:
            self.subscribed_tokens.add(t)

    async def unsubscribe(self, tokens: list[int]) -> None:
        for t in tokens:
            self.subscribed_tokens.discard(t)

    def load_from_list(self, ticks: list[ReplayTickData]) -> None:
        """Load in-memory list of tick events."""
        self.ticks = ticks
        self.subscribed_tokens = {t.token for t in self.ticks}

    async def stream_ticks(self) -> AsyncGenerator[MarketTick, None]:
        """Stream replay ticks, respecting speed multiplier delays."""
        if not self.ticks or not self.is_running:
            return

        prev_ts: datetime | None = None

        for item in self.ticks:
            if not self.is_running:
                break

            if item.token not in self.subscribed_tokens:
                continue

            # Compute real delay if speed_multiplier is finite
            if prev_ts is not None and self.speed_multiplier < float("inf"):
                time_delta = (item.timestamp - prev_ts).total_seconds()
                if time_delta > 0:
                    sleep_time = time_delta / max(self.speed_multiplier, 0.1)
                    if sleep_time > 0.001:
                        await asyncio.sleep(sleep_time)

            prev_ts = item.timestamp

            bids = [DepthLevel(price=p, quantity=q) for p, q in item.bids]
            asks = [DepthLevel(price=p, quantity=q) for p, q in item.asks]
            depth = OrderBookDepth(bids=bids, asks=asks)

            tick = MarketTick(
                token=item.token,
                symbol=item.symbol,
                timestamp=item.timestamp,
                last_price=item.price,
                last_quantity=item.qty,
                volume=item.volume,
                average_traded_price=item.price,
                total_buy_quantity=sum(b.quantity for b in bids),
                total_sell_quantity=sum(a.quantity for a in asks),
                open=item.price,
                high=item.price,
                low=item.price,
                close=item.price,
                depth=depth,
                feed_source="replay",
            )
            yield tick
