"""Market Data Normalization Contract & Abstract Feed Base.

Every feed (SimFeed, ReplayFeed, KiteFeed) normalizes incoming market data into
the exact same MarketTick structure so downstream modules (BarBuilder, Features,
RiskGate, Broker) are feed-agnostic.
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal


def utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class DepthLevel:
    price: float
    quantity: int
    orders: int = 1


@dataclass(frozen=True)
class OrderBookDepth:
    bids: list[DepthLevel] = field(default_factory=list)
    asks: list[DepthLevel] = field(default_factory=list)

    @property
    def best_bid(self) -> float:
        return self.bids[0].price if self.bids else 0.0

    @property
    def best_ask(self) -> float:
        return self.asks[0].price if self.asks else 0.0

    @property
    def mid_price(self) -> float:
        if self.best_bid > 0 and self.best_ask > 0:
            return (self.best_bid + self.best_ask) / 2.0
        return self.best_bid or self.best_ask

    @property
    def spread(self) -> float:
        if self.best_bid > 0 and self.best_ask > 0:
            return self.best_ask - self.best_bid
        return 0.0

    @property
    def spread_pct(self) -> float:
        mid = self.mid_price
        if mid > 0:
            return self.spread / mid
        return 0.0


@dataclass(frozen=True)
class MarketTick:
    """Canonical normalized market data event contract."""

    token: int
    symbol: str
    timestamp: datetime
    last_price: float
    last_quantity: int
    volume: int
    average_traded_price: float
    total_buy_quantity: int
    total_sell_quantity: int
    open: float
    high: float
    low: float
    close: float
    depth: OrderBookDepth
    feed_source: Literal["sim", "replay", "kite"]


class FeedBase(ABC):
    """Abstract market data feed provider."""

    @abstractmethod
    async def connect(self) -> None:
        """Establish network connection or initialize stream source."""
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """Disconnect and clean up resources."""
        pass

    @abstractmethod
    async def subscribe(self, tokens: list[int]) -> None:
        """Subscribe to tokens for streaming updates."""
        pass

    @abstractmethod
    async def unsubscribe(self, tokens: list[int]) -> None:
        """Unsubscribe from tokens."""
        pass

    @abstractmethod
    def stream_ticks(self) -> AsyncGenerator[MarketTick, None]:
        """Yield normalized MarketTick events."""
        pass
