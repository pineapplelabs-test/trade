"""Unified Market Data Provider Factory and Implementations.

Implements:
- DemoMarketDataProvider (deterministic simulated feed)
- GrowwMarketDataProvider (read-only live Groww feed)
- ReplayMarketDataProvider (historical replay feed)
All implement the MarketDataProvider contract so downstream strategy and execution
are 100% feed-agnostic.
"""

from datetime import UTC, datetime

from app.feed.base import MarketDataProvider, MarketTick
from app.feed.groww_feed import groww_feed
from app.feed.sim_feed import SimFeed


class DemoMarketDataProvider(MarketDataProvider):
    """Deterministic simulated market data provider."""

    def __init__(self, sim_feed: SimFeed | None = None) -> None:
        self.sim_feed = sim_feed or SimFeed()
        self.latest_ticks: dict[str, MarketTick] = {}

    async def get_latest_tick(self, symbol: str) -> MarketTick | None:
        tick = self.latest_ticks.get(symbol)
        if tick:
            return tick

        # If not yet ticked, synthesize one from sim_feed state
        inst = self.sim_feed.master.get_by_symbol(symbol)
        if not inst:
            return None

        st = self.sim_feed._states.get(inst.token)
        if not st:
            return None

        depth = self.sim_feed._generate_synthetic_depth(st["price"], inst.tick_size)
        total_buy_qty = sum(b.quantity for b in depth.bids)
        total_sell_qty = sum(a.quantity for a in depth.asks)

        t = MarketTick(
            token=inst.token,
            symbol=symbol,
            timestamp=datetime.now(UTC),
            last_price=st["price"],
            last_quantity=10,
            volume=st["volume"],
            average_traded_price=st["price"],
            total_buy_quantity=total_buy_qty,
            total_sell_quantity=total_sell_qty,
            open=st["open"],
            high=st["high"],
            low=st["low"],
            close=st["close"],
            depth=depth,
            feed_source="sim",
            exchange="NSE",
            market_status="REGULAR",
        )
        self.latest_ticks[symbol] = t
        return t

    def is_connected(self) -> bool:
        return True

    def get_source_name(self) -> str:
        return "DEMO"


class GrowwMarketDataProvider(MarketDataProvider):
    """Read-only live NSE market data provider backed by Groww Trade API."""

    def __init__(self) -> None:
        self.feed = groww_feed

    async def get_latest_tick(self, symbol: str) -> MarketTick | None:
        # Check memory cache first
        tick = self.feed.latest_ticks.get(symbol)
        if tick:
            return tick

        # If not cached yet and client ready, fetch synchronously via thread
        if self.feed.is_running and self.feed.api_client:
            return await self.feed.fetch_live_quote(symbol)

        return None

    def is_connected(self) -> bool:
        return bool(self.feed.is_running and self.feed.api_client)

    def get_source_name(self) -> str:
        return "LIVE — Groww"


# Provider instances
demo_provider = DemoMarketDataProvider()
groww_provider = GrowwMarketDataProvider()


def get_market_data_provider(mode: str | None = None) -> MarketDataProvider:
    """Return active provider depending on mode configuration."""
    from app.config import get_settings
    feed_mode = mode or get_settings().FEED_MODE
    if feed_mode == "groww":
        return groww_provider
    return demo_provider
