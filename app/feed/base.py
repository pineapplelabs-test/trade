"""Market Data Normalization Contract & Abstract Feed Base.

Every feed (SimFeed, ReplayFeed, GrowwFeed) normalizes incoming market data into
the exact same MarketTick structure so downstream modules (BarBuilder, Features,
RiskGate, Broker, Scanner) are completely feed-agnostic.
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
            return round(self.best_ask - self.best_bid, 4)
        return 0.0

    @property
    def spread_pct(self) -> float:
        mid = self.mid_price
        if mid > 0:
            return round(self.spread / mid, 6)
        return 0.0

    @property
    def is_complete_5_level(self) -> bool:
        """Verify whether full 5-level depth is available on both sides."""
        return len(self.bids) >= 5 and len(self.asks) >= 5

    def validate_sanity(self) -> tuple[bool, str | None]:
        """Validate order book pricing sanity and monotonicity.

        Rules:
        1. All prices and quantities must be > 0.
        2. Bids monotonic: bid[0] >= bid[1] >= ...
        3. Asks monotonic: ask[0] <= ask[1] <= ...
        4. In continuous market: best_bid < best_ask (no crossed/locked book).
        """
        if not self.bids or not self.asks:
            return False, "Empty bids or asks in order book"

        for b in self.bids:
            if b.price <= 0 or b.quantity <= 0:
                return False, f"Invalid bid level price={b.price}, qty={b.quantity}"
        for a in self.asks:
            if a.price <= 0 or a.quantity <= 0:
                return False, f"Invalid ask level price={a.price}, qty={a.quantity}"

        # Monotonicity checks
        for i in range(len(self.bids) - 1):
            if self.bids[i].price < self.bids[i + 1].price:
                return False, f"Bids not descending: {self.bids[i].price} < {self.bids[i + 1].price}"

        for i in range(len(self.asks) - 1):
            if self.asks[i].price > self.asks[i + 1].price:
                return False, f"Asks not ascending: {self.asks[i].price} > {self.asks[i + 1].price}"

        if self.best_bid >= self.best_ask:
            return False, f"Crossed or locked book: best_bid ({self.best_bid}) >= best_ask ({self.best_ask})"

        return True, None


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
    feed_source: Literal["sim", "replay", "groww"]
    exchange: str = "NSE"
    received_timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    market_status: str = "REGULAR"   # "REGULAR", "PRE_OPEN", "CLOSED", "HALTED"


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


class MarketDataProvider(ABC):
    """Unified read-only market data provider interface."""

    @abstractmethod
    async def get_latest_tick(self, symbol: str) -> MarketTick | None:
        """Get latest normalized snapshot for symbol."""
        pass

    @abstractmethod
    def is_connected(self) -> bool:
        """Check if market data feed is active."""
        pass

    @abstractmethod
    def get_source_name(self) -> str:
        """Return provider name (e.g. 'LIVE - Groww' or 'DEMO')."""
        pass
