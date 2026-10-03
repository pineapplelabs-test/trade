"""Offline Market Simulation Feed (SimFeed).

Produces continuous, normalized MarketTick events with synthetic 5-level depth
for offline testing and development without paid live data.
"""

import asyncio
import random
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

from app.feed.base import DepthLevel, FeedBase, MarketTick, OrderBookDepth
from app.feed.instruments import DEFAULT_INSTRUMENTS, InstrumentMaster


class SimFeed(FeedBase):
    """Simulated market data feed producing realistic 5-level depth updates."""

    def __init__(
        self,
        master: InstrumentMaster | None = None,
        tick_interval_ms: int = 250,
        volatility: float = 0.0005,
    ) -> None:
        self.master = master or InstrumentMaster()
        self.tick_interval_s = tick_interval_ms / 1000.0
        self.volatility = volatility
        self.subscribed_tokens: set[int] = set()
        self.is_running = False

        # Internal simulation states per token: (last_price, volume, high, low, open)
        self._states: dict[int, dict] = {}
        seed_prices = {
            "RELIANCE": 2950.0,
            "TATAMOTORS": 920.0,
            "SBIN": 810.0,
            "ITC": 505.0,
            "TATASTEEL": 165.0,
            "BEL": 295.0,
            "NIFTY 50": 25000.0,
        }
        for inst in DEFAULT_INSTRUMENTS:
            seed_price = seed_prices.get(inst.symbol, 1000.0)

            self._states[inst.token] = {
                "price": seed_price,
                "open": seed_price,
                "high": seed_price,
                "low": seed_price,
                "close": seed_price,
                "volume": 10000,
                "vwap_num": seed_price * 10000,
                "symbol": inst.symbol,
                "tick_size": inst.tick_size,
            }

    async def connect(self) -> None:
        self.is_running = True
        # Subscribe to default tokens if none subscribed
        if not self.subscribed_tokens:
            self.subscribed_tokens = set(self._states.keys())

    async def disconnect(self) -> None:
        self.is_running = False

    async def subscribe(self, tokens: list[int]) -> None:
        for t in tokens:
            self.subscribed_tokens.add(t)

    async def unsubscribe(self, tokens: list[int]) -> None:
        for t in tokens:
            self.subscribed_tokens.discard(t)

    def _generate_synthetic_depth(self, price: float, tick_size: float) -> OrderBookDepth:
        """Generate realistic 5-level bids and asks around current price."""
        bids: list[DepthLevel] = []
        asks: list[DepthLevel] = []

        half_tick = tick_size
        best_bid = round((price - half_tick) / tick_size) * tick_size
        best_ask = round((price + half_tick) / tick_size) * tick_size
        if best_bid >= best_ask:
            best_ask = best_bid + tick_size

        for i in range(5):
            b_price = round(best_bid - i * tick_size, 2)
            a_price = round(best_ask + i * tick_size, 2)
            b_qty = random.randint(50, 1500)
            a_qty = random.randint(50, 1500)
            bids.append(DepthLevel(price=b_price, quantity=b_qty, orders=random.randint(1, 10)))
            asks.append(DepthLevel(price=a_price, quantity=a_qty, orders=random.randint(1, 10)))

        return OrderBookDepth(bids=bids, asks=asks)

    async def stream_ticks(self) -> AsyncGenerator[MarketTick, None]:
        """Yield realistic simulated MarketTick objects continuously."""
        while self.is_running:
            for token in list(self.subscribed_tokens):
                st = self._states.get(token)
                if not st:
                    continue

                # Brownian motion price jump
                ret = random.gauss(0, self.volatility)
                tick_size = st["tick_size"]
                new_price = round((st["price"] * (1.0 + ret)) / tick_size) * tick_size
                new_price = max(new_price, tick_size)

                qty = random.randint(1, 200)
                st["price"] = new_price
                st["volume"] += qty
                st["vwap_num"] += new_price * qty
                st["high"] = max(st["high"], new_price)
                st["low"] = min(st["low"], new_price)

                depth = self._generate_synthetic_depth(new_price, tick_size)
                total_buy_qty = sum(b.quantity for b in depth.bids)
                total_sell_qty = sum(a.quantity for a in depth.asks)
                atp = round(st["vwap_num"] / st["volume"], 2)

                tick = MarketTick(
                    token=token,
                    symbol=st["symbol"],
                    timestamp=datetime.now(UTC),
                    last_price=new_price,
                    last_quantity=qty,
                    volume=st["volume"],
                    average_traded_price=atp,
                    total_buy_quantity=total_buy_qty,
                    total_sell_quantity=total_sell_qty,
                    open=st["open"],
                    high=st["high"],
                    low=st["low"],
                    close=new_price,
                    depth=depth,
                    feed_source="sim",
                )
                yield tick

            await asyncio.sleep(self.tick_interval_s)
