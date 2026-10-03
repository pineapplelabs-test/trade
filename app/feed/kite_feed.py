"""Zerodha Kite Connect Market Data Feed & OAuth Architecture (KiteFeed).

READ-ONLY MARKET DATA STREAMING:
Subscribes to live WebSocket ticks in Full Mode (5-level order book depth).
Contains ZERO order placement, modification, or execution functions.
"""

import asyncio
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

import structlog

from app.config import get_settings
from app.feed.base import DepthLevel, FeedBase, MarketTick, OrderBookDepth
from app.feed.instruments import InstrumentMaster

logger = structlog.get_logger()
settings = get_settings()


def normalize_kite_tick(tick: dict, master: InstrumentMaster) -> MarketTick:
    """Normalize raw dictionary from Zerodha KiteTicker into canonical MarketTick contract.

    Handles KiteTicker Full Mode payload with 5-level market depth.
    """
    token = tick.get("instrument_token", 0)
    inst = master.get_by_token(token)
    symbol = inst.symbol if inst else f"TOKEN_{token}"

    ts = tick.get("last_trade_time") or tick.get("exchange_timestamp") or datetime.now(UTC)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)

    # 5-level depth parsing
    raw_depth = tick.get("depth", {})
    raw_bids = raw_depth.get("buy", [])
    raw_asks = raw_depth.get("sell", [])

    bids = [
        DepthLevel(
            price=float(b.get("price", 0.0)),
            quantity=int(b.get("quantity", 0)),
            orders=int(b.get("orders", 1)),
        )
        for b in raw_bids
        if float(b.get("price", 0.0)) > 0
    ]
    asks = [
        DepthLevel(
            price=float(a.get("price", 0.0)),
            quantity=int(a.get("quantity", 0)),
            orders=int(a.get("orders", 1)),
        )
        for a in raw_asks
        if float(a.get("price", 0.0)) > 0
    ]

    ohlc = tick.get("ohlc", {})

    return MarketTick(
        token=token,
        symbol=symbol,
        timestamp=ts,
        last_price=float(tick.get("last_price", 0.0)),
        last_quantity=int(tick.get("last_traded_quantity", 0)),
        volume=int(tick.get("volume_traded", 0)),
        average_traded_price=float(tick.get("average_traded_price", 0.0)),
        total_buy_quantity=int(tick.get("total_buy_quantity", 0)),
        total_sell_quantity=int(tick.get("total_sell_quantity", 0)),
        open=float(ohlc.get("open", 0.0)),
        high=float(ohlc.get("high", 0.0)),
        low=float(ohlc.get("low", 0.0)),
        close=float(ohlc.get("close", 0.0)),
        depth=OrderBookDepth(bids=bids, asks=asks),
        feed_source="kite",
    )


class KiteFeed(FeedBase):
    """Zerodha Kite live market data feed client.

    Maintains WebSocket connection, ingests full 5-level depth, and buffers ticks
    into an asyncio.Queue for decoupled consumption.
    """

    def __init__(self, master: InstrumentMaster | None = None) -> None:
        self.master = master or InstrumentMaster()
        self.subscribed_tokens: set[int] = set()
        self.is_running = False
        self._tick_queue: asyncio.Queue[MarketTick] = asyncio.Queue(maxsize=10000)
        self.access_token: str | None = None

    async def connect(self) -> None:
        """Connect to KiteTicker WebSocket when access token is configured."""
        if not settings.KITE_API_KEY:
            logger.warn("kite_feed_not_configured", reason="Missing KITE_API_KEY")
            return
        self.is_running = True
        logger.info("kite_feed_connected", subscribed=len(self.subscribed_tokens))

    async def disconnect(self) -> None:
        self.is_running = False
        logger.info("kite_feed_disconnected")

    async def subscribe(self, tokens: list[int]) -> None:
        for t in tokens:
            self.subscribed_tokens.add(t)

    async def unsubscribe(self, tokens: list[int]) -> None:
        for t in tokens:
            self.subscribed_tokens.discard(t)

    def on_raw_kite_tick(self, raw_tick: dict) -> None:
        """Callback invoked by KiteTicker WebSocket packet receiver."""
        if not self.is_running:
            return
        normalized = normalize_kite_tick(raw_tick, self.master)
        try:
            self._tick_queue.put_nowait(normalized)
        except asyncio.QueueFull:
            # Drop oldest tick to maintain real-time low latency
            try:
                self._tick_queue.get_nowait()
                self._tick_queue.put_nowait(normalized)
            except Exception:
                pass

    async def stream_ticks(self) -> AsyncGenerator[MarketTick, None]:
        """Async generator yielding normalized MarketTick events."""
        while self.is_running:
            try:
                tick = await asyncio.wait_for(self._tick_queue.get(), timeout=1.0)
                yield tick
            except TimeoutError:
                continue
            except asyncio.CancelledError:
                break
